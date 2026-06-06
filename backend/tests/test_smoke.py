"""Basic smoke tests that don't require live infrastructure."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "quant-copilot"
    assert "version" in body


def test_openapi_schema():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "paths" in r.json()
