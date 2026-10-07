"""Replay logged fixed-cap runs and report where plateau rule would have stopped,
the quality at that point, and the API calls saved. No new API calls made.

Inputs are existing CSV logs (no LLM calls, no static analysis reruns):
  - runs.csv        : per-run summary (stop_rule, api_calls, stop_reason, final weights...)
  - iterations.csv  : per-issue rows (one row per (prompt_id, iteration, issue))

Algorithm for each run with stop_rule=fixed_cap:
  1. Collect all issues for the prompt_id from iterations.csv, grouped by iteration.
  2. Compute weighted_issue_score per iteration using SEVERITY_WEIGHTS from config.
  3. Walk the per-iteration weighted scores tracking best-so-far and a strike counter
     for consecutive iterations without strictly improving vs best-so-far.
  4. Plateau fires at the first iteration i where strikes >= PLATEAU_MIN_STRIKES after
     processing i. If plateau never fires within the actual iterations run, we use the
     full cap as the "plateau stop" (calls saved = 0).

Prints per prompt:
  - Actual fixed-cap run: iterations, api_calls, quality (pylint, weighted).
  - Plateau-simulated stop: iteration where it would stop, api_calls used, api_calls saved.
  - Quality retained: weighted score at plateau vs actual run (percent).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import (
    DEFAULT_SEVERITY_WEIGHT,
    PLATEAU_MIN_STRIKES,
    SEVERITY_WEIGHTS,
    STOP_RULE_FIXED_CAP,
)


@dataclass
class RunRow:
    """One row from runs.csv, relevant fields only."""
    prompt_id: str
    stop_rule: str
    iterations: int
    api_calls: int
    stop_reason: str
    pylint_score: float
    final_weighted_score: int
    avg_complexity: Optional[float]
    max_complexity: Optional[int]
    maintainability_index: Optional[float]


def _float_or_none(raw: str) -> Optional[float]:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int_or_none(raw: str) -> Optional[int]:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _int_field(row: Dict[str, str], key: str, default: int = 0) -> int:
    val = row.get(key, "") or ""
    if val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _float_field(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    val = row.get(key, "") or ""
    if val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def load_fixed_cap_runs(runs_csv: Path) -> List[RunRow]:
    """Load rows from runs.csv where stop_rule matches fixed_cap (or normalized variant)."""
    runs: List[RunRow] = []
    if not runs_csv.exists():
        return runs
    with runs_csv.open(newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        for row in reader:
            stop_rule = (row.get("stop_rule", "") or "").strip().lower()
            if stop_rule not in ("fixedcap", "fixed-cap", "fixed_cap", STOP_RULE_FIXED_CAP):
                continue
            pylint = _float_field(row, "pylint_score")
            iters = _int_field(row, "iterations")
            api_calls = _int_field(row, "api_calls", default=iters)
            final_ws = _int_field(row, "final_weighted_score")
            sr = (row.get("stop_reason", "") or "").strip()
            runs.append(RunRow(
                prompt_id=(row.get("prompt_id", "") or "").strip(),
                stop_rule=stop_rule,
                iterations=iters,
                api_calls=api_calls,
                stop_reason=sr,
                pylint_score=pylint,
                final_weighted_score=final_ws,
                avg_complexity=_float_or_none(row.get("avg_complexity", "")),
                max_complexity=_int_or_none(row.get("max_complexity", "")),
                maintainability_index=_float_or_none(row.get("maintainability_index", "")),
            ))
    return runs


def load_iteration_issues(iterations_csv: Path) -> Tuple[Dict[str, DefaultDict[int, List[Tuple[str, str, str, str]]]], Dict[str, str]]:
    """Return (prompt_id -> {iteration -> list of (tool, severity, rule_id, message)},
               prompt_id -> prompt_label)

    Only per-issue rows from iterations.csv are loaded; no analysis rerun.
    """
    issues_by_prompt: Dict[str, DefaultDict[int, List[Tuple[str, str, str, str]]]] = defaultdict(lambda: defaultdict(list))
    label_by_prompt: Dict[str, str] = {}
    if not iterations_csv.exists():
        return issues_by_prompt, label_by_prompt
    with iterations_csv.open(newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        for row in reader:
            pid = (row.get("prompt_id", "") or "").strip()
            if not pid:
                continue
            label = (row.get("prompt_label", "") or "").strip()
            if label and pid not in label_by_prompt:
                label_by_prompt[pid] = label
            it_raw = (row.get("iteration", "") or "").strip()
            try:
                it_num = int(it_raw)
            except ValueError:
                continue
            tool = (row.get("tool", "") or "").strip()
            severity = (row.get("severity", "") or "").strip().upper()
            rule_id = (row.get("rule_id", "") or "").strip()
            message = (row.get("message", "") or "").strip()
            issues_by_prompt[pid][it_num].append((tool, severity, rule_id, message))
    return issues_by_prompt, label_by_prompt


def compute_weighted_score(issues: List[Tuple[str, str, str, str]]) -> int:
    """Compute weighted issue score from severity strings (same as loop_controller.weighted_issue_score)."""
    score = 0
    for _tool, severity, _rid, _msg in issues:
        sev = (severity or "").upper()
        score += SEVERITY_WEIGHTS.get(sev, DEFAULT_SEVERITY_WEIGHT)
    return score


def simulate_plateau_stop(
    per_iter_weighted: List[int],
    strikes_required: int,
) -> Tuple[int, int, int]:
    """Given weighted scores ordered by iteration (1-indexed in our reasoning),
    return (plateau_stop_iteration, best_weighted_seen_at_stop, strikes_at_stop).

    plateau_stop_iteration is the first iteration i (1-based, 1..len(per_iter_weighted))
    such that after processing iteration i, the number of consecutive non-improvements
    vs best-so-far equals strikes_required. If no such iteration exists within the
    provided window, plateau_stop_iteration = len(per_iter_weighted).
    """
    best = float("inf")
    strikes = 0
    stop_at = len(per_iter_weighted)
    best_at_stop = best
    strikes_at_stop = strikes
    for idx, ws in enumerate(per_iter_weighted, start=1):
        if ws < best:
            best = ws
            strikes = 0
        else:
            strikes += 1
        if strikes >= strikes_required and stop_at == len(per_iter_weighted):
            stop_at = idx
            best_at_stop = best
            strikes_at_stop = strikes
            break
    if stop_at == len(per_iter_weighted):
        best_at_stop = int(best) if best != float("inf") else 0
        strikes_at_stop = strikes
    return stop_at, int(best_at_stop) if isinstance(best_at_stop, float) else best_at_stop, strikes_at_stop


def summarize_quality(
    run: RunRow,
    per_iter_weighted: List[int],
    plateau_stop_iter: int,
) -> Dict[str, object]:
    """Build a quality summary comparing actual fixed-cap result vs plateau stop point.

    Quality retained is measured by comparing the plateau-simulated best-so-far weighted
    score against the final_weighted_score logged for the fixed_cap run. Lower weighted
    is better; 100% retained means plateau preserves at least as good a score as the
    run achieved (always true by construction when plateau stops on stuck runs).
    """
    actual_ws = run.final_weighted_score
    # Determine best weighted observed within iterations 1..plateau_stop_iter (inclusive)
    window_weighted = per_iter_weighted[:plateau_stop_iter] if plateau_stop_iter > 0 else []
    plateau_best_ws = min(window_weighted) if window_weighted else actual_ws
    # Retention: if plateau_best_ws <= actual_ws we retained 100% quality.
    # If somehow plateau missed a later improvement, ratio = actual_ws / plateau_best_ws (clamped).
    if plateau_best_ws <= 0 and actual_ws <= 0:
        retained_pct = 100.0
    elif plateau_best_ws <= 0:
        retained_pct = 100.0
    elif actual_ws <= 0:
        retained_pct = 100.0
    else:
        ratio = actual_ws / plateau_best_ws
        retained_pct = min(100.0, ratio * 100.0) if ratio > 0 else 100.0
    # pylint: use the run's logged pylint_score as proxy (we lack per-iter pylint in CSV)
    pylint_at_plateau = run.pylint_score
    return {
        "actual_weighted": actual_ws,
        "plateau_best_weighted": plateau_best_ws,
        "weighted_retained_pct": retained_pct,
        "plateau_window_weighted": window_weighted,
        "pylint_at_plateau": pylint_at_plateau,
        "pylint_final": run.pylint_score,
    }


def format_report_line(
    prompt_id: str,
    prompt_label: Optional[str],
    run: RunRow,
    plateau_stop_iter: int,
    strikes_at_stop: int,
    quality: Dict[str, object],
) -> str:
    label = prompt_label or "(no label)"
    actual_iters = run.iterations
    actual_calls = run.api_calls
    # Assumption: each iteration performs exactly 1 generation API call.
    # This matches LoopController semantics (1 _generate call per iteration).
    plateau_calls = max(1, plateau_stop_iter) if plateau_stop_iter > 0 else actual_calls
    calls_saved = max(0, actual_calls - plateau_calls)
    saved_pct = (100.0 * calls_saved / actual_calls) if actual_calls > 0 else 0.0

    actual_ws = int(quality["actual_weighted"])
    plat_ws = int(quality["plateau_best_weighted"])
    retained_pct = float(quality["weighted_retained_pct"])
    pylint_final = float(quality["pylint_final"])
    pylint_plat = float(quality["pylint_at_plateau"])

    radon_bits = []
    if run.avg_complexity is not None:
        radon_bits.append(f"CCavg={run.avg_complexity:.2f}")
    if run.max_complexity is not None:
        radon_bits.append(f"CCmax={run.max_complexity}")
    if run.maintainability_index is not None:
        radon_bits.append(f"MI={run.maintainability_index:.2f}")
    radon_str = (" | " + " | ".join(radon_bits)) if radon_bits else ""

    seq_weighted = " -> ".join(str(w) for w in quality["plateau_window_weighted"]) or "n/a"

    lines = []
    lines.append("")
    lines.append(f"Prompt [{label}] (prompt_id={prompt_id})")
    lines.append(f"  Actual  fixed-cap: {actual_iters} iterations, api_calls={actual_calls}, "
                 f"weighted={actual_ws}, pylint={pylint_final:.2f}{radon_str}, stop_reason={run.stop_reason or 'n/a'}")
    lines.append(f"  Plateau would stop: iteration {plateau_stop_iter} "
                 f"(strikes={strikes_at_stop}, strikes_required={PLATEAU_MIN_STRIKES}), "
                 f"api_calls_used={plateau_calls}, api_calls_saved={calls_saved} ({saved_pct:.0f}%)")
    lines.append(f"  Weighted sequence in plateau window: {seq_weighted}")
    lines.append(f"  Quality at plateau stop: weighted={plat_ws} (retained {retained_pct:.0f}% vs run final {actual_ws}), "
                 f"pylint={pylint_plat:.2f}")
    lines.append(f"  => Calls saved: {calls_saved}  |  Quality retained: {retained_pct:.0f}%")
    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay logged fixed-cap runs and report plateau-rule savings.",
    )
    parser.add_argument(
        "--runs-csv",
        type=Path,
        default=PROJECT_ROOT / "logs" / "runs.csv",
        help="Path to runs-level CSV (default: logs/runs.csv)",
    )
    parser.add_argument(
        "--iterations-csv",
        type=Path,
        default=PROJECT_ROOT / "logs" / "iterations.csv",
        help="Path to per-issue iterations CSV (default: logs/iterations.csv)",
    )
    parser.add_argument(
        "--strikes",
        type=int,
        default=PLATEAU_MIN_STRIKES,
        help=f"Consecutive non-improvement strikes needed to stop (default: {PLATEAU_MIN_STRIKES})",
    )
    parser.add_argument(
        "--prompt-id",
        type=str,
        default=None,
        help="If set, only replay the given prompt_id (from runs.csv)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    strikes = max(1, int(args.strikes))

    runs_csv: Path = args.runs_csv
    iters_csv: Path = args.iterations_csv

    runs = load_fixed_cap_runs(runs_csv)
    if not runs:
        print(f"No fixed_cap runs found in {runs_csv}")
        print(f"Expected stop_rule values: fixed_cap / fixed-cap / fixedcap")
        return 0
    if args.prompt_id:
        runs = [r for r in runs if r.prompt_id == args.prompt_id]
        if not runs:
            print(f"No fixed_cap run with prompt_id={args.prompt_id} found in {runs_csv}")
            return 0

    issues_by_pid, label_by_pid = load_iteration_issues(iters_csv)

    total_runs_considered = 0
    total_calls_saved_all_prompts = 0
    total_runs_actual_calls = 0

    print("=" * 78)
    print("PLATEAU REPLAY: simulating stop_rule=plateau on logged fixed-cap runs")
    print(f"  strikes_required = {strikes}")
    print(f"  runs_csv         = {runs_csv}")
    print(f"  iterations_csv   = {iters_csv}")
    print("=" * 78)

    for run in runs:
        pid = run.prompt_id
        if not pid:
            continue
        issues_by_iter = issues_by_pid.get(pid)
        if issues_by_iter is None or len(issues_by_iter) == 0:
            # No per-iteration data: we can't recompute weighted; fall back to assuming
            # a stuck run (identical weighted every iteration) and simulate from cap.
            # This case prints a warning and uses iteration count only.
            if run.iterations < strikes + 1:
                stop_it, plat_best, strikes_used = run.iterations, run.final_weighted_score, 0
            else:
                stop_it, plat_best, strikes_used = strikes + 1, run.final_weighted_score, strikes
            per_iter_ws_fallback: List[int] = [run.final_weighted_score] * run.iterations
            quality = summarize_quality(run, per_iter_ws_fallback, stop_it)
            label = label_by_pid.get(pid)
            total_runs_considered += 1
            total_runs_actual_calls += run.api_calls
            calls_saved_here = max(0, run.api_calls - max(1, stop_it))
            total_calls_saved_all_prompts += calls_saved_here
            print(format_report_line(pid, label, run, stop_it, strikes_used, quality))
            print(f"  [NOTE: no per-iteration issue rows found in {iters_csv.name} for this prompt_id; "
                  f"stuck-run assumption used.]")
            continue
        max_iter_logged = max(issues_by_iter.keys()) if issues_by_iter else 0
        actual_iters = run.iterations
        n_iters = max(actual_iters, max_iter_logged)
        per_iter_ws: List[int] = []
        for i in range(1, n_iters + 1):
            issues = issues_by_iter.get(i, [])
            per_iter_ws.append(compute_weighted_score(issues))
        stop_it, plat_best, strikes_used = simulate_plateau_stop(per_iter_ws, strikes_required=strikes)
        quality = summarize_quality(run, per_iter_ws, stop_it)
        label = label_by_pid.get(pid)
        total_runs_considered += 1
        total_runs_actual_calls += run.api_calls
        calls_saved_here = max(0, run.api_calls - max(1, stop_it))
        total_calls_saved_all_prompts += calls_saved_here
        print(format_report_line(pid, label, run, stop_it, strikes_used, quality))

    print("")
    print("=" * 78)
    print("AGGREGATE")
    print("=" * 78)
    print(f"  fixed-cap runs considered:  {total_runs_considered}")
    print(f"  total actual api_calls:     {total_runs_actual_calls}")
    print(f"  total api_calls_saved:      {total_calls_saved_all_prompts}")
    pct_all = (100.0 * total_calls_saved_all_prompts / total_runs_actual_calls) if total_runs_actual_calls > 0 else 0.0
    print(f"  aggregate savings pct:      {pct_all:.0f}%")
    print("")
    print("Done. No API calls made — replay is purely from logged CSVs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
