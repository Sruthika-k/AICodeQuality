"""Static analyzer module integrating Bandit, Pylint, and Radon."""

import ast
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, List, Optional

import radon.complexity as radon_cc
import radon.metrics as radon_mi


@dataclass
class StaticAnalysisIssue:
    """Represents a standardized issue reported by a static analysis tool."""

    tool: str
    severity: str
    line: int
    message: str
    rule_id: str

    def __iter__(self):
        """Allow unpacking as a 5-tuple: (tool, severity, line, message, rule_id)."""
        return iter((self.tool, self.severity, self.line, self.message, self.rule_id))

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
            "rule_id": self.rule_id,
        }


class StaticAnalysisResult(list):
    """List of StaticAnalysisIssue with additional diagnostic metadata."""

    def __init__(
        self,
        issues: Optional[List[StaticAnalysisIssue]] = None,
        pylint_score: Optional[float] = None,
        has_syntax_error: bool = False,
        errors: Optional[List[str]] = None,
        avg_complexity: Optional[float] = None,
        max_complexity: Optional[int] = None,
        maintainability_index: Optional[float] = None,
    ):
        issues_list = issues or []
        super().__init__(issues_list)
        self.issues = issues_list
        self.pylint_score = pylint_score
        self.has_syntax_error = has_syntax_error
        self.errors = errors or []
        self.avg_complexity = avg_complexity
        self.max_complexity = max_complexity
        self.maintainability_index = maintainability_index

    def to_dict(self) -> dict:
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "pylint_score": self.pylint_score,
            "has_syntax_error": self.has_syntax_error,
            "errors": self.errors,
            "avg_complexity": self.avg_complexity,
            "max_complexity": self.max_complexity,
            "maintainability_index": self.maintainability_index,
        }


