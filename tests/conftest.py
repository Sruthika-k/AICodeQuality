"""Shared fixtures and helpers: FakeLLM, code samples."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Use temporary directory for test logs to avoid polluting production logs
TEST_LOGS_DIR = tempfile.mkdtemp(prefix="aicq_test_logs_")

# Override logs directory for tests
import os
os.environ["TEST_LOGS_DIR"] = TEST_LOGS_DIR

CLEAN_CODE = '''"""Clean utility module."""

import math


def sum_two(left: int, right: int) -> int:
    """Return the sum of two integers.

    Args:
        left: First operand.
        right: Second operand.

    Returns:
        Integer sum.
    """
    return left + right


def hypotenuse(a: float, b: float) -> float:
    """Compute hypotenuse length for right triangle legs a and b."""
    return math.sqrt(a * a + b * b)
'''


INSECURE_DIRTY_CODE = '''import os
import subprocess
def BADFunc(X,Y,Z):
    password = "hardcoded_secret_123"
    eval(X)
    subprocess.call(Y, shell=True)
    os.system(Z)
    print(password)
'''


class FakeLLM:
    """Scripted LLM replacement. Returns the next code from a list; records call count.

    Callers may also pass ``error_on_call`` (1-indexed) to raise a rate-limit-style
    exception on that specific call, simulating transient provider outages.
    """

    class RateLimitError(Exception):
        """Stand-in for google ResourceExhausted."""

        def __str__(self) -> str:  # pragma: no cover - trivial
            return "429 ResourceExhausted: Quota exceeded"

    def __init__(
        self,
        responses: Sequence[str],
        *,
        model_name: str = "fake-llm",
        error_on_call: Optional[int] = None,
        error_factory: Optional[Callable[[], BaseException]] = None,
    ) -> None:
        self.responses = list(responses)
        self.model_name = model_name
        self.call_count = 0
        self.error_on_call = error_on_call
        self.error_factory = error_factory

    def generate(self, prompt: str, temperature: Optional[float] = None, **kwargs) -> str:
        del prompt, temperature, kwargs
        self.call_count += 1
        if self.error_on_call is not None and self.call_count == self.error_on_call:
            if self.error_factory is not None:
                raise self.error_factory()
            raise FakeLLM.RateLimitError()
        if self.responses:
            return self.responses.pop(0)
        return ""


def pytest_configure(config):
    """Persistent test: verify replay_plateau.py imports nothing from LLM/Gemini."""
    import ast
    replay_script = PROJECT_ROOT / "scripts" / "replay_plateau.py"
    
    if replay_script.exists():
        with replay_script.open("r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source)
        forbidden_modules = ["llm_interface", "gemini", "google"]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.lower()
                    for forbidden in forbidden_modules:
                        assert forbidden not in module_name, \
                            f"replay_plateau.py imports forbidden module: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.lower()
                    for forbidden in forbidden_modules:
                        assert forbidden not in module_name, \
                            f"replay_plateau.py imports forbidden module: {node.module}"
