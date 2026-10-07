"""Unit tests for the MetricsTracker component."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.metrics_tracker import MetricsTracker
from backend.app.static_analyzer import StaticAnalysisIssue


def test_metrics_tracker_records_by_tool_and_severity():
    """Verify that MetricsTracker accurately records issues grouped by tool and severity."""
    tracker = MetricsTracker()

    iter1_issues = [
        StaticAnalysisIssue(tool="bandit", severity="HIGH", line=6, message="os.system", rule_id="B605"),
        StaticAnalysisIssue(tool="bandit", severity="MEDIUM", line=5, message="eval", rule_id="B307"),
        StaticAnalysisIssue(tool="pylint", severity="WARNING", line=5, message="eval used", rule_id="W0123"),
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", line=1, message="missing docstring", rule_id="C0114"),
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", line=4, message="missing func docstring", rule_id="C0116"),
    ]

    metric1 = tracker.record(
        iteration=1,
        issues=iter1_issues,
        pylint_score=7.50,
        threshold_met=False,
    )

    assert metric1.iteration == 1
    assert metric1.pylint_score == 7.50
    assert metric1.total_issues == 5
    assert metric1.counts_by_tool["bandit"] == 2
    assert metric1.counts_by_tool["pylint"] == 3
    assert metric1.counts_by_tool_and_severity["bandit"]["HIGH"] == 1
    assert metric1.counts_by_tool_and_severity["bandit"]["MEDIUM"] == 1
    assert metric1.counts_by_tool_and_severity["pylint"]["WARNING"] == 1
    assert metric1.counts_by_tool_and_severity["pylint"]["CONVENTION"] == 2


def test_before_after_summary_generation_and_table():
    """Verify BeforeAfterSummary metrics and formatted comparison table."""
    tracker = MetricsTracker()

    iter1_issues = [
        StaticAnalysisIssue(tool="bandit", severity="HIGH", line=6, message="os.system", rule_id="B605"),
        StaticAnalysisIssue(tool="bandit", severity="MEDIUM", line=5, message="eval", rule_id="B307"),
        StaticAnalysisIssue(tool="pylint", severity="WARNING", line=5, message="eval used", rule_id="W0123"),
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", line=1, message="missing docstring", rule_id="C0114"),
    ]
    tracker.record(iteration=1, issues=iter1_issues, pylint_score=7.0, threshold_met=False)

    iter2_issues = [
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", line=1, message="missing docstring", rule_id="C0114"),
    ]
    tracker.record(iteration=2, issues=iter2_issues, pylint_score=9.5, threshold_met=True)

    summary = tracker.get_before_after_summary(converged=True)

    assert summary.initial_iteration == 1
    assert summary.final_iteration == 2
    assert summary.initial_pylint_score == 7.0
    assert summary.final_pylint_score == 9.5
    assert summary.pylint_score_delta == 2.5
    assert summary.initial_total_issues == 4
    assert summary.final_total_issues == 1
    assert summary.issues_eliminated == 3
    assert summary.converged is True

    # Check formatted table
    table = summary.table
    print("\n" + table + "\n")
    assert "BEFORE / AFTER QUALITY SUMMARY" in table
    assert "Before (Iter 1)" in table
    assert "After (Iter 2)" in table
    assert "Pylint Score" in table
    assert "Bandit High Issues" in table
    assert "Total Issues Count" in table
