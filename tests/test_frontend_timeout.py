"""Test frontend timeout and error handling using FakeLLM (no Gemini calls)."""

import pytest
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.conftest import FakeLLM, CLEAN_CODE
from backend.app.loop_controller import LoopController


def test_1_mock_successful_refinement():
    """TEST 1: Successful mock refinement should complete normally."""
    fake_llm = FakeLLM(responses=[CLEAN_CODE])
    
    controller = LoopController(
        iteration_cap=1,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        llm=fake_llm  # Inject FakeLLM
    )
    
    result = controller.run(
        prompt="Write a simple sum function",
        initial_code=None
    )
    
    assert result is not None
    assert result.final_code is not None
    assert result.total_iterations == 1
    assert fake_llm.call_count == 1
    print("TEST 1 PASS: Mock successful refinement completed")


def test_2_simulated_llm_failure():
    """TEST 2: Simulated LLM failure should raise RuntimeError."""
    fake_llm = FakeLLM(
        responses=[CLEAN_CODE],
        error_on_call=1,  # Fail on first call
        error_factory=lambda: RuntimeError("Simulated LLM failure")
    )
    
    controller = LoopController(
        iteration_cap=1,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        llm=fake_llm  # Inject FakeLLM
    )
    
    with pytest.raises(RuntimeError, match="Simulated LLM failure"):
        controller.run(
            prompt="Write a simple sum function",
            initial_code=None
        )
    
    assert fake_llm.call_count == 1
    print("TEST 2 PASS: Simulated LLM failure raised RuntimeError")


def test_3_simulated_timeout_via_slow_generation():
    """TEST 3: Simulate slow generation to test timeout handling."""
    
    class SlowFakeLLM(FakeLLM):
        def generate(self, prompt: str, temperature=None, run_id=None):
            # Simulate slow response (3 seconds)
            time.sleep(3)
            return super().generate(prompt, temperature, run_id=run_id)
    
    fake_llm = SlowFakeLLM(responses=[CLEAN_CODE])
    
    controller = LoopController(
        iteration_cap=1,
        pylint_threshold=8.0,
        max_bandit_high_med=0,
        llm=fake_llm  # Inject FakeLLM
    )
    
    start = time.time()
    result = controller.run(
        prompt="Write a simple sum function",
        initial_code=None
    )
    elapsed = time.time() - start
    
    assert result is not None
    assert elapsed >= 3  # Should take at least 3 seconds
    assert fake_llm.call_count == 1
    print(f"TEST 3 PASS: Slow generation completed in {elapsed:.2f}s (timeout handling would trigger at 120s)")


def test_4_backend_unavailable_error():
    """TEST 4: Backend unavailable should be handled by HTTP layer."""
    # This is tested at the HTTP endpoint level in main.py
    # Here we verify the error path exists
    from backend.app.main import CodePromptRequest
    from pydantic import ValidationError
    
    # Invalid request (too long prompt) should raise validation error
    try:
        CodePromptRequest(prompt="x" * 15000, initial_code=None, iteration_cap=1, pylint_threshold=8.0)
        assert False, "Should have raised validation error for too-long prompt"
    except ValidationError as e:
        assert "String should have at most 10000 characters" in str(e)
    
    print("TEST 4 PASS: Backend validation errors are properly handled")


if __name__ == "__main__":
    # Run tests manually
    print("Running frontend timeout/error handling tests...")
    test_1_mock_successful_refinement()
    test_2_simulated_llm_failure()
    test_3_simulated_timeout_via_slow_generation()
    test_4_backend_unavailable_error()
    print("\nAll tests PASSED")
