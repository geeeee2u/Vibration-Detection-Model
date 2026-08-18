from pathlib import Path


def test_vercel_fastapi_entrypoint_is_declared():
    config = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "backend.main:app"' in config
