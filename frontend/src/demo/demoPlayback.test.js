import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import App from "../App";
import recordedRun01 from "./recorded_run_01.json";
import { validateRecording, RECORDING_LOAD_ERROR } from "./validateRecording";
import { recordingToUiResult } from "./recordingToResult";
import { createPlayback, mapEventToPipelineStage } from "./playbackEngine";

describe("recorded-run validation", () => {
  it("accepts the bundled test fixture", () => {
    const check = validateRecording(recordedRun01);
    expect(check.ok).toBe(true);
    expect(recordedRun01.recording_type).toBe("test_fixture");
  });

  it("rejects an invalid recording", () => {
    const check = validateRecording({ recording_version: "1.0" });
    expect(check.ok).toBe(false);
    expect(check.error).toBe(RECORDING_LOAD_ERROR);
  });
});

describe("recordingToUiResult", () => {
  it("preserves recorded metrics and diffs", () => {
    const result = recordingToUiResult(recordedRun01);
    expect(result.final_pylint_score).toBe(9.2);
    expect(result.final_bandit_high_medium).toBe(0);
    expect(result.unified_diff).toContain("ast.literal_eval");
    expect(result.iterations).toHaveLength(2);
    expect(result.decision_reason).toBe("ACCEPTED_CONSTRAINED_OK");
  });
});

describe("playback engine", () => {
  it("advances pipeline stages using recorded timing", () => {
    vi.useFakeTimers();
    const stages = [];
    const controller = createPlayback({
      timingEvents: [
        { stage: "input", duration_ms: 100 },
        { stage: "gemini", duration_ms: 100 },
        { stage: "bandit", duration_ms: 100 },
      ],
      speed: 1,
      iterationCount: 2,
      onStage: ({ active }) => stages.push(active),
      onComplete: () => stages.push("complete"),
    });
    controller.start();
    vi.runAllTimers();
    expect(stages).toContain("input");
    expect(stages).toContain("gemini");
    expect(stages).toContain("analysis");
    expect(stages.at(-1)).toBe("complete");
    expect(mapEventToPipelineStage("pylint")).toBe("analysis");
    vi.useRealTimers();
  });
});

describe("Demo (recorded run) UI", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("loads the JSON locally and never calls optimize, review, or any LLM", async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId("demo-mode-btn"));
    expect(screen.getByTestId("demo-badge").textContent).toMatch(/TEST FIXTURE/);
    expect(screen.getByText("Demo (test fixture)")).toBeTruthy();
    expect(screen.getByText("NOT A REAL EXPERIMENTAL RUN")).toBeTruthy();

    fireEvent.click(screen.getByTestId("skip-btn"));

    expect(globalThis.fetch).not.toHaveBeenCalled();
    const urls = (globalThis.fetch.mock.calls || []).map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/api/optimize"))).toBe(false);
    expect(urls.some((u) => u.includes("/api/review"))).toBe(false);

    expect(screen.getByTestId("playback-llm-calls").textContent).toBe("0");
    expect(screen.getByTestId("playback-api-calls").textContent).toBe("0");
    expect(screen.getByTestId("results")).toBeTruthy();
    expect(screen.getByTestId("iteration-timeline")).toBeTruthy();
    expect(screen.getByTestId("code-comparison")).toBeTruthy();
    expect(screen.getByTestId("acceptance-card").textContent).toMatch(/ACCEPTED/);
    expect(screen.getByTestId("acceptance-reason").textContent).toContain("ACCEPTED_CONSTRAINED_OK");
    expect(screen.getByTestId("final-code").textContent).toContain("literal_eval");
    expect(screen.getByTestId("pipeline-stage-best").className).toMatch(/done|running/);
    expect(screen.getByTestId("metrics-dashboard")).toBeTruthy();
    expect(document.body.textContent).toMatch(/Pylint/);
    expect(document.body.textContent).toMatch(/9\.2/);
  });
});
