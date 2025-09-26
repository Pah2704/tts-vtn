from importlib import reload
from urllib.parse import urlsplit

import numpy as np
from starlette.testclient import TestClient


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,*")

    from backend.services import render_service
    reload(render_service)
    import backend.main as main
    reload(main)
    from backend.main import app
    return TestClient(app), render_service


def test_outputs_cors_and_expose_headers(tmp_path, monkeypatch):
    client, rs = _make_client(tmp_path, monkeypatch)

    def fake_synth(voice_id, text, speed=1.0):
        sr = 24_000
        t = np.linspace(0, 0.2, int(sr * 0.2), endpoint=False)
        return (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr

    def fake_process(pcm, sr, preset_key=None, overrides=None):
        return pcm, {"lufsIntegrated": -16.0}

    rs.piper_engine.synth_text = fake_synth
    rs.audio_pipeline.process = fake_process

    body = {
        "text": "cors test",
        "textMode": "plain",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "wav",
    }
    r = client.post("/api/generate", json=body)
    assert r.status_code == 200
    path = urlsplit(r.json()["url"]).path

    origin = "http://localhost:5173"

    opt = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Range",
        },
    )
    assert opt.status_code in (200, 204)
    assert opt.headers.get("access-control-allow-origin") in (origin, "*")
    allow_hdrs = (opt.headers.get("access-control-allow-headers") or "").lower()
    assert "range" in allow_hdrs

    getr = client.get(path, headers={"Origin": origin, "Range": "bytes=0-15"})
    assert getr.status_code == 206
    assert getr.headers.get("access-control-allow-origin") in (origin, "*")
    exposed = (getr.headers.get("access-control-expose-headers") or "").lower()
    assert "content-range" in exposed and "accept-ranges" in exposed
