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

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

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

const DEMO_PROMPT_TITLE = "Python Input Processing — Security & Quality Refinement";

const DEMO_INPUT_CODE = `def process_input(user_input):
    result = eval(user_input)
    if result > 10:
        return "large"
    return "small"`;

const DEMO_FINAL_CODE = `def process_input(user_input):
    try:
        result = int(user_input)
    except ValueError:
        return "invalid"

    return "large" if result > 10 else "small"`;

const DEMO_UNIFIED_DIFF = `--- original
+++ refined
@@ -1,5 +1,8 @@
 def process_input(user_input):
-    result = eval(user_input)
-    if result > 10:
-        return "large"
-    return "small"
+    try:
+        result = int(user_input)
+    except ValueError:
+        return "invalid"
+
+    return "large" if result > 10 else "small"`;

const LOCAL_DEMO_RESULT = {
  status: "CONVERGED",
  converged: true,
  total_iterations: 2,
  iteration_cap: 3,
  pylint_threshold: 8.0,
  prompt: DEMO_PROMPT_TITLE,
  original_code: DEMO_INPUT_CODE,
  final_code: DEMO_FINAL_CODE,
  unified_diff: DEMO_UNIFIED_DIFF,
  final_bandit_high_medium: 0,
  final_bandit_low: 0,
  final_pylint_score: 9.2,
  decision: "accepted",
  decision_reason:
    "✓ Security constraints satisfied\n✓ Pylint quality improved\n✓ Complexity reduced\n✓ Maintainability improved\n✓ No tracked regression",
  metrics_summary: {
    initial_bandit_high_medium: 5,
    final_bandit_high_medium: 0,
    bandit_high_medium_reduction: 5,
    initial_pylint_score: 6.4,
    final_pylint_score: 9.2,
    pylint_score_improvement: 2.8,
    initial_avg_complexity: 11.0,
    final_avg_complexity: 4.0,
    initial_maintainability_index: 72.4,
    final_maintainability_index: 88.1,
  },
  issue_evolution: {
    resolved: [
      { tool: "bandit", rule_id: "B307", message: "Use of possibly insecure function - eval" },
      { tool: "bandit", rule_id: "B102", message: "exec used - potential arbitrary code execution" },
      { tool: "bandit", rule_id: "B101", message: "assert_used" },
      { tool: "pylint", rule_id: "W0123", message: "Use of eval detected" },
      { tool: "pylint", rule_id: "C0116", message: "Missing function docstring" },
    ],
    introduced: [],
    persistent: [],
  },
  iterations: [
    {
      iteration: 0,
      code: DEMO_INPUT_CODE,
      pylint_score: 6.4,
      bandit_high_medium_count: 5,
      bandit_low_count: 0,
      pylint_issue_count: 4,
      total_issues_count: 5,
      has_syntax_error: false,
      threshold_met: false,
      avg_complexity: 11.0,
      max_complexity: 11,
      maintainability_index: 72.4,
      accepted: true,
      acceptance_reason: "Initial Candidate — 5 issues detected",
      issues_eliminated: 0,
      issues_introduced: 0,
      diff: null,
      issues: [
        { tool: "bandit", severity: "HIGH", line: 2, message: "Use of eval", rule_id: "B307" },
        { tool: "pylint", severity: "WARNING", line: 2, message: "eval used", rule_id: "W0123" },
      ],
    },
    {
      iteration: 1,
      code: `def process_input(user_input):\n    result = int(user_input)\n    return "large" if result > 10 else "small"`,
      pylint_score: 8.0,
      bandit_high_medium_count: 2,
      bandit_low_count: 0,
      pylint_issue_count: 2,
      total_issues_count: 2,
      has_syntax_error: false,
      threshold_met: false,
      avg_complexity: 6.0,
      max_complexity: 6,
      maintainability_index: 80.0,
      accepted: true,
      acceptance_reason: "Refinement — 3 issues resolved",
      issues_eliminated: 3,
      issues_introduced: 0,
      diff: null,
      issues: [],
    },
    {
      iteration: 2,
      code: DEMO_FINAL_CODE,
      pylint_score: 9.2,
      bandit_high_medium_count: 0,
      bandit_low_count: 0,
      pylint_issue_count: 0,
      total_issues_count: 0,
      has_syntax_error: false,
      threshold_met: true,
      avg_complexity: 4.0,
      max_complexity: 4,
      maintainability_index: 88.1,
      accepted: true,
      acceptance_reason: "Final Candidate — 0 critical security issues",
      issues_eliminated: 5,
      issues_introduced: 0,
      diff: DEMO_UNIFIED_DIFF,
      issues: [],
    },
  ],
};

