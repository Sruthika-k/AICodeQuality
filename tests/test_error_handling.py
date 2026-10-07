"""Tests for error handling in the API.

Integration tests: require a live local server at API_URL (127.0.0.1:8001).
When the server is not reachable, each test is skipped automatically with a
short pre-check of the health endpoint (or a TCP connect probe).
"""

import socket
from typing import Optional

import pytest
import requests
from pathlib import Path

API_URL = "http://127.0.0.1:8001"
_SERVER_ALIVE_CACHE: Optional[bool] = None


def _server_alive() -> bool:
    """Best-effort check that API_URL is reachable; cached for the test session."""
    global _SERVER_ALIVE_CACHE
    if _SERVER_ALIVE_CACHE is not None:
        return _SERVER_ALIVE_CACHE
    # First try TCP connect (fast, no HTTP required).
    try:
        host = "127.0.0.1"
        port = 8001
        with socket.create_connection((host, port), timeout=0.2):
            pass
    except OSError:
        _SERVER_ALIVE_CACHE = False
        return False
    # Also hit /api/health briefly to confirm it's OUR server and not something else
    # on port 8001.
    try:
        r = requests.get(f"{API_URL}/api/health", timeout=0.5)
        _SERVER_ALIVE_CACHE = (r.status_code == 200 and r.json().get("status") == "healthy")
    except Exception:
        _SERVER_ALIVE_CACHE = False
    return _SERVER_ALIVE_CACHE


integration = pytest.mark.skipif(
    not _server_alive(),
    reason="Integration test: no live server reachable on 127.0.0.1:8001 (/api/health != healthy)",
)


@integration
def test_empty_prompt():
    """Test that empty prompt returns 400 error."""
    response = requests.post(
        f"{API_URL}/api/optimize",
        json={"prompt": "", "iteration_cap": 3, "pylint_threshold": 8.0},
        timeout=5
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@integration
def test_oversized_prompt():
    """Test that oversized prompt returns 422 validation error."""
    large_prompt = "x" * 11000  # Exceeds 10KB
    response = requests.post(
        f"{API_URL}/api/optimize",
        json={"prompt": large_prompt, "iteration_cap": 3, "pylint_threshold": 8.0},
        timeout=5
    )
    assert response.status_code == 422
    assert "too_long" in str(response.json()["detail"]).lower() or "characters" in str(response.json()["detail"]).lower()


@integration
def test_invalid_iteration_cap():
    """Test that invalid iteration cap returns 422 error."""
    response = requests.post(
        f"{API_URL}/api/optimize",
        json={"prompt": "test", "iteration_cap": 10, "pylint_threshold": 8.0},
        timeout=5
    )
    assert response.status_code == 422
    assert "iteration_cap" in response.json()["detail"][0]["loc"]


@integration
def test_invalid_pylint_threshold():
    """Test that invalid pylint threshold returns 422 error."""
    response = requests.post(
        f"{API_URL}/api/optimize",
        json={"prompt": "test", "iteration_cap": 3, "pylint_threshold": 15.0},
        timeout=5
    )
    assert response.status_code == 422
    assert "pylint_threshold" in response.json()["detail"][0]["loc"]


@integration
def test_empty_code_review():
    """Test that empty code in review mode returns 400 error."""
    response = requests.post(
        f"{API_URL}/api/review",
        json={"code": "", "iteration_cap": 3, "pylint_threshold": 8.0},
        timeout=5
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@integration
def test_oversized_code_review():
    """Test that oversized code in review mode returns 422 validation error."""
    large_code = "x" * 55000  # Exceeds 50KB
    response = requests.post(
        f"{API_URL}/api/review",
        json={"code": large_code, "iteration_cap": 3, "pylint_threshold": 8.0},
        timeout=5
    )
    assert response.status_code == 422
    assert "too_long" in str(response.json()["detail"]).lower() or "characters" in str(response.json()["detail"]).lower()


@integration
def test_health_endpoint():
    """Test that health endpoint returns 200."""
    response = requests.get(f"{API_URL}/api/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
