import React, { useEffect, useRef, useState } from "react";
import Header from "./components/Header";
import Pipeline from "./components/Pipeline";
import AnalysisTools from "./components/AnalysisTools";
import EmptyState from "./components/EmptyState";
import ResultsView from "./components/ResultsView";
import recordedRun01 from "./demo/recorded_run_01.json";
import { RECORDING_LOAD_ERROR, validateRecording } from "./demo/validateRecording";
import { recordingToUiResult, sliceResultThroughIteration } from "./demo/recordingToResult";
import { createPlayback } from "./demo/playbackEngine";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const SAMPLE_PROMPTS = [
  {
    label: "Flawed Math & Shell Utility (Triggers Eval & os.system)",
    prompt:
      "Write a Python utility with a function execute_command(user_input) that evaluates math expressions with eval() or executes system commands using os.system(). Keep it quick and concise without docstrings.",
  },
  {
    label: "Safe Data Processing (Clean Task)",
    prompt:
      "Write a Python module with a function calculate_statistics(numbers) that computes mean, median, and variance of a list of floats. Include type hints and complete docstrings.",
  },
  {
    label: "File Reader with Subprocess",
    prompt:
      "Write a Python script that takes a filename and prints line count, using subprocess.call('wc -l ' + filename, shell=True).",
  },
];

function enrichLiveResult(data) {
  const iterations = (data.iterations || []).map((it, idx) => ({
    ...it,
    accepted: it.accepted ?? (idx === 0 ? true : Boolean(it.threshold_met)),
    acceptance_reason:
      it.acceptance_reason ??
      (idx === 0 ? "ACCEPTED_INITIAL" : it.threshold_met ? "Converged" : "Improved metrics"),
    issues_eliminated: it.issues_eliminated ?? null,
    issues_introduced: it.issues_introduced ?? null,
  }));
  const last = iterations[iterations.length - 1];
  return {
    ...data,
    iterations,
    original_code: data.original_code || iterations[0]?.code || "",
    unified_diff: data.unified_diff || last?.diff || null,
    issue_evolution: data.issue_evolution || { resolved: null, introduced: null, persistent: null },
    decision: data.decision || (last?.accepted ? "accepted" : data.converged ? "accepted" : "rejected"),
    decision_reason: data.decision_reason || last?.acceptance_reason || null,
  };
}

