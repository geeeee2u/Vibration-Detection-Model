"""FastAPI entry point for the local Case1 vibration dashboard."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from backend.analysis_service import rerun_analysis, rerun_analysis_from_repository
from backend.config import ModelSettings, load_settings, save_settings
from backend.database import DatabaseRepository
from case1_vibration_isolation_forest import load_case1
from backend.data_service import (
    filter_results,
    load_results,
    overview_payload,
    performance_payload,
    performance_payload_frame,
    rows_payload,
)

ROOT = Path(__file__).parents[1]
INPUT = ROOT / "AI Model Raw Data.xlsx"
RESULTS = ROOT / "case1_vibration_anomaly_results.csv"
SETTINGS = ROOT / "runtime" / "model_settings.json"
METRICS = ROOT / "synthetic_anomaly_outputs" / "synthetic_anomaly_metrics.csv"
PAGES = {"/": "overview.html", "/analysis": "analysis.html", "/alarms": "alarms.html", "/performance": "performance.html", "/settings": "settings.html"}


def load_local_env(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class AuthConfig:
    session_secret: str
    administrator_username: str
    administrator_password: str
    technician_username: str
    technician_password: str

    @classmethod
    def from_environment(cls) -> "AuthConfig":
        load_local_env(ROOT / ".env")
        return cls(
            session_secret=os.getenv("SESSION_SECRET", "local-development-change-me"),
            administrator_username=os.getenv("ADMIN_USERNAME", ""),
            administrator_password=os.getenv("ADMIN_PASSWORD", ""),
            technician_username=os.getenv("TECHNICIAN_USERNAME", ""),
            technician_password=os.getenv("TECHNICIAN_PASSWORD", ""),
        )


class LoginRequest(BaseModel):
    username: str
    password: str

def create_app(
    results_path: Path = RESULTS,
    settings_path: Path = SETTINGS,
    metrics_path: Path = METRICS,
    input_path: Path = INPUT,
    auth_config: AuthConfig | None = None,
    repository: DatabaseRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="Case1 Vibration Dashboard")
    auth = auth_config or AuthConfig.from_environment()
    repository = repository or (DatabaseRepository(os.environ["DATABASE_URL"]) if os.getenv("DATABASE_URL") else None)
    app.add_middleware(SessionMiddleware, secret_key=auth.session_secret, same_site="lax", https_only=os.getenv("COOKIE_HTTPS_ONLY", "").lower() in {"1", "true", "yes"})
    frontend = ROOT / "frontend"
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
    def results(start: str | None, end: str | None):
        if repository is not None:
            return filter_results(repository.load_active_results(), start, end)
        if not results_path.exists(): raise HTTPException(404, "분석 결과 파일이 없습니다. 설정 화면에서 재분석을 실행하세요.")
        return filter_results(load_results(results_path), start, end)
    for route, filename in PAGES.items():
        app.add_api_route(route, lambda filename=filename: FileResponse(frontend / filename), methods=["GET"])

    def current_user(request: Request) -> dict[str, str]:
        username = request.session.get("username")
        role = request.session.get("role")
        if not username or role not in {"administrator", "technician"}:
            raise HTTPException(401, "로그인이 필요합니다.")
        return {"username": username, "role": role}

    def require_administrator(request: Request) -> None:
        if current_user(request)["role"] != "administrator":
            raise HTTPException(403, "해당 계정으로는 접근할 수 없습니다.")

    @app.post("/api/auth/login")
    def login(credentials: LoginRequest, request: Request):
        accounts = {
            auth.administrator_username: (auth.administrator_password, "administrator"),
            auth.technician_username: (auth.technician_password, "technician"),
        }
        password_and_role = accounts.get(credentials.username)
        if not password_and_role or credentials.password != password_and_role[0]:
            raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
        request.session.clear()
        request.session.update({"username": credentials.username, "role": password_and_role[1]})
        return {"username": credentials.username, "role": password_and_role[1]}

    @app.post("/api/auth/logout")
    def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(request: Request):
        return current_user(request)
    @app.get("/api/overview")
    def overview(start: str | None = None, end: str | None = None): return overview_payload(results(start, end))
    @app.get("/api/trend")
    def trend(start: str | None = None, end: str | None = None): return rows_payload(results(start, end), ["Timestamps","Vibration","short_mean","anomaly_score","threshold","raw_anomaly","is_anomaly"])
    @app.get("/api/analysis")
    def analysis(start: str | None = None, end: str | None = None): return rows_payload(results(start, end))
    @app.get("/api/alarms")
    def alarms(start: str | None = None, end: str | None = None):
        frame = results(start, end); return rows_payload(frame[frame["raw_anomaly"]].sort_values("Timestamps", ascending=False))
    @app.get("/api/performance")
    def performance():
        if repository is not None:
            return performance_payload_frame(repository.load_active_metrics())
        if not metrics_path.exists():
            raise HTTPException(404, "성능 지표 파일이 없습니다. 모델 설정 화면에서 재분석을 실행해 주세요.")
        return performance_payload(metrics_path)
    @app.get("/api/settings")
    def get_settings(request: Request):
        require_administrator(request)
        if repository is not None:
            return repository.load_settings().__dict__
        return load_settings(settings_path).__dict__
    @app.put("/api/settings")
    def put_settings(settings: ModelSettings, request: Request):
        require_administrator(request)
        if repository is not None:
            return repository.save_settings(settings).__dict__
        save_settings(settings, settings_path)
        return settings.__dict__
    @app.post("/api/reanalyze")
    def reanalyze(settings: ModelSettings, request: Request):
        require_administrator(request)
        if repository is not None:
            try:
                repository.create_schema()
                if repository.load_raw_data("Case1").empty:
                    repository.import_raw_data(load_case1(INPUT), "Case1")
                result = rerun_analysis_from_repository(settings, repository)
            except Exception as exc:
                raise HTTPException(500, f"Analysis failed: {exc}") from exc
            return {
                "rows": len(result),
                "confirmed_alarm_count": int(result["is_anomaly"].sum()),
                "performance": performance_payload_frame(repository.load_active_metrics()),
            }
        save_settings(settings, settings_path)
        try: result = rerun_analysis(settings, input_path, results_path, metrics_path)
        except Exception as exc: raise HTTPException(500, f"재분석 실패: {exc}") from exc
        return {
            "rows": len(result),
            "confirmed_alarm_count": int(result["is_anomaly"].sum()),
            "performance": performance_payload(metrics_path),
        }
    return app

app = create_app()
