import React, { useState } from "react";
import Charts from "./Charts";

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

export default function App() {
  const [prompt, setPrompt] = useState(SAMPLE_PROMPTS[0].prompt);
  const [code, setCode] = useState("");
  const [mode, setMode] = useState("generate"); // "generate" or "review"
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState(0); // for iteration tabs
  const [copied, setCopied] = useState(false);
  const [diffMode, setDiffMode] = useState("side-by-side"); // "side-by-side" or "unified"
  const [iterationCap, setIterationCap] = useState(3);
  const [pylintThreshold, setPylintThreshold] = useState(8.0);

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

  const handleRun = async () => {
    if (mode === "generate" && !prompt.trim()) return;
    if (mode === "review" && !code.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const endpoint = mode === "generate" ? "/api/optimize" : "/api/review";
      const body = mode === "generate"
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

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setResult(data);
      if (data.iterations && data.iterations.length > 0) {
        setActiveTab(data.iterations.length - 1); // Select the latest iteration
      }
    } catch (err) {
      setError(err.message || "Failed to communicate with optimization backend");
    } finally {
      setLoading(false);
    }
  };

  const copyCode = (code) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadReport = async () => {
    if (!result) return;

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

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="logo-badge">AI</div>
          <div>
            <h1>AICodeQuality</h1>
            <p className="subtitle">
              Automated Code Enhancement Loop &middot; Gemini Flash + Bandit + Pylint
            </p>
          </div>
        </div>
        <div className="header-meta">
          <span className="api-badge">API: {API_BASE_URL}</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {/* Input Card */}
        <section className="card input-card">
          <div className="card-header">
            <h2>1. {mode === "generate" ? "Describe Code or Paste Requirements" : "Review Existing Code"}</h2>
            <div className="mode-toggle">
              <button
                type="button"
                className={`mode-btn ${mode === "generate" ? "active" : ""}`}
                onClick={() => setMode("generate")}
                disabled={loading}
              >
                Generate
              </button>
              <button
                type="button"
                className={`mode-btn ${mode === "review" ? "active" : ""}`}
                onClick={() => setMode("review")}
                disabled={loading}
              >
                Review
              </button>
            </div>
          </div>

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

          <div className="action-row">
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
            <button
              id="run-button"
              className={`run-btn ${loading ? "running" : ""}`}
              onClick={handleRun}
              disabled={loading || (mode === "generate" && !prompt.trim()) || (mode === "review" && !code.trim())}
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
          </div>
        </section>

        {/* Loading Indicator View */}
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

        {/* Error View */}
        {error && (
          <section className="card error-card">
            <div className="error-title">Optimization Error</div>
            <div className="error-body">{error}</div>
          </section>
        )}

        {/* Results Section */}
        {result && (
          <section className="results-container">
            {/* Status Summary Banner */}
            <div className={`summary-banner ${result.converged ? "converged" : "cap-reached"}`}>
              <div className="banner-left">
                <span className="status-indicator-dot"></span>
                <div>
                  <h3 className="banner-title">
                    {result.converged
                      ? `Convergence Satisfied in Iteration ${result.total_iterations}!`
                      : `Iteration Cap (${result.total_iterations}) Reached`}
                  </h3>
                  <p className="banner-subtitle">
                    Status: <strong>{result.status}</strong> &bull; Total Cycles:{" "}
                    <strong>{result.total_iterations}</strong> &bull; Cap:{" "}
                    <strong>{result.iteration_cap}</strong> &bull; Threshold:{" "}
                    <strong>{result.pylint_threshold}</strong>
                  </p>
                </div>
              </div>

              <div className="banner-stats">
                <div className="stat-box">
                  <div className="stat-label">Final Pylint Score</div>
                  <div className="stat-val">{result.final_pylint_score.toFixed(2)} / 10</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">Bandit High/Med</div>
                  <div className={`stat-val ${result.final_bandit_high_medium === 0 ? "good" : "bad"}`}>
                    {result.final_bandit_high_medium}
                  </div>
                </div>
                {result.metrics_summary?.final_maintainability_index !== null && (
                  <div className="stat-box">
                    <div className="stat-label">Maintainability Index</div>
                    <div className="stat-val">
                      {result.metrics_summary.final_maintainability_index.toFixed(2)}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Before / After Metrics Table */}
            {result.metrics_summary && (
              <div className="card metrics-card">
                <div className="card-header">
                  <h2>2. Before & After Quality Comparison</h2>
                  <span className="badge-highlight">
                    Score Delta:{" "}
                    {result.metrics_summary.pylint_score_delta >= 0 ? "+" : ""}
                    {result.metrics_summary.pylint_score_delta.toFixed(2)} pts
                  </span>
                </div>

                <div className="metrics-grid">
                  <div className="metric-box">
                    <span className="metric-label">Pylint Score</span>
                    <div className="metric-comparison">
                      <span className="val-before">
                        {result.metrics_summary.initial_pylint_score.toFixed(2)}
                      </span>
                      <span className="arrow-change">&rarr;</span>
                      <span className="val-after">
                        {result.metrics_summary.final_pylint_score.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Total Diagnostic Issues</span>
                    <div className="metric-comparison">
                      <span className="val-before">
                        {result.metrics_summary.initial_total_issues}
                      </span>
                      <span className="arrow-change">&rarr;</span>
                      <span className="val-after">
                        {result.metrics_summary.final_total_issues}
                      </span>
                    </div>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Issues Resolved</span>
                    <div className="metric-comparison single-val green">
                      {result.metrics_summary.issues_eliminated >= 0
                        ? `-${result.metrics_summary.issues_eliminated}`
                        : `+${Math.abs(result.metrics_summary.issues_eliminated)}`}
                    </div>
                  </div>

                  <div className="metric-box">
                    <span className="metric-label">Quality Threshold</span>
                    <div className="metric-comparison single-val">
                      {result.converged ? (
                        <span className="badge-pass">PASSED</span>
                      ) : (
                        <span className="badge-fail">UNRESOLVED</span>
                      )}
                    </div>
                  </div>

                  {result.metrics_summary.initial_avg_complexity !== null && (
                    <div className="metric-box">
                      <span className="metric-label">Avg Complexity</span>
                      <div className="metric-comparison">
                        <span className="val-before">
                          {result.metrics_summary.initial_avg_complexity.toFixed(2)}
                        </span>
                        <span className="arrow-change">&rarr;</span>
                        <span className="val-after">
                          {result.metrics_summary.final_avg_complexity.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}

                  {result.metrics_summary.initial_maintainability_index !== null && (
                    <div className="metric-box">
                      <span className="metric-label">Maintainability Index</span>
                      <div className="metric-comparison">
                        <span className="val-before">
                          {result.metrics_summary.initial_maintainability_index.toFixed(2)}
                        </span>
                        <span className="arrow-change">&rarr;</span>
                        <span className="val-after">
                          {result.metrics_summary.final_maintainability_index.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Formatted ASCII Summary Table */}
                <div className="ascii-table-container">
                  <pre className="ascii-table">{result.metrics_summary.table}</pre>
                </div>
              </div>
            )}

            {/* Charts */}
            <Charts result={result} />

            {/* Iteration Breakdown & Diffs */}
            {result.iterations && result.iterations.length > 0 && (
              <div className="card iterations-card">
                <div className="card-header">
                  <h2>3. Iteration Breakdown & Code Diffs</h2>
                  <div className="iteration-tabs">
                    {result.iterations.map((it, idx) => (
                      <button
                        key={idx}
                        className={`tab-btn ${activeTab === idx ? "active" : ""}`}
                        onClick={() => setActiveTab(idx)}
                      >
                        Iteration {it.iteration}
                        <span className={`pill-score ${it.threshold_met ? "good" : ""}`}>
                          {it.pylint_score.toFixed(1)}/10
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Selected Iteration Detail */}
                {result.iterations[activeTab] && (
                  <div className="tab-content">
                    <div className="iter-meta-row">
                      <div className="meta-badge">
                        <span>Pylint Score:</span>
                        <strong>{result.iterations[activeTab].pylint_score.toFixed(2)}/10</strong>
                      </div>
                      <div className="meta-badge">
                        <span>Bandit High/Med:</span>
                        <strong
                          className={
                            result.iterations[activeTab].bandit_high_medium_count === 0
                              ? "good"
                              : "bad"
                          }
                        >
                          {result.iterations[activeTab].bandit_high_medium_count}
                        </strong>
                      </div>
                      <div className="meta-badge">
                        <span>Total Issues:</span>
                        <strong>{result.iterations[activeTab].total_issues_count}</strong>
                      </div>
                      <div className="meta-badge">
                        <span>Threshold Met:</span>
                        <strong
                          className={
                            result.iterations[activeTab].threshold_met ? "good" : "bad"
                          }
                        >
                          {result.iterations[activeTab].threshold_met ? "YES" : "NO"}
                        </strong>
                      </div>
                    </div>

                    {/* Extracted Issues List */}
                    {result.iterations[activeTab].issues &&
                      result.iterations[activeTab].issues.length > 0 && (
                        <div className="issues-list">
                          <h4 className="issues-title">
                            Diagnostic Issues Identified in Iteration {result.iterations[activeTab].iteration}:
                          </h4>
                          <ul>
                            {result.iterations[activeTab].issues.map((iss, i) => (
                              <li key={i} className={`issue-item ${iss.severity.toLowerCase()}`}>
                                <span className={`severity-tag ${iss.severity.toLowerCase()}`}>
                                  [{iss.severity}]
                                </span>
                                <span className="issue-tool">{iss.tool}</span>
                                <span className="issue-line">Line {iss.line}</span>
                                <span className="issue-rule">({iss.rule_id})</span>
                                <span className="issue-msg">{iss.message}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                    {/* Side-by-side or line diff view */}
                    {result.iterations[activeTab].diff_lines &&
                    result.iterations[activeTab].diff_lines.length > 0 ? (
                      <div className="diff-view-section">
                        <div className="diff-header">
                          <div className="diff-title-row">
                            <h4>
                              Code Changes (Iteration {result.iterations[activeTab].iteration - 1} &rarr; Iteration {result.iterations[activeTab].iteration})
                            </h4>
                            <div className="diff-stats-badges">
                              <span className="badge-stat-add">
                                +{result.iterations[activeTab].diff_lines.filter(l => l.type === "insert" || l.type === "replace").length} added
                              </span>
                              <span className="badge-stat-del">
                                -{result.iterations[activeTab].diff_lines.filter(l => l.type === "delete" || l.type === "replace").length} removed
                              </span>
                            </div>
                          </div>

                          <div className="diff-controls">
                            <div className="diff-mode-toggle">
                              <button
                                type="button"
                                className={`toggle-btn ${diffMode === "side-by-side" ? "active" : ""}`}
                                onClick={() => setDiffMode("side-by-side")}
                              >
                                Side-by-Side
                              </button>
                              <button
                                type="button"
                                className={`toggle-btn ${diffMode === "unified" ? "active" : ""}`}
                                onClick={() => setDiffMode("unified")}
                              >
                                Unified
                              </button>
                            </div>
                            <div className="diff-legend">
                              <span className="legend-del"><span className="legend-marker">-</span> Removed</span>
                              <span className="legend-add"><span className="legend-marker">+</span> Added</span>
                            </div>
                          </div>
                        </div>

                        {diffMode === "unified" ? (
                          <div className="unified-diff-view">
                            <pre className="unified-diff-pre">
                              {result.iterations[activeTab].diff || "No text diff available"}
                            </pre>
                          </div>
                        ) : (
                          <div className="side-by-side-diff">
                            <div className="diff-column old-column">
                              <div className="column-title">
                                <span>Previous Iteration ({result.iterations[activeTab].iteration - 1})</span>
                              </div>
                              <div className="diff-code-block">
                                {result.iterations[activeTab].diff_lines.map((dl, dIdx) => (
                                  <div
                                    key={dIdx}
                                    className={`diff-line ${dl.type === "delete" || dl.type === "replace" ? "line-deleted" : ""}`}
                                  >
                                    <span className="line-num">{dl.old_line_num || ""}</span>
                                    <span className="line-marker">{dl.type === "delete" || dl.type === "replace" ? "-" : " "}</span>
                                    <span className="line-text">{dl.old_line !== null ? dl.old_line : ""}</span>
                                  </div>
                                ))}
                              </div>
                            </div>

                            <div className="diff-column new-column">
                              <div className="column-title">
                                <span>Refined Code (Iteration {result.iterations[activeTab].iteration})</span>
                              </div>
                              <div className="diff-code-block">
                                {result.iterations[activeTab].diff_lines.map((dl, dIdx) => (
                                  <div
                                    key={dIdx}
                                    className={`diff-line ${dl.type === "insert" || dl.type === "replace" ? "line-added" : ""}`}
                                  >
                                    <span className="line-num">{dl.new_line_num || ""}</span>
                                    <span className="line-marker">{dl.type === "insert" || dl.type === "replace" ? "+" : " "}</span>
                                    <span className="line-text">{dl.new_line !== null ? dl.new_line : ""}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="code-display-section">
                        <div className="diff-header">
                          <h4>Initial Code (Iteration {result.iterations[activeTab].iteration})</h4>
                          <span className="badge-initial">Baseline Generation</span>
                        </div>
                        <pre className="code-pre">
                          <code>{result.iterations[activeTab].code}</code>
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Final Optimized Code Card */}
            <div className="card final-code-card">
              <div className="card-header">
                <h2>4. Final Optimized Python Code</h2>
                <div className="header-actions">
                  <button
                    className="download-btn"
                    onClick={downloadReport}
                  >
                    Download Report
                  </button>
                  <button
                    className="copy-btn"
                    onClick={() => copyCode(result.final_code)}
                  >
                    {copied ? "Copied!" : "Copy Code"}
                  </button>
                </div>
              </div>

              <div className="code-container">
                <pre className="code-pre">
                  <code>{result.final_code}</code>
                </pre>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
