"""MetricsTracker component recording iteration metrics and producing before/after quality comparisons."""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.static_analyzer import StaticAnalysisIssue


@dataclass
class IterationMetrics:
    """Detailed metrics captured for a single loop iteration."""

    iteration: int
    pylint_score: float
    total_issues: int
    counts_by_tool: Dict[str, int]
    counts_by_tool_and_severity: Dict[str, Dict[str, int]]
    threshold_met: bool
    has_syntax_error: bool
    avg_complexity: Optional[float] = None
    max_complexity: Optional[int] = None
    maintainability_index: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "pylint_score": self.pylint_score,
            "total_issues": self.total_issues,
            "counts_by_tool": self.counts_by_tool,
            "counts_by_tool_and_severity": self.counts_by_tool_and_severity,
            "threshold_met": self.threshold_met,
            "has_syntax_error": self.has_syntax_error,
            "avg_complexity": self.avg_complexity,
            "max_complexity": self.max_complexity,
            "maintainability_index": self.maintainability_index,
            "timestamp": self.timestamp,
        }


@dataclass
class BeforeAfterSummary:
    """Comparison of quality metrics between the initial (before) and final (after) iterations."""

    initial_iteration: int
    final_iteration: int
    total_iterations: int
    converged: bool
    initial_pylint_score: float
    final_pylint_score: float
    pylint_score_delta: float
    initial_total_issues: int
    final_total_issues: int
    issues_eliminated: int
    initial_metrics: IterationMetrics
    final_metrics: IterationMetrics
    table: str
    initial_avg_complexity: Optional[float] = None
    final_avg_complexity: Optional[float] = None
    initial_max_complexity: Optional[int] = None
    final_max_complexity: Optional[int] = None
    initial_maintainability_index: Optional[float] = None
    final_maintainability_index: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_iteration": self.initial_iteration,
            "final_iteration": self.final_iteration,
            "total_iterations": self.total_iterations,
            "converged": self.converged,
            "initial_pylint_score": self.initial_pylint_score,
            "final_pylint_score": self.final_pylint_score,
            "pylint_score_delta": self.pylint_score_delta,
            "initial_total_issues": self.initial_total_issues,
            "final_total_issues": self.final_total_issues,
            "issues_eliminated": self.issues_eliminated,
            "initial_metrics": self.initial_metrics.to_dict(),
            "final_metrics": self.final_metrics.to_dict(),
            "table": self.table,
            "initial_avg_complexity": self.initial_avg_complexity,
            "final_avg_complexity": self.final_avg_complexity,
            "initial_max_complexity": self.initial_max_complexity,
            "final_max_complexity": self.final_max_complexity,
            "initial_maintainability_index": self.initial_maintainability_index,
            "final_maintainability_index": self.final_maintainability_index,
        }