class StaticAnalyzer:
    """Runs Bandit and Pylint on Python source code and returns consistent issues."""

    def __init__(self, python_executable: Optional[str] = None, timeout_seconds: int = 30):
        self.python_executable = python_executable or sys.executable
        self.timeout_seconds = timeout_seconds

    def analyze(self, source_code: str, enable_radon: bool = False) -> StaticAnalysisResult:
        """Analyze Python source string with Bandit and Pylint.

        Args:
            source_code: Python source code to analyze.
            enable_radon: When True, also run Radon to compute cyclomatic
                complexity (avg/max) and maintainability index. Defaults to
                False: Radon is skipped entirely, keeping the call lightweight.

        Returns:
            StaticAnalysisResult holding issues and quality metadata.
        """
        issues: List[StaticAnalysisIssue] = []
        execution_errors: List[str] = []
        has_syntax_error = False
        pylint_score: Optional[float] = None
        avg_complexity: Optional[float] = None
        max_complexity: Optional[int] = None
        maintainability_index: Optional[float] = None

        # Check for syntax error first via AST parse to guarantee graceful detection
        try:
            ast.parse(source_code)
        except SyntaxError as exc:
            has_syntax_error = True
            issues.append(
                StaticAnalysisIssue(
                    tool="python",
                    severity="ERROR",
                    line=exc.lineno or 1,
                    message=f"SyntaxError: {exc.msg}",
                    rule_id="E9999",
                )
            )

        # Write code to a temporary file
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".py",
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as temp_file:
                temp_file.write(source_code)
                temp_file_path = temp_file.name

            # Run Bandit
            bandit_issues, bandit_errs, bandit_syntax = self._run_bandit(temp_file_path)
            issues.extend(bandit_issues)
            execution_errors.extend(bandit_errs)
            if bandit_syntax:
                has_syntax_error = True

            # Run Pylint
            pylint_issues, score, pylint_errs, pylint_syntax = self._run_pylint(temp_file_path)
            issues.extend(pylint_issues)
            execution_errors.extend(pylint_errs)
            if pylint_syntax:
                has_syntax_error = True
            if score is not None:
                pylint_score = score

            # Run Radon for complexity and maintainability — ONLY when enabled
            # (off by default) AND the code has no syntax error.
            if enable_radon and not has_syntax_error:
                avg_complexity, max_complexity = self._run_radon_cc(source_code)
                maintainability_index = self._run_radon_mi(source_code)

        except Exception as exc:
            execution_errors.append(f"Unexpected error during static analysis: {str(exc)}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

        return StaticAnalysisResult(
            issues=issues,
            pylint_score=pylint_score,
            has_syntax_error=has_syntax_error,
            errors=execution_errors,
            avg_complexity=avg_complexity,
            max_complexity=max_complexity,
            maintainability_index=maintainability_index,
        )

    def analyze_code(self, source_code: str, enable_radon: bool = False) -> StaticAnalysisResult:
        """Alias for analyze."""
        return self.analyze(source_code, enable_radon=enable_radon)

    def _run_bandit(self, file_path: str):
        """Execute Bandit and parse security issues."""
        issues: List[StaticAnalysisIssue] = []
        errors: List[str] = []
        syntax_error = False

        cmd = [
            self.python_executable,
            "-m",
            "bandit",
            "-f",
            "json",
            "-q",
            file_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )

            stdout = proc.stdout.strip()
            if not stdout:
                if proc.returncode not in (0, 1):
                    errors.append(f"Bandit exited with code {proc.returncode}: {proc.stderr.strip()}")
                return issues, errors, syntax_error

            data = json.loads(stdout)

            # Check for file parsing errors in Bandit report
            for error_item in data.get("errors", []):
                reason = error_item.get("reason", "")
                if "syntax error" in reason.lower():
                    syntax_error = True
                issues.append(
                    StaticAnalysisIssue(
                        tool="bandit",
                        severity="ERROR",
                        line=1,
                        message=f"Bandit parser notice: {reason}",
                        rule_id="BANDIT_PARSER_ERROR",
                    )
                )

            # Check for security results
            for result in data.get("results", []):
                issues.append(
                    StaticAnalysisIssue(
                        tool="bandit",
                        severity=str(result.get("issue_severity", "MEDIUM")).upper(),
                        line=int(result.get("line_number", 1)),
                        message=str(result.get("issue_text", "")).strip(),
                        rule_id=str(result.get("test_id", "")).strip(),
                    )
                )

        except subprocess.TimeoutExpired:
            errors.append(f"Bandit execution timed out after {self.timeout_seconds}s")
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse Bandit JSON output: {str(exc)}")
        except Exception as exc:
            errors.append(f"Bandit execution failed: {str(exc)}")

        return issues, errors, syntax_error

    def _run_pylint(self, file_path: str):
        """Execute Pylint and parse code quality issues and score."""
        issues: List[StaticAnalysisIssue] = []
        errors: List[str] = []
        syntax_error = False
        score: Optional[float] = None

        # Attempt json2 format first for score + messages
        cmd = [
            self.python_executable,
            "-m",
            "pylint",
            "--output-format=json2",
            file_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )

            stdout = proc.stdout.strip()
            if not stdout:
                # Try fallback format json
                return self._run_pylint_fallback(file_path)

            data = json.loads(stdout)
            if isinstance(data, dict):
                # Parse score if present
                raw_score = data.get("statistics", {}).get("score")
                if raw_score is not None:
                    try:
                        score = round(float(raw_score), 2)
                    except (ValueError, TypeError):
                        pass

                # Parse messages
                for msg in data.get("messages", []):
                    msg_id = str(msg.get("messageId", msg.get("symbol", ""))).strip()
                    symbol = str(msg.get("symbol", "")).strip()
                    if symbol == "syntax-error" or msg_id == "E0001":
                        syntax_error = True

                    issues.append(
                        StaticAnalysisIssue(
                            tool="pylint",
                            severity=str(msg.get("type", "WARNING")).upper(),
                            line=int(msg.get("line", 1) or 1),
                            message=str(msg.get("message", "")).strip(),
                            rule_id=msg_id or symbol,
                        )
                    )

        except subprocess.TimeoutExpired:
            errors.append(f"Pylint execution timed out after {self.timeout_seconds}s")
        except json.JSONDecodeError:
            # Fallback to standard json format if json2 output failed
            return self._run_pylint_fallback(file_path)
        except Exception as exc:
            errors.append(f"Pylint execution failed: {str(exc)}")

        return issues, score, errors, syntax_error

    def _run_pylint_fallback(self, file_path: str):
        """Fallback runner for older or standard pylint json format."""
        issues: List[StaticAnalysisIssue] = []
        errors: List[str] = []
        syntax_error = False
        score: Optional[float] = None

        cmd = [
            self.python_executable,
            "-m",
            "pylint",
            "--output-format=json",
            file_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            stdout = proc.stdout.strip()
            if stdout:
                data = json.loads(stdout)
                if isinstance(data, list):
                    for msg in data:
                        msg_id = str(msg.get("message-id", msg.get("symbol", ""))).strip()
                        symbol = str(msg.get("symbol", "")).strip()
                        if symbol == "syntax-error" or msg_id == "E0001":
                            syntax_error = True

                        issues.append(
                            StaticAnalysisIssue(
                                tool="pylint",
                                severity=str(msg.get("type", "WARNING")).upper(),
                                line=int(msg.get("line", 1) or 1),
                                message=str(msg.get("message", "")).strip(),
                                rule_id=msg_id or symbol,
                            )
                        )
        except Exception as exc:
            errors.append(f"Pylint fallback execution failed: {str(exc)}")

        return issues, score, errors, syntax_error

    def _run_radon_cc(self, source_code: str):
        """Execute Radon cyclomatic complexity analysis."""
        try:
            results = radon_cc.cc_visit(source_code)
            if not results:
                return None, None

            complexities = [block.complexity for block in results]
            avg_complexity = round(sum(complexities) / len(complexities), 2) if complexities else None
            max_complexity = max(complexities) if complexities else None

            return avg_complexity, max_complexity
        except Exception as exc:
            # Silently fail on Radon errors - complexity metrics are optional
            return None, None

    def _run_radon_mi(self, source_code: str):
        """Execute Radon maintainability index analysis."""
        try:
            mi_score = radon_mi.mi_visit(source_code, multi=False)
            if mi_score is not None:
                return round(mi_score, 2)
            return None
        except Exception as exc:
            # Silently fail on Radon errors - maintainability metrics are optional
            return None


def analyze_code(source_code: str) -> StaticAnalysisResult:
    """Convenience function to run StaticAnalyzer on source code."""
    analyzer = StaticAnalyzer()
    return analyzer.analyze(source_code)
