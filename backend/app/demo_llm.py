"""Offline demo LLM used when the client requests demo mode. No network calls."""

from typing import Optional

DEMO_CLEAN_CODE = '''"""Demo utility module."""


def add(left: int, right: int) -> int:
    """Return the sum of two integers.

    Args:
        left: First operand.
        right: Second operand.

    Returns:
        Integer sum.
    """
    return left + right
'''


class DemoLLM:
    """Returns a fixed clean snippet. Used for demo mode and never calls Gemini."""

    def __init__(self) -> None:
        self.model_name = "demo-local"
        self.call_count = 0

    def generate(self, prompt: str, temperature: Optional[float] = None) -> str:
        del prompt, temperature
        self.call_count += 1
        return DEMO_CLEAN_CODE
