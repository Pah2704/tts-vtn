from importlib import reload
from urllib.parse import urlsplit
from pathlib import Path
import importlib

from starlette.testclient import TestClient
import numpy as np


def _safe_reload(modname: str):
    try:
        module = importlib.import_module(modname)
        return reload(module)
    except Exception:
        return None


def _spin(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))

    _safe_reload("backend.settings")
    _safe_reload("backend.config")
    _safe_reload("backend.services.render_service")
    _safe_reload("backend.routes.history")
    _safe_reload("backend.main")

    from backend.services import render_service as rs

    def fake_synth(voice_id, text, speed=1.0):
        sr = 24_000
        t = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
        pcm = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return pcm, sr

    def fake_run_pipeline(wav_bytes, preset_key=None):
        return wav_bytes, {
            "lufsIntegrated": -16.0,
            "truePeakDb": -1.0,
            "durationSec": 0.12,
        }

    rs.piper_engine.synth_text = fake_synth
    rs.run_pipeline = fake_run_pipeline

    from backend.main import app
    outputs_dir = Path(getattr(rs, "OUTPUTS_DIR", tmp_path))
    return TestClient(app), outputs_dir


def _gen(client: TestClient, text="x"):
    body = {
        "text": text,
        "textMode": "plain",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "mp3",
    }
    resp = client.post("/api/generate", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["url"]


def _items(payload):
    return payload.get("items") if isinstance(payload, dict) else payload


def test_history_limit_and_sorting(tmp_path, monkeypatch):
    client, outputs_dir = _spin(tmp_path, monkeypatch)

    url1 = _gen(client, "one")
    url2 = _gen(client, "two")
    url3 = _gen(client, "three")

    fn1 = urlsplit(url1).path.split("/")[-1]
    fn2 = urlsplit(url2).path.split("/")[-1]
    fn3 = urlsplit(url3).path.split("/")[-1]

    h = client.get("/api/history?limit=2")
    assert h.status_code == 200, h.text
    items = _items(h.json())
    assert isinstance(items, list)

    names = [it.get("filename") for it in items]
    assert fn3 in names, f"Newest file {fn3} must appear in history (limit=2)."

    if len(items) >= 2:
        assert fn2 in names, f"Second latest {fn2} should appear when limit>=2."
        created = [it.get("createdAt") for it in items]
        assert created == sorted(created, reverse=True), "History items should be newest-first."

    for fn in (fn1, fn2, fn3):
        assert (outputs_dir / fn).exists(), f"Expect audio exists: {outputs_dir / fn}"


def test_history_absolute_url_single(tmp_path, monkeypatch):
    client, outputs_dir = _spin(tmp_path, monkeypatch)
    url = _gen(client, "abs")

    h = client.get("/api/history?limit=1")
    assert h.status_code == 200
    items = _items(h.json())
    assert isinstance(items, list) and len(items) >= 1

    item = items[0]
    abs_url = item.get("url") or ""
    assert abs_url.startswith("http://testserver/"), f"absolute url expected, got {abs_url}"
    fname = item.get("filename")
    assert fname, "history item should contain filename"

    audio_path = outputs_dir / fname
    assert audio_path.exists(), f"audio file should exist at {audio_path}"
