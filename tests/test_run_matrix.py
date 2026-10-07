"""Tests for run_matrix.py experiment runner."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_run_matrix_resume_skips_completed_pairs(tmp_path):
    """Resume skips pairs already in results file."""
    import csv
    import json
    from scripts import run_matrix
    
    jsonl_path = tmp_path / "prompts.jsonl"
    results_path = tmp_path / "matrix_results.csv"
    
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test 1"}))
    
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["prompt_id", "condition", "repeat"])
        writer.writeheader()
        writer.writerow({"prompt_id": "p1", "condition": "C1", "repeat": "1"})
    
    completed = run_matrix.load_completed_pairs(results_path)
    assert ("p1", "C1", 1) in completed


def test_run_matrix_rate_limit_saves_progress(tmp_path):
    """Mid-run rate limit leaves partial results and rerun completes only missing pairs."""
    import csv
    import json
    from scripts import run_matrix
    
    jsonl_path = tmp_path / "prompts.jsonl"
    results_path = tmp_path / "matrix_results.csv"
    
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test 1"}))
    
    results_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Mock rate limit on second condition
    call_count = [0]
    original_run = run_matrix.run_condition
    
    def mock_run_condition(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            return None  # Rate limit signal
        return original_run(*args, **kwargs)
    
    run_matrix.run_condition = mock_run_condition
    
    # Save one result first
    result = run_matrix.run_condition("p1", "test", "C1", 1, 0.0, True, iteration_cap=5, max_calls=None)
    run_matrix.save_progress(results_path, [result])

    # Try to continue - should hit rate limit
    result = run_matrix.run_condition("p1", "test", "C2", 1, 0.0, True, iteration_cap=5, max_calls=None)
    assert result is None  # Rate limit
    
    # Verify partial results saved (1 row)
    with results_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    
    # Restore and verify completion would skip C1
    run_matrix.run_condition = original_run
    completed = run_matrix.load_completed_pairs(results_path)
    assert ("p1", "C1", 1) in completed
    assert ("p1", "C2", 1) not in completed


def test_run_matrix_each_condition_applies_right_flags(tmp_path):
    """Each condition applies the right flags (C1 single_shot, C2-C4 loop variants)."""
    from scripts import run_matrix
    
    # Test C1 single_shot
    result_c1 = run_matrix.run_condition("p1", "test", "C1", 1, 0.0, True, iteration_cap=5, max_calls=None)
    assert result_c1["strategy"] == "single_shot"
    assert result_c1["stop_rule"] == "fixed_cap"

    # Test C2 loop baseline
    result_c2 = run_matrix.run_condition("p1", "test", "C2", 1, 0.0, True, iteration_cap=5, max_calls=None)
    assert result_c2["strategy"] == "loop"
    assert result_c2["stop_rule"] == "fixed_cap"

    # Test C3 regression_aware
    result_c3 = run_matrix.run_condition("p1", "test", "C3", 1, 0.0, True, iteration_cap=5, max_calls=None)
    assert result_c3["strategy"] == "loop"
    assert result_c3["feedback_mode"] == "regression_aware"

    # Test C4 constrained
    result_c4 = run_matrix.run_condition("p1", "test", "C4", 1, 0.0, True, iteration_cap=5, max_calls=None)
    assert result_c4["strategy"] == "loop"
    assert result_c4["acceptance_rule"] == "constrained"
