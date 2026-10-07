"""Tests for IssueExtractor and FeedbackGenerator components."""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.feedback_generator import FeedbackGenerator
from backend.app.issue_extractor import IssueExtractor
from backend.app.static_analyzer import StaticAnalysisIssue, StaticAnalyzer


def test_insecure_snippet_feedback_generation():
    """Verify that feedback for an insecure snippet is short, clear, and ordered by severity."""
    insecure_snippet = """import os
import subprocess

def run_untrusted(user_cmd):
    eval(user_cmd)
    os.system(user_cmd)
    subprocess.call(user_cmd, shell=True)
"""
    # 1. Run static analysis
    analyzer = StaticAnalyzer()
    raw_results = analyzer.analyze(insecure_snippet)
    assert len(raw_results) > 0

    # 2. Extract, deduplicate, sort, and cap
    max_cap = 5
    extractor = IssueExtractor(max_issues=max_cap, dedupe_semantic=True)
    cleaned_issues = extractor.extract(raw_results)

    # Assert capping
    assert len(cleaned_issues) <= max_cap

    # Assert severity ordering
    weights = [extractor.get_severity_weight(i.severity) for i in cleaned_issues]
    assert weights == sorted(weights, reverse=True), "Issues must be sorted in descending severity"

    # 3. Generate plain-text LLM feedback
    generator = FeedbackGenerator()
    feedback = generator.generate_feedback(cleaned_issues)

    print("\n--- INSTRUCTION FOR LLM ---")
    print(feedback)
    print("---------------------------\n")

    # Assertions on feedback quality
    assert isinstance(feedback, str)
    assert len(feedback.splitlines()) < 25, "Feedback should be short and concise"
    assert "Line" in feedback, "Feedback must reference line numbers"
    assert "What to fix:" in feedback, "Feedback must include actionable fix instructions"

    # Verify severity order in the feedback text
    high_pos = feedback.find("[HIGH]")
    med_pos = feedback.find("[MEDIUM]")
    low_pos = feedback.find("[LOW]")

    assert high_pos != -1, "High severity issue should be present"
    assert med_pos != -1, "Medium severity issue should be present"
    assert high_pos < med_pos, "High severity issue must precede Medium severity issue"
    if low_pos != -1:
        assert med_pos < low_pos, "Medium severity issue must precede Low severity issue"


def test_issue_extractor_exact_deduplication():
    """Verify that identical issues are deduplicated."""
    extractor = IssueExtractor(max_issues=10)
    duplicate_issues = [
        StaticAnalysisIssue(tool="bandit", severity="HIGH", line=10, message="Hardcoded secret", rule_id="B105"),
        StaticAnalysisIssue(tool="bandit", severity="HIGH", line=10, message="Hardcoded secret", rule_id="B105"),
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", line=1, message="Missing docstring", rule_id="C0114"),
    ]
    extracted = extractor.extract(duplicate_issues)
    assert len(extracted) == 2


def test_clean_code_feedback():
    """Verify that feedback on zero issues states that code meets quality criteria."""
    generator = FeedbackGenerator()
    feedback = generator.generate_feedback([])
    assert "No issues detected" in feedback


# ---------------------------------------------------------------------------
# regression_aware feedback mode tests
# ---------------------------------------------------------------------------


def _mk(tool: str, severity: str, line: int, message: str, rule_id: str) -> StaticAnalysisIssue:
    return StaticAnalysisIssue(
        tool=tool, severity=severity, line=line, message=message, rule_id=rule_id
    )


