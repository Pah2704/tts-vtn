from importlib import reload

from starlette.testclient import TestClient
import pytest


def _client_with_models_dir(models_dir, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(models_dir))

    import backend.routes.voices as voices_route
    reload(voices_route)

    import backend.main as main
    reload(main)
    from backend.main import app
    return TestClient(app)


def _extract_items(resp_json):
    return resp_json.get("items") if isinstance(resp_json, dict) else resp_json


def test_voices_empty_dir_returns_empty_list(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    client = _client_with_models_dir(models_dir, monkeypatch)
    r = client.get("/api/voices")
    assert r.status_code == 200, r.text
    items = _extract_items(r.json())
    assert isinstance(items, list)
    assert len(items) == 0


def test_voices_bad_json_does_not_500(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    base = models_dir / "en_GB-broken-medium.onnx"
    base.touch()
    (models_dir / "en_GB-broken-medium.onnx.json").write_text(
        "{ this is not valid json",
        encoding="utf-8",
    )

    client = _client_with_models_dir(models_dir, monkeypatch)
    r = client.get("/api/voices")
    assert r.status_code == 200, r.text
    items = _extract_items(r.json())
    assert isinstance(items, list)
    assert len(items) >= 0
