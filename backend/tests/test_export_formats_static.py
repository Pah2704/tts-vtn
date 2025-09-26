import shutil
from importlib import reload
from urllib.parse import urlsplit

import numpy as np
import pytest
from starlette.testclient import TestClient

ALLOWED = ["wav", "mp3", "flac", "m4a"]


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    from backend.services import render_service
    reload(render_service)
    import backend.main as main
    reload(main)
    from backend.main import app
    return TestClient(app), render_service


@pytest.fixture
def client_and_service(tmp_path, monkeypatch):
    client, rs = _make_client(tmp_path, monkeypatch)

    def fake_synth(voice_id, text, speed=1.0):
        sr = 24_000
        t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
        pcm = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return pcm, sr

    def fake_process(pcm, sr, preset_key=None, overrides=None):
        return pcm, {"lufsIntegrated": -16.0, "truePeakDb": -1.0}

    rs.piper_engine.synth_text = fake_synth
    rs.audio_pipeline.process = fake_process
    return client, rs


def _supported_formats():
    fmts = ["wav"]
    has_ffmpeg = shutil.which("ffmpeg") is not None
    try:
        import soundfile  # noqa: F401
        has_sf = True
    except Exception:
        has_sf = False

    if has_ffmpeg:
        fmts += ["mp3", "m4a", "flac"]
    elif has_sf:
        fmts += ["flac"]
    return [f for f in fmts if f in ALLOWED]


@pytest.mark.parametrize("ext", _supported_formats())
def test_generate_serves_with_mime_and_range(client_and_service, ext):
    client, _ = client_and_service

    body = {
        "text": "hello",
        "textMode": "plain",
        "engine": "piper",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": ext,
    }
    resp = client.post("/api/generate", json=body)
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    path = urlsplit(url).path

    head = client.head(path)
    assert head.status_code == 200
    ctype = head.headers.get("content-type", "")
    if ext == "mp3":
        assert ctype.startswith("audio/") and "mpeg" in ctype
    elif ext == "m4a":
        assert ctype.startswith("audio/")
    else:
        assert ctype.startswith("audio/") and ctype.endswith(ext)
    assert head.headers.get("accept-ranges") == "bytes"

    rng = client.get(path, headers={"Range": "bytes=0-1"})
    assert rng.status_code == 206
    assert rng.headers.get("content-range", "").startswith("bytes 0-1/")
    assert len(rng.content) == 2