def test_e1_diff_classifies_fixed_introduced_unchanged():
    """E1 diff (tool, rule_id) correctly splits transitions into fixed / introduced / unchanged."""
    fg = FeedbackGenerator()

    prev = [
        _mk("pylint", "WARNING", 1, "Unused import os", "W0611"),
        _mk("pylint", "CONVENTION", 3, "Missing docstring", "C0116"),
        _mk("bandit", "MEDIUM", 5, "Hardcoded password", "B105"),
    ]
    curr = [
        _mk("pylint", "CONVENTION", 4, "Missing docstring", "C0116"),
        _mk("bandit", "MEDIUM", 7, "Hardcoded password", "B105"),
        _mk("bandit", "HIGH", 6, "subprocess shell=True", "B602"),
        _mk("pylint", "ERROR", 8, "Undefined variable 'x'", "E0602"),
    ]

    fixed, introduced, unchanged = fg.compute_e1_diff(prev, curr)

    assert ("pylint", "W0611") in fixed, "W0611 was removed — must be FIXED"
    assert len(fixed) == 1, "Only W0611 was fixed"

    assert ("bandit", "B602") in introduced, "B602 newly appeared — must be INTRODUCED"
    assert ("pylint", "E0602") in introduced, "E0602 newly appeared — must be INTRODUCED"
    assert len(introduced) == 2, "B602 + E0602 were introduced"

    assert ("pylint", "C0116") in unchanged, "C0116 present in both — must be UNCHANGED"
    assert ("bandit", "B105") in unchanged, "B105 present in both — must be UNCHANGED"
    assert len(unchanged) == 2


def test_e1_diff_is_equivalence_by_rule_id_not_line():
    """E1 treats same (tool, rule_id) on different lines as UNCHANGED — not fixed+introduced."""
    fg = FeedbackGenerator()
    prev = [_mk("bandit", "MEDIUM", 2, "Hardcoded", "B105")]
    curr = [_mk("bandit", "MEDIUM", 99, "Hardcoded", "B105")]
    fixed, introduced, unchanged = fg.compute_e1_diff(prev, curr)
    assert unchanged == {("bandit", "B105")}
    assert fixed == set()
    assert introduced == set()


def test_regression_aware_rejected_and_introduced_names_rule_ids():
    """ACCEPTANCE CRITERION: rejected iteration that introduced rules → feedback names the introduced rule_ids.

    This is the key requirement: the feedback produced for a *rejected* iteration
    (threshold not met) that also introduced new E1-rule-classes must explicitly
    list each introduced rule_id (e.g. ``bandit:B602``, ``pylint:E0602``) so the
    LLM is told exactly which regressions to reverse.
    """
    fg = FeedbackGenerator()

    # Iteration 1 (previous): had W0611, C0116, B105
    previous_issues = [
        _mk("pylint", "WARNING", 1, "Unused import os", "W0611"),
        _mk("pylint", "CONVENTION", 3, "Missing docstring", "C0116"),
        _mk("bandit", "MEDIUM", 5, "Hardcoded password", "B105"),
    ]

    # Iteration 2 (current, REJECTED — threshold_met=False):
    #   Fixed: W0611         ← great, preserve it
    #   Unchanged: C0116, B105
    #   Introduced: B602, E0602  ← regressions the LLM must reverse
    current_issues = [
        _mk("pylint", "CONVENTION", 4, "Missing docstring", "C0116"),
        _mk("bandit", "MEDIUM", 7, "Hardcoded password", "B105"),
        _mk("bandit", "HIGH", 6, "subprocess shell=True", "B602"),
        _mk("pylint", "ERROR", 8, "Undefined variable 'x'", "E0602"),
    ]

    # Prioritized (top_k) subset — may exclude some low-priority items; E1 diff
    # however is always run against the *full* current set.
    prioritized = [
        _mk("bandit", "HIGH", 6, "subprocess shell=True", "B602"),
        _mk("pylint", "ERROR", 8, "Undefined variable 'x'", "E0602"),
        _mk("bandit", "MEDIUM", 7, "Hardcoded password", "B105"),
    ]

    feedback = fg.generate_feedback(
        issues=prioritized,
        mode="regression_aware",
        previous_issues=previous_issues,
        previous_rejected=True,  # ← key: previous iteration was REJECTED
        current_all_issues=current_issues,
    )

    print("\n--- regression_aware FEEDBACK (rejected + introduced) ---")
    print(feedback)
    print("---------------------------------------------------------\n")

    # 1. Section headers present
    assert "Regression-aware repair instructions" in feedback
    assert "PRESERVE" in feedback, "Must tell LLM what to preserve from the last change"
    assert "FIX the regressions" in feedback or "REGRESSIONS" in feedback
    assert "IMPORTANT" in feedback, "Must include do-not-reintroduce instruction"
    assert "prioritized issues" in feedback

    # 2. Fixed rule is listed as PRESERVED
    assert "pylint:W0611" in feedback, "W0611 was fixed — must be listed under PRESERVE"

    # 3. ACCEPTANCE CRITERION: introduced rule_ids are NAMED explicitly
    assert "bandit:B602" in feedback, (
        "ACCEPTANCE FAIL: rejected iteration introduced bandit:B602 but feedback did not name it."
    )
    assert "pylint:E0602" in feedback, (
        "ACCEPTANCE FAIL: rejected iteration introduced pylint:E0602 but feedback did not name it."
    )

    # 4. Guardrails: no reintroduction instruction present
    assert "Do NOT reintroduce" in feedback or "do NOT reintroduce" in feedback

    # 5. Closing line forbids regressing prior fixes
    assert "without regressing prior fixes" in feedback


