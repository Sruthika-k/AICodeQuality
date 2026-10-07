"""Tests for experiment strategies and the evaluation harness."""

import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig, SECURE_CODE_INSTRUCTION, STRATEGIES
from backend.app.eval_harness import EVAL_PROMPTS, run_evaluation
from backend.app.loop_controller import LoopController
from backend.app.run_logger import RunLogger

CLEAN_CODE = '''"""Addition helper."""


def add(left: int, right: int) -> int:
    """Return the sum of left and right.

    Args:
        left: First addend.
        right: Second addend.

    Returns:
        The numeric sum.
    """
    return left + right
'''

INSECURE_CODE = """import os

def run(cmd):
    eval(cmd)
    os.system(cmd)
"""


def test_single_shot_makes_one_call_and_analyzes_once(tmp_path):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = INSECURE_CODE
    controller = LoopController(
        config=ExperimentConfig(strategy="single_shot", iteration_cap=3),
        llm=mock_llm,
        run_logger=RunLogger(tmp_path / "runs.csv"),
    )
    result = controller.run("Write an execution utility")
    assert mock_llm.generate.call_count == 1
    assert result.total_iterations == 1
    assert SECURE_CODE_INSTRUCTION not in mock_llm.generate.call_args[0][0]


def test_single_shot_secure_adds_fixed_instruction(tmp_path):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = CLEAN_CODE
    controller = LoopController(
        config=ExperimentConfig(strategy="single_shot_secure"),
        llm=mock_llm,
        run_logger=RunLogger(tmp_path / "runs.csv"),
    )
    result = controller.run("Write a function that adds two numbers")
    assert mock_llm.generate.call_count == 1
    assert result.total_iterations == 1
    assert SECURE_CODE_INSTRUCTION in mock_llm.generate.call_args[0][0]


def test_loop_strategy_refines_until_cap_or_threshold(tmp_path):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = INSECURE_CODE
    controller = LoopController(
        config=ExperimentConfig(strategy="loop", iteration_cap=3),
        llm=mock_llm,
        run_logger=RunLogger(tmp_path / "runs.csv"),
    )
    result = controller.run("Never fixing code")
    assert result.total_iterations == 3
    assert mock_llm.generate.call_count == 3


def test_harness_runs_all_strategies_on_prompt_set(tmp_path):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = CLEAN_CODE
    csv_path = tmp_path / "runs.csv"
    results = run_evaluation(
        strategies=STRATEGIES,
        prompts=EVAL_PROMPTS,
        llm=mock_llm,
        csv_path=csv_path,
    )
    assert len(results) == len(EVAL_PROMPTS) * len(STRATEGIES)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(EVAL_PROMPTS) * len(STRATEGIES)
    logged_strategies = {row["strategy"] for row in rows}
    assert logged_strategies == set(STRATEGIES)
    prompt_ids = {row["prompt_id"] for row in rows}
    assert len(prompt_ids) == len(EVAL_PROMPTS)
    for prompt_id in prompt_ids:
        prompt_rows = [row for row in rows if row["prompt_id"] == prompt_id]
        assert {row["strategy"] for row in prompt_rows} == set(STRATEGIES)
