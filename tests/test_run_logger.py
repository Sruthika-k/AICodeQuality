"""Tests for experiment config and CSV run logging."""

import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig
from backend.app.loop_controller import LoopController
from backend.app.run_logger import CSV_FIELDS, RunLogger


def test_experiment_config_defaults_match_current_behavior():
    config = ExperimentConfig()
    assert config.feedback_mode == "detailed"
    assert config.top_k == 5
    assert config.stop_rule == "threshold"
    assert config.strategy == "iterative"
    assert config.temperature is None
    assert config.iteration_cap == 3
    assert config.pylint_threshold == 8.0
    assert config.max_bandit_high_med == 0


def test_loop_run_appends_csv_row(tmp_path):
    insecure_code = """import os

def run(cmd):
    eval(cmd)
    os.system(cmd)
"""
    clean_code = '''"""Clean and secure execution module."""

import ast
import subprocess


def run_math_or_command(command: str) -> None:
    """Evaluate safe math expression or run a pre-approved command.

    Args:
        command: Arithmetic string to evaluate.
    """
    try:
        result = ast.literal_eval(command)
        print(f"Evaluated: {result}")
    except (ValueError, SyntaxError):
        subprocess.run(["echo", command], check=False)
'''
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [insecure_code, clean_code]
    csv_path = tmp_path / "runs.csv"
    controller = LoopController(
        iteration_cap=3,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        llm=mock_llm,
        run_logger=RunLogger(csv_path),
    )
    result = controller.run("Write an execution utility")

    assert result.converged is True
    assert result.total_iterations == 2
    assert csv_path.exists()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(CSV_FIELDS)
    assert len(rows) == 1
    row = rows[0]
    assert row["feedback_mode"] == "detailed"
    assert row["top_k"] == "5"
    assert row["stop_rule"] == "threshold"
    assert row["strategy"] == "iterative"
    assert row["iteration_cap"] == "3"
    assert row["iterations"] == "2"
    assert row["rejected_iterations"] == "1"
    assert row["api_calls"] == "2"
    assert row["pylint_score"]
    assert row["timestamp"]
    assert row["prompt_id"]
    assert row["model"]
