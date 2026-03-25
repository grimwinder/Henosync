import pytest
from fastapi.testclient import TestClient
from henosync.api.app import create_app

client = TestClient(create_app())

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_health_returns_version():
    response = client.get("/health")
    assert "version" in response.json()