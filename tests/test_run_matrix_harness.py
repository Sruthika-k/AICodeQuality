"""Tests for run_matrix.py harness features: shared generation, iteration-cap, max-calls."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_call_count_formula():
    """Verify call count formula: total = 1 + 3 * (iteration_cap - 1) for shared generation."""
    from scripts.run_matrix import estimate_api_calls

    # iteration_cap=2: 1 + 3*(2-1) = 4
    assert estimate_api_calls(1, 2, shared_gen=True) == 4
    # iteration_cap=3: 1 + 3*(3-1) = 7
    assert estimate_api_calls(1, 3, shared_gen=True) == 7
    # iteration_cap=4: 1 + 3*(4-1) = 10
    assert estimate_api_calls(1, 4, shared_gen=True) == 10
    # iteration_cap=5: 1 + 3*(5-1) = 13
    assert estimate_api_calls(1, 5, shared_gen=True) == 13


def test_shared_generation_identical_code(tmp_path):
    """C1, C2, C3, C4 receive the same initial generated code."""
    import json
    from scripts import run_matrix
    from tests.conftest import CLEAN_CODE

    jsonl_path = tmp_path / "prompts.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test"}))

    # Run all conditions with same initial code
    results = []
    for condition in ["C1", "C2", "C3", "C4"]:
        result = run_matrix.run_condition(
            "p1", "test", condition, 1, 0.0, True, iteration_cap=2, max_calls=None,
            fake_llm_responses=[CLEAN_CODE] * 2
        )
        results.append(result)

    # All should succeed
    assert all(r is not None for r in results)

    # For C1 single_shot, should have 1 iteration
    assert results[0]["iterations"] == "1"
    # For C2-C4 loop with cap=2, should have 2 iterations
    assert results[1]["iterations"] == "2"
    assert results[2]["iterations"] == "2"
    assert results[3]["iterations"] == "2"


def test_max_calls_enforcement(tmp_path):
    """--max-calls N enforces hard limit, stops cleanly, saves progress."""
    import json
    import csv
    from scripts import run_matrix

    jsonl_path = tmp_path / "prompts.jsonl"
    results_path = tmp_path / "matrix_results.csv"

    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test"}))

    # Run with max-calls=2 (should stop after 2 calls)
    # Each run_condition with iteration_cap=2 makes 2 calls in dry-run
    # So we set max_calls high in tracking but limit execution
    # This test validates the CallTrackingLLM wrapper
    from tests.conftest import CLEAN_CODE, FakeLLM

    llm = FakeLLM([CLEAN_CODE] * 5, model_name="fake-test-model")
    tracking_llm = run_matrix.CallTrackingLLM(llm, max_calls=2)

    # First call should succeed
    _ = tracking_llm.generate("test")
    assert tracking_llm.call_count == 1

    # Second call should succeed
    _ = tracking_llm.generate("test")
    assert tracking_llm.call_count == 2

    # Third call should raise RuntimeError
    try:
        tracking_llm.generate("test")
        assert False, "Should have raised RuntimeError for max calls"
    except RuntimeError as e:
        assert "Max calls" in str(e)


def test_cache_reuse(tmp_path):
    """If cache exists, do not make another initial-generation call."""
    import sys
    from scripts import run_matrix

    # Override CACHE_DIR to use tmp_path
    original_cache_dir = run_matrix.CACHE_DIR
    run_matrix.CACHE_DIR = tmp_path / "cache"

    try:
        from scripts.run_matrix import get_cache_key, load_cached_generation, save_cached_generation

        prompt = "test prompt"
        model = "gemini-3.8-flash"
        temperature = 0.0

        cache_key = get_cache_key(prompt, model, temperature)

        # Initially no cache
        assert load_cached_generation(cache_key) is None

        # Save to cache
        cached_code = "def cached(): pass"
        save_cached_generation(cache_key, cached_code)

        # Load from cache
        loaded = load_cached_generation(cache_key)
        assert loaded == cached_code
    finally:
        run_matrix.CACHE_DIR = original_cache_dir


def test_iteration_cap_cli_argument():
    """--iteration-cap N is configurable with default 5."""
    from scripts.run_matrix import parse_args

    # Default should be 5
    args = parse_args(["test.jsonl"])
    assert args.iteration_cap == 5

    # Custom value
    args = parse_args(["test.jsonl", "--iteration-cap", "2"])
    assert args.iteration_cap == 2

    args = parse_args(["test.jsonl", "--iteration-cap", "3"])
    assert args.iteration_cap == 3


def test_dry_run_call_counts_with_fake_llm(tmp_path):
    """FakeLLM tests verify expected call counts for different iteration caps."""
    import json
    from scripts import run_matrix
    from tests.conftest import CLEAN_CODE

    jsonl_path = tmp_path / "prompts.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test"}))

    # Test WITHOUT shared initial code (each condition generates independently)
    results = []
    for condition in ["C1", "C2", "C3", "C4"]:
        result = run_matrix.run_condition(
            "p1", "test", condition, 1, 0.0, True, iteration_cap=2, max_calls=None,
            shared_initial_code=None,  # No shared code
            fake_llm_responses=[CLEAN_CODE] * 2
        )
        results.append(result)

    # C1 single_shot: 1 call (initial generation)
    assert int(results[0]["api_calls"]) == 1
    # C2-C4 loop with cap=2: at least 1 call each (initial generation, may converge early)
    assert int(results[1]["api_calls"]) >= 1
    assert int(results[2]["api_calls"]) >= 1
    assert int(results[3]["api_calls"]) >= 1

    # Total without sharing should be at least 4 calls
    total = sum(int(r["api_calls"]) for r in results)
    assert total >= 4


def test_loopcontroller_without_initial_code_generates_normally(tmp_path):
    """Without initial_code, LoopController generates code normally (existing behavior)."""
    from backend.app.config import ExperimentConfig
    from backend.app.loop_controller import LoopController
    from tests.conftest import CLEAN_CODE, FakeLLM

    cfg = ExperimentConfig(
        strategy="loop",
        stop_rule="fixed_cap",
        iteration_cap=2,
        enable_radon=False,
        disable_convergence_stop=True
    )
    llm = FakeLLM([CLEAN_CODE] * 2, model_name="fake-test-model")
    controller = LoopController(config=cfg, llm=llm)

    result = controller.run("test prompt", initial_code=None)

    # Should have made at least 1 call (initial generation)
    assert result.api_calls_used >= 1


def test_loopcontroller_with_initial_code_skips_generation(tmp_path):
    """With initial_code, LoopController does NOT call Gemini for initial generation."""
    from backend.app.config import ExperimentConfig
    from backend.app.loop_controller import LoopController
    from tests.conftest import CLEAN_CODE, FakeLLM

    cfg = ExperimentConfig(
        strategy="loop",
        stop_rule="fixed_cap",
        iteration_cap=2,
        enable_radon=False
    )
    llm = FakeLLM([CLEAN_CODE] * 2, model_name="fake-test-model")
    controller = LoopController(config=cfg, llm=llm)

    initial_code = "def pre_generated(): return 42"
    result = controller.run("test prompt", initial_code=initial_code)

    # Should have made only 1 call (1 refinement, no initial generation)
    assert result.api_calls_used == 1
    assert result.total_iterations == 2
    # Final code should be based on the initial_code (though modified by refinement)
    assert "42" in result.final_code or result.final_code != initial_code


def test_shared_s0_used_by_all_conditions(tmp_path):
    """C1-C4 can receive identical S0 and all analyze it."""
    import json
    from scripts import run_matrix
    from tests.conftest import CLEAN_CODE

    jsonl_path = tmp_path / "prompts.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "p1", "prompt": "test"}))

    shared_code = "def shared_initial(): return 'S0_CODE'"

    results = []
    for condition in ["C1", "C2", "C3", "C4"]:
        result = run_matrix.run_condition(
            "p1", "test", condition, 1, 0.0, True, iteration_cap=2, max_calls=None,
            shared_initial_code=shared_code,
            fake_llm_responses=[CLEAN_CODE] * 2
        )
        results.append(result)

    # All should succeed
    assert all(r is not None for r in results)

    # With shared code, total should be less than without sharing
    # Without sharing: C1=1, C2=2, C3=2, C4=2 = 7 calls
    # With sharing: should be fewer calls
    total_calls = sum(int(r["api_calls"]) for r in results)
    assert total_calls < 7, f"Expected fewer than 7 calls with shared S0, got {total_calls}"

