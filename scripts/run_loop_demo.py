"""Terminal script running the full LoopController on a prompt that tends to produce flawed code."""

import sys
from pathlib import Path

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.loop_controller import LoopController


def main():
    # Prompt deliberately phrased in a way that commonly triggers eval/shell flaws on initial generation
    flawed_prompt = (
        "Write a Python utility with a function execute_command(user_input) that evaluates "
        "math expressions with eval() or executes system commands using os.system(). "
        "Keep it quick and concise without docstrings."
    )

    print("\n" + "=" * 75)
    print("DEMO: Automated AI Code Quality & Security Enhancement Loop")
    print("=" * 75)
    print(f"Target Prompt:\n\"{flawed_prompt}\"\n")

    controller = LoopController(iteration_cap=3, pylint_threshold=8.0, max_bandit_high_med=0)
    result = controller.run(flawed_prompt)

    print("\n--- FINAL OPTIMIZED PYTHON CODE ---")
    print(result.final_code)
    print("=" * 75 + "\n")

    # Ensure the terminal run concludes with the clean before/after table
    if result.before_after_summary:
        print(result.before_after_summary.table)


if __name__ == "__main__":
    main()
