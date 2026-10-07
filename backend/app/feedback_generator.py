"""FeedbackGenerator component converting diagnostic issues into clear LLM prompt instructions."""

from typing import Any, Iterable, List, Optional, Set, Tuple
from backend.app.static_analyzer import StaticAnalysisIssue


class FeedbackGenerator:
    """Formats static analysis findings into concise, plain-text instructions for LLM repair."""

    DEFAULT_SUGGESTIONS = {
        "B307": "Avoid eval(); use ast.literal_eval() for safe literal evaluation or parse inputs explicitly.",
        "W0123": "Avoid eval(); use ast.literal_eval() or safe alternatives.",
        "B605": "Avoid os.system(); use subprocess.run() passing command and arguments as a list with shell=False.",
        "B602": "Remove shell=True and pass command arguments as a list to subprocess functions.",
        "B607": "Provide the full absolute path to the executable when invoking subprocesses.",
        "B404": "Ensure all subprocess command arguments are validated and not constructed from raw inputs.",
        "B101": "Avoid assert in production logic; raise explicit exceptions (e.g. ValueError).",
        "B105": "Hardcoded password string detected; load secrets from environment variables.",
        "B106": "Hardcoded password argument detected; load secrets from environment variables.",
        "B107": "Hardcoded password default detected; load secrets from environment variables.",
        "B108": "Avoid hardcoded /tmp directory paths; use tempfile.NamedTemporaryFile.",
        "C0114": "Add a descriptive docstring at the top of the module.",
        "C0115": "Add a docstring explaining the purpose of the class.",
        "C0116": "Add a docstring explaining the function's purpose, arguments, and return value.",
        "C0301": "Shorten the line to under 100 characters.",
        "C0103": "Rename identifier to comply with standard snake_case naming conventions.",
        "W0611": "Remove the unused import statement.",
        "W0612": "Remove the unused local variable or prefix it with an underscore.",
        "W0613": "Remove the unused argument or prefix it with an underscore.",
        "E0001": "Fix the syntax error to ensure valid Python syntax.",
        "E9999": "Fix the syntax error to ensure valid Python syntax.",
    }

    def _e1_rule_key(self, issue: StaticAnalysisIssue) -> Tuple[str, str]:
        """Return the E1 equivalence-class key: (tool, rule_id)."""
        return (issue.tool or "", issue.rule_id or "")

    def _e1_keys(self, issues: Iterable[StaticAnalysisIssue]) -> Set[Tuple[str, str]]:
        return {self._e1_rule_key(issue) for issue in issues}

    def compute_e1_diff(
        self,
        previous_issues: Iterable[StaticAnalysisIssue],
        current_issues: Iterable[StaticAnalysisIssue],
    ) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
        """Compute E1 rule transitions between two iteration snapshots.

        Returns (fixed_keys, introduced_keys, unchanged_keys) where each key
        is a (tool, rule_id) tuple (E1 equivalence class).
        """
        prev_keys = self._e1_keys(previous_issues)
        curr_keys = self._e1_keys(current_issues)
        fixed = prev_keys - curr_keys
        introduced = curr_keys - prev_keys
        unchanged = prev_keys & curr_keys
        return fixed, introduced, unchanged

    def get_fix_action(self, issue: StaticAnalysisIssue) -> str:
        """Provide a concise remediation action based on the rule or message."""
        rule = issue.rule_id.upper()
        if rule in self.DEFAULT_SUGGESTIONS:
            return self.DEFAULT_SUGGESTIONS[rule]

        msg_lower = issue.message.lower()
        if "eval" in msg_lower:
            return "Avoid eval(); use safe parsing or ast.literal_eval()."
        if "shell" in msg_lower or "subprocess" in msg_lower:
            return "Avoid shell=True or os.system; use subprocess.run() with arguments as a list."
        if "docstring" in msg_lower:
            return "Add appropriate docstrings describing functionality."
        if "syntax" in msg_lower:
            return "Correct the invalid Python syntax."
        if "unused" in msg_lower:
            return "Remove the unused identifier."

        return f"Refactor code to fix this {issue.severity.lower()} issue."

    def _format_key_list(self, keys: Set[Tuple[str, str]]) -> str:
        if not keys:
            return "(none)"
        parts = []
        for tool, rid in sorted(keys):
            label = f"{tool}:{rid}" if tool else rid
            parts.append(label)
        return ", ".join(parts)

    def generate_feedback(
        self,
        issues: Iterable[StaticAnalysisIssue],
        mode: str = "detailed",
        previous_issues: Optional[Iterable[StaticAnalysisIssue]] = None,
        previous_rejected: bool = False,
        current_all_issues: Optional[Iterable[StaticAnalysisIssue]] = None,
    ) -> str:
        """Generate a short plain-text instruction for the LLM.

        Args:
            issues: An ordered collection of prioritized StaticAnalysisIssue instances
                (already extracted / sorted / capped by top_k).
            mode: Feedback verbosity / style. Supported: ``detailed`` (default),
                ``minimal``, ``concise``, ``structured``, and ``regression_aware``.
            previous_issues: Full issue set from the prior iteration (E1 baseline).
                Required by ``regression_aware`` mode when available.
            previous_rejected: True if the prior iteration did not satisfy the
                convergence thresholds (was "rejected"). Used by
                ``regression_aware`` to decide whether to include regression
                preamble.
            current_all_issues: Full (uncapped) issue set from the current
                iteration. Used by ``regression_aware`` for E1 diff so
                introduced/fixed counts reflect *all* rules, not just the
                top-k prioritized subset.

        Returns:
            A concise, plain-text instruction covering what's wrong, which line, and what to fix.
        """
        issue_list = list(issues) if issues else []
        full_current = list(current_all_issues) if current_all_issues is not None else issue_list

        if not issue_list:
            return "No issues detected. Code meets all quality and security criteria."

        if mode == "regression_aware":
            lines: List[str] = []
            prev_list = list(previous_issues) if previous_issues is not None else []
            has_prev = len(prev_list) > 0
            fixed_keys: Set[Tuple[str, str]] = set()
            introduced_keys: Set[Tuple[str, str]] = set()
            if has_prev:
                fixed_keys, introduced_keys, _ = self.compute_e1_diff(prev_list, full_current)

            triggered = previous_rejected or len(introduced_keys) > 0

            if triggered and has_prev:
                lines.append("Regression-aware repair instructions for the last code change:")
                lines.append("")
                if fixed_keys:
                    lines.append(
                        f"PRESERVE these fixes from the last iteration (do NOT reintroduce them): "
                        f"{self._format_key_list(fixed_keys)}."
                    )
                else:
                    lines.append(
                        "PRESERVE: No new rule fixes were achieved in the last iteration."
                    )
                if introduced_keys:
                    lines.append(
                        f"FIX the regressions (newly introduced rules) from the last iteration: "
                        f"{self._format_key_list(introduced_keys)}."
                    )
                else:
                    lines.append(
                        "REGRESSIONS: No new rules were introduced by the last iteration."
                    )
                lines.append("")
                lines.append(
                    "IMPORTANT: Do NOT reintroduce any previously resolved issues. "
                    "Keep all fixes that were already working, and focus on removing "
                    "the newly introduced issues plus the remaining prioritized issues below."
                )
                lines.append("")
                lines.append(
                    f"Remaining {len(issue_list)} prioritized issues to fix (ordered by severity):"
                )
            else:
                lines.append(
                    f"Fix the following {len(issue_list)} code quality and security issues (ordered by severity):"
                )
            lines.append("")

            for idx, issue in enumerate(issue_list, start=1):
                rule_str = f" ({issue.rule_id})" if issue.rule_id else ""
                lines.append(f"{idx}. [{issue.severity}] Line {issue.line}{rule_str}: {issue.message}")
                action = self.get_fix_action(issue)
                lines.append(f"   What to fix: {action}")
                lines.append("")

            lines.append(
                "Provide the revised Python code that resolves all issues while "
                "preserving intended functionality and without regressing prior fixes."
            )
            return "\n".join(lines).strip()

        if mode == "minimal":
            items = ", ".join(
                f"{issue.rule_id or issue.severity}@{issue.line}" for issue in issue_list
            )
            return f"Fix issues: {items}."

        if mode == "concise":
            lines = [f"Fix {len(issue_list)} issues:"]
            for issue in issue_list:
                rule_str = f" {issue.rule_id}" if issue.rule_id else ""
                lines.append(f"- L{issue.line}{rule_str}: {issue.message}")
            return "\n".join(lines)

        if mode == "structured":
            lines = ["Issues:"]
            for issue in issue_list:
                lines.append(
                    f"- severity={issue.severity} line={issue.line} "
                    f"rule={issue.rule_id} message={issue.message} "
                    f"fix={self.get_fix_action(issue)}"
                )
            return "\n".join(lines)

        lines = [
            f"Fix the following {len(issue_list)} code quality and security issues (ordered by severity):",
            "",
        ]

        for idx, issue in enumerate(issue_list, start=1):
            rule_str = f" ({issue.rule_id})" if issue.rule_id else ""
            lines.append(f"{idx}. [{issue.severity}] Line {issue.line}{rule_str}: {issue.message}")
            action = self.get_fix_action(issue)
            lines.append(f"   What to fix: {action}")
            lines.append("")

        lines.append("Provide the revised Python code that resolves all issues while preserving intended functionality.")
        return "\n".join(lines).strip()
