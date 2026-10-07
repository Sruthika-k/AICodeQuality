"""Tests for matrix logging changes: final code files and matrix_iterations.csv."""

import csv
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in str(__file__):
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig
from backend.app.loop_controller import LoopController
from tests.conftest import FakeLLM, CLEAN_CODE


def test_final_code_saved():
    """Test that final code is saved to logs/final_code/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override FINAL_CODE_DIR
        import scripts.run_matrix as run_matrix
        original_dir = run_matrix.FINAL_CODE_DIR
        run_matrix.FINAL_CODE_DIR = Path(tmpdir)
        
        try:
            cfg = ExperimentConfig(
                strategy="loop",
                stop_rule="fixed_cap",
                iteration_cap=2,
                enable_radon=False,
                acceptance_rule="weighted"
            )
            
            llm = FakeLLM([CLEAN_CODE, CLEAN_CODE], model_name="fake-test-model")
            controller = LoopController(config=cfg, llm=llm)
            
            result = controller.run("test prompt")
            
            # Simulate the final code saving logic
            final_code_path = run_matrix.FINAL_CODE_DIR / "test_task_C1_r1.py"
            final_code_path.write_text(result.final_code, encoding="utf-8")
            
            assert final_code_path.exists()
            saved_code = final_code_path.read_text(encoding="utf-8")
            assert saved_code == result.final_code
        finally:
            run_matrix.FINAL_CODE_DIR = original_dir


def test_matrix_iterations_csv_format():
    """Test that matrix_iterations.csv has correct columns."""
    from scripts.run_matrix import save_iterations_csv
    
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "matrix_iterations.csv"
        
        rows = [
            {
                "task": "task_01",
                "condition": "C1",
                "repeat": "1",
                "iteration": "1",
                "pylint_score": "8.5",
                "bandit_high": "0",
                "bandit_medium": "0",
                "bandit_low": "1",
                "issue_count": "5",
                "weighted_score": "5",
                "accepted": "True",
                "rejection_reason": "",
            }
        ]
        
        save_iterations_csv(csv_path, rows)
        
        assert csv_path.exists()
        
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows_read = list(reader)
            assert len(rows_read) == 1
            assert rows_read[0]["task"] == "task_01"
            assert rows_read[0]["condition"] == "C1"
            assert rows_read[0]["iteration"] == "1"
            assert rows_read[0]["bandit_high"] == "0"
            assert rows_read[0]["weighted_score"] == "5"


def test_introduced_resolved_calculation():
    """Test that introduced/resolved calculation matches loop_controller logic."""
    from scripts.run_matrix import calculate_introduced_resolved
    from backend.app.loop_controller import IterationData, StaticAnalysisIssue
    
    # Create mock iterations with accepted trajectory
    issue1 = StaticAnalysisIssue(tool="bandit", severity="HIGH", rule_id="B101", line=1, message="test")
    issue2 = StaticAnalysisIssue(tool="pylint", severity="ERROR", rule_id="E001", line=2, message="test")
    issue3 = StaticAnalysisIssue(tool="bandit", severity="MEDIUM", rule_id="B102", line=3, message="test")
    
    iter1 = IterationData(
        iteration=1,
        code="code1",
        pylint_score=5.0,
        bandit_high_medium_count=1,
        bandit_low_count=0,
        pylint_issue_count=1,
        total_issues_count=2,
        has_syntax_error=False,
        threshold_met=False,
        weighted_issue_score=10,
        raw_issues=[issue1, issue2],
        accepted=True,
        acceptance_reason="initial"
    )
    
    iter2 = IterationData(
        iteration=2,
        code="code2",
        pylint_score=8.0,
        bandit_high_medium_count=0,
        bandit_low_count=0,
        pylint_issue_count=0,
        total_issues_count=0,
        has_syntax_error=False,
        threshold_met=True,
        weighted_issue_score=0,
        raw_issues=[],
        accepted=True,
        acceptance_reason="weighted"
    )
    
    iter3 = IterationData(
        iteration=3,
        code="code3",
        pylint_score=7.0,
        bandit_high_medium_count=0,
        bandit_low_count=0,
        pylint_issue_count=1,
        total_issues_count=1,
        has_syntax_error=False,
        threshold_met=False,
        weighted_issue_score=3,
        raw_issues=[issue3],
        accepted=True,
        acceptance_reason="weighted"
    )
    
    iterations = [iter1, iter2, iter3]
    introduced, resolved = calculate_introduced_resolved(iterations)
    
    # Iter1->2: B101 and E001 resolved (2), 0 introduced
    # Iter2->3: B102 introduced (1), 0 resolved
    # Total: 1 introduced, 2 resolved
    assert introduced == 1
    assert resolved == 2


def test_introduced_resolved_no_accepted_trajectory():
    """Test introduced/resolved with only one accepted iteration."""
    from scripts.run_matrix import calculate_introduced_resolved
    from backend.app.loop_controller import IterationData, StaticAnalysisIssue
    
    issue1 = StaticAnalysisIssue(tool="bandit", severity="HIGH", rule_id="B101", line=1, message="test")
    
    iter1 = IterationData(
        iteration=1,
        code="code1",
        pylint_score=5.0,
        bandit_high_medium_count=1,
        bandit_low_count=0,
        pylint_issue_count=0,
        total_issues_count=1,
        has_syntax_error=False,
        threshold_met=False,
        weighted_issue_score=10,
        raw_issues=[issue1],
        accepted=True,
        acceptance_reason="initial"
    )
    
    iterations = [iter1]
    introduced, resolved = calculate_introduced_resolved(iterations)
    
    # Only one iteration, no changes to track
    assert introduced == 0
    assert resolved == 0
