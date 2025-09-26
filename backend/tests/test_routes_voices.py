from fastapi.testclient import TestClient

from backend.main import app


def test_voices_list() -> None:
    client = TestClient(app)
    response = client.get("/api/voices")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
