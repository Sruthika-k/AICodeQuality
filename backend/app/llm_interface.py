"""LLMInterface component for interacting with Google Gemini Flash models."""

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

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


class GeminiError(RuntimeError):
    """Base error for Gemini API integration failures."""


class GeminiAuthenticationError(GeminiError):
    """Raised for 403 or invalid authentication/permissions. Not retried."""


class GeminiRateLimitError(GeminiError):
    """Raised when 429 / quota / rate limit is exceeded."""


class GeminiTimeoutError(GeminiError):
    """Raised when Gemini request times out."""


class GeminiNetworkError(GeminiError):
    """Raised when connection/network fails."""


class GeminiInvalidRequestError(GeminiError):
    """Raised when prompt or request arguments are invalid (400). Not retried."""


class LLMInterface:
    """Client interface for Google Gemini Flash with automatic rate-limit retry and code extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
        timeout: int = 120,
    ):
        """Initialize LLMInterface from configuration or parameters."""
        raw_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.api_key = raw_key.strip() if raw_key else None
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_retries = max(1, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.timeout = timeout

        if not self.api_key:
            logger.error("GEMINI_API_KEY is not set or empty")
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide it in .env or as an environment variable."
            )

        # Configure google-generativeai client safely (never log API key)
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=(
                "You are an expert Python engineer specializing in automated code repair and security. "
                "Output ONLY valid, functional Python code. Do not wrap code in markdown formatting or add explanations."
            ),
        )
        logger.info(f"LLMInterface initialized with model: {self.model_name}")

    def _extract_response_text(self, response: Any) -> str:
        """Extract text content from Gemini response safely, handling candidate blocks."""
        if response is None:
            raise RuntimeError("Gemini returned an empty response")

        # Try direct text attribute if available and not blocked
        try:
            if hasattr(response, "text") and response.text:
                return str(response.text)
        except Exception as exc:
            logger.warning(f"Could not read response.text directly: {exc}")

        # Check candidate parts if direct text raised (e.g. safety block or empty parts)
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            finish_reason = getattr(cand, "finish_reason", None)
            # FinishReason.MAX_TOKENS is 2 in google.generativeai / protobuf enum
            if finish_reason in (2, "MAX_TOKENS", "FinishReason.MAX_TOKENS"):
                logger.warning("Gemini generation reached MAX_TOKENS limit; candidate text may be truncated.")
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", "")
                if text:
                    return str(text)

        # If candidates exist but contain finish_reason block or no text
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            raise RuntimeError(f"Gemini response contained no text (finish_reason: {finish_reason})")

        raise RuntimeError("Gemini returned no candidates or valid text output")

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = 3000,
        **kwargs,
    ) -> str:
        """Call Gemini Flash with the given prompt, retry on rate-limits, and return clean Python code.

        Args:
            prompt: Instruction and source code prompt for the model.
            temperature: Optional sampling temperature. Omitted uses the model default.
            max_output_tokens: Optional max tokens to prevent unbounded output length (default: 3000).

        Returns:
            Clean Python source code without markdown fences.

        Raises:
            ValueError / GeminiInvalidRequestError: For invalid arguments / prompt (400)
            GeminiAuthenticationError: For permission/auth failures (403)
            GeminiRateLimitError / RuntimeError: For rate limit exhaustion (429)
            GeminiTimeoutError: If the request times out
            GeminiNetworkError: On connection/network failures
            RuntimeError: For other API failures or malformed outputs
        """
        if not prompt or not prompt.strip():
            raise GeminiInvalidRequestError("Prompt must not be empty.")

        generate_kwargs = {}
        gen_config_kwargs = {}
        if temperature is not None:
            gen_config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            gen_config_kwargs["max_output_tokens"] = max_output_tokens

        if gen_config_kwargs:
            generate_kwargs["generation_config"] = genai.types.GenerationConfig(**gen_config_kwargs)

        # Pass request timeout to prevent indefinite hangs
        if self.timeout is not None:
            generate_kwargs["request_options"] = {"timeout": float(self.timeout)}

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"LLM generate call (attempt {attempt}/{self.max_retries})")
            try:
                response = self.model.generate_content(prompt, **generate_kwargs)
                raw_text = self._extract_response_text(response)
                extracted_code = strip_markdown_fences(raw_text)
                if not extracted_code.strip():
                    raise RuntimeError("Gemini returned an empty code response")
                logger.info(f"LLM generate succeeded on attempt {attempt}")
                return extracted_code

            except (google_exceptions.PermissionDenied, google_exceptions.Unauthenticated) as exc:
                # 403 / 401 — do NOT retry
                logger.error(f"Gemini access/permission problem (403): {type(exc).__name__}")
                raise GeminiAuthenticationError("Gemini access/permission problem (403): Invalid API key or permission denied.") from exc

            except google_exceptions.InvalidArgument as exc:
                # 400 — do NOT retry
                logger.error(f"Invalid Gemini request/configuration (400): {type(exc).__name__}")
                raise GeminiInvalidRequestError(f"Invalid Gemini request/configuration (400): {str(exc)}") from exc

            except (TimeoutError, google_exceptions.DeadlineExceeded) as exc:
                # Timeouts fail immediately — do NOT retry to prevent long cascade hangs
                logger.warning(f"Gemini request timed out on attempt {attempt}/{self.max_retries}")
                raise GeminiTimeoutError("Gemini request timed out.") from exc

            except (google_exceptions.ResourceExhausted, google_exceptions.TooManyRequests) as exc:
                last_exception = exc
                logger.warning(f"Gemini quota/rate-limit problem (429) on attempt {attempt}/{self.max_retries}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    time.sleep(sleep_time)
                    continue
                raise GeminiRateLimitError("Gemini quota/rate-limit problem (429): API rate limit exceeded.") from exc

            except (google_exceptions.ServiceUnavailable, google_exceptions.InternalServerError) as exc:
                last_exception = exc
                logger.warning(f"Gemini service unavailable on attempt {attempt}/{self.max_retries}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    time.sleep(sleep_time)
                    continue
                raise GeminiNetworkError("Gemini connection failure: service temporarily unavailable.") from exc

            except Exception as exc:
                # Inspect for string-based rate limit / network / permission signals if wrapped
                exc_str = str(exc).lower()
                if is_rate_limit_error(exc):
                    last_exception = exc
                    logger.warning(f"Gemini rate limit error on attempt {attempt}/{self.max_retries}")
                    if attempt < self.max_retries:
                        sleep_time = self.retry_delay_seconds * attempt
                        time.sleep(sleep_time)
                        continue
                    raise GeminiRateLimitError(f"Gemini quota/rate-limit problem: {str(exc)}") from exc

                if "permission denied" in exc_str or "unauthenticated" in exc_str or "403" in exc_str:
                    logger.error("Gemini access/permission problem (403)")
                    raise GeminiAuthenticationError("Gemini access/permission problem (403): Invalid API key or permission denied.") from exc

                if "invalid argument" in exc_str or "400" in exc_str:
                    logger.error("Invalid Gemini request (400)")
                    raise GeminiInvalidRequestError(f"Invalid Gemini request: {str(exc)}") from exc

                if "timed out" in exc_str or "timeout" in exc_str or "deadline exceeded" in exc_str:
                    logger.warning(f"Timeout on attempt {attempt}/{self.max_retries}")
                    raise GeminiTimeoutError("Gemini request timed out.") from exc

                if "connection" in exc_str or "network" in exc_str or "unavailable" in exc_str:
                    last_exception = exc
                    logger.warning(f"Network error on attempt {attempt}/{self.max_retries}")
                    if attempt < self.max_retries:
                        sleep_time = self.retry_delay_seconds * attempt
                        time.sleep(sleep_time)
                        continue
                    raise GeminiNetworkError(f"Gemini connection failure: {str(exc)}") from exc

                last_exception = exc
                logger.error(f"Unexpected LLM error on attempt {attempt}: {type(exc).__name__}")
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay_seconds * attempt
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Gemini generation failed: {str(exc)}") from exc

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
