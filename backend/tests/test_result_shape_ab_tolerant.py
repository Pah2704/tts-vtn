# backend/tests/test_result_shape_ab_tolerant.py
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class DummyAsyncResult:
    def __init__(self, state="SUCCESS", result=None):
        self.state = state
        self.result = result or {}

def test_result_ignores_raw_url_field(monkeypatch):
    import backend.api.routes as routes
    monkeypatch.setattr(
        routes, "AsyncResult",
        lambda job_id: DummyAsyncResult(
            state="SUCCESS",
            result={
                "audio_url": "/outputs/async/xyz/processed.wav",
                "raw_url": "/outputs/async/xyz/original.wav",
                "format": "wav",
                "metrics": {"lufsIntegrated": -16.0, "truePeakDb": -1.0, "durationSec": 1.23},
            }
        )
    )
    r = client.get("/api/result/xyz")
    assert r.status_code == 200
    d = r.json()
    assert d["url"].endswith(".wav")
    assert d["format"] == "wav"
    assert "metrics" in d and "lufsIntegrated" in d["metrics"]
