"""Standalone rule-level analysis.

Two modes:
  1. --run-eval: Runs the eval harness with an extended per-iteration logger
     (captures rule_ids per iteration WITHOUT modifying the main pipeline).
  2. Default (no flag): Reads existing runs.csv + iterations.csv/iterations.jsonl
     and reports per-rule_id reliability.

For each transition (iteration i -> i+1) within a run, every rule_id observed
in either side is classified as:
  - FIXED:      present at i, absent at i+1
  - UNCHANGED:  present at both i and i+1  (same rule_id, any line)
  - INTRODUCED: absent at i, present at i+1

These counts are aggregated by (feedback_mode, tool, rule_id) and also by
(feedback_mode, category), where category is a coarse roll-up of rule families.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig, STRATEGIES
from backend.app.eval_harness import EVAL_PROMPTS
from backend.app.llm_interface import LLMInterface
from backend.app.loop_controller import IterationData, LoopController, LoopResult
from backend.app.run_logger import RunLogger
from backend.app.static_analyzer import StaticAnalysisIssue


RUNS_CSV = PROJECT_ROOT / "logs" / "runs.csv"
ITERATIONS_CSV = PROJECT_ROOT / "logs" / "iterations.csv"
ITERATIONS_JSONL = PROJECT_ROOT / "logs" / "iterations.jsonl"
ANALYSIS_CSV = PROJECT_ROOT / "logs" / "rule_analysis.csv"
ANALYSIS_MD = PROJECT_ROOT / "logs" / "rule_analysis.md"


ITERATION_CSV_FIELDS = (
    "timestamp",
    "prompt_id",
    "prompt_label",
    "feedback_mode",
    "top_k",
    "stop_rule",
    "strategy",
    "temperature",
    "iteration_cap",
    "model",
    "iteration",
    "tool",
    "severity",
    "rule_id",
    "line",
    "message",
)


def _rule_category(tool: str, rule_id: str) -> str:
    """Coarse rule family used for the category-level aggregation."""
    rid = (rule_id or "").strip()
    t = (tool or "").lower()
    if t == "bandit":
        if rid.startswith("B1"):
            return "bandit:hardcoded_secrets"
        if rid.startswith("B2"):
            return "bandit:password_interaction"
        if rid.startswith("B3"):
            return "bandit:injection"
        if rid.startswith("B4"):
            return "bandit:cryptography"
        if rid.startswith("B5"):
            return "bandit:tls_ssl"
        if rid.startswith("B6"):
            return "bandit:shell_injection"
        if rid.startswith("B7"):
            return "bandit:templates"
        if rid.startswith("B10"):
            return "bandit:asserts"
        if rid.startswith("B11"):
            return "bandit:general"
        if rid.startswith("B12"):
            return "bandit:file_permissions"
        if rid.startswith("B15"):
            return "bandit:file_ownership"
        if rid.startswith("B20"):
            return "bandit:multiprocessing"
        if rid.startswith("B30"):
            return "bandit:input_output"
        if rid.startswith("B31"):
            return "bandit:crypto_password"
        if rid.startswith("B32"):
            return "bandit:hashlib"
        if rid.startswith("B40"):
            return "bandit:imports"
        if rid.startswith("B41"):
            return "bandit:ssl_wrapper"
        if rid.startswith("B50"):
            return "bandit:requests"
        if rid.startswith("B60"):
            return "bandit:subprocess_shell"
        if rid.startswith("B61"):
            return "bandit:paramiko"
        if rid.startswith("B70"):
            return "bandit:mako_templates"
        if rid.startswith("B101"):
            return "bandit:assert_usage"
        return "bandit:other"

    if t == "pylint":
        if rid.startswith("E0401") or rid.startswith("F0401") or rid in ("import-error", "unused-import"):
            return "pylint:imports"
        if rid == "W0611" or rid == "unused-import":
            return "pylint:unused_imports"
        if rid.startswith("C0") or rid.startswith("C01") or rid in (
            "missing-module-docstring",
            "missing-class-docstring",
            "missing-function-docstring",
            "invalid-name",
            "line-too-long",
            "wrong-import-order",
            "wrong-import-position",
        ):
            return "pylint:conventions_style"
        if rid.startswith("C03"):
            return "pylint:formatting"
        if rid.startswith("W03") or rid.startswith("W06"):
            return "pylint:warnings_unused"
        if rid.startswith("E06") or rid.startswith("E11"):
            return "pylint:errors_names"
        if rid.startswith("E01") or rid.startswith("E02") or rid.startswith("E03"):
            return "pylint:errors_runtime"
        if rid.startswith("R0") or rid in (
            "too-many-lines",
            "too-many-arguments",
            "too-many-locals",
            "too-many-branches",
            "too-many-statements",
            "duplicate-code",
        ):
            return "pylint:refactor_complexity"
        if rid.startswith("E00") or rid == "E0001" or rid == "syntax-error":
            return "pylint:syntax"
        return "pylint:other"

    if t == "python":
        return "python:syntax"
    return f"{t}:other"


# ---------------------------------------------------------------------------
# Extended logging (standalone — no modifications to backend/app/*).
# ---------------------------------------------------------------------------


class IterationLogger:
    """Append-only logger that writes per-iteration, per-issue rows.

    Completely standalone: it is not referenced from LoopController. The
    standalone runner below calls ``write_iterations`` after each
    LoopController.run() returns with the full LoopResult (which already
    carries IterationData.raw_issues in memory — see IterationData in
    loop_controller.py).
    """

    def __init__(
        self,
        csv_path: Path = ITERATIONS_CSV,
        jsonl_path: Path = ITERATIONS_JSONL,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.jsonl_path = Path(jsonl_path)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_csv_header(self) -> None:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with self.csv_path.open("w", newline="", encoding="utf-8") as h:
                writer = csv.DictWriter(h, fieldnames=ITERATION_CSV_FIELDS)
                writer.writeheader()

    def write_iterations(
        self,
        timestamp: str,
        prompt_id: str,
        prompt_label: str,
        config: ExperimentConfig,
        model: str,
        result: LoopResult,
    ) -> None:
        self._write_csv_header()

        with self.csv_path.open("a", newline="", encoding="utf-8") as csv_h, \
             self.jsonl_path.open("a", encoding="utf-8") as jsonl_h:
            writer = csv.DictWriter(csv_h, fieldnames=ITERATION_CSV_FIELDS)
            for it in result.iterations:
                issues: List[StaticAnalysisIssue] = list(it.raw_issues) or []
                for iss in issues:
                    row = {
                        "timestamp": timestamp,
                        "prompt_id": prompt_id,
                        "prompt_label": prompt_label,
                        "feedback_mode": config.feedback_mode,
                        "top_k": config.top_k,
                        "stop_rule": config.stop_rule,
                        "strategy": config.strategy,
                        "temperature": "" if config.temperature is None else config.temperature,
                        "iteration_cap": config.iteration_cap,
                        "model": model,
                        "iteration": it.iteration,
                        "tool": iss.tool,
                        "severity": iss.severity,
                        "rule_id": iss.rule_id,
                        "line": iss.line,
                        "message": (iss.message or "").replace("\r", " ").replace("\n", " ")[:500],
                    }
                    writer.writerow(row)
                    jsonl_h.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_extended_eval(
    strategies: Sequence[str] = STRATEGIES,
    prompts: Sequence[dict] = EVAL_PROMPTS,
    llm=None,
) -> List[LoopResult]:
    """Run the eval harness exactly like eval_harness.run_evaluation, but
    additionally persists per-iteration issue rule_ids via IterationLogger.

    This is the logging-extension the task asks for. It does **not** modify
    ``backend/app``: it uses the same public classes and wraps their output.
    """
    from dataclasses import replace
    from datetime import datetime, timezone
    from backend.app.run_logger import prompt_id_for

    run_logger = RunLogger()
    iter_logger = IterationLogger()
    engine = llm if llm is not None else LLMInterface()
    config_template = ExperimentConfig()
    results: List[LoopResult] = []

    for item in prompts:
        prompt_text = item["prompt"]
        prompt_label = item.get("id", "")
        pid = prompt_id_for(prompt_text)
        for strategy in strategies:
            cfg = replace(config_template, strategy=strategy)
            ts = datetime.now(timezone.utc).isoformat()
            controller = LoopController(config=cfg, llm=engine, run_logger=run_logger)
            print(f"\n>>> eval prompt={prompt_label!r} strategy={cfg.strategy} feedback={cfg.feedback_mode}")
            result = controller.run(prompt_text)
            raw_model = getattr(engine, "model_name", None)
            model_name = raw_model if isinstance(raw_model, str) else cfg.model
            iter_logger.write_iterations(
                timestamp=ts,
                prompt_id=pid,
                prompt_label=prompt_label,
                config=cfg,
                model=model_name,
                result=result,
            )
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Analysis layer — reads runs.csv + iterations.csv and produces the report.
# ---------------------------------------------------------------------------


@dataclass
class TransitionCounts:
    fixed: int = 0
    unchanged: int = 0
    introduced: int = 0

    @property
    def total(self) -> int:
        return self.fixed + self.unchanged + self.introduced

    @property
    def fix_rate(self) -> float:
        opportunities = self.fixed + self.unchanged
        if opportunities == 0:
            return 0.0
        return self.fixed / opportunities


def _read_iterations(iter_csv: Path) -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    """Return { (prompt_id, iteration, rule_id) -> row } plus run metadata."""
    if not iter_csv.exists():
        return {}
    rows: Dict[Tuple[str, int, int, str], Dict[str, Any]] = {}
    with iter_csv.open(newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        for row in reader:
            try:
                it = int(row["iteration"])
            except (TypeError, ValueError):
                continue
            key = (row["prompt_id"], hash(row.get("timestamp", "")), it, row["rule_id"])
            rows[key] = row
    return rows


def _group_iterations(iter_csv: Path) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    """Group per-issue rows by (prompt_id, timestamp, feedback_mode).

    Each group represents one LoopController.run() execution with its full
    iteration trail.
    """
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    if not iter_csv.exists():
        return groups
    with iter_csv.open(newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        for row in reader:
            key = (row["prompt_id"], row["timestamp"], row["feedback_mode"])
            groups[key].append(row)
    return groups


def _rule_ids_at(rows: Iterable[Dict[str, Any]], iteration: int) -> Set[Tuple[str, str, str]]:
    """Return {(tool, rule_id, category)} for the given iteration number."""
    s: Set[Tuple[str, str, str]] = set()
    for row in rows:
        try:
            it = int(row["iteration"])
        except (TypeError, ValueError):
            continue
        if it != iteration:
            continue
        tool = row.get("tool", "")
        rid = row.get("rule_id", "")
        s.add((tool, rid, _rule_category(tool, rid)))
    return s


def compute_rule_transitions(
    runs_csv: Path = RUNS_CSV,
    iter_csv: Path = ITERATIONS_CSV,
) -> Tuple[Dict[Tuple[str, str, str], TransitionCounts], Dict[Tuple[str, str], TransitionCounts]]:
    """Walk every (iteration i -> i+1) transition in every run and tally.

    Returns:
      by_rule:   {(feedback_mode, tool, rule_id) -> TransitionCounts}
      by_category: {(feedback_mode, category) -> TransitionCounts}
    """
    by_rule: Dict[Tuple[str, str, str], TransitionCounts] = defaultdict(TransitionCounts)
    by_category: Dict[Tuple[str, str], TransitionCounts] = defaultdict(TransitionCounts)

    groups = _group_iterations(iter_csv)
    for (_, _, feedback_mode), rows in groups.items():
        # discover iteration numbers used in this run
        its = sorted({int(r["iteration"]) for r in rows if r["iteration"].isdigit()})
        for i, j in zip(its[:-1], its[1:]):
            before = _rule_ids_at(rows, i)
            after = _rule_ids_at(rows, j)
            before_ids = {(t, r) for (t, r, _) in before}
            after_ids = {(t, r) for (t, r, _) in after}

            tool_by_rule = {t_r: t_r[0] for t_r in (before_ids | after_ids)}
            cat_by_rule = {
                (t, r): c for (t, r, c) in (before | after)
            }

            # fixed
            for t_r in before_ids - after_ids:
                tool, rid = t_r
                cat = cat_by_rule.get(t_r, _rule_category(tool, rid))
                by_rule[(feedback_mode, tool, rid)].fixed += 1
                by_category[(feedback_mode, cat)].fixed += 1
            # unchanged
            for t_r in before_ids & after_ids:
                tool, rid = t_r
                cat = cat_by_rule.get(t_r, _rule_category(tool, rid))
                by_rule[(feedback_mode, tool, rid)].unchanged += 1
                by_category[(feedback_mode, cat)].unchanged += 1
            # introduced
            for t_r in after_ids - before_ids:
                tool, rid = t_r
                cat = cat_by_rule.get(t_r, _rule_category(tool, rid))
                by_rule[(feedback_mode, tool, rid)].introduced += 1
                by_category[(feedback_mode, cat)].introduced += 1

    return by_rule, by_category


def write_analysis_outputs(
    by_rule: Dict[Tuple[str, str, str], TransitionCounts],
    by_category: Dict[Tuple[str, str], TransitionCounts],
    out_csv: Path = ANALYSIS_CSV,
    out_md: Path = ANALYSIS_MD,
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # --- CSV ---------------------------------------------------------------
    rows: List[Dict[str, Any]] = []
    for (feedback_mode, tool, rid), tc in sorted(by_rule.items()):
        rows.append({
            "level": "rule",
            "feedback_mode": feedback_mode,
            "tool": tool,
            "category": _rule_category(tool, rid),
            "rule_id": rid,
            "transitions": tc.total,
            "fixed": tc.fixed,
            "unchanged": tc.unchanged,
            "introduced": tc.introduced,
            "fix_rate": f"{tc.fix_rate:.3f}",
            "reliability": _reliability_label(tc),
        })
    for (feedback_mode, cat), tc in sorted(by_category.items()):
        tool = cat.split(":", 1)[0] if ":" in cat else ""
        rows.append({
            "level": "category",
            "feedback_mode": feedback_mode,
            "tool": tool,
            "category": cat,
            "rule_id": "",
            "transitions": tc.total,
            "fixed": tc.fixed,
            "unchanged": tc.unchanged,
            "introduced": tc.introduced,
            "fix_rate": f"{tc.fix_rate:.3f}",
            "reliability": _reliability_label(tc),
        })

    fieldnames = [
        "level", "feedback_mode", "tool", "category", "rule_id",
        "transitions", "fixed", "unchanged", "introduced",
        "fix_rate", "reliability",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # --- Markdown ---------------------------------------------------------
    md_lines: List[str] = []
    md_lines.append("# Rule-Level Fix Reliability Report")
    md_lines.append("")
    md_lines.append(
        "For each consecutive-iteration pair in every logged run, each `rule_id` "
        "is classified as **FIXED** (present → absent), **UNCHANGED** (present → present), "
        "or **INTRODUCED** (absent → present). `fix_rate = fixed / (fixed + unchanged)`."
    )
    md_lines.append("")

    # Summary: top reliably-fixed rules and top rules that are NOT fixed reliably.
    rule_rows = [r for r in rows if r["level"] == "rule" and r["transitions"] >= 1]
    fixed_reliably = sorted(
        [r for r in rule_rows if float(r["fix_rate"]) >= 0.7 and r["fixed"] >= 1],
        key=lambda r: (-float(r["fix_rate"]), -int(r["fixed"])),
    )
    not_fixed = sorted(
        [r for r in rule_rows if float(r["fix_rate"]) < 0.5 and (r["unchanged"] + r["introduced"]) >= 1],
        key=lambda r: (float(r["fix_rate"]), -(int(r["unchanged"]) + int(r["introduced"]))),
    )

    md_lines.append("## Summary: Rules fixed reliably vs. NOT fixed reliably")
    md_lines.append("")
    md_lines.append("### Fixed reliably (fix_rate ≥ 0.7)")
    md_lines.append("")
    if fixed_reliably:
        md_lines.append("| feedback_mode | tool | rule_id | category | fixed | unchanged | introduced | fix_rate |")
        md_lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
        for r in fixed_reliably:
            md_lines.append(
                f"| {r['feedback_mode']} | {r['tool']} | {r['rule_id']} | {r['category']} "
                f"| {r['fixed']} | {r['unchanged']} | {r['introduced']} | {r['fix_rate']} |"
            )
    else:
        md_lines.append("_No rule crossed the ≥0.7 fix_rate threshold in the available data._")
    md_lines.append("")

    md_lines.append("### NOT fixed reliably (fix_rate < 0.5)")
    md_lines.append("")
    if not_fixed:
        md_lines.append("| feedback_mode | tool | rule_id | category | fixed | unchanged | introduced | fix_rate |")
        md_lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
        for r in not_fixed:
            md_lines.append(
                f"| {r['feedback_mode']} | {r['tool']} | {r['rule_id']} | {r['category']} "
                f"| {r['fixed']} | {r['unchanged']} | {r['introduced']} | {r['fix_rate']} |"
            )
    else:
        md_lines.append("_Every observed rule had a fix_rate ≥ 0.5._")
    md_lines.append("")

    # Per feedback_mode: full rule table
    fbs = sorted({r["feedback_mode"] for r in rows if r["level"] == "rule"})
    md_lines.append("## Full tables per feedback_mode")
    md_lines.append("")
    for fb in fbs:
        md_lines.append(f"### feedback_mode = `{fb}` — Rule-level")
        md_lines.append("")
        md_lines.append(
            "| tool | rule_id | category | transitions | fixed | unchanged | introduced | fix_rate | reliability |"
        )
        md_lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        fb_rules = sorted(
            [r for r in rows if r["level"] == "rule" and r["feedback_mode"] == fb],
            key=lambda r: (-float(r["fix_rate"]), r["tool"], r["rule_id"]),
        )
        for r in fb_rules:
            md_lines.append(
                f"| {r['tool']} | {r['rule_id']} | {r['category']} | {r['transitions']} "
                f"| {r['fixed']} | {r['unchanged']} | {r['introduced']} "
                f"| {r['fix_rate']} | {r['reliability']} |"
            )
        md_lines.append("")

        md_lines.append(f"### feedback_mode = `{fb}` — Category-level")
        md_lines.append("")
        md_lines.append(
            "| tool | category | transitions | fixed | unchanged | introduced | fix_rate | reliability |"
        )
        md_lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        fb_cats = sorted(
            [r for r in rows if r["level"] == "category" and r["feedback_mode"] == fb],
            key=lambda r: (-float(r["fix_rate"]), r["category"]),
        )
        for r in fb_cats:
            md_lines.append(
                f"| {r['tool']} | {r['category']} | {r['transitions']} "
                f"| {r['fixed']} | {r['unchanged']} | {r['introduced']} "
                f"| {r['fix_rate']} | {r['reliability']} |"
            )
        md_lines.append("")

    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def _reliability_label(tc: TransitionCounts) -> str:
    if tc.total == 0:
        return "no_transitions"
    fr = tc.fix_rate
    if fr >= 0.7 and tc.fixed >= 1:
        return "FIXED_RELIABLY"
    if fr >= 0.4:
        return "mixed"
    if tc.introduced > tc.fixed + tc.unchanged:
        return "OFTEN_INTRODUCED"
    return "NOT_FIXED_RELIABLY"


# ---------------------------------------------------------------------------
# Seed: synthesize a iterations.csv so the report is demonstrable even before
# the real LLM eval is re-run. The seed data is only used when no real
# iterations.csv exists and --seed is passed.
# ---------------------------------------------------------------------------


def maybe_seed_demo_iterations(iter_csv: Path) -> bool:
    """Write a small, realistic iterations.csv if none exists yet.

    The goal is to exercise the analysis layer end-to-end: we make three runs
    (one per feedback_mode) and include rule families the task mentions
    (unused imports as the reliably-fixed example; B602, B105 as examples
    that are NOT fixed reliably).
    """
    if iter_csv.exists() and iter_csv.stat().st_size > 0:
        return False

    from datetime import datetime, timezone
    from hashlib import sha256

    rows: List[Dict[str, Any]] = []
    feedback_modes = ["detailed", "concise", "minimal"]
    now = datetime.now(timezone.utc).isoformat()

    scenarios = [
        ("p_add", "Write a Python function that adds two numbers.", {
            1: [("pylint", "WARNING", "W0611", 1, "Unused import os"),
                ("pylint", "CONVENTION", "missing-function-docstring", 3, "Missing docstring"),
                ("pylint", "CONVENTION", "C0103", 3, "Invalid name addNums"),
                ("bandit", "MEDIUM", "B105", 7, "Possible hardcoded password")],
            2: [("pylint", "CONVENTION", "missing-function-docstring", 3, "Missing docstring"),
                ("pylint", "CONVENTION", "C0103", 3, "Invalid name addNums"),
                ("bandit", "MEDIUM", "B105", 7, "Possible hardcoded password")],
            3: [("pylint", "CONVENTION", "missing-function-docstring", 3, "Missing docstring"),
                ("bandit", "MEDIUM", "B105", 5, "Possible hardcoded password")],
        }),
        ("p_exec", "Write execute_command(user_input) that runs math or a shell command.", {
            1: [("bandit", "HIGH", "B602", 5, "subprocess call with shell=True"),
                ("bandit", "LOW", "B404", 3, "import subprocess"),
                ("pylint", "ERROR", "E0602", 4, "Undefined variable 'out'"),
                ("pylint", "WARNING", "W0611", 1, "Unused import json")],
            2: [("bandit", "HIGH", "B602", 6, "subprocess call with shell=True"),
                ("bandit", "LOW", "B404", 3, "import subprocess"),
                ("pylint", "WARNING", "W0611", 1, "Unused import json")],
            3: [("bandit", "HIGH", "B602", 8, "subprocess call with shell=True"),
                ("bandit", "LOW", "B404", 3, "import subprocess"),
                ("pylint", "CONVENTION", "C0103", 2, "Invalid function name exec_cmd")],
        }),
        ("p_read", "Read a file at a user-supplied path and print the contents.", {
            1: [("pylint", "WARNING", "W0611", 1, "Unused import sys"),
                ("pylint", "CONVENTION", "C0103", 5, "Invalid name F"),
                ("bandit", "LOW", "B101", 10, "Use of assert detected"),
                ("pylint", "REFACTOR", "R0914", 2, "Too many local variables")],
            2: [("pylint", "CONVENTION", "C0103", 5, "Invalid name F"),
                ("bandit", "LOW", "B101", 10, "Use of assert detected"),
                ("pylint", "REFACTOR", "R0914", 2, "Too many local variables")],
            3: [("bandit", "LOW", "B101", 10, "Use of assert detected"),
                ("pylint", "REFACTOR", "R0914", 2, "Too many local variables")],
        }),
    ]

    for fb in feedback_modes:
        for label, prompt, iters in scenarios:
            pid = sha256(prompt.encode("utf-8")).hexdigest()[:12]
            for it_n, issues in iters.items():
                for (tool, sev, rid, line, msg) in issues:
                    rows.append({
                        "timestamp": now,
                        "prompt_id": pid,
                        "prompt_label": label,
                        "feedback_mode": fb,
                        "top_k": "5",
                        "stop_rule": "threshold",
                        "strategy": "loop",
                        "temperature": "",
                        "iteration_cap": "3",
                        "model": "seeded-demo",
                        "iteration": it_n,
                        "tool": tool,
                        "severity": sev,
                        "rule_id": rid,
                        "line": str(line),
                        "message": msg,
                    })

    iter_csv.parent.mkdir(parents=True, exist_ok=True)
    with iter_csv.open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=ITERATION_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return True


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-eval",
        action="store_true",
        help="Run the real eval harness (requires LLM credentials) and log per-iteration rule_ids.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="If no iterations.csv exists, seed a small synthetic dataset so the report is demo-able.",
    )
    parser.add_argument("--runs-csv", type=Path, default=RUNS_CSV)
    parser.add_argument("--iterations-csv", type=Path, default=ITERATIONS_CSV)
    parser.add_argument("--out-csv", type=Path, default=ANALYSIS_CSV)
    parser.add_argument("--out-md", type=Path, default=ANALYSIS_MD)
    args = parser.parse_args(argv)

    if args.run_eval:
        print("[rule_level_analysis] Running eval harness with extended iteration logging...")
        run_extended_eval()
    elif args.seed:
        wrote = maybe_seed_demo_iterations(args.iterations_csv)
        if wrote:
            print(f"[rule_level_analysis] Seeded demo data at {args.iterations_csv}.")
        else:
            print(f"[rule_level_analysis] {args.iterations_csv} already has data — no seed written.")

    if not args.iterations_csv.exists():
        sys.stderr.write(
            f"[rule_level_analysis] ERROR: no {args.iterations_csv}.\n"
            "  Pass --run-eval (needs LLM keys) or --seed to generate a demo report.\n"
        )
        sys.exit(1)

    print(f"[rule_level_analysis] Analyzing {args.runs_csv} + {args.iterations_csv} ...")
    by_rule, by_category = compute_rule_transitions(args.runs_csv, args.iterations_csv)
    write_analysis_outputs(by_rule, by_category, args.out_csv, args.out_md)
    print(f"[rule_level_analysis] Wrote {args.out_csv}")
    print(f"[rule_level_analysis] Wrote {args.out_md}")

    n_rules = sum(1 for tc in by_rule.values() if tc.total > 0)
    if n_rules:
        fixed_ok = [k for k, tc in by_rule.items() if tc.total and tc.fix_rate >= 0.7 and tc.fixed >= 1]
        not_ok = [k for k, tc in by_rule.items() if tc.total and tc.fix_rate < 0.5]
        print(f"[rule_level_analysis] Observed {n_rules} rule/feedback_mode combinations.")
        print(f"[rule_level_analysis] Fixed reliably (fix_rate>=0.7): {len(fixed_ok)}")
        for (fb, tool, rid) in fixed_ok:
            tc = by_rule[(fb, tool, rid)]
            print(f"   - [{fb}] {tool}:{rid}  fixed={tc.fixed} unchanged={tc.unchanged} introduced={tc.introduced}")
        print(f"[rule_level_analysis] NOT fixed reliably (fix_rate<0.5): {len(not_ok)}")
        for (fb, tool, rid) in not_ok:
            tc = by_rule[(fb, tool, rid)]
            print(f"   - [{fb}] {tool}:{rid}  fixed={tc.fixed} unchanged={tc.unchanged} introduced={tc.introduced}")


if __name__ == "__main__":
    main()
