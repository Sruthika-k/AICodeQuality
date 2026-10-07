"""Demo: prove plateau stop_rule beats the cap on a stuck run, and the CSV log
captures stop_reason + API calls used.

Compares two runs with identical stuck code (same insecure result every iteration):
  A. stop_rule=fixed_cap  — runs up to iteration_cap=5, stop_reason=STOP_FIXED_CAP
  B. stop_rule=plateau   — stops at iteration 3 (< cap 5), stop_reason=STOP_PLATEAU_WEIGHTED
     with terminal output explaining the 2 consecutive non-improvement strikes
     and printing the weighted scores per iteration.

Also writes a fresh CSV in logs/ so you can inspect stop_reason column directly.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import (
    PLATEAU_MIN_STRIKES,
    STOP_REASON_FIXED_CAP,
    STOP_REASON_PLATEAU,
    STOP_RULE_FIXED_CAP,
    STOP_RULE_PLATEAU,
    ExperimentConfig,
)
from backend.app.loop_controller import LoopController
from backend.app.run_logger import CSV_FIELDS, RunLogger


STUCK_CODE = '''import os
import subprocess
import json

def danger(user_cmd):
    """Dangerous code that the LLM keeps returning unchanged."""
    eval(user_cmd)
    os.system(user_cmd)
    subprocess.call(user_cmd, shell=True)
    password = "hardcoded_secret_123"
    print(password)
    return None
'''


def _make_controller(stop_rule: str, cap: int, csv_path: Path):
    mock_llm = MagicMock()
    mock_llm.generate.return_value = STUCK_CODE
    cfg = ExperimentConfig(
        stop_rule=stop_rule,
        iteration_cap=cap,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        feedback_mode="detailed",
        model="demo-mock",
    )
    return LoopController(config=cfg, llm=mock_llm, run_logger=RunLogger(csv_path))


def main() -> int:
    cap = 5
    tmp_csv = PROJECT_ROOT / "logs" / "demo_plateau_runs.csv"
    tmp_csv.parent.mkdir(parents=True, exist_ok=True)
    if tmp_csv.exists():
        tmp_csv.unlink()

    print("=" * 78)
    print(f"[RUN A] stop_rule=fixed_cap, iteration_cap={cap} (expected: runs all {cap} iters)")
    print("=" * 78)
    ctrl_cap = _make_controller(STOP_RULE_FIXED_CAP, cap, tmp_csv)
    res_cap = ctrl_cap.run("Demonstrate fixed_cap stop rule with stuck bad code")

    print("\n" + "=" * 78)
    print(f"[RUN B] stop_rule=plateau, iteration_cap={cap}  (expected: stop at {PLATEAU_MIN_STRIKES+1} iters)")
    print("=" * 78)
    ctrl_plat = _make_controller(STOP_RULE_PLATEAU, cap, tmp_csv)
    res_plat = ctrl_plat.run("Demonstrate plateau stop rule with stuck bad code")

    print("\n" + "=" * 78)
    print("COMPARISON")
    print("=" * 78)
    print(f"fixed_cap: iterations={res_cap.total_iterations} "
          f"stop_reason={res_cap.stop_reason} api_calls={res_cap.api_calls_used}")
    print(f"plateau:   iterations={res_plat.total_iterations} "
          f"stop_reason={res_plat.stop_reason} api_calls={res_plat.api_calls_used}")
    print()
    print("Weighted scores plateau run:")
    for it in res_plat.iterations:
        print(f"  iter {it.iteration}: weighted={it.weighted_issue_score}  "
              f"pylint={it.pylint_score:.2f}  total_issues={it.total_issues_count}")
    print()
    earlier = res_plat.total_iterations < res_cap.total_iterations
    print(f"plateau_stopped_earlier_than_cap = {earlier}")
    print(f"expected plateau_stop_reason={STOP_REASON_PLATEAU!r} actual={res_plat.stop_reason!r}")
    print(f"expected cap_stop_reason={STOP_REASON_FIXED_CAP!r} actual={res_cap.stop_reason!r}")

    with tmp_csv.open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    print(f"\nWrote {len(rows)} rows to {tmp_csv}")
    print(f"CSV columns include stop_reason: {'stop_reason' in CSV_FIELDS}")
    for idx, row in enumerate(rows, 1):
        print(f"  row {idx}: stop_rule={row['stop_rule']} "
              f"stop_reason={row['stop_reason']} "
              f"iterations={row['iterations']} "
              f"api_calls={row['api_calls']} "
              f"final_weighted_score={row['final_weighted_score']}")

    ok = (
        earlier
        and res_plat.stop_reason == STOP_REASON_PLATEAU
        and res_cap.stop_reason == STOP_REASON_FIXED_CAP
        and res_plat.total_iterations == PLATEAU_MIN_STRIKES + 1
        and res_cap.total_iterations == cap
    )
    print(f"\nDEMO {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
