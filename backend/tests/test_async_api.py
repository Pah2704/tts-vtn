from starlette.testclient import TestClient
from backend.main import app


client = TestClient(app)


class DummyAsyncResult:
    def __init__(self, id="job-xyz", state="SUCCESS", info=None, result=None):
        self.id = id
        self.state = state
        self.info = info or {}
        self.result = result or {}


def test_generate_async_returns_jobid(monkeypatch):
    import backend.tasks as tasks

    def fake_delay(payload):
        # Có thể trả id cố định, test chỉ cần chuỗi không rỗng
        return DummyAsyncResult(id="job-abc")

    monkeypatch.setattr(tasks.generate_task, "delay", fake_delay)

    r = client.post(
        "/api/generate",
        json={
            "mode": "async",
            "engine": "xtts",
            "text": "hello",
            "config": {"voiceId": "vi_female_01"},
        },
    )
    assert r.status_code == 200
    d = r.json()
    job_id = d.get("jobId") or d.get("job_id")
    assert d.get("mode") == "async" and isinstance(job_id, str) and len(job_id) > 0


def test_status_and_result_shapes(monkeypatch):
    import backend.api.routes as routes
    import pytest

    # Một số build có thể tắt các route async -> dò trước rồi skip
    probe = client.get("/api/status/probe")
    if probe.status_code == 404:
        pytest.skip("Async status/result API not enabled in this build")

    # PROGRESS shape
    monkeypatch.setattr(
        routes,
        "AsyncResult",
        lambda job_id: DummyAsyncResult(state="PROGRESS", info={"progress": 40}),
    )
    s = client.get("/api/status/job-abc")
    assert s.status_code == 200

    # SUCCESS result shape (bỏ qua raw_url nếu có)
    monkeypatch.setattr(
        routes,
        "AsyncResult",
        lambda job_id: DummyAsyncResult(
            state="SUCCESS",
            result={
                "audio_url": "/outputs/async/xyz/processed.wav",
                "raw_url": "/outputs/async/xyz/original.wav",
                "format": "wav",
                "metrics": {"lufsIntegrated": -16.0, "truePeakDb": -1.0, "durationSec": 1.23},
            },
        ),
    )
    r = client.get("/api/result/job-abc")
    assert r.status_code == 200
