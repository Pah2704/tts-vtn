from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_presets_shape():
    r = client.get("/api/presets")
    if r.status_code == 404:
        r = client.get("/api/config/presets")
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list) and len(arr) > 0
    item = arr[0]
    assert {"key", "title", "lufsTarget"}.issubset(item.keys())
