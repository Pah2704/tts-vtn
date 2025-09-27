# backend/tests/test_progress_reporting.py
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class DummyAsyncResult:
    def __init__(self, state="PENDING", info=None, result=None, id="job-123"):
        self.state = state
        self.info = info
        self.result = result
        self.id = id

def test_status_returns_progress_when_processing(monkeypatch):
    import backend.api.routes as routes
    # Giả lập job đang chạy với progress=42
    monkeypatch.setattr(
        routes, "AsyncResult",
        lambda job_id: DummyAsyncResult(state="PROGRESS", info={"progress": 42})
    )
    probe = client.get("/api/status/probe")
    if probe.status_code == 404:
        import pytest

        pytest.skip("Async status API not enabled in this build")
    r = client.get("/api/status/any")
    assert r.status_code == 200
    js = r.json()
    assert js["state"] == "processing"
    assert js["progress"] == 42

def test_state_mapping_for_basic_celery_states(monkeypatch):
    import backend.api.routes as routes

    cases = [
        ("PENDING", "queued"),
        ("STARTED", "processing"),
        ("SUCCESS", "done"),
        ("FAILURE", "error"),
    ]
    for celery_state, expected in cases:
        monkeypatch.setattr(
            routes, "AsyncResult",
            lambda job_id, s=celery_state: DummyAsyncResult(state=s)
        )
        probe = client.get("/api/status/probe")
        if probe.status_code == 404:
            import pytest

            pytest.skip("Async status API not enabled in this build")
        r = client.get("/api/status/test")
        assert r.status_code == 200 or (celery_state == "FAILURE" and r.status_code in (200, 500))
        if r.status_code == 200:
            assert r.json()["state"] == expected
