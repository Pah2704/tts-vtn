# backend/tests/test_async_api.py
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class DummyAsyncResult:
    def __init__(self, state="PENDING", info=None, result=None, id="job-123"):
        self.state = state
        self.info = info
        self.result = result
        self.id = id

def test_generate_async_returns_jobid(monkeypatch):
    import backend.tasks as tasks
    def fake_delay(payload):
        return DummyAsyncResult(id="job-abc")
    monkeypatch.setattr(tasks.generate_task, "delay", fake_delay)

    r = client.post("/api/generate", json={
        "mode": "async",
        "engine": "xtts",
        "text": "hello",
        "config": {"voiceId": "vi_female_01"}
    })
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "async" and d["jobId"] == "job-abc"

def test_status_and_result_shapes(monkeypatch):
    import backend.api.routes as routes
    # PROGRESS
    monkeypatch.setattr(routes, "AsyncResult",
        lambda job_id: DummyAsyncResult(state="PROGRESS", info={"progress": 40}))
    s = client.get("/api/status/job-abc")
    assert s.status_code == 200
    js = s.json()
    assert js["state"] in ("queued","processing","done","error")
    if js["state"] == "processing":
        assert js.get("progress") == 40

    # SUCCESS + result
    monkeypatch.setattr(routes, "AsyncResult",
        lambda job_id: DummyAsyncResult(state="SUCCESS",
            result={
                "audio_url": "/outputs/abc.wav",
                "format": "wav",
                "metrics": {"lufsIntegrated": -16.1, "truePeakDb": -1.0, "durationSec": 1.23}
            }))
    r = client.get("/api/result/job-abc")
    assert r.status_code == 200
    d = r.json()
    assert d["url"].endswith(".wav")
    assert "metrics" in d and "lufsIntegrated" in d["metrics"]
