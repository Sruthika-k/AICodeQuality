"""Unit tests for the StaticAnalyzer component."""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.static_analyzer import StaticAnalyzer, StaticAnalysisIssue


def test_insecure_snippet_reports_both_tools():
    """Test that a deliberately insecure snippet produces issues from both Bandit and Pylint."""
    insecure_snippet = """import os
import subprocess

def run_untrusted(user_cmd):
    eval(user_cmd)
    os.system(user_cmd)
    subprocess.call(user_cmd, shell=True)
"""
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(insecure_snippet)

    bandit_issues = [issue for issue in result if issue.tool == "bandit"]
    pylint_issues = [issue for issue in result if issue.tool == "pylint"]

    print("\n--- Bandit Issues Found ---")
    for issue in bandit_issues:
        print(f"[{issue.tool}] Line {issue.line} | Severity: {issue.severity} | Rule: {issue.rule_id} | {issue.message}")

    print("\n--- Pylint Issues Found ---")
    for issue in pylint_issues:
        print(f"[{issue.tool}] Line {issue.line} | Severity: {issue.severity} | Rule: {issue.rule_id} | {issue.message}")

    # Verify both tools produced findings
    assert len(bandit_issues) > 0, "Expected at least one Bandit issue"
    assert len(pylint_issues) > 0, "Expected at least one Pylint issue"

    # Verify consistent issue structure (tool, severity, line, message, rule id)
    for issue in result:
        tool, severity, line, message, rule_id = issue
        assert isinstance(tool, str) and tool in ("bandit", "pylint", "python")
        assert isinstance(severity, str) and len(severity) > 0
        assert isinstance(line, int) and line >= 1
        assert isinstance(message, str) and len(message) > 0
        assert isinstance(rule_id, str) and len(rule_id) > 0


def test_syntax_error_handled_gracefully():
    """Test that invalid Python syntax does not crash the analyzer and flags syntax errors."""
    syntax_error_snippet = """def unclosed_function(
        return 1
    """
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(syntax_error_snippet)

    assert result.has_syntax_error is True
    assert len(result.issues) > 0
    assert any(
        "syntax" in issue.message.lower() or "syntax" in issue.rule_id.lower() or issue.rule_id == "E0001"
        for issue in result.issues
    )


def test_tool_failure_gracefully_handled():
    """Test that analyzer handles an invalid python executable without raising an uncaught exception."""
    analyzer = StaticAnalyzer(python_executable="non_existent_python_binary_xyz")
    result = analyzer.analyze("x = 1\n")

    # Should not raise exception; errors should be captured gracefully in result.errors
    assert isinstance(result.errors, list)
    assert len(result.errors) > 0


def test_radon_disabled_by_default(tmp_path):
    """enable_radon defaults to False -> complexity/MI fields must remain None."""
    clean_snippet = '''"""Simple clean module."""


def double(value: int) -> int:
    """Return value times two."""
    return value * 2
'''
    analyzer = StaticAnalyzer()
    disabled = analyzer.analyze(clean_snippet, enable_radon=False)
    assert disabled.avg_complexity is None
    assert disabled.max_complexity is None
    assert disabled.maintainability_index is None


def test_radon_enabled_populates_metrics(tmp_path):
    """enable_radon=True -> complexity/MI fields are populated for valid Python."""
    clean_snippet = '''"""Simple clean module."""


def double(value: int) -> int:
    """Return value times two."""
    return value * 2


def tripled(value: int) -> int:
    """Return value times three."""
    return value * 3
'''
    analyzer = StaticAnalyzer()
    enabled = analyzer.analyze(clean_snippet, enable_radon=True)
    # Values are floats/ints for syntactically clean code of two functions.
    assert enabled.avg_complexity is not None
    assert isinstance(enabled.avg_complexity, float)
    assert enabled.avg_complexity > 0
    assert enabled.max_complexity is not None and enabled.max_complexity >= 1
    assert enabled.maintainability_index is not None
    assert isinstance(enabled.maintainability_index, float)
    assert 0 <= enabled.maintainability_index <= 100


def test_radon_flag_is_isolated(tmp_path):
    """Enabling Radon must not change the issue list or severity counts."""
    insecure_snippet = """import os

def run(cmd):
    eval(cmd)
    os.system(cmd)
"""
    analyzer = StaticAnalyzer()
    off = analyzer.analyze(insecure_snippet, enable_radon=False)
    on = analyzer.analyze(insecure_snippet, enable_radon=True)
    off_ids = [(i.tool, i.rule_id, i.line) for i in off.issues]
    on_ids = [(i.tool, i.rule_id, i.line) for i in on.issues]
    assert off_ids == on_ids, "Enabling Radon must not affect issue findings."
    assert off.has_syntax_error == on.has_syntax_error
    assert off.pylint_score == on.pylint_score
