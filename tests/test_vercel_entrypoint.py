from pathlib import Path
import tomllib


def test_vercel_fastapi_entrypoint_is_declared():
    config = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "backend.main:app"' in config


def test_vercel_pyproject_declares_python_dependencies():
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert config["project"]["name"] == "vibration-detection-model"
    assert any(dependency.startswith("fastapi") for dependency in config["project"]["dependencies"])
