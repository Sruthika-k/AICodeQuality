"""Recorder and recording validation tests. Does not call Gemini."""

import ast

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = PROJECT_ROOT / "scripts" / "save_recorded_run.py"
_SPEC = importlib.util.spec_from_file_location("save_recorded_run", _MODULE_PATH)
save_recorded_run = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(save_recorded_run)

LOAD_ERROR = save_recorded_run.LOAD_ERROR
build_recording = save_recorded_run.build_recording
extract_result_payload = save_recorded_run.extract_result_payload
main = save_recorded_run.main
validate_recording = save_recorded_run.validate_recording

SAMPLE_RESULT = {
    "prompt": "Write add",
    "final_code": "def add(a, b):\n    return a + b\n",
    "converged": True,
    "total_iterations": 2,
    "final_pylint_score": 9.0,
    "final_bandit_high_medium": 0,
    "status": "CONVERGED",
    "iteration_cap": 2,
    "pylint_threshold": 8.0,
    "metrics_summary": {
        "initial_iteration": 1,
        "final_iteration": 2,
        "total_iterations": 2,
        "converged": True,
        "initial_pylint_score": 4.0,
        "final_pylint_score": 9.0,
        "pylint_score_delta": 5.0,
        "initial_total_issues": 1,
        "final_total_issues": 0,
        "issues_eliminated": 1,
        "table": "t",
        "initial_avg_complexity": 2.0,
        "final_avg_complexity": 1.0,
        "initial_maintainability_index": 40.0,
        "final_maintainability_index": 80.0,
    },
    "iterations": [
        {
            "iteration": 1,
            "code": "def add(a,b):\n    return eval('a+b')\n",
            "pylint_score": 4.0,
            "bandit_high_medium_count": 1,
            "issues": [
                {"tool": "bandit", "severity": "HIGH", "line": 2, "message": "eval", "rule_id": "B307"}
            ],
            "accepted": True,
            "acceptance_reason": "ACCEPTED_INITIAL",
            "diff": None,
        },
        {
            "iteration": 2,
            "code": "def add(a, b):\n    return a + b\n",
            "pylint_score": 9.0,
            "bandit_high_medium_count": 0,
            "issues": [],
            "accepted": True,
            "acceptance_reason": "ACCEPTED_CONSTRAINED_OK",
            "diff": "--- a\n+++ b\n",
        },
    ],
}


def test_recorder_has_no_llm_imports():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not (imports & {"llm_interface", "gemini", "google", "backend"})


def test_fixture_json_is_not_labeled_real_run():
    path = PROJECT_ROOT / "frontend" / "src" / "demo" / "recorded_run_01.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_recording(data)
    assert data["recording_type"] == "test_fixture"
    assert data["recording_type"] != "real_run"


def test_build_recording_defaults_to_test_fixture():
    rec = build_recording(
        SAMPLE_RESULT,
        recording_type="test_fixture",
        recording_id="t1",
        model="none-test-fixture",
        mode="generate",
    )
    assert rec["recording_type"] == "test_fixture"
    assert rec["result"]["final_pylint_score"] == 9.0
    assert rec["issue_evolution"]["resolved"][0]["rule_id"] == "B307"
    assert rec["diffs"]["unified"] == "--- a\n+++ b\n"


def test_validate_rejects_missing_fields():
    try:
        validate_recording({"recording_version": "1.0"})
        assert False, "expected error"
    except ValueError as exc:
        assert str(exc) == LOAD_ERROR


def test_csv_like_input_is_rejected():
    try:
        extract_result_payload({"timestamp": "x", "api_calls": 2})
        assert False, "expected error"
    except ValueError as exc:
        assert "CSV" in str(exc) or "iterations" in str(exc)


def test_cli_writes_recording(tmp_path):
    src = tmp_path / "result.json"
    src.write_text(json.dumps(SAMPLE_RESULT), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = main([str(src), "--output-dir", str(out_dir), "--model", "none-test-fixture"])
    assert rc == 0
    files = list(out_dir.glob("recorded_run_*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["recording_type"] == "test_fixture"
    assert saved["result"]["final_code"] == SAMPLE_RESULT["final_code"]


def test_cli_requires_model_for_real_run(tmp_path):
    src = tmp_path / "result.json"
    src.write_text(json.dumps(SAMPLE_RESULT), encoding="utf-8")
    try:
        main([str(src), "--output-dir", str(tmp_path), "--confirm-real-run"])
        assert False, "expected error"
    except ValueError:
        pass
