from importlib import reload

from fastapi.testclient import TestClient

from backend.main import app


def test_generate_piper_ssml_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    from backend.services import render_service

    reload(render_service)

    client = TestClient(app)
    body = {
        "text": '<speak>Hello<break time="250ms"/>world</speak>',
        "textMode": "ssml",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "wav",
    }
    response = client.post("/api/generate", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine"] == "piper"
    assert payload["mode"] == "sync"
    assert payload["url"].endswith(".wav")
    assert payload["filename"].endswith(".wav")
