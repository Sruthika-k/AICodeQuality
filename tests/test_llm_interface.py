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


def test_missing_api_key_raises_value_error():
    """Verify that an empty or missing API key raises ValueError clearly."""
    import pytest
    with patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=True):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
            LLMInterface(api_key=None)


def test_successful_mocked_generation():
    """Verify standard clean code extraction on success."""
    llm = LLMInterface(api_key="mock_key", model_name="gemini-2.5-flash")
    mock_resp = MagicMock()
    mock_resp.text = "```python\ndef add(a, b):\n    return a + b\n```"
    llm.model.generate_content = MagicMock(return_value=mock_resp)

    res = llm.generate("Write an adder")
    assert res == "def add(a, b):\n    return a + b"
    llm.model.generate_content.assert_called_once()


def test_malformed_and_empty_response_handling():
    """Verify that empty responses or responses without candidates raise cleanly."""
    import pytest
    llm = LLMInterface(api_key="mock_key")
    empty_resp = MagicMock()
    empty_resp.text = ""
    empty_resp.candidates = []
    llm.model.generate_content = MagicMock(return_value=empty_resp)

    with pytest.raises(RuntimeError, match="Gemini returned an empty response|Gemini returned no candidates"):
        llm.generate("Some prompt")


def test_403_permission_denied_not_retried():
    """Verify that 403 / permission denied fails immediately without retry."""
    import pytest
    from google.api_core import exceptions as g_exc
    from backend.app.llm_interface import GeminiAuthenticationError

    llm = LLMInterface(api_key="mock_key", max_retries=3)
    llm.model.generate_content = MagicMock(side_effect=g_exc.PermissionDenied("Invalid API key"))

    with pytest.raises(GeminiAuthenticationError):
        llm.generate("Prompt")

    assert llm.model.generate_content.call_count == 1


def test_429_resource_exhaustion_exhausts_retries():
    """Verify that 429 retries up to max_retries and raises GeminiRateLimitError."""
    import pytest
    from google.api_core import exceptions as g_exc
    from backend.app.llm_interface import GeminiRateLimitError

    llm = LLMInterface(api_key="mock_key", max_retries=3, retry_delay_seconds=0.001)
    llm.model.generate_content = MagicMock(side_effect=g_exc.ResourceExhausted("Quota exceeded"))

    with pytest.raises(GeminiRateLimitError):
        llm.generate("Prompt")

    assert llm.model.generate_content.call_count == 3


def test_timeout_handling_fails_immediately_without_retry():
    """Verify that timeout/deadline exceeded fails immediately on attempt 1 without retrying."""
    import pytest
    from google.api_core import exceptions as g_exc
    from backend.app.llm_interface import GeminiTimeoutError

    llm = LLMInterface(api_key="mock_key", max_retries=3, retry_delay_seconds=10.0, timeout=60)
    llm.model.generate_content = MagicMock(side_effect=g_exc.DeadlineExceeded("Deadline exceeded"))

    with pytest.raises(GeminiTimeoutError):
        llm.generate("Prompt")

    # Must be called exactly once: no retries and no backoff delay
    assert llm.model.generate_content.call_count == 1


