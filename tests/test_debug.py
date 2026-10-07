"""Debug helper for job polling. Uses FakeLLM — no Gemini calls."""

from backend.app.main import jobs_store
from fastapi.testclient import TestClient
from backend.app.main import app
from tests.conftest import CLEAN_CODE, FakeLLM

client = TestClient(app)


def test_debug_job_lifecycle(monkeypatch):
    from backend.app import main as mainmod

    jobs_store.clear()
    mainmod.llm_override = lambda: FakeLLM([CLEAN_CODE] * 4)
    try:
        response = client.post("/api/runs", json={
            "mode": "generate",
            "prompt": "Write a sum function",
            "iteration_cap": 1,
            "pylint_threshold": 8.0,
        })
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        res = client.get(f"/api/runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["id"] == run_id
        assert res.json()["status"] in ("queued", "running", "done", "failed")
    finally:
        mainmod.llm_override = None
        jobs_store.clear()
