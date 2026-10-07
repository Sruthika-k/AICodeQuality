"""Run experiment matrix: C1 single_shot, C2-C4 loop variants with configurable options."""

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import ExperimentConfig
from backend.app.loop_controller import LoopController

RESULTS_CSV = PROJECT_ROOT / "logs" / "matrix_results.csv"
ITERATIONS_CSV = PROJECT_ROOT / "logs" / "matrix_iterations.csv"
FINAL_CODE_DIR = PROJECT_ROOT / "logs" / "final_code"
CACHE_DIR = PROJECT_ROOT / "logs" / "generation_cache"


def get_cache_key(prompt: str, model: str, temperature: float) -> str:
    """Generate cache key for initial generation."""
    key_str = f"{prompt}|{model}|{temperature}"
    return hashlib.sha256(key_str.encode()).hexdigest()


def load_cached_generation(cache_key: str) -> Optional[str]:
    """Load cached initial generation if exists."""
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return None


def save_cached_generation(cache_key: str, code: str) -> None:
    """Save initial generation to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    cache_file.write_text(code, encoding="utf-8")


def load_prompts(jsonl_path: Path) -> List[Dict[str, str]]:
    """Load prompts from JSONL file (id, prompt)."""
    prompts = []
    if not jsonl_path.exists():
        return prompts
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "id" in data and "prompt" in data:
                    prompts.append(data)
            except json.JSONDecodeError:
                continue
    return prompts


def load_completed_pairs(results_csv: Path) -> Set[Tuple[str, str, int]]:
    """Load (prompt_id, condition, repeat) from existing results to skip."""
    completed: Set[Tuple[str, str, int]] = set()
    if not results_csv.exists():
        return completed
    with results_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("prompt_id", "").strip()
            cond = row.get("condition", "").strip()
            repeat = int(row.get("repeat", "0") or "0")
            if pid and cond:
                completed.add((pid, cond, repeat))
    return completed


def save_progress(
    results_csv: Path,
    rows: List[Dict[str, str]],
):
    """Append new rows to results CSV."""
    results_csv.parent.mkdir(parents=True, exist_ok=True)
    write_header = not results_csv.exists() or results_csv.stat().st_size == 0
    fieldnames = [
        "timestamp",
        "prompt_id",
        "condition",
        "repeat",
        "feedback_mode",
        "top_k",
        "stop_rule",
        "strategy",
        "acceptance_rule",
        "iteration_cap",
        "pylint_threshold",
        "max_bandit_high_med",
        "model",
        "temperature",
        "iterations",
        "api_calls",
        "stop_reason",
        "pylint_score",
        "bandit_after",
        "introduced",
        "resolved",
        "rejected_iterations",
    ]
    with results_csv.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def save_iterations_csv(
    iterations_csv: Path,
    rows: List[Dict[str, str]],
):
    """Append per-iteration rows to matrix_iterations.csv."""
    iterations_csv.parent.mkdir(parents=True, exist_ok=True)
    write_header = not iterations_csv.exists() or iterations_csv.stat().st_size == 0
    fieldnames = [
        "task",
        "condition",
        "repeat",
        "iteration",
        "pylint_score",
        "bandit_high",
        "bandit_medium",
        "bandit_low",
        "issue_count",
        "weighted_score",
        "accepted",
        "rejection_reason",
    ]
    with iterations_csv.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def calculate_introduced_resolved(iterations: List) -> Tuple[int, int]:
    """Calculate introduced and resolved from iteration history (matches loop_controller logic)."""
    accepted_trajectory = [it for it in iterations if it.accepted]
    if len(accepted_trajectory) < 2:
        return 0, 0
    
    _e1_distinct = lambda issues: {(i.tool or "", i.rule_id or "") for i in issues}
    introduced_total = 0
    resolved_total = 0
    
    for j in range(1, len(accepted_trajectory)):
        prev_acc = accepted_trajectory[j - 1]
        curr_acc = accepted_trajectory[j]
        prev_e1 = _e1_distinct(prev_acc.raw_issues)
        curr_e1 = _e1_distinct(curr_acc.raw_issues)
        resolved_total += len(prev_e1 - curr_e1)
        introduced_total += len(curr_e1 - prev_e1)
    
    return introduced_total, resolved_total


class CallTrackingLLM:
    """Wrapper to track and limit API calls."""

    def __init__(self, llm, max_calls: Optional[int] = None):
        self.llm = llm
        self.max_calls = max_calls
        self.call_count = 0

    def generate(self, prompt: str, temperature: float = 0.0) -> str:
        """Generate with call tracking and limit enforcement."""
        if self.max_calls is not None and self.call_count >= self.max_calls:
            raise RuntimeError(f"Max calls ({self.max_calls}) reached. Cannot make additional API calls.")
        self.call_count += 1
        return self.llm.generate(prompt, temperature=temperature)

    @property
    def model_name(self) -> str:
        return getattr(self.llm, "model_name", "unknown")


def run_condition(
    prompt_id: str,
    prompt: str,
    condition: str,
    repeat: int,
    delay: float,
    dry_run: bool,
    iteration_cap: int,
    max_calls: Optional[int],
    fake_llm_responses: Optional[List[str]] = None,
    shared_initial_code: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Run a single condition and return result row or None on rate limit."""
    from datetime import datetime, timezone

    conditions = {
        "C1": {
            "strategy": "single_shot",
            "stop_rule": "fixed_cap",
            "acceptance_rule": "weighted",
            "feedback_mode": "detailed",
        },
        "C2": {
            "strategy": "loop",
            "stop_rule": "fixed_cap",
            "acceptance_rule": "weighted",
            "feedback_mode": "detailed",
            "disable_convergence_stop": True,
        },
        "C3": {
            "strategy": "loop",
            "stop_rule": "fixed_cap",
            "acceptance_rule": "weighted",
            "feedback_mode": "regression_aware",
            "disable_convergence_stop": True,
        },
        "C4": {
            "strategy": "loop",
            "stop_rule": "fixed_cap",
            "acceptance_rule": "constrained",
            "feedback_mode": "detailed",
            "disable_convergence_stop": True,
        },
    }

    cfg = conditions.get(condition, conditions["C2"])
    cfg["iteration_cap"] = iteration_cap
    cfg["pylint_threshold"] = 8.0
    cfg["max_bandit_high_med"] = 0
    cfg["model"] = "fake-test-model" if dry_run else "gemini-3.8-flash"
    cfg["temperature"] = 0.0
    cfg["top_k"] = 5

    config = ExperimentConfig(**cfg)

    if delay > 0:
        time.sleep(delay)

    try:
        if dry_run:
            # Use FakeLLM with CLEAN_CODE for all responses
            if fake_llm_responses is None:
                from tests.conftest import CLEAN_CODE
                fake_llm_responses = [CLEAN_CODE] * iteration_cap
            from tests.conftest import FakeLLM
            llm = FakeLLM(fake_llm_responses, model_name="fake-test-model")
        else:
            # In production, use real LLM
            from backend.app.llm_interface import LLMInterface
            real_llm = LLMInterface(model_name=config.model)
            llm = CallTrackingLLM(real_llm, max_calls)

        controller = LoopController(config=config, llm=llm)

        # If shared initial code is provided, use it directly (bypasses generation)
        # This ensures C1-C4 all start from the same S0 for fair comparison
        result = controller.run(prompt, initial_code=shared_initial_code)

        # Calculate introduced/resolved (matches loop_controller logic)
        introduced, resolved = calculate_introduced_resolved(result.iterations)

        # Save final code to file
        FINAL_CODE_DIR.mkdir(parents=True, exist_ok=True)
        final_code_filename = f"{prompt_id}_{condition}_r{repeat}.py"
        final_code_path = FINAL_CODE_DIR / final_code_filename
        final_code_path.write_text(result.final_code, encoding="utf-8")

        # Write per-iteration results to matrix_iterations.csv
        iteration_rows = []
        for it in result.iterations:
            # Count bandit issues by severity
            bandit_high = sum(1 for iss in it.raw_issues if iss.tool == "bandit" and iss.severity == "HIGH")
            bandit_medium = sum(1 for iss in it.raw_issues if iss.tool == "bandit" and iss.severity == "MEDIUM")
            bandit_low = sum(1 for iss in it.raw_issues if iss.tool == "bandit" and iss.severity == "LOW")
            issue_count = len(it.raw_issues)
            
            iteration_rows.append({
                "task": prompt_id,
                "condition": condition,
                "repeat": str(repeat),
                "iteration": str(it.iteration),
                "pylint_score": str(it.pylint_score),
                "bandit_high": str(bandit_high),
                "bandit_medium": str(bandit_medium),
                "bandit_low": str(bandit_low),
                "issue_count": str(issue_count),
                "weighted_score": str(it.weighted_issue_score),
                "accepted": str(it.accepted),
                "rejection_reason": it.acceptance_reason if not it.accepted else "",
            })
        
        if iteration_rows:
            save_iterations_csv(ITERATIONS_CSV, iteration_rows)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_id": prompt_id,
            "condition": condition,
            "repeat": str(repeat),
            "feedback_mode": config.feedback_mode,
            "top_k": str(config.top_k),
            "stop_rule": config.stop_rule,
            "strategy": config.strategy,
            "acceptance_rule": config.acceptance_rule,
            "iteration_cap": str(config.iteration_cap),
            "pylint_threshold": str(config.pylint_threshold),
            "max_bandit_high_med": str(config.max_bandit_high_med),
            "model": config.model,
            "temperature": str(config.temperature),
            "iterations": str(result.total_iterations),
            "api_calls": str(result.api_calls_used),
            "stop_reason": result.stop_reason or "",
            "pylint_score": str(result.final_pylint_score),
            "bandit_after": str(result.final_bandit_high_medium),
            "introduced": str(introduced),
            "resolved": str(resolved),
            "rejected_iterations": str(sum(1 for it in result.iterations if not it.accepted)),
        }
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
            print(f"\n[RATE LIMIT] {prompt_id} {condition} repeat={repeat}: {error_str}")
            return None  # Signal rate limit
        if "Max calls" in error_str:
            print(f"\n[MAX CALLS] {prompt_id} {condition} repeat={repeat}: {error_str}")
            return None  # Signal max calls reached
        raise


