"""LoopController orchestrates the code generation, static analysis, feedback, and refinement loop."""

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from backend.app.config import ExperimentConfig
from backend.app.feedback_generator import FeedbackGenerator
from backend.app.issue_extractor import IssueExtractor
from backend.app.llm_interface import LLMInterface
from backend.app.metrics_tracker import BeforeAfterSummary, MetricsTracker
from backend.app.run_logger import RunLogger
from backend.app.static_analyzer import StaticAnalysisIssue, StaticAnalysisResult, StaticAnalyzer


import difflib

@dataclass
class IterationData:
    """Detailed record of a single refinement cycle."""

    iteration: int
    code: str
    pylint_score: float
    bandit_high_medium_count: int
    bandit_low_count: int
    pylint_issue_count: int
    total_issues_count: int
    has_syntax_error: bool
    threshold_met: bool
    raw_issues: List[StaticAnalysisIssue] = field(default_factory=list)
    extracted_issues: List[StaticAnalysisIssue] = field(default_factory=list)
    feedback_text: Optional[str] = None
    diff: Optional[str] = None
    diff_lines: List[Dict[str, Any]] = field(default_factory=list)

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
            "feedback_text": self.feedback_text,
            "diff": self.diff,
            "diff_lines": self.diff_lines,
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

    def _is_plateau(self, history: List[IterationData]) -> bool:
        window = self.config.plateau_window
        if len(history) < window:
            return False
        scores = [item.pylint_score for item in history[-window:]]
        return (max(scores) - min(scores)) < self.config.plateau_threshold

    def _should_stop(self, threshold_met: bool, iteration: int, history: List[IterationData]) -> bool:
        if self.config.strategy == "single_shot":
            return True
        if iteration >= self.iteration_cap:
            return True
        if self.config.stop_rule == "cap":
            return False
        if self.config.stop_rule == "plateau" and self._is_plateau(history):
            return True
        if self.config.stop_rule == "threshold" and threshold_met:
            return True
        return threshold_met

    def run(self, prompt: str, initial_code: Optional[str] = None) -> LoopResult:
        """Run the refinement loop on the user prompt.

        Args:
            prompt: User description of the desired Python program.
            initial_code: Optional starting code snippet (skips initial generation if provided).

        Returns:
            LoopResult with complete iteration history, before/after summary, and final code.
        """
        self.tracker.reset()
        self.api_calls_used = 0
        iterations_history: List[IterationData] = []
        current_code = initial_code
        converged = False

        print(f"\n{'='*70}")
        print(f"Starting LoopController Optimization (Cap: {self.iteration_cap}, Pylint Threshold: >={self.pylint_threshold}, Bandit High/Med: {self.max_bandit_high_med})")
        print(f"{'='*70}")

        for i in range(1, self.iteration_cap + 1):
            print(f"\n--- [Iteration {i}/{self.iteration_cap}] ---")

            # 1. Generate code if needed
            if current_code is None:
                print("Generating initial code from prompt...")
                gen_prompt = (
                    f"Write complete, executable Python code for the following user request:\n\n"
                    f"{prompt}\n\n"
                    f"Requirements:\n"
                    f"- Return ONLY runnable Python code without markdown fences or explanations.\n"
                    f"- Implement all requested functionality."
                )
                current_code = self._generate(gen_prompt)

            # 2. Run Static Analysis
            print("Running static analysis (Bandit & Pylint)...")
            analysis: StaticAnalysisResult = self.analyzer.analyze(current_code)

            raw_issues = list(analysis.issues)
            pylint_score = analysis.pylint_score if analysis.pylint_score is not None else 0.0

            # Count Bandit severities
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

            # Check threshold
            threshold_met = self.check_threshold(
                bandit_high_med=bandit_high_med,
                pylint_score=pylint_score,
                has_syntax_error=analysis.has_syntax_error,
            )

            # Log iteration status to terminal
            print(
                f"Result: Pylint Score = {pylint_score:.2f}/10.0 | "
                f"Bandit High/Med = {bandit_high_med} | "
                f"Total Issues = {total_issues}"
            )
            print(f"Threshold Met: {'YES (Converged)' if threshold_met else 'NO'}")

            # 3. Extract and prioritize issues for feedback
            extracted_issues = self.extractor.extract(analysis)
            feedback_text = None

            if i < self.iteration_cap and self.config.strategy != "single_shot":
                if not threshold_met or self.config.stop_rule == "cap":
                    feedback_text = self.feedback_gen.generate_feedback(
                        extracted_issues,
                        mode=self.config.feedback_mode,
                    )

            # Compute diff with previous iteration if available
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

            # Record iteration data in controller history
            iter_data = IterationData(
                iteration=i,
                code=current_code,
                pylint_score=pylint_score,
                bandit_high_medium_count=bandit_high_med,
                bandit_low_count=bandit_low,
                pylint_issue_count=pylint_issues,
                total_issues_count=total_issues,
                has_syntax_error=analysis.has_syntax_error,
                threshold_met=threshold_met,
                raw_issues=raw_issues,
                extracted_issues=extracted_issues,
                feedback_text=feedback_text,
                diff=iter_diff,
                diff_lines=iter_diff_lines,
            )
            iterations_history.append(iter_data)

            # Record in MetricsTracker
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

            # 4. Check stopping condition
            if threshold_met:
                converged = True
                print(f"\n=> SUCCESS: Code quality thresholds satisfied in iteration {i}!")

            if self._should_stop(threshold_met, i, iterations_history):
                if not threshold_met and i >= self.iteration_cap:
                    print(f"\n=> STOPPED: Reached maximum iteration cap ({self.iteration_cap}).")
                break

            # 5. Send feedback to LLM for next iteration
            print("Constructing feedback prompt for LLM repair...")
            refinement_prompt = (
                f"The following Python code was analyzed and failed quality/security checks:\n\n"
                f"```python\n{current_code}\n```\n\n"
                f"{feedback_text}\n\n"
                f"Provide the complete revised Python code that fixes all of the issues. "
                f"Ensure 100% adherence to docstring conventions and secure coding guidelines. "
                f"Output ONLY executable Python code."
            )
            current_code = self._generate(refinement_prompt)

        final_iter = iterations_history[-1]
        before_after_summary = self.tracker.get_before_after_summary(converged=converged)
        status = "CONVERGED" if converged else "CAP_REACHED"

        print(f"{'='*70}\n")

        rejected_iterations = sum(1 for item in iterations_history if not item.threshold_met)
        raw_model = getattr(self.llm, "model_name", None)
        model_name = raw_model if isinstance(raw_model, str) else self.config.model
        self.run_logger.log_run(
            prompt=prompt,
            config=self.config,
            model=model_name,
            iterations=len(iterations_history),
            issues=final_iter.raw_issues,
            pylint_score=final_iter.pylint_score,
            rejected_iterations=rejected_iterations,
            api_calls=self.api_calls_used,
        )

        return LoopResult(
            prompt=prompt,
            final_code=final_iter.code,
            converged=converged,
            total_iterations=len(iterations_history),
            final_pylint_score=final_iter.pylint_score,
            final_bandit_high_medium=final_iter.bandit_high_medium_count,
            status=status,
            iterations=iterations_history,
            before_after_summary=before_after_summary,
        )
