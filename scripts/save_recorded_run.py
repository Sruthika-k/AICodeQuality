#!/usr/bin/env python3
"""Save a completed AICodeQuality run JSON as a frontend playback recording.

Does not call Gemini or any LLM. Reads an existing completed API/job result
and writes recordings/recorded_run_YYYYMMDD_HHMMSS.json.

Usage:
  python scripts/save_recorded_run.py path/to/result.json
  python scripts/save_recorded_run.py path/to/result.json --confirm-real-run --model gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "recordings"

DEFAULT_TIMING_EVENTS = [
    {"stage": "input", "duration_ms": 400},
    {"stage": "gemini", "duration_ms": 1400},
    {"stage": "bandit", "duration_ms": 500},
    {"stage": "pylint", "duration_ms": 700},
    {"stage": "radon", "duration_ms": 500},
    {"stage": "issue_extraction", "duration_ms": 400},
    {"stage": "feedback", "duration_ms": 800},
    {"stage": "refinement", "duration_ms": 1200},
    {"stage": "regression", "duration_ms": 600},
    {"stage": "acceptance", "duration_ms": 700},
    {"stage": "best", "duration_ms": 400},
]

LOAD_ERROR = "Recorded run could not be loaded."


def issue_key(issue: Dict[str, Any]) -> tuple:
    return (str(issue.get("tool") or ""), str(issue.get("rule_id") or ""))


def compute_issue_evolution(iterations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    if not iterations:
        return {"resolved": [], "introduced": [], "persistent": []}
    first = {issue_key(i): i for i in iterations[0].get("issues") or []}
    last = {issue_key(i): i for i in iterations[-1].get("issues") or []}
    resolved_keys = set(first) - set(last)
    introduced_keys = set(last) - set(first)
    persistent_keys = set(first) & set(last)

    def pack(keys, source):
        packed = []
        for key in sorted(keys):
            item = source[key]
            packed.append(
                {
                    "tool": item.get("tool"),
                    "rule_id": item.get("rule_id"),
                    "message": item.get("message"),
                }
            )
        return packed

    return {
        "resolved": pack(resolved_keys, first),
        "introduced": pack(introduced_keys, last),
        "persistent": pack(persistent_keys, last),
    }


def extract_result_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    if "result" in raw and isinstance(raw["result"], dict) and "final_code" in raw["result"]:
        return raw["result"]
    if "final_code" in raw and "iterations" in raw:
        return raw
    raise ValueError(
        "Input is not a completed API/job result. Provide JSON with final_code and iterations. "
        "CSV summaries cannot produce a recorded run."
    )


def validate_recording(recording: Dict[str, Any]) -> None:
    if not recording.get("recording_version"):
        raise ValueError(LOAD_ERROR)
    if not recording.get("recording_type"):
        raise ValueError(LOAD_ERROR)
    iterations = recording.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        raise ValueError(LOAD_ERROR)
    final = recording.get("final") or {}
    result = recording.get("result") or {}
    if not final.get("code") and not result.get("final_code"):
        raise ValueError(LOAD_ERROR)
    metrics = result.get("metrics_summary") or final.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError(LOAD_ERROR)


def build_recording(
    payload: Dict[str, Any],
    *,
    recording_type: str,
    recording_id: str,
    model: str,
    mode: str,
    timing_events: Optional[List[Dict[str, Any]]] = None,
    api_call_count: Optional[int] = None,
) -> Dict[str, Any]:
    iterations = payload.get("iterations") or []
    if not iterations:
        raise ValueError("Completed result has no iterations.")
    first = iterations[0]
    last = iterations[-1]
    summary = payload.get("metrics_summary") or {}
    unified = last.get("diff")
    original_code = first.get("code") or ""
    final_code = payload.get("final_code") or last.get("code") or ""
    timing_source = "recorded" if timing_events else "unavailable_using_playback_defaults"
    events = timing_events or DEFAULT_TIMING_EVENTS
    historical_calls = api_call_count
    if historical_calls is None:
        historical_calls = payload.get("api_call_count")
    if historical_calls is None:
        historical_calls = 0 if recording_type != "real_run" else None

    recording = {
        "recording_version": "1.0",
        "recording_type": recording_type,
        "recording_id": recording_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "timing_source": timing_source,
        "metadata": {
            "model": model,
            "mode": mode,
            "iteration_cap": payload.get("iteration_cap"),
        },
        "input": {
            "prompt": payload.get("prompt") or "",
            "original_code": original_code,
        },
        "configuration": {
            "pylint_threshold": payload.get("pylint_threshold"),
            "bandit_threshold": "high_medium_zero",
        },
        "api_call_count": historical_calls,
        "timing_events": events,
        "iterations": iterations,
        "issue_evolution": compute_issue_evolution(iterations),
        "diffs": {
            "original_code": original_code,
            "final_code": final_code,
            "unified": unified,
        },
        "final": {
            "code": final_code,
            "metrics": {
                "pylint_score": payload.get("final_pylint_score"),
                "bandit_high_medium": payload.get("final_bandit_high_medium"),
                "avg_complexity": summary.get("final_avg_complexity"),
                "maintainability_index": summary.get("final_maintainability_index"),
            },
            "decision": "accepted" if last.get("accepted", payload.get("converged")) else "rejected",
            "decision_reason": last.get("acceptance_reason"),
            "converged": payload.get("converged"),
            "status": payload.get("status"),
        },
        "result": payload,
    }
    validate_recording(recording)
    return recording


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Save a completed run as a playback recording.")
    parser.add_argument("input_json", type=Path, help="Completed /api/optimize or job result JSON")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--recording-id", default=None)
    parser.add_argument("--mode", default="generate", choices=["generate", "review"])
    parser.add_argument("--model", default="unknown")
    parser.add_argument(
        "--confirm-real-run",
        action="store_true",
        help="Label recording_type=real_run. Use only for a genuine LLM run JSON.",
    )
    parser.add_argument("--api-call-count", type=int, default=None)
    parser.add_argument("--timing-json", type=Path, default=None, help="Optional JSON list of timing events")
    args = parser.parse_args(argv)

    raw = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Input JSON must be an object.")
    payload = extract_result_payload(raw)
    timing = None
    if args.timing_json:
        timing = json.loads(args.timing_json.read_text(encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recording_type = "real_run" if args.confirm_real_run else "test_fixture"
    recording_id = args.recording_id or f"run_{stamp}"
    model = args.model
    if args.confirm_real_run and model in ("unknown", "none-test-fixture"):
        raise ValueError("Refusing to label real_run without --model of the actual LLM.")

    recording = build_recording(
        payload,
        recording_type=recording_type,
        recording_id=recording_id,
        model=model,
        mode=args.mode,
        timing_events=timing,
        api_call_count=args.api_call_count,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"recorded_run_{stamp}.json"
    out_path.write_text(json.dumps(recording, indent=2), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
