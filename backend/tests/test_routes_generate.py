from fastapi.testclient import TestClient
from backend.main import app
from backend.modules import tts_manager as tts_mod
from backend.tests.conftest import gen_sine_wav_bytes

client = TestClient(app)

def _stub_manager(monkeypatch):
    # __init__ no-op để khỏi cần PIPER_* env trong unit tests
    def dummy_init(self, *args, **kwargs):
        self.engine = "piper"
    monkeypatch.setattr(tts_mod.TTSManager, "__init__", dummy_init)

    # synthesize giả: chấp nhận (self, text, cfg)
    def fake_synth(self, text, cfg):
        return gen_sine_wav_bytes(dur_sec=0.5)
    monkeypatch.setattr(tts_mod.TTSManager, "synthesize", fake_synth)

def test_generate_sync_happy_path(monkeypatch, tmp_path):
    _stub_manager(monkeypatch)

    payload = {
        "mode": "sync",
        "engine": "piper",
        "text": "xin chao",
        "config": {"voiceId": "vi_VN-fake", "speed": 1.0},
        "export": {"format": "mp3", "bitrateKbps": 128}
    }
    res = client.post("/api/generate", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["kind"] == "sync"
    assert data["format"] == "mp3"
    assert data["metrics"]["durationSec"] > 0.4

def test_generate_speed_out_of_range(monkeypatch):
    # Pydantic validation xảy ra trước khi vào route ⇒ 422
    bad = {
        "mode": "sync",
        "engine": "piper",
        "text": "hello",
        "config": {"voiceId": "vi_VN", "speed": 2.5}
    }
    r = client.post("/api/generate", json=bad)
    assert r.status_code == 422
