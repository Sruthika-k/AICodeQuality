import ast
import difflib
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.config import (
    ACCEPTANCE_RULE_CONSTRAINED,
    ACCEPTANCE_RULE_WEIGHTED,
    DEFAULT_SEVERITY_WEIGHT,
    PLATEAU_MIN_STRIKES,
    SECURE_CODE_INSTRUCTION,
    SEVERITY_WEIGHTS,
    STOP_REASON_CAP,
    STOP_REASON_CONVERGED,
    STOP_REASON_FIXED_CAP,
    STOP_REASON_PLATEAU,
    STOP_REASON_SINGLE_SHOT,
    STOP_RULE_CAP,
    STOP_RULE_FIXED_CAP,
    STOP_RULE_PLATEAU,
    STOP_RULE_THRESHOLD,
    ExperimentConfig,
)
from backend.app.exceptions import JobCancelled
from backend.app.feedback_generator import FeedbackGenerator
from backend.app.issue_extractor import IssueExtractor
from backend.app.llm_interface import LLMInterface
from backend.app.metrics_tracker import BeforeAfterSummary, MetricsTracker
from backend.app.run_logger import RunLogger
from backend.app.static_analyzer import StaticAnalysisIssue, StaticAnalysisResult, StaticAnalyzer

ACC_REASON_INITIAL = "ACCEPTED_INITIAL"
ACC_REASON_WEIGHTED = "ACCEPTED_WEIGHTED"
ACC_REASON_CONSTRAINED_OK = "ACCEPTED_CONSTRAINED_OK"
REJ_SECURITY_WORSE = "REJECTED_SECURITY_WEIGHT_INCREASED"
REJ_PYLINT_DROP = "REJECTED_PYLINT_SCORE_DROPPED"
REJ_AVG_COMPLEXITY = "REJECTED_AVG_COMPLEXITY_EXCEEDED_LIMIT"
REJ_MAX_COMPLEXITY = "REJECTED_MAX_COMPLEXITY_EXCEEDED_LIMIT"
REJ_MAINTAINABILITY = "REJECTED_MAINTAINABILITY_BELOW_LIMIT"
REJ_INVALID_SYNTAX = "REJECTED_INVALID_SYNTAX"


def weighted_issue_score(issues: Iterable[StaticAnalysisIssue]) -> int:
    """Weighted issue-count used by plateau detection.

    Higher severity = higher weight. Weights come from config.SEVERITY_WEIGHTS.
    A decreasing score means issues are being fixed; flat or rising for 2+
    consecutive iterations signals a plateau (stuck run).
    """
    score = 0
    for issue in issues:
        severity = (issue.severity or "").upper()
        score += SEVERITY_WEIGHTS.get(severity, DEFAULT_SEVERITY_WEIGHT)
    return score


def security_weighted_score(issues: Iterable[StaticAnalysisIssue]) -> int:
    """Weighted score of ONLY Bandit (security) issues.

    Used by the ``constrained`` acceptance rule to detect whether a candidate
    regressed security posture relative to the last accepted baseline.
    """
    score = 0
    for issue in issues:
        if (issue.tool or "").lower() != "bandit":
            continue
        severity = (issue.severity or "").upper()
        score += SEVERITY_WEIGHTS.get(severity, DEFAULT_SEVERITY_WEIGHT)
    return score


def plateau_strikes_weighted(history: List["IterationData"], required: int = PLATEAU_MIN_STRIKES) -> Tuple[int, int]:
    """Count consecutive latest iterations where weighted score did NOT improve vs BEST-SO-FAR.

    "Improvement vs best-so-far" means weighted_issue_score strictly < the previous best seen.
    Ties (cur == best) count as no-improvement → strike.

    Returns tuple (strikes_latest_run, best_so_far_weighted_seen).
    """
    best = float("inf")
    strikes_latest = 0
    for item in history:
        if item.weighted_issue_score < best:
            best = item.weighted_issue_score
            strikes_latest = 0
        else:
            strikes_latest += 1
    return strikes_latest, int(best) if best != float("inf") else 0