def test_regression_aware_rejected_no_new_introductions_still_triggers():
    """Previous iteration was rejected even if no NEW rules were introduced → regression preamble still shown."""
    fg = FeedbackGenerator()
    previous_issues = [
        _mk("bandit", "HIGH", 5, "shell=True", "B602"),
        _mk("pylint", "CONVENTION", 1, "Missing module docstring", "C0114"),
    ]
    current_issues = list(previous_issues)  # nothing changed
    prioritized = list(current_issues)

    feedback = fg.generate_feedback(
        issues=prioritized,
        mode="regression_aware",
        previous_issues=previous_issues,
        previous_rejected=True,  # rejected (threshold not met)
        current_all_issues=current_issues,
    )

    # Still shows regression-aware preamble because previous_rejected=True
    assert "Regression-aware repair instructions" in feedback
    assert "PRESERVE: No new rule fixes were achieved" in feedback
    assert "REGRESSIONS: No new rules were introduced" in feedback


def test_regression_aware_not_rejected_but_introduced_still_triggers():
    """Even if previous technically passed thresholds, introducing new rules still triggers preamble."""
    fg = FeedbackGenerator()
    previous_issues = [
        _mk("pylint", "CONVENTION", 3, "Missing docstring", "C0116"),
    ]
    current_issues = [
        _mk("pylint", "CONVENTION", 3, "Missing docstring", "C0116"),
        _mk("pylint", "WARNING", 5, "Unused variable 'tmp'", "W0612"),  # introduced
    ]
    prioritized = list(current_issues)

    feedback = fg.generate_feedback(
        issues=prioritized,
        mode="regression_aware",
        previous_issues=previous_issues,
        previous_rejected=False,  # not rejected
        current_all_issues=current_issues,
    )

    # Triggered because introduced_keys is non-empty
    assert "Regression-aware repair instructions" in feedback
    assert "pylint:W0612" in feedback  # introduced rule named


def test_regression_aware_first_iteration_no_previous_skips_preamble():
    """First iteration (no previous issues data) behaves like detailed mode — no regression preamble."""
    fg = FeedbackGenerator()
    current_issues = [
        _mk("pylint", "CONVENTION", 1, "Missing docstring", "C0114"),
        _mk("bandit", "HIGH", 5, "eval()", "B307"),
    ]
    feedback = fg.generate_feedback(
        issues=current_issues,
        mode="regression_aware",
        previous_issues=[],   # first iteration: nothing to compare
        previous_rejected=False,
        current_all_issues=current_issues,
    )
    assert "Regression-aware repair instructions" not in feedback
    assert "Fix the following" in feedback  # falls through to standard header


def test_regression_aware_not_triggered_falls_through():
    """Neither rejected nor any introduced rules → standard header without preamble."""
    fg = FeedbackGenerator()
    previous_issues = [
        _mk("pylint", "CONVENTION", 1, "Missing doc", "C0114"),
        _mk("bandit", "MEDIUM", 5, "Hardcoded", "B105"),
    ]
    current_issues = list(previous_issues)  # same as before
    prioritized = list(current_issues)

    feedback = fg.generate_feedback(
        issues=prioritized,
        mode="regression_aware",
        previous_issues=previous_issues,
        previous_rejected=False,  # NOT rejected
        current_all_issues=current_issues,
    )
    assert "Regression-aware repair instructions" not in feedback
    assert "Fix the following" in feedback