def estimate_api_calls(num_prompts: int, iteration_cap: int, shared_gen: bool) -> int:
    """Estimate total API calls based on configuration."""
    if shared_gen:
        # 1 shared initial + 3 * (iteration_cap - 1) refinements per prompt
        return num_prompts * (1 + 3 * (iteration_cap - 1))
    else:
        # Without sharing: each condition generates independently
        # C1: 1 call, C2-C4: iteration_cap calls each
        return num_prompts * (1 + 3 * iteration_cap)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run experiment matrix C1-C4")
    parser.add_argument("jsonl", type=Path, help="JSONL file with id,prompt")
    parser.add_argument("--repeats", type=int, default=1, help="Repeat count per condition")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay between runs (seconds)")
    parser.add_argument("--limit", type=int, default=None, help="Limit total pairs")
    parser.add_argument("--dry-run", action="store_true", help="Use FakeLLM, no real API calls")
    parser.add_argument("--results", type=Path, default=RESULTS_CSV, help="Results CSV path")
    parser.add_argument("--iteration-cap", type=int, default=5, help="Iteration cap (default: 5)")
    parser.add_argument("--max-calls", type=int, default=None, help="Maximum API calls (hard limit)")
    parser.add_argument("--shared-gen", action="store_true", help="Share initial generation across C1-C4")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    prompts = load_prompts(args.jsonl)
    completed = load_completed_pairs(args.results)
    conditions = ["C1", "C2", "C3", "C4"]
    total_pairs = len(prompts) * len(conditions) * args.repeats
    remaining_pairs = total_pairs - len(completed)
    total_api_calls = 0

    # Preflight estimate
    estimated_calls = estimate_api_calls(len(prompts), args.iteration_cap, args.shared_gen)

    print(f"Loaded {len(prompts)} prompts from {args.jsonl}")
    print(f"Total pairs: {total_pairs}, Completed: {len(completed)}, Remaining: {remaining_pairs}")
    print(f"Conditions: {', '.join(conditions)}")
    print(f"Iteration cap: {args.iteration_cap}")
    print(f"Shared first generation: {args.shared_gen}")
    print(f"Estimated API calls: {estimated_calls}")
    if args.max_calls:
        print(f"Max calls budget: {args.max_calls}")
    print(f"Delay: {args.delay}s, Dry-run: {args.dry_run}")

    if args.max_calls and estimated_calls > args.max_calls:
        print(f"\n[WARNING] Estimated calls ({estimated_calls}) exceed max-calls budget ({args.max_calls})")
        print(f"Execution will stop when budget is reached.")

    for repeat in range(1, args.repeats + 1):
        for prompt_data in prompts:
            prompt_id = prompt_data["id"]
            prompt = prompt_data["prompt"]
            shared_code = None

            # Generate shared initial code if enabled
            if args.shared_gen and not args.dry_run:
                cache_key = get_cache_key(prompt, "gemini-3.8-flash", 0.0)
                shared_code = load_cached_generation(cache_key)
                if shared_code is None:
                    # Need to generate - this counts against max_calls
                    print(f"\n[SHARED GEN] Generating initial code for {prompt_id}")
                    try:
                        from backend.app.llm_interface import LLMInterface
                        real_llm = LLMInterface(model_name="gemini-3.8-flash")
                        tracking_llm = CallTrackingLLM(real_llm, args.max_calls)
                        shared_code = tracking_llm.generate(prompt, temperature=0.0)
                        save_cached_generation(cache_key, shared_code)
                        total_api_calls += tracking_llm.call_count
                        print(f"  -> Shared generation used {tracking_llm.call_count} call(s)")
                    except RuntimeError as e:
                        if "Max calls" in str(e):
                            print(f"\n[MAX CALLS] Shared generation hit max-calls limit")
                            save_progress(args.results, [])
                            return 1
                        raise

            for condition in conditions:
                key = (prompt_id, condition, repeat)
                if key in completed:
                    continue

                print(f"\n{prompt_id} {condition} repeat={repeat}")
                result = run_condition(
                    prompt_id,
                    prompt,
                    condition,
                    repeat,
                    args.delay,
                    args.dry_run,
                    args.iteration_cap,
                    args.max_calls,
                    shared_initial_code=shared_code,
                )

                if result is None:
                    # Rate limit or max calls - save progress and exit
                    print(f"\n[EXIT] Interrupted. Progress saved.")
                    print(f"Remaining pairs to complete: {remaining_pairs - 1}")
                    save_progress(args.results, [])
                    return 1

                save_progress(args.results, [result])
                if not args.dry_run:
                    total_api_calls += int(result["api_calls"])
                print(f"  -> iterations={result['iterations']}, api_calls={result['api_calls']}, stop={result['stop_reason']}")

                if args.limit and (len(completed) + 1) >= args.limit:
                    print(f"\n[LIMIT] Reached limit of {args.limit} pairs")
                    break

    print(f"\n[COMPLETE] All pairs processed. Total API calls: {total_api_calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
