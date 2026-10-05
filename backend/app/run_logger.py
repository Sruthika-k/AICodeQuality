"""Append-only CSV logger for experiment runs."""

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from backend.app.config import ExperimentConfig
from backend.app.static_analyzer import StaticAnalysisIssue

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CSV_PATH = PROJECT_ROOT / "logs" / "runs.csv"

SEVERITY_COLUMNS = (
    "issues_high",
    "issues_medium",
    "issues_low",
    "issues_error",
    "issues_warning",
    "issues_convention",
    "issues_refactor",
    "issues_other",
)

CSV_FIELDS = (
    "timestamp",
    "prompt_id",
    "feedback_mode",
    "top_k",
    "stop_rule",
    "strategy",
    "temperature",
    "iteration_cap",
    "pylint_threshold",
    "max_bandit_high_med",
    "model",
    "iterations",
    *SEVERITY_COLUMNS,
    "pylint_score",
    "rejected_iterations",
    "api_calls",
)


def prompt_id_for(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def count_issues_by_severity(issues: Iterable[StaticAnalysisIssue]) -> Dict[str, int]:
    counts = {key: 0 for key in SEVERITY_COLUMNS}
    for issue in issues:
        severity = (issue.severity or "").upper()
        if severity == "HIGH":
            counts["issues_high"] += 1
        elif severity == "MEDIUM":
            counts["issues_medium"] += 1
        elif severity == "LOW":
            counts["issues_low"] += 1
        elif severity == "ERROR":
            counts["issues_error"] += 1
        elif severity == "WARNING":
            counts["issues_warning"] += 1
        elif severity == "CONVENTION":
            counts["issues_convention"] += 1
        elif severity == "REFACTOR":
            counts["issues_refactor"] += 1
        else:
            counts["issues_other"] += 1
    return counts


class RunLogger:
    """Writes one CSV row per completed LoopController run."""

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH

    def log_run(
        self,
        prompt: str,
        config: ExperimentConfig,
        model: str,
        iterations: int,
        issues: Iterable[StaticAnalysisIssue],
        pylint_score: float,
        rejected_iterations: int,
        api_calls: int,
    ) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        row: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_id": prompt_id_for(prompt),
            "feedback_mode": config.feedback_mode,
            "top_k": config.top_k,
            "stop_rule": config.stop_rule,
            "strategy": config.strategy,
            "temperature": "" if config.temperature is None else config.temperature,
            "iteration_cap": config.iteration_cap,
            "pylint_threshold": config.pylint_threshold,
            "max_bandit_high_med": config.max_bandit_high_med,
            "model": model,
            "iterations": iterations,
            "pylint_score": pylint_score,
            "rejected_iterations": rejected_iterations,
            "api_calls": api_calls,
        }
        row.update(count_issues_by_severity(issues))

        write_header = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