def plateau_strikes_adjacent(history: List["IterationData"]) -> int:
    """LEGACY adjacent-pair strike counter (for diagnostics only, not stop-rule).

    Counts how many of the LATEST adjacent transitions satisfied
    weighted[iter] >= weighted[iter-1]. Used only when printing progress diagnostics
    so developers see both adjacent-delta and best-so-far strike counts.
    """
    strikes = 0
    for idx in range(len(history) - 1, 0, -1):
        prev = history[idx - 1].weighted_issue_score
        cur = history[idx].weighted_issue_score
        if cur >= prev:
            strikes += 1
        else:
            break
    return strikes


@dataclass
class IterationData:
    """Detailed record of a single refinement cycle."""

    iteration: int
    code: str
    pylint_score: Optional[float]
    bandit_high_medium_count: int
    bandit_low_count: int
    pylint_issue_count: int
    total_issues_count: int
    has_syntax_error: bool
    threshold_met: bool
    weighted_issue_score: int = 0
    avg_complexity: Optional[float] = None
    max_complexity: Optional[int] = None
    maintainability_index: Optional[float] = None
    raw_issues: List[StaticAnalysisIssue] = field(default_factory=list)
    extracted_issues: List[StaticAnalysisIssue] = field(default_factory=list)
    feedback_text: Optional[str] = None
    diff: Optional[str] = None
    diff_lines: List[Dict[str, Any]] = field(default_factory=list)
    accepted: bool = True
    acceptance_reason: str = ACC_REASON_INITIAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "code": self.code,
            "pylint_score": self.pylint_score,
            "bandit_high_medium_count": self.bandit_high_medium_count,
            "bandit_low_count": self.bandit_low_count,
            "pylint_issue_count": self.pylint_issue_count,
            "total_issues_count": self.total_issues_count,
            "has_syntax_error": self.has_syntax_error,
            "threshold_met": self.threshold_met,
            "weighted_issue_score": self.weighted_issue_score,
            "avg_complexity": self.avg_complexity,
            "max_complexity": self.max_complexity,
            "maintainability_index": self.maintainability_index,
            "feedback_text": self.feedback_text,
            "diff": self.diff,
            "diff_lines": self.diff_lines,
            "accepted": self.accepted,
            "acceptance_reason": self.acceptance_reason,
            "issues": [issue.to_dict() for issue in self.extracted_issues],
        }


def compute_line_diff(prev_code: str, new_code: str) -> List[Dict[str, Any]]:
    """Compute structured line-by-line diff between previous and new code."""
    prev_lines = prev_code.splitlines()
    new_lines = new_code.splitlines()
    matcher = difflib.SequenceMatcher(None, prev_lines, new_lines)
    diff_entries: List[Dict[str, Any]] = []
    old_num = 1
    new_num = 1
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in prev_lines[i1:i2]:
                diff_entries.append({
                    "type": "equal",
                    "old_line_num": old_num,
                    "new_line_num": new_num,
                    "old_line": line,
                    "new_line": line,
                })
                old_num += 1
                new_num += 1
        elif tag == "replace":
            # First show deletions from old code
            for line in prev_lines[i1:i2]:
                diff_entries.append({
                    "type": "delete",
                    "old_line_num": old_num,
                    "new_line_num": None,
                    "old_line": line,
                    "new_line": None,
                })
                old_num += 1
            # Then show insertions from new code
            for line in new_lines[j1:j2]:
                diff_entries.append({
                    "type": "insert",
                    "old_line_num": None,
                    "new_line_num": new_num,
                    "old_line": None,
                    "new_line": line,
                })
                new_num += 1
        elif tag == "delete":
            for line in prev_lines[i1:i2]:
                diff_entries.append({
                    "type": "delete",
                    "old_line_num": old_num,
                    "new_line_num": None,
                    "old_line": line,
                    "new_line": None,
                })
                old_num += 1
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                diff_entries.append({
                    "type": "insert",
                    "old_line_num": None,
                    "new_line_num": new_num,
                    "old_line": None,
                    "new_line": line,
                })
                new_num += 1
    return diff_entries


@dataclass
class LoopResult:
    """Final result of the convergence loop containing all iteration records."""

    prompt: str
    final_code: str
    converged: bool
    total_iterations: int
    final_pylint_score: float
    final_bandit_high_medium: int
    status: str
    stop_reason: str
    api_calls_used: int = 0
    iterations: List[IterationData] = field(default_factory=list)
    before_after_summary: Optional[BeforeAfterSummary] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "final_code": self.final_code,
            "converged": self.converged,
            "total_iterations": self.total_iterations,
            "final_pylint_score": self.final_pylint_score,
            "final_bandit_high_medium": self.final_bandit_high_medium,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "api_calls_used": self.api_calls_used,
            "iterations": [it.to_dict() for it in self.iterations],
            "before_after_summary": self.before_after_summary.to_dict() if self.before_after_summary else None,
        }