def test_regression_aware_signature_backward_compat():
    """Calling generate_feedback without the new kwargs still works (all modes)."""
    fg = FeedbackGenerator()
    issues = [_mk("pylint", "WARNING", 1, "Unused import", "W0611")]
    for mode in ("detailed", "minimal", "concise", "structured"):
        fb = fg.generate_feedback(issues, mode=mode)
        assert isinstance(fb, str) and len(fb) > 0
    # regression_aware without prev data — must still return string
    fb_ra = fg.generate_feedback(issues, mode="regression_aware")
    assert isinstance(fb_ra, str) and len(fb_ra) > 0


# ---------------------------------------------------------------------------
# NEW explicit E1 diff tests: empty before/after, duplicates, hand-made cases
# ---------------------------------------------------------------------------


def test_e1_diff_empty_before():
    """Empty previous issue set = all current issues are INTRODUCED; nothing resolved/persisting."""
    fg = FeedbackGenerator()
    prev: List[StaticAnalysisIssue] = []
    curr = [
        StaticAnalysisIssue(tool="bandit", severity="HIGH", rule_id="B602", line=5,
                             message="subprocess call with shell=True"),
        StaticAnalysisIssue(tool="pylint", severity="CONVENTION", rule_id="C0116", line=1,
                             message="Missing module docstring"),
    ]
    resolved, introduced, persisting = fg.compute_e1_diff(prev, curr)
    assert len(resolved) == 0
    assert len(persisting) == 0
    assert len(introduced) == 2
    # compute_e1_diff returns sets of (tool, rule_id) E1 keys, not issue objects.
    assert introduced == {("bandit", "B602"), ("pylint", "C0116")}


def test_e1_diff_empty_after():
    """Empty current issue set = all previous issues are RESOLVED; nothing introduced/persisting."""
    fg = FeedbackGenerator()
    prev = [
        StaticAnalysisIssue(tool="bandit", severity="MEDIUM", rule_id="B105", line=2,
                             message="Hardcoded password string"),
        StaticAnalysisIssue(tool="pylint", severity="WARNING", rule_id="W0611", line=3,
                             message="Unused import os"),
    ]
    curr: List[StaticAnalysisIssue] = []
    resolved, introduced, persisting = fg.compute_e1_diff(prev, curr)
    assert len(introduced) == 0
    assert len(persisting) == 0
    assert len(resolved) == 2
    assert resolved == {("bandit", "B105"), ("pylint", "W0611")}


def test_e1_diff_with_duplicate_issues_does_not_crash_and_counts_once_per_e1_key():
    """Duplicate issues (same tool+rule_id) are deduplicated per E1 equivalence;
    the computation does not crash and each (tool, rule_id) contributes at most once.
    """
    fg = FeedbackGenerator()
    # Two duplicates of the same E1 class in both prev and curr — should only count once.
    prev = [
        StaticAnalysisIssue(tool="pylint", severity="WARNING", rule_id="W0611", line=2, message="A"),
        StaticAnalysisIssue(tool="pylint", severity="WARNING", rule_id="W0611", line=5, message="B"),
        StaticAnalysisIssue(tool="bandit", severity="HIGH", rule_id="B602", line=10, message="C"),
    ]
    curr = [
        StaticAnalysisIssue(tool="pylint", severity="WARNING", rule_id="W0611", line=17, message="A'"),
        StaticAnalysisIssue(tool="pylint", severity="WARNING", rule_id="W0611", line=99, message="B'"),
        # W0611 is still there on another line → PERSISTING (not resolved+introduced pair)
    ]
    resolved, introduced, persisting = fg.compute_e1_diff(prev, curr)
    # B602 appears only in prev → resolved once.
    assert len(resolved) == 1
    assert resolved == {("bandit", "B602")}
    # W0611 in both → persisting, exactly one E1 key.
    assert len(persisting) == 1
    assert persisting == {("pylint", "W0611")}
    assert len(introduced) == 0