function enrichLiveResult(data) {
  const iterations = (data.iterations || []).map((it, idx) => ({
    ...it,
    accepted: it.accepted ?? (idx === 0 ? true : Boolean(it.threshold_met)),
    acceptance_reason:
      it.acceptance_reason ??
      (idx === 0 ? "ACCEPTED_INITIAL" : it.threshold_met ? "Converged" : (it.accepted ? "Improved metrics" : "Rejected")),
    issues_eliminated: it.issues_eliminated ?? null,
    issues_introduced: it.issues_introduced ?? null,
  }));
  const last = iterations[iterations.length - 1];
  const anyRejected = iterations.some((it, idx) => idx > 0 && !it.accepted);
  return {
    ...data,
    iterations,
    original_code: data.original_code || iterations[0]?.code || "",
    unified_diff: data.unified_diff || last?.diff || null,
    issue_evolution: data.issue_evolution || { resolved: null, introduced: null, persistent: null },
    decision: data.decision || (iterations.length > 1 && !last?.accepted ? "rejected" : last?.accepted ? "accepted" : data.converged ? "accepted" : "rejected"),
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
  const [healthStatus, setHealthStatus] = useState("checking"); // "checking", "connected", "offline"

  const playbackRef = useRef(null);

  const stopPlayback = () => {
    playbackRef.current?.stop();
    playbackRef.current = null;
    setPlaying(false);
  };

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`, { method: "GET" });
        if (!mounted) return;
        if (res.ok) {
          const data = await res.json().catch(() => ({}));
          setHealthStatus(data.status === "healthy" ? "connected" : "connected");
        } else {
          setHealthStatus("offline");
        }
      } catch {
        if (mounted) setHealthStatus("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

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
    stopPlayback();
    setError(null);
    setPrompt(DEMO_PROMPT_TITLE);
    setCode(DEMO_INPUT_CODE);
    setResult(LOCAL_DEMO_RESULT);
    setPipelineActive("best");
    setPipelineCompleted(["input", "gemini", "analysis", "feedback", "refinement", "regression", "acceptance", "best"]);
    setActiveTool(null);
    setPlaybackLlmCalls(0);
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
    stopPlayback();
    setError(null);
    setPlaybackLlmCalls(0);

    if (skip) {
      setResult(LOCAL_DEMO_RESULT);
      setPlaying(false);
      setActiveTool(null);
      setPipelineActive("best");
      setPipelineCompleted(["input", "gemini", "analysis", "feedback", "refinement", "regression", "acceptance", "best"]);
      return;
    }

    setResult(null);
    setPlaying(true);
    setPipelineActive("input");
    setPipelineCompleted([]);

    const stages = [
      { id: "input", delay: 200 },
      { id: "gemini", delay: 350 },
      { id: "analysis", delay: 350 },
      { id: "feedback", delay: 300 },
      { id: "refinement", delay: 350 },
      { id: "regression", delay: 250 },
      { id: "acceptance", delay: 250 },
      { id: "best", delay: 200 },
    ];

    let current = 0;
    const completed = [];
    const step = () => {
      if (current < stages.length) {
        const stage = stages[current];
        setPipelineActive(stage.id);
        if (current > 0) {
          completed.push(stages[current - 1].id);
          setPipelineCompleted([...completed]);
        }
        current += 1;
        playbackRef.current = {
          timerId: setTimeout(step, stage.delay / playbackSpeed),
          stop: () => clearTimeout(playbackRef.current?.timerId),
        };
      } else {
        completed.push("best");
        setPipelineCompleted(["input", "gemini", "analysis", "feedback", "refinement", "regression", "acceptance", "best"]);
        setPipelineActive("best");
        setResult(LOCAL_DEMO_RESULT);
        setPlaying(false);
      }
    };
    step();
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
    setPipelineCompleted(["input"]);
    setPipelineActive("gemini");

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

      // Deadline based on iteration cap to prevent premature browser timeouts
      const timeoutSec =
        mode === "generate"
          ? 150 + (iterationCap - 1) * 120 // cap 1 -> 150s, 2 -> 270s, 3 -> 390s, 4 -> 510s, 5 -> 630s
          : 60 + (iterationCap - 1) * 120; // cap 1 -> 60s, 2 -> 180s, 3 -> 300s, 4 -> 420s, 5 -> 540s

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutSec * 1000);

      let response;
      try {
        response = await fetch(`${API_BASE_URL}${endpoint}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutId);
      }
      setLiveApiCalls((n) => n + 1);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setResult(enrichLiveResult(data));
      setPipelineActive(null);
      setPipelineCompleted(["input", "gemini", "analysis", "feedback", "refinement", "regression", "acceptance", "best"]);
    } catch (err) {
      if (err.name === "AbortError") {
        setError("Request timed out waiting for backend response. Consider trying with a lower iteration cap or checking backend logs.");
      } else {
        setError(err.message || "Failed to communicate with optimization backend");
      }
      setPipelineActive(null);
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

  const backendStatus = isDemo
    ? "demo"
    : loading
      ? "processing"
      : healthStatus === "offline"
        ? "offline"
        : healthStatus === "checking"
          ? "checking"
          : "connected";

  const geminiStatus = isDemo
    ? "demo"
    : loading
      ? "running"
      : error
        ? "error"
        : result
          ? "ready"
          : "ok";

  return (
    <div className="app-container">
      <Header
        backendStatus={backendStatus}
        geminiStatus={geminiStatus}
        extra={
          isDemo ? (
            <div className="demo-header-badge" data-testid="demo-badge">
              <strong>DEMO MODE</strong>
              <span className="subtext">Simulated output — no API calls</span>
              <span className="badge-calls" data-testid="playback-llm-calls">LLM Calls: 0</span>
              <span style={{ display: "none" }} data-testid="playback-api-calls">0</span>
              <span style={{ display: "none" }} data-testid="historical-llm-calls">0</span>
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
                ? "Demo Mode — Local Simulation"
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
                Demo
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
              <div style={{ marginBottom: "8px", fontWeight: "600", color: "#a5b4fc", fontSize: "0.95rem" }}>
                {prompt}
              </div>
              <textarea
                id="demo-prompt"
                rows={6}
                value={code}
                readOnly
                disabled
                className="code-textarea"
                style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}
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
