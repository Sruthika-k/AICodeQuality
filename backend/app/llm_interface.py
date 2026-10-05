"""LLMInterface component for interacting with Google Gemini Flash models."""

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)

# Load environment variables from workspace root or backend .env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences and surrounding text, returning only the code.

    Args:
        text: Raw LLM response string.

    Returns:
        Clean Python source code without markdown fences.
    """
    if not text:
        return ""

    # Match closed code blocks: ```python ... ``` or ``` ... ```
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # Take the longest matching code block
        longest_block = max(matches, key=len)
        return longest_block.strip()

    # Match unclosed fence if the model output was truncated or omitted closing fence
    open_pattern = r"```(?:python|py)?\s*\n(.*)"
    match_open = re.search(open_pattern, text, re.DOTALL)
    if match_open:
        code_part = match_open.group(1)
        code_part = re.sub(r"```.*$", "", code_part, flags=re.DOTALL)
        return code_part.strip()

    # Fallback to trimmed text if no markdown fences exist
    return text.strip()


def is_rate_limit_error(exc: Exception) -> bool:
    """Determine whether an exception indicates a rate-limit (429/ResourceExhausted) error."""
    if isinstance(exc, (google_exceptions.ResourceExhausted, google_exceptions.TooManyRequests)):
        return True
    exc_str = str(exc).lower()
    return "429" in exc_str or "resourceexhausted" in exc_str or "rate limit" in exc_str or "quota exceeded" in exc_str


class LLMInterface:
    """Client interface for Google Gemini Flash with automatic rate-limit retry and code extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
        timeout: int = 60,
    ):
        """Initialize LLMInterface from configuration or parameters."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.timeout = timeout

        if not self.api_key:
            logger.error("GEMINI_API_KEY not configured")
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide it in .env or as an environment variable."
            )

        # Configure google-generativeai client
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=(
                "You are an expert Python engineer specializing in automated code repair and security. "
                "Output ONLY valid, functional Python code. Do not wrap code in markdown formatting or add explanations."
            ),
        )
        logger.info(f"LLMInterface initialized with model: {self.model_name}")

    def generate(self, prompt: str, temperature: Optional[float] = None) -> str:
        """Call Gemini Flash with the given prompt, retry on rate-limits, and return clean Python code.

        Args:
            prompt: Instruction and source code prompt for the model.
            temperature: Optional sampling temperature. Omitted uses the model default.

        Returns:
            Clean Python source code without markdown fences.

        Raises:
            ValueError: If API key is missing
            RuntimeError: If rate limit is exceeded
            TimeoutError: If request times out
            Exception: For other API failures
        """
        last_exception: Optional[Exception] = None
        prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
        logger.info(f"LLM generate call (attempt 1/{self.max_retries})")
        generate_kwargs = {}
        if temperature is not None:
            generate_kwargs["generation_config"] = genai.types.GenerationConfig(temperature=temperature)

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.model.generate_content(prompt, **generate_kwargs)
                raw_text = getattr(response, "text", "") or ""
                logger.info(f"LLM generate succeeded on attempt {attempt}")
                return strip_markdown_fences(raw_text)

            except google_exceptions.ResourceExhausted as exc:
                last_exception = exc
                logger.warning(f"Rate limit error on attempt {attempt}/{self.max_retries}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    logger.info(f"Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError("API rate limit exceeded. Please try again later.") from exc

            except google_exceptions.InvalidArgument as exc:
                logger.error(f"Invalid API argument: {str(exc)}")
                raise ValueError("Invalid request to API") from exc

            except google_exceptions.PermissionDenied as exc:
                logger.error(f"API permission denied: {str(exc)}")
                raise ValueError("Invalid API key or permissions") from exc

            except google_exceptions.ServiceUnavailable as exc:
                last_exception = exc
                logger.warning(f"Service unavailable on attempt {attempt}/{self.max_retries}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError("API service unavailable. Please try again later.") from exc

            except Exception as exc:
                last_exception = exc
                logger.error(f"Unexpected LLM error on attempt {attempt}: {type(exc).__name__}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"LLM generation failed: {str(exc)}") from exc

        if last_exception:
            raise last_exception
        raise RuntimeError("Failed to generate code: Unknown error")


_default_instance: Optional[LLMInterface] = None


def generate(prompt: str) -> str:
    """Module-level function calling Gemini Flash to generate code from a prompt.

    Args:
        prompt: Instruction and source code prompt for the model.

    Returns:
        Clean Python source code with markdown fences stripped.
    """
    global _default_instance
    if _default_instance is None:
        _default_instance = LLMInterface()
    return _default_instance.generate(prompt)
