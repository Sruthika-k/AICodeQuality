"""Tiny script to test LLMInterface generation with Gemini Flash."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.llm_interface import generate


def main():
    test_prompt = (
        "Write a Python function named `fibonacci(n)` that returns the n-th Fibonacci number. "
        "Include module and function docstrings and type annotations. "
        "Output Python code only."
    )
    print("Sending prompt to Gemini Flash via LLMInterface.generate()...\n")
    code = generate(test_prompt)
    print("=== GENERATED PYTHON CODE ===")
    print(code)
    print("=============================")


if __name__ == "__main__":
    main()