export default function App() {
  const [prompt, setPrompt] = useState(SAMPLE_PROMPTS[0].prompt);
  const [code, setCode] = useState("");
  const [mode, setMode] = useState("generate");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [diffMode, setDiffMode] = useState("side-by-side");
  const [iterationCap, setIterationCap] = useState(3);
  const [pylintThreshold, setPylintThreshold] = useState(8.0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [pipelineActive, setPipelineActive] = useState(null);
  const [pipelineCompleted, setPipelineCompleted] = useState([]);
  const [activeTool, setActiveTool] = useState(null);
  const [playbackLlmCalls, setPlaybackLlmCalls] = useState(0);
  const [liveApiCalls, setLiveApiCalls] = useState(0);
  const [recording, setRecording] = useState(null);
  const [playing, setPlaying] = useState(false);

  const playbackRef = useRef(null);

  const stopPlayback = () => {
    playbackRef.current?.stop();
    playbackRef.current = null;
    setPlaying(false);
  };

  useEffect(() => {
    return () => stopPlayback();
  }, []);

  useEffect(() => {
    if (mode !== "demo") {
      stopPlayback();
      setPipelineActive(null);
      setPipelineCompleted([]);
      setActiveTool(null);
      setRecording(null);
      return;
    }
    const check = validateRecording(recordedRun01);
    if (!check.ok) {
      setError(RECORDING_LOAD_ERROR);
      setRecording(null);
      return;
    }
    setError(null);
    setRecording(recordedRun01);
    setPrompt(recordedRun01.input?.prompt || "");
    setCode(recordedRun01.input?.original_code || "");
    setResult(null);
    setPipelineActive(null);
    setPipelineCompleted([]);
  }, [mode]);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 50 * 1024) {
        setError("File size exceeds 50KB limit.");
        return;
      }
      const reader = new FileReader();
      reader.onload = (event) => {
        setCode(event.target.result);
      };
      reader.readAsText(file);
    }
  };

  const startDemoPlayback = (skip = false) => {
    if (mode !== "demo") return;
    const check = validateRecording(recordedRun01);
    if (!check.ok) {
      setError(RECORDING_LOAD_ERROR);
      return;
    }
    const full = recordingToUiResult(recordedRun01);
    setRecording(recordedRun01);
    setError(null);
    setResult(null);
    setPlaybackLlmCalls(0);
    setPipelineActive("input");
    setPipelineCompleted([]);
    setActiveTool(null);

    stopPlayback();
    const controller = createPlayback({
      timingEvents: recordedRun01.timing_events,
      speed: playbackSpeed,
      iterationCount: full.iterations.length,
      onStage: ({ active, completed }) => {
        setPipelineActive(active);
        setPipelineCompleted(completed);
        setPlaying(true);
      },
      onTool: (tool) => setActiveTool(tool),
      onVisibleIterations: (count) => {
        setResult(sliceResultThroughIteration(full, count));
      },
      onComplete: () => {
        setResult(full);
        setPlaying(false);
        setActiveTool(null);
        setPipelineActive("best");
        setPipelineCompleted(["input", "gemini", "analysis", "feedback", "refinement", "regression", "acceptance", "best"]);
      },
    });
    playbackRef.current = controller;
    if (skip) {
      controller.skip();
    } else {
      setPlaying(true);
      controller.start();
    }
  };

  const handleRun = async () => {
    if (mode === "demo") {
      startDemoPlayback(false);
      return;
    }
    if (mode === "generate" && !prompt.trim()) return;
    if (mode === "review" && !code.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const endpoint = mode === "generate" ? "/api/optimize" : "/api/review";
      const body =
        mode === "generate"
          ? {
              prompt: prompt.trim(),
              iteration_cap: iterationCap,
              pylint_threshold: pylintThreshold,
            }
          : {
              code: code.trim(),
              iteration_cap: iterationCap,
              pylint_threshold: pylintThreshold,
            };

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setLiveApiCalls((n) => n + 1);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setResult(enrichLiveResult(data));
    } catch (err) {
      setError(err.message || "Failed to communicate with optimization backend");
    } finally {
      setLoading(false);
    }
  };

  const copyCode = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadReport = async () => {
    if (!result || mode === "demo") return;

    try {
      const response = await fetch(`${API_BASE_URL}/api/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: result.prompt,
          initial_code: code || null,
          iterations: result.iterations,
          final_code: result.final_code,
          metrics_summary: result.metrics_summary,
          converged: result.converged,
          total_iterations: result.total_iterations,
          iteration_cap: result.iteration_cap,
          pylint_threshold: result.pylint_threshold,
          mode: mode,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to generate report");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aicodequality_report_${new Date().toISOString().slice(0, 10)}.md`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err.message || "Failed to download report");
    }
  };

  const isDemo = mode === "demo";
  const isFixture = recording?.recording_type === "test_fixture";
  const historicalCalls = recording?.api_call_count ?? "N/A";

  return (
    <div className="app-container">
      <Header
        backendStatus={isDemo ? "demo" : "unknown"}
        geminiStatus={isDemo ? "demo" : "unknown"}
        extra={
          isDemo ? (
            <div className={`demo-badge ${isFixture ? "fixture" : "recorded"}`} data-testid="demo-badge">
              <strong>{isFixture ? "TEST FIXTURE" : "RECORDED RUN"}</strong>
              <span>
                {isFixture ? "Not a real experimental run" : "Playback mode • 0 LLM calls"}
              </span>
            </div>
          ) : (
            <span className="api-badge">API: {API_BASE_URL}</span>
          )
        }
      />

      <main className="main-content">
        <Pipeline activeStage={pipelineActive} completedStages={pipelineCompleted} />
        <AnalysisTools activeTool={activeTool} />

        <section className="card input-card">
          <div className="card-header">
            <h2>
              {isDemo
                ? "Demo (recorded run)"
                : mode === "generate"
                  ? "1. Describe Code or Paste Requirements"
                  : "1. Review Existing Code"}
            </h2>
            <div className="mode-toggle">
              <button
                type="button"
                className={`mode-btn ${mode === "generate" ? "active" : ""}`}
                onClick={() => setMode("generate")}
                disabled={loading || playing}
              >
                Generate
              </button>
              <button
                type="button"
                className={`mode-btn ${mode === "review" ? "active" : ""}`}
                onClick={() => setMode("review")}
                disabled={loading || playing}
              >
                Review
              </button>
              <button
                type="button"
                className={`mode-btn demo ${mode === "demo" ? "active" : ""}`}
                onClick={() => setMode("demo")}
                disabled={loading || playing}
                data-testid="demo-mode-btn"
              >
                Demo (recorded run)
              </button>
            </div>
          </div>

          {isDemo && recording && (
            <div className="demo-meta" data-testid="demo-meta">
              {isFixture ? (
                <>
                  <p className="demo-title">Demo (test fixture)</p>
                  <p className="demo-warning">NOT A REAL EXPERIMENTAL RUN</p>
                </>
              ) : (
                <>
                  <p className="demo-title">Demo (recorded run)</p>
                  <p>Recorded: {recording.created_at}</p>
                </>
              )}
              <p>
                Historical LLM calls: <strong data-testid="historical-llm-calls">{historicalCalls}</strong>
              </p>
              <p>
                Playback LLM calls: <strong data-testid="playback-llm-calls">{playbackLlmCalls}</strong>
              </p>
              <p>
                API Calls During Playback: <strong data-testid="playback-api-calls">{playbackLlmCalls}</strong>
              </p>
              <p className="demo-note">
                Recorded run: {historicalCalls} LLM calls · Current playback: {playbackLlmCalls} LLM
                calls
              </p>
            </div>
          )}

          {mode === "generate" && (
            <>
              <div className="sample-buttons">
                <span className="sample-label">Presets:</span>
                {SAMPLE_PROMPTS.map((sample, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="preset-btn"
                    onClick={() => setPrompt(sample.prompt)}
                    disabled={loading}
                  >
                    {sample.label.split(" ")[0]}
                  </button>
                ))}
              </div>

              <div className="prompt-wrapper">
                <textarea
                  id="prompt-input"
                  rows={4}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe the Python program or code functionality you need..."
                  disabled={loading}
                />
              </div>
            </>
          )}

          {mode === "review" && (
            <>
              <div className="file-upload-section">
                <input
                  type="file"
                  id="file-upload"
                  accept=".py"
                  onChange={handleFileUpload}
                  disabled={loading}
                  className="file-input"
                />
                <label htmlFor="file-upload" className="file-upload-btn">
                  Upload Python File
                </label>
                <span className="file-size-limit">(Max 50KB)</span>
              </div>

              <div className="prompt-wrapper">
                <textarea
                  id="code-input"
                  rows={12}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Paste your Python code here for review and improvement..."
                  disabled={loading}
                  className="code-textarea"
                />
              </div>
            </>
          )}

          {isDemo && (
            <div className="prompt-wrapper">
              <textarea
                id="demo-prompt"
                rows={3}
                value={prompt}
                readOnly
                disabled
              />
            </div>
          )}

          <div className="action-row">
            {!isDemo && (
              <div className="settings-controls">
                <div className="setting-group">
                  <label htmlFor="iteration-cap" className="setting-label">
                    Iteration Cap:
                  </label>
                  <select
                    id="iteration-cap"
                    className="setting-select"
                    value={iterationCap}
                    onChange={(e) => setIterationCap(parseInt(e.target.value))}
                    disabled={loading}
                  >
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                    <option value={4}>4</option>
                    <option value={5}>5</option>
                  </select>
                </div>
                <div className="setting-group">
                  <label htmlFor="pylint-threshold" className="setting-label">
                    Pylint Threshold:
                  </label>
                  <select
                    id="pylint-threshold"
                    className="setting-select"
                    value={pylintThreshold}
                    onChange={(e) => setPylintThreshold(parseFloat(e.target.value))}
                    disabled={loading}
                  >
                    <option value={6.0}>6.0</option>
                    <option value={7.0}>7.0</option>
                    <option value={8.0}>8.0</option>
                    <option value={9.0}>9.0</option>
                    <option value={10.0}>10.0</option>
                  </select>
                </div>
                <div className="threshold-info">
                  <span className="info-text">Bandit High/Med = 0</span>
                </div>
              </div>
            )}

            {isDemo ? (
              <div className="playback-controls" data-testid="playback-controls">
                <button
                  type="button"
                  className="run-btn"
                  data-testid="replay-btn"
                  onClick={() => startDemoPlayback(false)}
                  disabled={playing}
                >
                  ▶ Replay
                </button>
                <button
                  type="button"
                  className="preset-btn"
                  data-testid="restart-btn"
                  onClick={() => {
                    setResult(null);
                    startDemoPlayback(false);
                  }}
                >
                  ↻ Restart
                </button>
                <button
                  type="button"
                  className="preset-btn"
                  data-testid="skip-btn"
                  onClick={() => startDemoPlayback(true)}
                >
                  ⏭ Skip to Results
                </button>
                <div className="speed-toggle">
                  <span>Playback speed:</span>
                  <button
                    type="button"
                    className={`toggle-btn ${playbackSpeed === 1 ? "active" : ""}`}
                    onClick={() => setPlaybackSpeed(1)}
                  >
                    1×
                  </button>
                  <button
                    type="button"
                    className={`toggle-btn ${playbackSpeed === 2 ? "active" : ""}`}
                    onClick={() => setPlaybackSpeed(2)}
                  >
                    2×
                  </button>
                </div>
              </div>
            ) : (
              <button
                id="run-button"
                className={`run-btn ${loading ? "running" : ""}`}
                onClick={handleRun}
                disabled={
                  loading ||
                  (mode === "generate" && !prompt.trim()) ||
                  (mode === "review" && !code.trim())
                }
              >
                {loading ? (
                  <>
                    <span className="spinner"></span>
                    <span>{mode === "generate" ? "Optimizing Code..." : "Reviewing Code..."}</span>
                  </>
                ) : (
                  <>
                    <span>{mode === "generate" ? "Run Convergence Loop" : "Review & Improve Code"}</span>
                    <span className="arrow-icon">&rarr;</span>
                  </>
                )}
              </button>
            )}
          </div>
        </section>

        {loading && (
          <section className="card loading-card">
            <div className="loading-animation">
              <div className="pulse-ring"></div>
              <div className="pulse-dot"></div>
            </div>
            <div className="loading-text">
              <h3>Iterative Refinement in Progress</h3>
              <p>Executing Gemini Flash repair, Bandit AST scan, and Pylint evaluation...</p>
            </div>
          </section>
        )}

        {error && (
          <section className="card error-card" data-testid="error-card">
            <div className="error-title">Optimization Error</div>
            <div className="error-body">{typeof error === "string" ? error : error}</div>
          </section>
        )}

        {!result && !loading && !playing && <EmptyState />}

        <ResultsView
          result={result}
          diffMode={diffMode}
          onDiffModeChange={setDiffMode}
          onCopy={copyCode}
          copied={copied}
          onDownloadReport={downloadReport}
          allowReportDownload={!isDemo}
          originalFallback={code}
        />
      </main>
    </div>
  );
}