class MetricsTracker:
    """In-memory tracker for iteration issue counts by tool and severity, scores, and comparisons."""

    def __init__(self):
        # In-memory only storage
        self.history: List[IterationMetrics] = []

    def record(
        self,
        iteration: int,
        issues: List[StaticAnalysisIssue],
        pylint_score: Optional[float],
        threshold_met: bool,
        has_syntax_error: bool = False,
        avg_complexity: Optional[float] = None,
        max_complexity: Optional[int] = None,
        maintainability_index: Optional[float] = None,
    ) -> IterationMetrics:
        """Record issue counts by tool and severity, Pylint score, and iteration number.

        Args:
            iteration: Current iteration number.
            issues: List of StaticAnalysisIssue instances from analysis.
            pylint_score: Pylint score (0.0 to 10.0).
            threshold_met: Whether quality threshold was satisfied.
            has_syntax_error: Whether a syntax error occurred.
            avg_complexity: Average cyclomatic complexity from Radon.
            max_complexity: Maximum cyclomatic complexity from Radon.
            maintainability_index: Maintainability index from Radon.

        Returns:
            The created IterationMetrics entry.
        """
        score = round(pylint_score if pylint_score is not None else 0.0, 2)

        counts_by_tool: Dict[str, int] = {}
        counts_by_tool_and_severity: Dict[str, Dict[str, int]] = {}

        for issue in issues:
            tool = issue.tool.lower()
            severity = issue.severity.upper()

            # Tool counts
            counts_by_tool[tool] = counts_by_tool.get(tool, 0) + 1

            # Tool + Severity counts
            if tool not in counts_by_tool_and_severity:
                counts_by_tool_and_severity[tool] = {}
            counts_by_tool_and_severity[tool][severity] = (
                counts_by_tool_and_severity[tool].get(severity, 0) + 1
            )

        metric = IterationMetrics(
            iteration=iteration,
            pylint_score=score,
            total_issues=len(issues),
            counts_by_tool=counts_by_tool,
            counts_by_tool_and_severity=counts_by_tool_and_severity,
            threshold_met=threshold_met,
            has_syntax_error=has_syntax_error,
            avg_complexity=avg_complexity,
            max_complexity=max_complexity,
            maintainability_index=maintainability_index,
        )
        self.history.append(metric)
        return metric

    def get_before_after_summary(self, converged: bool) -> BeforeAfterSummary:
        """Produce a before/after quality comparison between the initial and final iterations."""
        if not self.history:
            dummy_metric = IterationMetrics(
                iteration=0,
                pylint_score=0.0,
                total_issues=0,
                counts_by_tool={},
                counts_by_tool_and_severity={},
                threshold_met=False,
                has_syntax_error=False,
                avg_complexity=None,
                max_complexity=None,
                maintainability_index=None,
            )
            return BeforeAfterSummary(
                initial_iteration=0,
                final_iteration=0,
                total_iterations=0,
                converged=converged,
                initial_pylint_score=0.0,
                final_pylint_score=0.0,
                pylint_score_delta=0.0,
                initial_total_issues=0,
                final_total_issues=0,
                issues_eliminated=0,
                initial_metrics=dummy_metric,
                final_metrics=dummy_metric,
                table="No iteration metrics recorded.",
            )

        initial = self.history[0]
        final = self.history[-1]

        score_delta = round(final.pylint_score - initial.pylint_score, 2)
        issues_eliminated = initial.total_issues - final.total_issues

        table_str = self.format_before_after_table(converged=converged)

        return BeforeAfterSummary(
            initial_iteration=initial.iteration,
            final_iteration=final.iteration,
            total_iterations=len(self.history),
            converged=converged,
            initial_pylint_score=initial.pylint_score,
            final_pylint_score=final.pylint_score,
            pylint_score_delta=score_delta,
            initial_total_issues=initial.total_issues,
            final_total_issues=final.total_issues,
            issues_eliminated=issues_eliminated,
            initial_metrics=initial,
            final_metrics=final,
            table=table_str,
            initial_avg_complexity=initial.avg_complexity,
            final_avg_complexity=final.avg_complexity,
            initial_max_complexity=initial.max_complexity,
            final_max_complexity=final.max_complexity,
            initial_maintainability_index=initial.maintainability_index,
            final_maintainability_index=final.maintainability_index,
        )

    def format_before_after_table(self, converged: Optional[bool] = None) -> str:
        """Format an aligned before/after comparison table as a clean string."""
        if not self.history:
            return "No metrics history available."

        initial = self.history[0]
        final = self.history[-1]

        # Helper to safely extract severity counts
        def get_count(m: IterationMetrics, tool: str, severity: str) -> int:
            return m.counts_by_tool_and_severity.get(tool.lower(), {}).get(severity.upper(), 0)

        # Helper to compute delta string
        def fmt_delta_int(before: int, after: int) -> str:
            d = after - before
            return f"{d:+d}" if d != 0 else "0"

        def fmt_delta_float(before: float, after: float) -> str:
            d = round(after - before, 2)
            return f"{d:+.2f}" if d != 0 else "0.00"

        rows = []

        # 1. Pylint Score
        rows.append(
            (
                "Pylint Score",
                f"{initial.pylint_score:.2f} / 10.0",
                f"{final.pylint_score:.2f} / 10.0",
                fmt_delta_float(initial.pylint_score, final.pylint_score),
            )
        )

        # 2. Bandit by severity
        for sev in ("HIGH", "MEDIUM", "LOW"):
            b_cnt = get_count(initial, "bandit", sev)
            a_cnt = get_count(final, "bandit", sev)
            rows.append(
                (
                    f"Bandit {sev.capitalize()} Issues",
                    str(b_cnt),
                    str(a_cnt),
                    fmt_delta_int(b_cnt, a_cnt),
                )
            )

        # 3. Pylint by severity
        for sev in ("ERROR", "WARNING", "CONVENTION", "REFACTOR"):
            b_cnt = get_count(initial, "pylint", sev)
            a_cnt = get_count(final, "pylint", sev)
            if b_cnt > 0 or a_cnt > 0 or sev in ("ERROR", "WARNING", "CONVENTION"):
                rows.append(
                    (
                        f"Pylint {sev.capitalize()}s",
                        str(b_cnt),
                        str(a_cnt),
                        fmt_delta_int(b_cnt, a_cnt),
                    )
                )

        # 4. Total Issues
        rows.append(
            (
                "Total Issues Count",
                str(initial.total_issues),
                str(final.total_issues),
                fmt_delta_int(initial.total_issues, final.total_issues),
            )
        )

        # 5. Complexity Metrics
        if initial.avg_complexity is not None and final.avg_complexity is not None:
            rows.append(
                (
                    "Avg Cyclomatic Complexity",
                    f"{initial.avg_complexity:.2f}",
                    f"{final.avg_complexity:.2f}",
                    fmt_delta_float(initial.avg_complexity, final.avg_complexity),
                )
            )
        if initial.max_complexity is not None and final.max_complexity is not None:
            rows.append(
                (
                    "Max Cyclomatic Complexity",
                    str(initial.max_complexity),
                    str(final.max_complexity),
                    fmt_delta_int(initial.max_complexity, final.max_complexity),
                )
            )

        # 6. Maintainability Index
        if initial.maintainability_index is not None and final.maintainability_index is not None:
            rows.append(
                (
                    "Maintainability Index (Debt Score)",
                    f"{initial.maintainability_index:.2f}",
                    f"{final.maintainability_index:.2f}",
                    fmt_delta_float(initial.maintainability_index, final.maintainability_index),
                )
            )

        # 7. Threshold Satisfaction
        init_status = "YES" if initial.threshold_met else "NO"
        final_status = "YES" if final.threshold_met else "NO"
        change_status = "PASSED" if final.threshold_met else ("IMPROVED" if final.pylint_score > initial.pylint_score else "UNCHANGED")
        rows.append(
            (
                "Threshold Satisfied (Bandit H/M=0 & Pylint>=8)",
                init_status,
                final_status,
                change_status,
            )
        )

        # Render Table
        col1_w = 46
        col2_w = 18
        col3_w = 18
        col4_w = 12

        sep_line = f"+{'-' * (col1_w + 2)}+{'-' * (col2_w + 2)}+{'-' * (col3_w + 2)}+{'-' * (col4_w + 2)}+"
        hdr_sep = f"+{'=' * (col1_w + 2)}+{'=' * (col2_w + 2)}+{'=' * (col3_w + 2)}+{'=' * (col4_w + 2)}+"

        iter_b_label = f"Before (Iter {initial.iteration})"
        iter_a_label = f"After (Iter {final.iteration})"

        lines = [
            hdr_sep,
            f"| {'BEFORE / AFTER QUALITY SUMMARY':^{col1_w + col2_w + col3_w + col4_w + 8}} |",
            hdr_sep,
            f"| {'Metric':<{col1_w}} | {iter_b_label:^{col2_w}} | {iter_a_label:^{col3_w}} | {'Change':^{col4_w}} |",
            sep_line,
        ]

        for metric, before, after, change in rows:
            lines.append(
                f"| {metric:<{col1_w}} | {before:^{col2_w}} | {after:^{col3_w}} | {change:^{col4_w}} |"
            )

        lines.append(hdr_sep)
        return "\n".join(lines)

    def reset(self) -> None:
        """Clear the in-memory history."""
        self.history.clear()
