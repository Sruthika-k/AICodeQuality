"""IssueExtractor component for deduplicating, sorting, and capping static analysis issues."""

import re
from typing import Any, Iterable, List, Optional, Set
from backend.app.static_analyzer import StaticAnalysisIssue, StaticAnalysisResult


class IssueExtractor:
    """Cleans StaticAnalyzer results: removes duplicates, sorts by severity, and caps count."""

    SEVERITY_WEIGHTS = {
        "FATAL": 50,
        "CRITICAL": 50,
        "HIGH": 40,
        "ERROR": 40,
        "MEDIUM": 30,
        "WARNING": 20,
        "LOW": 10,
        "REFACTOR": 10,
        "CONVENTION": 5,
        "INFO": 1,
    }

    def __init__(self, max_issues: int = 5, dedupe_semantic: bool = True):
        """Initialize IssueExtractor.

        Args:
            max_issues: Maximum number of issues to retain after sorting.
            dedupe_semantic: Whether to deduplicate overlapping findings on the same line.
        """
        self.max_issues = max_issues
        self.dedupe_semantic = dedupe_semantic

    def get_severity_weight(self, severity: str) -> int:
        """Return numerical weight for a severity string."""
        return self.SEVERITY_WEIGHTS.get(severity.upper(), 0)

    def extract(self, results: Any) -> List[StaticAnalysisIssue]:
        """Extract, deduplicate, sort by severity, and cap issues.

        Args:
            results: StaticAnalysisResult, list of StaticAnalysisIssue, or iterable of issues.

        Returns:
            List of prioritized, cleaned StaticAnalysisIssue instances.
        """
        if results is None:
            return []

        # Extract issues list if passed StaticAnalysisResult or dict
        if isinstance(results, StaticAnalysisResult):
            raw_issues = list(results.issues)
        elif isinstance(results, dict) and "issues" in results:
            raw_issues = results["issues"]
        elif isinstance(results, Iterable) and not isinstance(results, (str, bytes)):
            raw_issues = list(results)
        else:
            return []

        # Convert any raw dicts to StaticAnalysisIssue instances
        normalized_issues: List[StaticAnalysisIssue] = []
        for item in raw_issues:
            if isinstance(item, StaticAnalysisIssue):
                normalized_issues.append(item)
            elif isinstance(item, dict):
                normalized_issues.append(
                    StaticAnalysisIssue(
                        tool=item.get("tool", "unknown"),
                        severity=str(item.get("severity", "LOW")).upper(),
                        line=int(item.get("line", 1)),
                        message=str(item.get("message", "")),
                        rule_id=str(item.get("rule_id", "")),
                    )
                )

        # Sort by severity descending, then line number ascending
        sorted_issues = sorted(
            normalized_issues,
            key=lambda issue: (-self.get_severity_weight(issue.severity), issue.line, issue.rule_id),
        )

        # Deduplicate
        deduped_issues: List[StaticAnalysisIssue] = []
        seen_exact_keys: Set[str] = set()
        seen_line_topics: Set[str] = set()

        for issue in sorted_issues:
            exact_key = f"{issue.tool}:{issue.rule_id}:{issue.line}"
            if exact_key in seen_exact_keys:
                continue

            if self.dedupe_semantic:
                # Identify key topic (e.g. eval, subprocess, shell, docstring)
                topic = self._extract_topic(issue)
                topic_key = f"{issue.line}:{topic}" if topic else None

                if topic_key and topic_key in seen_line_topics:
                    # Skip lower-severity duplicate on same line
                    continue

                if topic_key:
                    seen_line_topics.add(topic_key)

            seen_exact_keys.add(exact_key)
            deduped_issues.append(issue)

        # Cap the count
        return deduped_issues[: self.max_issues]

    def _extract_topic(self, issue: StaticAnalysisIssue) -> Optional[str]:
        """Extract a topic signature to detect overlapping findings on the same line."""
        text = f"{issue.rule_id} {issue.message}".lower()
        if "eval" in text:
            return "eval"
        if "subprocess" in text or "shell=true" in text or "process with a shell" in text or "b602" in text or "b605" in text:
            return "shell_exec"
        if "docstring" in text:
            return "docstring"
        if "syntax" in text:
            return "syntax"
        return None
