"""FastAPI entry point for the local Case1 vibration dashboard."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.analysis_service import rerun_analysis
from backend.config import ModelSettings, load_settings, save_settings
from backend.data_service import filter_results, load_results, overview_payload, rows_payload

ROOT = Path(__file__).parents[1]
INPUT = ROOT / "AI Model Raw Data.xlsx"
RESULTS = ROOT / "case1_vibration_anomaly_results.csv"
SETTINGS = ROOT / "runtime" / "model_settings.json"
PAGES = {"/": "overview.html", "/analysis": "analysis.html", "/alarms": "alarms.html", "/performance": "performance.html", "/settings": "settings.html"}

def create_app(results_path: Path = RESULTS, settings_path: Path = SETTINGS) -> FastAPI:
    app = FastAPI(title="Case1 Vibration Dashboard")
    frontend = ROOT / "frontend"
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
    def results(start: str | None, end: str | None):
        if not results_path.exists(): raise HTTPException(404, "분석 결과 파일이 없습니다. 설정 화면에서 재분석을 실행하세요.")
        return filter_results(load_results(results_path), start, end)
    for route, filename in PAGES.items():
        app.add_api_route(route, lambda filename=filename: FileResponse(frontend / filename), methods=["GET"])
    @app.get("/api/overview")
    def overview(start: str | None = None, end: str | None = None): return overview_payload(results(start, end))
    @app.get("/api/trend")
    def trend(start: str | None = None, end: str | None = None): return rows_payload(results(start, end), ["Timestamps","Vibration","short_mean","anomaly_score","threshold","raw_anomaly","is_anomaly"])
    @app.get("/api/analysis")
    def analysis(start: str | None = None, end: str | None = None): return rows_payload(results(start, end))
    @app.get("/api/alarms")
    def alarms(start: str | None = None, end: str | None = None):
        frame = results(start, end); return rows_payload(frame[frame["raw_anomaly"]].sort_values("Timestamps", ascending=False))
    @app.get("/api/settings")
    def get_settings(): return load_settings(settings_path).__dict__
    @app.put("/api/settings")
    def put_settings(settings: ModelSettings): save_settings(settings, settings_path); return settings.__dict__
    @app.post("/api/reanalyze")
    def reanalyze(settings: ModelSettings):
        save_settings(settings, settings_path)
        try: result = rerun_analysis(settings, INPUT, results_path)
        except Exception as exc: raise HTTPException(500, f"재분석 실패: {exc}") from exc
        return {"rows": len(result), "confirmed_alarm_count": int(result["is_anomaly"].sum())}
    return app

app = create_app()
