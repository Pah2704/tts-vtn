import io, wave, numpy as np
from typing import Any, Dict
from fastapi.testclient import TestClient
from backend.main import app
from backend.modules.tts_manager import TTSManager, SynthesisConfig

client = TestClient(app)

def _rms_dbfs_from_wav_bytes(wav_bytes: bytes) -> float:
    import soundfile as sf, numpy as np, io as _io
    bio = _io.BytesIO(wav_bytes)
    x, sr = sf.read(bio, dtype="float32", always_2d=True)
    if x.ndim == 2 and x.shape[1] > 1:
        x = x.mean(axis=1, keepdims=True)
    x = x.reshape(-1)
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x**2)))
    rms = max(rms, 1e-12)
    return 20.0 * np.log10(rms)

def test_router_forces_mode_xtts_async():
    req: Dict[str, Any] = {
        "engine": "xtts",
        "text": "Xin chào XTTS!",
        "config": {"voiceId": "any", "speed": 1.0},
        "export": {"format": "mp3", "bitrateKbps": 192},
        "mode": "sync",  # cố tình sai — BE phải ép async
    }
    r = client.post("/api/generate", json=req)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "async"
    assert "jobId" in j

def test_router_forces_mode_piper_sync(monkeypatch):
    # tránh phụ thuộc binary Piper thật
    from backend.modules.tts_manager import TTSManager as TM

    def fake_init(self, engine="piper", **kwargs):
        self.engine = engine
        self.piper_bin = "piper"
        self.model_path = "dummy"
        self.config_path = None
    monkeypatch.setattr(TM, "__init__", fake_init, raising=True)

    def fake_piper(self, text, cfg):
        sr = 16000
        data = (np.zeros(int(sr * 1.0), dtype=np.int16)).tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(data)
        buf.seek(0); return buf.getvalue()
    monkeypatch.setattr(TM, "synthesize", fake_piper, raising=True)

    req = {
        "engine": "piper",
        "text": "Xin chào Piper!",
        "config": {"voiceId": "vi_VN-vais1000-medium", "speed": 1.0},
        "export": {"format": "mp3", "bitrateKbps": 192},
        "mode": "async",  # cố tình sai — BE phải ép sync
    }
    r = client.post("/api/generate", json=req)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "sync"
    assert j["format"] == "mp3"
    assert "url" in j and "metrics" in j

def test_xtts_stub_synthesize_is_quiet_and_long_enough():
    tm = TTSManager(engine="xtts")
    wav = tm.synthesize("XTTS stub length check", SynthesisConfig(voice_id="any", speed=1.0))
    import soundfile as sf, io as _io
    bio = _io.BytesIO(wav)
    x, sr = sf.read(bio, dtype="float32", always_2d=True)
    assert len(x) / sr >= 1.15  # ~≥1.2s
    rms_db = _rms_dbfs_from_wav_bytes(wav)
    assert rms_db < -30.0  # gần im lặng

def test_xtts_text_limit():
    tm = TTSManager(engine="xtts")
    big = "a" * 2100
    import pytest
    with pytest.raises(ValueError):
        tm.synthesize(big, SynthesisConfig(voice_id="any", speed=1.0))
