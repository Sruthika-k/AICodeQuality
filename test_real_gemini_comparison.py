"""Run loop with real Gemini to compare default vs constrained+regression_aware."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv()

from backend.app.config import ExperimentConfig
from backend.app.loop_controller import LoopController
from backend.app.llm_interface import LLMInterface
from backend.app.run_logger import RunLogger

# Prompt that tends to produce insecure code
PROMPT = "Write a function to execute a shell command from user input"

def run_experiment(name: str, config: ExperimentConfig):
    """Run experiment and return results table."""
    print(f"\n{'='*60}")
    print(f"EXPERIMENT: {name}")
    print(f"{'='*60}")
    print(f"Strategy: {config.strategy}")
    print(f"Stop rule: {config.stop_rule}")
    print(f"Acceptance: {config.acceptance_rule}")
    print(f"Feedback mode: {config.feedback_mode}")
    print(f"Iteration cap: {config.iteration_cap}")
    print(f"{'='*60}\n")

    logger = RunLogger(PROJECT_ROOT / "logs" / "runs.csv")
    llm = LLMInterface(model_name=config.model)
    controller = LoopController(config=config, llm=llm, run_logger=logger)

    result = controller.run(PROMPT)

    print(f"{'Iteration':<10} {'Issues':<10} {'Pylint':<10} {'Decision':<15} {'Reason'}")
    print("-" * 70)
    for it in result.iterations:
        decision = "ACCEPTED" if it.accepted else "REJECTED"
        reason = it.acceptance_reason or "-"
        print(f"{it.iteration:<10} {it.total_issues_count:<10} {it.pylint_score:<10.2f} {decision:<15} {reason}")

    print(f"\nAPI calls used: {result.api_calls_used}")
    print(f"Total iterations: {result.total_iterations}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Final Pylint: {result.final_pylint_score:.2f}")
    print(f"Final Bandit H/M: {result.final_bandit_high_medium}")

    return result

if __name__ == "__main__":
    # Check API key
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)

    # Experiment 1: Default flags (weighted acceptance, detailed feedback)
    cfg1 = ExperimentConfig(
        strategy="loop",
        stop_rule="fixed_cap",
        acceptance_rule="weighted",
        feedback_mode="detailed",
        iteration_cap=3,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        model="gemini-3.8-flash",
        temperature=0.0,
        enable_radon=False,
    )

    result1 = run_experiment("Default (weighted + detailed)", cfg1)

    # Experiment 2: Constrained acceptance + regression_aware feedback
    cfg2 = ExperimentConfig(
        strategy="loop",
        stop_rule="fixed_cap",
        acceptance_rule="constrained",
        feedback_mode="regression_aware",
        iteration_cap=3,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        model="gemini-3.8-flash",
        temperature=0.0,
        enable_radon=False,
    )

    result2 = run_experiment("Constrained + regression_aware", cfg2)

    # Check CSV
    csv_path = PROJECT_ROOT / "logs" / "runs.csv"
    if csv_path.exists():
        print(f"\n{'='*60}")
        print(f"CSV CONFIRMATION")
        print(f"{'='*60}")
        with csv_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"CSV rows written: {len(lines) - 1}")  # Exclude header
            print(f"CSV path: {csv_path}")
    else:
        print(f"\nERROR: CSV not found at {csv_path}")