class LoopController:
    """Manages the iterative code refinement loop until quality thresholds are satisfied or cap is reached."""

    def __init__(
        self,
        iteration_cap: Optional[int] = None,
        pylint_threshold: Optional[float] = None,
        max_bandit_high_med: Optional[int] = None,
        llm: Optional[LLMInterface] = None,
        analyzer: Optional[StaticAnalyzer] = None,
        extractor: Optional[IssueExtractor] = None,
        feedback_gen: Optional[FeedbackGenerator] = None,
        tracker: Optional[MetricsTracker] = None,
        run_timeout: int = 300,  # 5 minutes total
        tool_timeout: int = 30,  # 30 seconds per tool call
        config: Optional[ExperimentConfig] = None,
        run_logger: Optional[RunLogger] = None,
    ):
        self.config = config or ExperimentConfig()
        if iteration_cap is not None:
            self.config = replace(self.config, iteration_cap=iteration_cap)
        if pylint_threshold is not None:
            self.config = replace(self.config, pylint_threshold=pylint_threshold)
        if max_bandit_high_med is not None:
            self.config = replace(self.config, max_bandit_high_med=max_bandit_high_med)

        self.iteration_cap = self.config.iteration_cap
        self.pylint_threshold = self.config.pylint_threshold
        self.max_bandit_high_med = self.config.max_bandit_high_med
        self.run_timeout = run_timeout
        self.tool_timeout = tool_timeout

        self.llm = llm or LLMInterface(model_name=self.config.model)
        self.analyzer = analyzer or StaticAnalyzer(timeout_seconds=tool_timeout)
        self.extractor = extractor or IssueExtractor(max_issues=self.config.top_k)
        self.feedback_gen = feedback_gen or FeedbackGenerator()
        self.tracker = tracker or MetricsTracker()
        self.run_logger = run_logger or RunLogger()
        self.api_calls_used = 0

    def check_threshold(self, bandit_high_med: int, pylint_score: float, has_syntax_error: bool) -> bool:
        """Evaluate if the analysis results satisfy the design-lock quality threshold."""
        if has_syntax_error:
            return False
        if bandit_high_med > self.max_bandit_high_med:
            return False
        if pylint_score < self.pylint_threshold:
            return False
        return True

    def _generate(self, prompt: str) -> str:
        if self.config.temperature is None:
            result = self.llm.generate(prompt)
        else:
            result = self.llm.generate(prompt, temperature=self.config.temperature)
        self.api_calls_used += 1
        return result

    def _notify_job(self, callback, iteration: int, stage: str) -> None:
        if callback:
            callback({"current_iteration": iteration, "stage": stage})

    def _raise_if_cancelled(self, job_cancel_check) -> None:
        if job_cancel_check and job_cancel_check():
            raise JobCancelled("Job cancelled")

    def _is_plateau_pylint(self, history: List[IterationData]) -> bool:
        """Legacy plateau based on pylint_score range — retained for backward reference."""
        window = self.config.plateau_window
        if len(history) < window:
            return False
        scores = [item.pylint_score for item in history[-window:]]
        return (max(scores) - min(scores)) < self.config.plateau_threshold

    def _is_plateau_weighted(self, history: List[IterationData]) -> bool:
        """Plateau = weighted-issue score did NOT improve for PLATEAU_MIN_STRIKES consecutive steps.

        Requires at least (required + 1) recorded iterations so there are enough
        consecutive non-improvement transitions to observe.
        """
        required = PLATEAU_MIN_STRIKES
        if len(history) < required + 1:
            return False
        strikes, _best = plateau_strikes_weighted(history, required=required)
        return strikes >= required

    def _build_generation_prompt(self, prompt: str) -> str:
        """Build the initial code-generation prompt for the configured strategy."""
        base = (
            f"Write complete, executable Python code for the following user request:\n\n"
            f"{prompt}\n\n"
            f"Requirements:\n"
            f"- Return ONLY runnable Python code without markdown fences or explanations.\n"
            f"- Implement all requested functionality."
        )
        if self.config.strategy == "single_shot_secure":
            return f"{base}\n- {SECURE_CODE_INSTRUCTION}"
        return base

    def _evaluate_stopping(
        self,
        threshold_met: bool,
        iteration: int,
        history: List[IterationData],
    ) -> Tuple[bool, Optional[str]]:
        """Return (should_stop, stop_reason_or_None_if_continue)."""
        if self.config.is_single_shot:
            return True, STOP_REASON_SINGLE_SHOT

        sr = self.config.stop_rule

        # Convergence (quality threshold met) — by default, short-circuits all stop rules.
        # When disable_convergence_stop=True (for experiment runs), non-threshold rules
        # keep running until their natural termination.  STOP_RULE_THRESHOLD always honors
        # convergence (its semantic meaning is stop on quality threshold).
        if threshold_met and not (
            self.config.disable_convergence_stop and sr != STOP_RULE_THRESHOLD
        ):
            return True, STOP_REASON_CONVERGED

        if iteration >= self.iteration_cap:
            if sr == STOP_RULE_FIXED_CAP:
                return True, STOP_REASON_FIXED_CAP
            return True, STOP_REASON_CAP

        if sr == STOP_RULE_FIXED_CAP:
            # fixed_cap / cap both run the full iteration schedule — never stop before cap.
            return False, None

        if sr == STOP_RULE_PLATEAU and self._is_plateau_weighted(history):
            return True, STOP_REASON_PLATEAU

        return False, None

    def _evaluate_acceptance(
        self,
        previous: Optional[IterationData],
        current: IterationData,
    ) -> Tuple[bool, str]:
        """Evaluate candidate acceptance against acceptance_rule.

        Args:
            previous: Last *accepted* iteration (None for the first iteration).
            current: Candidate iteration with populated metrics + raw_issues.

        Returns:
            (accepted: bool, reason: str) — see ACC_REASON_* / REJ_* constants.
        """
        cfg = self.config
        if previous is None:
            return True, ACC_REASON_INITIAL
        if cfg.acceptance_rule == ACCEPTANCE_RULE_WEIGHTED:
            return True, ACC_REASON_WEIGHTED
        # constrained
        sec_prev = security_weighted_score(previous.raw_issues)
        sec_curr = security_weighted_score(current.raw_issues)
        if sec_curr > sec_prev:
            return False, REJ_SECURITY_WORSE
        cur_pylint = current.pylint_score if current.pylint_score is not None else -1.0
        prev_pylint = previous.pylint_score if previous.pylint_score is not None else -1.0
        if cur_pylint < prev_pylint:
            return False, REJ_PYLINT_DROP
        if cfg.enable_radon:
            if current.avg_complexity is not None and current.avg_complexity > cfg.max_avg_complexity:
                return False, REJ_AVG_COMPLEXITY
            if current.max_complexity is not None and current.max_complexity > cfg.max_max_complexity:
                return False, REJ_MAX_COMPLEXITY
            if (
                current.maintainability_index is not None
                and current.maintainability_index < cfg.min_maintainability_index
            ):
                return False, REJ_MAINTAINABILITY
        return True, ACC_REASON_CONSTRAINED_OK

    @staticmethod
    def _candidate_better(candidate: IterationData, current_best: IterationData) -> bool:
        """Return True if candidate is strictly better quality than current_best.

        Order: lower weighted_issue_score wins; tie-break higher pylint_score.
        """
        if candidate.has_syntax_error:
            return False
        if candidate.weighted_issue_score < current_best.weighted_issue_score:
            return True
        cand_pylint = candidate.pylint_score if candidate.pylint_score is not None else -1.0
        best_pylint = current_best.pylint_score if current_best.pylint_score is not None else -1.0
        if (
            candidate.weighted_issue_score == current_best.weighted_issue_score
            and cand_pylint > best_pylint
        ):
            return True
        return False

    def run(
        self,
        prompt: str,
        initial_code: Optional[str] = None,
        run_id: Optional[str] = None,
        job_status_callback: Optional[callable] = None,
        job_cancel_check: Optional[callable] = None,
    ) -> LoopResult:
        """Run the refinement loop on the user prompt.

        Args:
            prompt: User description of the desired Python program.
            initial_code: Optional starting code snippet (skips initial generation if provided).
            run_id: Optional job ID for tracking (used in async jobs).
            job_status_callback: Optional callback to update job status.
            job_cancel_check: Optional callable to check if job was cancelled.

        Returns:
            LoopResult with complete iteration history, before/after summary, and final code.
            The returned final_code is the best ACCEPTED version (per acceptance_rule),
            which may differ from the last generated candidate if the latter was rejected.
        """
        self.tracker.reset()
        self.api_calls_used = 0
        iterations_history: List[IterationData] = []
        current_code = initial_code
        best_iter_data: Optional[IterationData] = None
        code_for_next_generation: Optional[str] = initial_code
        converged = False
        stop_reason: Optional[str] = None

        print(f"\n{'='*70}")
        print(
            f"Starting LoopController Optimization "
            f"(strategy={self.config.strategy}, "
            f"stop_rule={self.config.stop_rule}, "
            f"acceptance={self.config.acceptance_rule}, "
            f"Cap={self.iteration_cap}, "
            f"Pylint>={self.pylint_threshold}, "
            f"Bandit H/M<={self.max_bandit_high_med}, "
            f"Radon={'ON' if self.config.enable_radon else 'OFF'})"
        )
        print(f"{'='*70}")

        for i in range(1, self.iteration_cap + 1):
            self._raise_if_cancelled(job_cancel_check)
            self._notify_job(job_status_callback, i, "refinement")

            print(f"\n--- [Iteration {i}/{self.iteration_cap}] ---")

            if current_code is None:
                print("Generating initial code from prompt...")
                self._notify_job(job_status_callback, i, "gemini")
                gen_prompt = self._build_generation_prompt(prompt)
                current_code = self._generate(gen_prompt)
                self._raise_if_cancelled(job_cancel_check)

            # 2. Syntax Validation & Static Analysis
            syntax_error_obj: Optional[SyntaxError] = None
            try:
                ast.parse(current_code)
            except SyntaxError as syn_err:
                syntax_error_obj = syn_err

            if syntax_error_obj is not None:
                # Candidate has invalid syntax: bypass Bandit/Pylint/Radon subprocesses
                print(f"Candidate iteration {i} has INVALID SYNTAX: {syntax_error_obj.msg} (line {syntax_error_obj.lineno})")
                raw_issues = [
                    StaticAnalysisIssue(
                        tool="python",
                        severity="ERROR",
                        line=syntax_error_obj.lineno or 1,
                        message=f"SyntaxError: {syntax_error_obj.msg}",
                        rule_id="INVALID_SYNTAX",
                    )
                ]
                pylint_score = None
                weighted = weighted_issue_score(raw_issues)
                bandit_high_med = 0
                bandit_low = 0
                pylint_issues = 0
                total_issues = len(raw_issues)
                threshold_met = False
                analysis = StaticAnalysisResult(
                    issues=raw_issues,
                    pylint_score=None,
                    has_syntax_error=True,
                    errors=[f"SyntaxError: {syntax_error_obj.msg}"],
                )
                print("Result: Syntax=INVALID | Pylint=N/A | Bandit H/M=0 | Issues=1")
                print("Threshold Met: NO")
            else:
                print(
                    "Running static analysis (Bandit & Pylint"
                    + (" + Radon complexity/MI" if self.config.enable_radon else "")
                    + ")..."
                )
                self._notify_job(job_status_callback, i, "analysis")
                analysis = self.analyzer.analyze(
                    current_code,
                    enable_radon=self.config.enable_radon,
                )

                raw_issues = list(analysis.issues)
                pylint_score = analysis.pylint_score
                weighted = weighted_issue_score(raw_issues)

                bandit_high_med = sum(
                    1
                    for issue in raw_issues
                    if issue.tool == "bandit" and issue.severity.upper() in ("HIGH", "MEDIUM")
                )
                bandit_low = sum(
                    1
                    for issue in raw_issues
                    if issue.tool == "bandit" and issue.severity.upper() == "LOW"
                )
                pylint_issues = sum(1 for issue in raw_issues if issue.tool == "pylint")
                total_issues = len(raw_issues)

                threshold_met = self.check_threshold(
                    bandit_high_med=bandit_high_med,
                    pylint_score=pylint_score if pylint_score is not None else 0.0,
                    has_syntax_error=analysis.has_syntax_error,
                )

                pylint_str = f"{pylint_score:.2f}/10.0" if pylint_score is not None else "N/A"
                status_bits = [
                    f"Pylint={pylint_str}",
                    f"Bandit H/M={bandit_high_med}",
                    f"Issues={total_issues}",
                    f"WeightedScore={weighted}",
                ]
                if self.config.enable_radon:
                    if analysis.avg_complexity is not None:
                        status_bits.append(f"CCavg={analysis.avg_complexity}")
                    if analysis.max_complexity is not None:
                        status_bits.append(f"CCmax={analysis.max_complexity}")
                    if analysis.maintainability_index is not None:
                        status_bits.append(f"MI={analysis.maintainability_index}")
                print("Result: " + " | ".join(status_bits))
                print(f"Threshold Met: {'YES (Converged)' if threshold_met else 'NO'}")

            # 3. Extract prioritized issues for feedback
            extracted_issues = self.extractor.extract(analysis)
            feedback_text = None

            # 3b. Build candidate IterationData BEFORE deciding acceptance (so metrics are available)
            iter_diff = None
            iter_diff_lines: List[Dict[str, Any]] = []
            if i > 1 and len(iterations_history) >= 1:
                prev_code = iterations_history[-1].code
                iter_diff = "\n".join(
                    difflib.unified_diff(
                        prev_code.splitlines(),
                        current_code.splitlines(),
                        fromfile=f"Iteration {i-1}",
                        tofile=f"Iteration {i}",
                        lineterm="",
                    )
                )
                iter_diff_lines = compute_line_diff(prev_code, current_code)

            candidate_iter = IterationData(
                iteration=i,
                code=current_code,
                pylint_score=pylint_score,
                bandit_high_medium_count=bandit_high_med,
                bandit_low_count=bandit_low,
                pylint_issue_count=pylint_issues,
                total_issues_count=total_issues,
                has_syntax_error=analysis.has_syntax_error,
                threshold_met=threshold_met,
                weighted_issue_score=weighted,
                avg_complexity=analysis.avg_complexity,
                max_complexity=analysis.max_complexity,
                maintainability_index=analysis.maintainability_index,
                raw_issues=raw_issues,
                extracted_issues=extracted_issues,
                feedback_text=None,
                diff=iter_diff,
                diff_lines=iter_diff_lines,
                accepted=False,
                acceptance_reason="",
            )

            if syntax_error_obj is not None:
                accepted_bool = False
                acc_reason = REJ_INVALID_SYNTAX
            else:
                prev_accepted_for_compare = best_iter_data  # compare vs last *accepted*, not last generated
                accepted_bool, acc_reason = self._evaluate_acceptance(
                    prev_accepted_for_compare, candidate_iter
                )
            candidate_iter.accepted = accepted_bool
            candidate_iter.acceptance_reason = acc_reason

            self._notify_job(job_status_callback, i, "acceptance")

            # Generate feedback_text now that we know acceptance for regression_aware (uses prior iteration history)
            if i < self.iteration_cap and not self.config.is_single_shot:
                sr = self.config.stop_rule
                if not threshold_met or sr in (STOP_RULE_CAP, STOP_RULE_FIXED_CAP):
                    fb_kwargs: Dict[str, Any] = {
                        "issues": extracted_issues,
                        "mode": self.config.feedback_mode,
                    }
                    if self.config.feedback_mode == "regression_aware":
                        if i >= 2 and len(iterations_history) >= 1:
                            fb_kwargs["previous_issues"] = iterations_history[-1].raw_issues
                            fb_kwargs["previous_rejected"] = not iterations_history[-1].threshold_met
                        else:
                            fb_kwargs["previous_issues"] = []
                            fb_kwargs["previous_rejected"] = False
                        fb_kwargs["current_all_issues"] = raw_issues
                    self._notify_job(job_status_callback, i, "feedback")
                    feedback_text = self.feedback_gen.generate_feedback(**fb_kwargs)
            candidate_iter.feedback_text = feedback_text

            # Append candidate to history ALWAYS (per requirement: log every candidate with its decision)
            iterations_history.append(candidate_iter)

            # Record in MetricsTracker every candidate (as before)
            self.tracker.record(
                iteration=i,
                issues=raw_issues,
                pylint_score=pylint_score,
                threshold_met=threshold_met,
                has_syntax_error=analysis.has_syntax_error,
                avg_complexity=analysis.avg_complexity,
                max_complexity=analysis.max_complexity,
                maintainability_index=analysis.maintainability_index,
            )

            # Update best accepted + working baseline for next generation
            if accepted_bool:
                if (
                    self.config.acceptance_rule == ACCEPTANCE_RULE_WEIGHTED
                    or best_iter_data is None
                    or self._candidate_better(candidate_iter, best_iter_data)
                ):
                    best_iter_data = candidate_iter
                code_for_next_generation = candidate_iter.code
                print(
                    f"Acceptance: ACCEPTED ({acc_reason}). "
                    f"Working baseline now iteration {candidate_iter.iteration}."
                )
            else:
                if best_iter_data is not None:
                    code_for_next_generation = best_iter_data.code
                print(
                    f"Acceptance: REJECTED ({acc_reason}). "
                    f"Keeping working baseline from iteration "
                    f"{best_iter_data.iteration if best_iter_data is not None else 'none'}."
                )

            # 4. Check stopping condition (evaluate on the actual generated candidate — original semantics preserved)
            if threshold_met:
                converged = True

            should_stop, sreason = self._evaluate_stopping(
                threshold_met, i, iterations_history
            )
            if sreason is not None:
                stop_reason = sreason

            if should_stop:
                if threshold_met:
                    print(
                        f"\n=> STOPPED[{stop_reason}]: quality thresholds satisfied in iteration {i}. "
                        f"API calls used: {self.api_calls_used}."
                    )
                elif stop_reason == STOP_REASON_PLATEAU:
                    strikes, best_seen = plateau_strikes_weighted(iterations_history)
                    scores = " -> ".join(
                        f"it{it.iteration}:{it.weighted_issue_score}"
                        for it in iterations_history
                    )
                    print(
                        f"\n=> STOPPED[{stop_reason}]: weighted issue score not improved for "
                        f"{strikes} consecutive iterations (PLATEAU_MIN_STRIKES={PLATEAU_MIN_STRIKES}, "
                        f"best-so-far weighted={best_seen}). "
                        f"API calls used: {self.api_calls_used}. Sequence: {scores}."
                    )
                elif stop_reason in (STOP_REASON_CAP, STOP_REASON_FIXED_CAP):
                    print(
                        f"\n=> STOPPED[{stop_reason}]: reached iteration cap ({self.iteration_cap}). "
                        f"API calls used: {self.api_calls_used}."
                    )
                elif stop_reason == STOP_REASON_SINGLE_SHOT:
                    print(
                        f"\n=> STOPPED[{stop_reason}]: single-shot strategy. "
                        f"API calls used: {self.api_calls_used}."
                    )
                else:
                    print(
                        f"\n=> STOPPED[{stop_reason}]: iteration {i}. "
                        f"API calls used: {self.api_calls_used}."
                    )
                break

            # 5. Send feedback to LLM for next iteration.
            # IMPORTANT: use the code of the last ACCEPTED version (code_for_next_generation)
            # as the code in the prompt block — never build on top of a rejected candidate.
            print("Constructing feedback prompt for LLM repair...")
            self._raise_if_cancelled(job_cancel_check)
            self._notify_job(job_status_callback, i, "gemini")
            prompt_base_code = code_for_next_generation if code_for_next_generation is not None else current_code
            refinement_prompt = (
                f"The following Python code was analyzed and failed quality/security checks:\n\n"
                f"```python\n{prompt_base_code}\n```\n\n"
                f"{feedback_text}\n\n"
                f"Return ONLY the complete revised Python code. Do not include Markdown fences, explanations, commentary, or analysis."
            )
            current_code = self._generate(refinement_prompt)

        # Loop exit: finalize output from best accepted iteration (never fall back to rejected)
        final_iter = best_iter_data if best_iter_data is not None else iterations_history[0]
        before_after_summary = self.tracker.get_before_after_summary(
            converged=final_iter.threshold_met,
            final_iteration=final_iter.iteration,
        )
        if stop_reason is None:
            stop_reason = STOP_REASON_CAP
        if stop_reason == STOP_REASON_CONVERGED and final_iter.threshold_met:
            status = "CONVERGED"
        else:
            status = stop_reason
        # Derive converged flag from best accepted iteration (not last generated)
        converged_final = final_iter.threshold_met

        print(f"{'='*70}\n")

        acceptance_rejected_count = sum(1 for item in iterations_history if not item.accepted)
        # Compute real before/after and diff counts from iteration history (not totals proxies).
        # IMPORTANT: after-state and diffs are based on the accepted-state trajectory only;
        # rejected candidates never become baseline, so their deltas must not be counted.
        accepted_trajectory = [it for it in iterations_history if it.accepted]
        first_iter = iterations_history[0]
        bandit_before = sum(1 for iss in first_iter.raw_issues if iss.tool == "bandit")
        bandit_after = sum(1 for iss in final_iter.raw_issues if iss.tool == "bandit")
        pylint_before = sum(1 for iss in first_iter.raw_issues if iss.tool == "pylint")
        pylint_after = sum(1 for iss in final_iter.raw_issues if iss.tool == "pylint")
        introduced_total = 0
        resolved_total = 0
        introduced_instances_total = 0
        resolved_instances_total = 0
        _e1_distinct = lambda issues: {(i.tool or "", i.rule_id or "") for i in issues}
        for j in range(1, len(accepted_trajectory)):
            prev_acc = accepted_trajectory[j - 1]
            curr_acc = accepted_trajectory[j]
            prev_e1 = _e1_distinct(prev_acc.raw_issues)
            curr_e1 = _e1_distinct(curr_acc.raw_issues)
            resolved_total += len(prev_e1 - curr_e1)
            introduced_total += len(curr_e1 - prev_e1)
            # "instances" = individual issue occurrences (not distinct rule ids): a duplicate
            # (tool, rule_id) appearing twice counts twice.  We count a resolved instance as
            # any distinct issue (tool,rule_id,line) from prev that no longer appears in curr
            # under the same (tool, rule_id) — here we use _e1_occurrence keys for accuracy.
            _occ = lambda issues: [
                ((i.tool or ""), (i.rule_id or ""), int(i.line) if i.line is not None else -1)
                for i in issues
            ]
            prev_occ = _occ(prev_acc.raw_issues)
            curr_occ_distinct_e1 = _e1_distinct(curr_acc.raw_issues)
            # Resolved instances: prev occurrences whose E1 class disappeared entirely.
            for occ in prev_occ:
                if (occ[0], occ[1]) not in curr_occ_distinct_e1:
                    resolved_instances_total += 1
            prev_e1_keys_occ = _e1_distinct(prev_acc.raw_issues)
            # Introduced instances: curr occurrences whose E1 class was NOT in prev at all
            # (i.e., new E1 rules — but we count them individually per occurrence).
            for occ in _occ(curr_acc.raw_issues):
                if (occ[0], occ[1]) not in prev_e1_keys_occ:
                    introduced_instances_total += 1
        raw_model = getattr(self.llm, "model_name", None)
        model_name = raw_model if isinstance(raw_model, str) else self.config.model
        self.run_logger.log_run(
            prompt=prompt,
            config=self.config,
            model=model_name,
            iterations=len(iterations_history),
            issues=final_iter.raw_issues,
            pylint_score=final_iter.pylint_score,
            rejected_iterations=acceptance_rejected_count,
            api_calls=self.api_calls_used,
            stop_reason=stop_reason,
            final_weighted_score=final_iter.weighted_issue_score,
            avg_complexity=final_iter.avg_complexity,
            max_complexity=final_iter.max_complexity,
            maintainability_index=final_iter.maintainability_index,
            bandit_before=bandit_before,
            bandit_after=bandit_after,
            pylint_before=pylint_before,
            pylint_after=pylint_after,
            introduced=introduced_total,
            resolved=resolved_total,
            introduced_instances=introduced_instances_total,
            resolved_instances=resolved_instances_total,
        )

        self._notify_job(job_status_callback, len(iterations_history), "best")

        return LoopResult(
            prompt=prompt,
            final_code=final_iter.code,
            converged=converged_final,
            total_iterations=len(iterations_history),
            final_pylint_score=final_iter.pylint_score,
            final_bandit_high_medium=final_iter.bandit_high_medium_count,
            status=status,
            stop_reason=stop_reason,
            api_calls_used=self.api_calls_used,
            iterations=iterations_history,
            before_after_summary=before_after_summary,
        )
