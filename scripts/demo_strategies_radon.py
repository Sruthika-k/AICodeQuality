"""Demo: three strategies + Radon flag.

  1. Runs all THREE strategies (single_shot, single_shot_secure, loop) on the
     SAME prompt set → verifies each strategy logs to CSV.
  2. Runs once with enable_radon=False (default) and once with enable_radon=True
     → verifies Radon columns are added ONLY when flag is True (otherwise empty),
     and nothing else changes about the logged severity counts, issue counts, etc.

Also prints a quick terminal summary so you can eyeball correctness.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig, SECURE_CODE_INSTRUCTION, STRATEGIES
from backend.app.eval_harness import EVAL_PROMPTS
from backend.app.loop_controller import LoopController
from backend.app.run_logger import CSV_FIELDS, RunLogger


DEMO_PROMPTS = EVAL_PROMPTS  # Same prompt set for every strategy.

# Clean-ish return value that still lets Radon compute complexity but
# has a security finding so the loop strategy won't converge immediately
# (we want to observe >1 iteration in loop mode).
INSECURE_FOR_LOOP_DEMO = '''"""Helper module for demo (intentionally has one security finding)."""

import os


def run_calc(user_cmd):
    """Calculate an arithmetic expression via eval."""
    result = eval(user_cmd)
    password = "hardcoded-secret-123"
    os.system(password)
    return result


def add(a: int, b: int) -> int:
    """Return sum of two integers.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        Integer sum.
    """
    return a + b


def multiply(a: int, b: int) -> int:
    """Return product of two integers."""
    return a * b
'''


def _run_all_strategies(csv_path: Path, enable_radon: bool) -> None:
    if csv_path.exists():
        csv_path.unlink()
    logger = RunLogger(csv_path)
    for prompt in DEMO_PROMPTS:
        for strategy in STRATEGIES:
            mock_llm = MagicMock()
            calls = []

            def _stubbed_generate(prompt_text: str, temperature=None, model=None) -> str:
                calls.append(prompt_text)
                return INSECURE_FOR_LOOP_DEMO

            mock_llm.generate = _stubbed_generate
            cfg = ExperimentConfig(
                strategy=strategy,
                stop_rule="fixed_cap",
                enable_radon=enable_radon,
                iteration_cap=2,
                pylint_threshold=8.0,
                max_bandit_high_med=0,
                model="demo-mock",
            )
            controller = LoopController(config=cfg, llm=mock_llm, run_logger=logger)
            result = controller.run(prompt["prompt"])

            # Strategy-specific assertions:
            assert result.total_iterations == (1 if cfg.is_single_shot else 2), (
                f"{strategy} should produce {(1 if cfg.is_single_shot else 2)} iterations"
            )
            if strategy == "single_shot_secure":
                assert any(SECURE_CODE_INSTRUCTION in c for c in calls), (
                    "single_shot_secure prompt must include the security instruction"
                )
            elif strategy == "single_shot":
                assert all(SECURE_CODE_INSTRUCTION not in c for c in calls), (
                    "vanilla single_shot prompt must NOT include security instruction"
                )


def _compare_flag_off_vs_flag_on(off_rows, on_rows) -> None:
    """Verify enabling the flag changes ONLY the three Radon columns."""
    assert len(off_rows) == len(on_rows), "Same prompt-set, strategies → same row count"
    for i, (off, on) in enumerate(zip(off_rows, on_rows)):
        # Same (prompt_id, strategy, iterations, issues, pylint_score, issue severities).
        for col in (
            "prompt_id",
            "strategy",
            "feedback_mode",
            "stop_rule",
            "iteration_cap",
            "pylint_threshold",
            "iterations",
            "pylint_score",
            "issues_high",
            "issues_medium",
            "issues_low",
            "issues_error",
            "issues_warning",
            "issues_convention",
            "issues_refactor",
            "issues_other",
        ):
            assert off[col] == on[col], (
                f"Row {i} column {col!r} differs when flipping enable_radon: "
                f"{off[col]!r} vs {on[col]!r}"
            )
        # Flag-Off: three Radon columns empty.
        assert off["avg_complexity"] == ""
        assert off["max_complexity"] == ""
        assert off["maintainability_index"] == ""
        # Flag-On: three Radon columns populated.
        assert on["avg_complexity"] != ""
        assert on["max_complexity"] != ""
        assert on["maintainability_index"] != ""
        avg = float(on["avg_complexity"])
        mx = int(on["max_complexity"])
        mi = float(on["maintainability_index"])
        assert avg >= 1.0 and mx >= 1 and 0 <= mi <= 100


def main() -> int:
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    off_csv = logs_dir / "demo_strategies_radon_off.csv"
    on_csv = logs_dir / "demo_strategies_radon_on.csv"

    print("=== Run #1: enable_radon=False (default) ===")
    _run_all_strategies(off_csv, enable_radon=False)
    print(f"Wrote {off_csv}")

    print("\n=== Run #2: enable_radon=True ===")
    _run_all_strategies(on_csv, enable_radon=True)
    print(f"Wrote {on_csv}")

    with off_csv.open(newline="", encoding="utf-8") as h:
        off_rows = list(csv.DictReader(h))
    with on_csv.open(newline="", encoding="utf-8") as h:
        on_rows = list(csv.DictReader(h))

    expected_rows = len(DEMO_PROMPTS) * len(STRATEGIES)
    assert len(off_rows) == expected_rows, (
        f"Expected {expected_rows} rows for {len(DEMO_PROMPTS)} prompts × "
        f"{len(STRATEGIES)} strategies; got {len(off_rows)}"
    )
    assert list(off_rows[0].keys()) == list(CSV_FIELDS)
    assert list(on_rows[0].keys()) == list(CSV_FIELDS)
    print(f"\nRow count: {len(off_rows)} = {len(DEMO_PROMPTS)} prompts × {len(STRATEGIES)} strategies. OK.")

    # Per-strategy coverage
    by_strat = defaultdict(set)
    for row in off_rows:
        by_strat[row["strategy"]].add(row["prompt_id"])
    for s in STRATEGIES:
        missing = [p["id"] for p in DEMO_PROMPTS if True]  # dummy - sanity only
        assert len(by_strat[s]) == len(DEMO_PROMPTS), (
            f"Strategy {s!r} didn't cover all {len(DEMO_PROMPTS)} prompts"
        )
    print(f"Strategies × prompts verified: {dict((s, len(pids)) for s, pids in by_strat.items())}")

    # Flag isolation check
    _compare_flag_off_vs_flag_on(off_rows, on_rows)
    print("\nRadon flag isolated correctly: only avg_complexity / max_complexity / maintainability_index "
          "differ between runs, and they are non-empty only when enable_radon=True.")

    # Sample row printing
    print("\n--- Sample rows (first row of each file, last few columns) ---")
    sample_cols = [
        "strategy",
        "iterations",
        "pylint_score",
        "stop_reason",
        "final_weighted_score",
        "avg_complexity",
        "max_complexity",
        "maintainability_index",
    ]
    for label, row in [("enable_radon=False", off_rows[0]), ("enable_radon=True ", on_rows[0])]:
        print(label, " | ".join(f"{c}={row[c]!r}" for c in sample_cols))

    print("\nDEMO PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
