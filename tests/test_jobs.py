"""Job-lifecycle tests for POST/GET/cancel /api/runs using FakeLLM (no Gemini)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.exceptions import QuotaExceeded
from backend.app.loop_controller import LoopController, LoopResult
from backend.app.main import app, jobs_store
from tests.conftest import CLEAN_CODE, FakeLLM

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_jobs():
    from backend.app import main as mainmod

    jobs_store.clear()
    mainmod.llm_override = lambda: FakeLLM([CLEAN_CODE] * 8)
    yield
    mainmod.llm_override = None
    jobs_store.clear()


def _wait_for_status(run_id, allowed, timeout=40.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in allowed:
            return last
        time.sleep(0.1)
    raise AssertionError(f"Job {run_id} stuck at {last}")


def test_create_job_generate():
    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": "Write a simple hello world function",
        "iteration_cap": 1,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert len(data["run_id"]) == 8
    return data["run_id"]


def test_create_job_review():
    response = client.post("/api/runs", json={
        "mode": "review",
        "code": "def hello():\n    print('world')",
        "iteration_cap": 1,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert len(data["run_id"]) == 8


def test_create_job_missing_prompt():
    response = client.post("/api/runs", json={
        "mode": "generate",
        "iteration_cap": 2,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 400
    assert "Prompt must not be empty" in response.json()["detail"]


def test_create_job_missing_code():
    response = client.post("/api/runs", json={
        "mode": "review",
        "iteration_cap": 2,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 400
    assert "Code must not be empty" in response.json()["detail"]


def test_get_job_status_queued():
    run_id = test_create_job_generate()
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert data["status"] in ("queued", "running", "done")
    assert "stage" in data
    assert "current_iteration" in data
    assert "events" in data


def test_get_job_status_not_found():
    response = client.get("/api/runs/nonexistent")
    assert response.status_code == 404
    assert "Run not found" in response.json()["detail"]


def test_cancel_job():
    from backend.app import main as mainmod

    started = threading.Event()
    release = threading.Event()

    class BlockingLLM(FakeLLM):
        def generate(self, prompt, temperature=None):
            started.set()
            assert release.wait(timeout=10)
            return super().generate(prompt, temperature)

    mainmod.llm_override = lambda: BlockingLLM([CLEAN_CODE] * 8)

    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": "Write a simple hello world function",
        "iteration_cap": 2,
        "pylint_threshold": 8.0,
    })
    run_id = response.json()["run_id"]
    assert started.wait(timeout=10)

    cancel = client.post(f"/api/runs/{run_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelling"
    release.set()

    job = _wait_for_status(run_id, {"cancelled", "failed", "done"})
    assert job["status"] == "cancelled"


def test_cancel_job_not_found():
    response = client.post("/api/runs/nonexistent/cancel")
    assert response.status_code == 404
    assert "Run not found" in response.json()["detail"]


def test_job_large_prompt_fails():
    large_prompt = "x" * 15000
    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": large_prompt,
        "iteration_cap": 2,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 422


def test_job_large_code_fails():
    large_code = "x" * 60000
    response = client.post("/api/runs", json={
        "mode": "review",
        "code": large_code,
        "iteration_cap": 2,
        "pylint_threshold": 8.0,
    })
    assert response.status_code == 422


def test_job_completes_with_fakellm():
    run_id = test_create_job_generate()
    job = _wait_for_status(run_id, {"done", "failed"})
    assert job["status"] == "done"
    assert job["result"] is not None
    assert job["result"]["final_code"]
    assert job["error"] is None
    assert job["current_iteration"] >= 1
    stages = {event.get("stage") for event in job["events"]}
    assert "analysis" in stages or "gemini" in stages or "best" in stages


def test_job_quota_exhausted_with_fakellm():
    from backend.app import main as mainmod

    mainmod.llm_override = lambda: FakeLLM(
        [CLEAN_CODE],
        error_on_call=1,
        error_factory=lambda: QuotaExceeded("quota", retry_after=42),
    )
    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": "Write a sum function",
        "iteration_cap": 1,
        "pylint_threshold": 8.0,
    })
    run_id = response.json()["run_id"]
    job = _wait_for_status(run_id, {"failed"})
    assert job["status"] == "failed"
    assert job["error"]["code"] == "quota_exhausted"
    assert job["error"]["retry_after"] == 42
    assert job["result"] is None


def test_job_timeout_with_fakellm():
    from backend.app import main as mainmod

    mainmod.llm_override = lambda: FakeLLM(
        [CLEAN_CODE],
        error_on_call=1,
        error_factory=lambda: TimeoutError("LLM timed out"),
    )
    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": "Write a sum function",
        "iteration_cap": 1,
        "pylint_threshold": 8.0,
    })
    run_id = response.json()["run_id"]
    job = _wait_for_status(run_id, {"failed"})
    assert job["error"]["code"] == "timeout"


def test_demo_mode_uses_no_gemini():
    from backend.app import main as mainmod

    mainmod.llm_override = None
    response = client.post("/api/runs", json={
        "mode": "generate",
        "prompt": "Write a sum function",
        "iteration_cap": 1,
        "pylint_threshold": 8.0,
        "demo": True,
    })
    run_id = response.json()["run_id"]
    job = _wait_for_status(run_id, {"done", "failed"})
    assert job["status"] == "done"
    assert "add" in job["result"]["final_code"]


def test_blocking_endpoints_still_work():
    mock_result = LoopResult(
        prompt="Write a simple function",
        final_code="def hello():\n    return 1\n",
        converged=True,
        total_iterations=1,
        final_pylint_score=9.0,
        final_bandit_high_medium=0,
        status="CONVERGED",
        stop_reason="CONVERGED_THRESHOLD",
        api_calls_used=1,
        iterations=[],
        before_after_summary=None,
    )
    original_run = LoopController.run

    def fake_run(self, *args, **kwargs):
        return mock_result

    LoopController.run = fake_run
    try:
        response = client.post("/api/optimize", json={
            "prompt": "Write a simple function",
            "iteration_cap": 1,
            "pylint_threshold": 6.0,
        })
        assert response.status_code == 200
        assert response.json()["final_code"] == mock_result.final_code

        response = client.post("/api/review", json={
            "code": "def hello():\n    print('world')",
            "iteration_cap": 1,
            "pylint_threshold": 6.0,
        })
        assert response.status_code == 200
    finally:
        LoopController.run = original_run
