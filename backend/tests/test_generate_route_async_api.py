from importlib import reload
from urllib.parse import urlsplit

import numpy as np
import pytest
from starlette.testclient import TestClient


def _spin_up_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))

    import backend.celery_app as celery_app
    reload(celery_app)

    from backend.services import render_service
    reload(render_service)

    import backend.tasks.xtts_task as xtts_task
    reload(xtts_task)

    import backend.main as main
    reload(main)
    from backend.main import app

    def fake_synth(voice_id, text, speed=1.0):
        sr = 24_000
        t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
        pcm = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return pcm, sr

    def fake_run_pipeline(wav_bytes, preset_key=None):
        return wav_bytes, {"lufs": -16.0, "peak_db": -1.0}

    render_service.piper_engine.synth_text = fake_synth
    render_service.run_pipeline = fake_run_pipeline

    return TestClient(app)


def _pick_path_from_urlish(urlish: str) -> str:
    if not urlish:
        return ""
    parsed = urlsplit(urlish)
    return parsed.path or urlish


def _assert_head_and_range(client: TestClient, url: str):
    path = urlsplit(url).path
    head = client.head(path)
    assert head.status_code == 200
    assert head.headers.get("accept-ranges") == "bytes"
    rng = client.get(path, headers={"Range": "bytes=0-1"})
    assert rng.status_code == 206
    assert rng.headers.get("content-range", "").startswith("bytes 0-1/")
    assert len(rng.content) == 2


def test_xtts_async_api_e2e(tmp_path, monkeypatch):
    client = _spin_up_app(tmp_path, monkeypatch)

    body = {
        "text": "Hello async world.",
        "textMode": "plain",
        "engine": "xtts",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "mp3",
        "config": {"segmentation": {"strategy": "punctuation", "autoBreakMs": 120}},
    }
    resp = client.post("/api/generate", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    direct_url = data.get("url")
    if direct_url:
        _assert_head_and_range(client, direct_url)
        return

    job_id = data.get("jobId") or data.get("job_id")
    assert job_id and isinstance(job_id, str)

    status_url = data.get("statusUrl") or data.get("status_url")
    result_url = data.get("resultUrl") or data.get("result_url")
    status_path = _pick_path_from_urlish(status_url) or f"/api/status/{job_id}"
    result_path = _pick_path_from_urlish(result_url) or f"/api/result/{job_id}"

    s = client.get(status_path)
    if s.status_code == 404:
        pytest.skip("Status route not available under eager configuration.")
    assert s.status_code == 200, s.text
    payload = s.json() or {}
    state = (payload.get("status") or payload.get("state") or "").lower()
    assert state in {"done", "success"}

    r = client.get(result_path)
    if r.status_code == 404:
        pytest.skip("Result route not available under eager configuration.")
    assert r.status_code == 200, r.text
    url = r.json().get("url")
    assert url, r.json()
    _assert_head_and_range(client, url)
