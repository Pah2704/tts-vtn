import json
import os
import shutil
import tempfile
from importlib import reload

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import presets_user as pu


def test_presets_crud(monkeypatch) -> None:
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setenv("PRESETS_USER_DIR", temp_dir)
    reload(pu)

    client = TestClient(app)
    body = {
        "key": "my_podcast_v1",
        "title": "My Podcast V1",
        "engine": "piper",
        "defaults": {"voiceId": "en_GB-alan-medium", "speed": 1.0},
    }

    resp = client.put("/api/presets_user/my_podcast_v1", json=body)
    assert resp.status_code == 200

    resp = client.get("/api/presets_user")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert any(item.get("key") == "my_podcast_v1" for item in resp.json())

    resp = client.delete("/api/presets_user/my_podcast_v1")
    assert resp.status_code == 200

    shutil.rmtree(temp_dir, ignore_errors=True)
