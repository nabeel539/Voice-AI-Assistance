"""
Tests for the health check endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_health_check_returns_200(client):
    """GET /health should return 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_returns_status_ok(client):
    """GET /health response body should contain status: ok."""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
