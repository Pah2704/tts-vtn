from importlib import reload
import math
import numpy as np
from starlette.testclient import TestClient


def _spin(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))

    from backend.services import render_service
    reload(render_service)

    import backend.main as main
    reload(main)
    from backend.main import app

    def fake_synth(voice_id, text, speed=1.0):
        sr = 24_000
        t = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
        pcm = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return pcm, sr

    def fake_run_pipeline(wav_bytes, preset_key=None):
        return wav_bytes, {
            "lufsIntegrated": float("inf"),
            "truePeakDb": float("-inf"),
            "rms": float("nan"),
            "durationSec": 0.08,
        }

    render_service.piper_engine.synth_text = fake_synth
    render_service.run_pipeline = fake_run_pipeline
    return TestClient(app)


def test_generate_sanitizes_non_finite_metrics(tmp_path, monkeypatch):
    client = _spin(tmp_path, monkeypatch)

    body = {
        "text": "hello",
        "textMode": "plain",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "mp3",
    }
    resp = client.post("/api/generate", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    metrics = payload.get("metrics") or {}

    for key, value in metrics.items():
        assert isinstance(value, (int, float)), f"metric {key} should be numeric"
        assert math.isfinite(value), f"metric {key} must be finite, got {value}"
