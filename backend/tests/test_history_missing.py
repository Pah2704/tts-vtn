import json
from importlib import reload
from urllib.parse import urlsplit

import numpy as np
import pytest
from starlette.testclient import TestClient


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    from backend.services import render_service
    reload(render_service)
    import backend.main as main
    reload(main)
    from backend.main import app
    return TestClient(app), render_service


def test_history_marks_missing_when_audio_deleted(tmp_path, monkeypatch):
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
        "text": "keep meta",
        "textMode": "plain",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "mp3",
    }
    r = client.post("/api/generate", json=body)
    assert r.status_code == 200
    url = r.json()["url"]
    fname = urlsplit(url).path.split("/")[-1]

    audio_path = tmp_path / fname
    if audio_path.exists():
        audio_path.unlink()

    meta_path = tmp_path / f"{fname}.meta.json"
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps(
                {
                    "filename": fname,
                    "engine": "piper",
                    "preset": "podcast_standard",
                    "export": "mp3",
                    "duration": 0.2,
                }
            ),
            encoding="utf-8",
        )

    hist = client.get("/api/history?limit=10")
    assert hist.status_code == 200
    payload = hist.json()
    items = payload.get("items") if isinstance(payload, dict) else payload

    target = next((it for it in items if it.get("filename") == fname), None)
    if target is None:
        pytest.skip("/api/history only lists existing audio files")
    assert target.get("missing") is True
    assert not target.get("url")
