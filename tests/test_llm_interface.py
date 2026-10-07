"""Unit tests for the LLMInterface component."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.llm_interface import (
    LLMInterface,
    is_rate_limit_error,
    strip_markdown_fences,
)


def test_strip_markdown_fences_with_python_tag():
    """Verify that ```python fences are cleanly stripped."""
    raw = "```python\ndef hello():\n    return 'world'\n```"
    cleaned = strip_markdown_fences(raw)
    assert cleaned == "def hello():\n    return 'world'"


def test_strip_markdown_fences_with_conversational_text():
    """Verify that commentary before or after code fences is stripped."""
    raw = (
        "Here is the fixed Python code:\n"
        "```python\ndef compute(x: int) -> int:\n    return x * 2\n```\n"
        "Let me know if you need any adjustments!"
    )
    cleaned = strip_markdown_fences(raw)
    assert cleaned == "def compute(x: int) -> int:\n    return x * 2"


def test_strip_markdown_fences_without_fences():
    """Verify that code already without fences is preserved."""
    raw = "def add(a, b):\n    return a + b"
    cleaned = strip_markdown_fences(raw)
    assert cleaned == raw


def test_is_rate_limit_error_detection():
    """Verify rate-limit error identification logic."""
    err_429 = Exception("429 ResourceExhausted: Quota exceeded")
    err_val = ValueError("Invalid syntax")

    assert is_rate_limit_error(err_429) is True
    assert is_rate_limit_error(err_val) is False


def test_rate_limit_retry_behavior():
    """Verify that generate() retries upon receiving a rate-limit error."""
    llm = LLMInterface(api_key="mock_key", model_name="gemini-2.5-flash", max_retries=3, retry_delay_seconds=0.01)

    mock_response = MagicMock()
    mock_response.text = "```python\ndef fixed():\n    return True\n```"

    # Simulate rate-limit error on first call, success on second
    rate_limit_exc = Exception("429 ResourceExhausted: Rate limit reached")
    llm.model.generate_content = MagicMock(side_effect=[rate_limit_exc, mock_response])

    result = llm.generate("Fix this code")
    assert result == "def fixed():\n    return True"
    assert llm.model.generate_content.call_count == 2
