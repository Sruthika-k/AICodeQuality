"""Unit tests for the FastAPI backend API endpoints."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.loop_controller import IterationData, LoopController, LoopResult
from backend.app.metrics_tracker import BeforeAfterSummary, IterationMetrics
from backend.app.static_analyzer import StaticAnalysisIssue

client = TestClient(app)


def test_health_check():
    """Verify health-check endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_docs_endpoint():
    """Verify OpenAPI Swagger documentation is available."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower() or "openapi" in response.text.lower()


def test_cors_headers_for_vite_dev_server():
    """Verify CORS headers allow requests from Vite dev server on port 5173."""
    response = client.options(
        "/api/optimize",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("http://localhost:5173", "*")


def test_optimize_endpoint_returns_full_structure():
    """Verify POST /api/optimize returns final_code, iterations, and metrics_summary."""
    dummy_issue = StaticAnalysisIssue(tool="bandit", severity="HIGH", line=5, message="eval", rule_id="B307")
    mock_iter_1 = IterationData(
        iteration=1,
        code="def bad(): eval('1')",
        pylint_score=7.0,
        bandit_high_medium_count=1,
        bandit_low_count=0,
        pylint_issue_count=1,
        total_issues_count=2,
        has_syntax_error=False,
        threshold_met=False,
        weighted_issue_score=13,
        raw_issues=[dummy_issue],
        extracted_issues=[dummy_issue],
        feedback_text="Fix eval",
    )
    mock_iter_2 = IterationData(
        iteration=2,
        code='"""Clean module."""\ndef clean(): return 1\n',
        pylint_score=10.0,
        bandit_high_medium_count=0,
        bandit_low_count=0,
        pylint_issue_count=0,
        total_issues_count=0,
        has_syntax_error=False,
        threshold_met=True,
        weighted_issue_score=0,
        raw_issues=[],
        extracted_issues=[],
        feedback_text=None,
        diff="--- a\n+++ b\n@@ -1 +1 @@\n-bad\n+clean",
        diff_lines=[{"type": "replace", "old_line_num": 1, "new_line_num": 1, "old_line": "bad", "new_line": "clean"}],
    )

    mock_metrics_1 = IterationMetrics(
        iteration=1,
        pylint_score=7.0,
        total_issues=2,
        counts_by_tool={"bandit": 1, "pylint": 1},
        counts_by_tool_and_severity={"bandit": {"HIGH": 1}},
        threshold_met=False,
        has_syntax_error=False,
    )
    mock_metrics_2 = IterationMetrics(
        iteration=2,
        pylint_score=10.0,
        total_issues=0,
        counts_by_tool={},
        counts_by_tool_and_severity={},
        threshold_met=True,
        has_syntax_error=False,
    )

    mock_summary = BeforeAfterSummary(
        initial_iteration=1,
        final_iteration=2,
        total_iterations=2,
        converged=True,
        initial_pylint_score=7.0,
        final_pylint_score=10.0,
        pylint_score_delta=3.0,
        initial_total_issues=2,
        final_total_issues=0,
        issues_eliminated=2,
        initial_metrics=mock_metrics_1,
        final_metrics=mock_metrics_2,
        table="+=== MOCK TABLE ===+",
    )

    mock_result = LoopResult(
        prompt="Write something",
        final_code='"""Clean module."""\ndef clean(): return 1\n',
        converged=True,
        total_iterations=2,
        final_pylint_score=10.0,
        final_bandit_high_medium=0,
        status="CONVERGED",
        stop_reason="CONVERGED_THRESHOLD",
        api_calls_used=2,
        iterations=[mock_iter_1, mock_iter_2],
        before_after_summary=mock_summary,
    )

    with patch.object(LoopController, "run", return_value=mock_result):
        payload = {"prompt": "Write a clean function"}
        response = client.post("/api/optimize", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Check required fields from user request
        assert "final_code" in data
        assert "iterations" in data
        assert "metrics_summary" in data

        assert data["converged"] is True
        assert data["total_iterations"] == 2
        assert len(data["iterations"]) == 2
        assert data["iterations"][1]["diff"] is not None
        assert len(data["iterations"][1]["diff_lines"]) > 0
        assert data["metrics_summary"]["pylint_score_delta"] == 3.0
        assert data["metrics_summary"]["table"] == "+=== MOCK TABLE ===+"
