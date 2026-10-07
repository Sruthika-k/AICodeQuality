import re

with open("frontend/src/App.jsx", "r", encoding="utf-8") as f:
    app_jsx = f.read()

start_idx = app_jsx.find("{/* Results Section */}")
end_idx = app_jsx.find("</main>")

new_results = """{/* Results Section */}
        {result && (
          <section className="results-container">
            {/* 1. Verdict banner */}
            <div className={`verdict-banner ${result.converged ? 'success' : 'warning'}`}>
              <h2>
                {result.converged ? "✨ Improved: " : "⚠️ Partial Improvement: "}
                {result.metrics_summary?.initial_bandit_high_medium} security issues &rarr; {result.final_bandit_high_medium},
                Pylint {result.metrics_summary?.initial_pylint_score?.toFixed(1)} &rarr; {result.final_pylint_score?.toFixed(1)}
              </h2>
            </div>

            {/* 2. Metric cards */}
            <div className="metrics-dashboard simplified-metrics">
              <div className="metric-card" title="Bandit scans for security vulnerabilities. Lower is better.">
                <h4>Security Issues (Bandit)</h4>
                <div className="metric-values">
                  <span className="before">{result.metrics_summary?.initial_bandit_high_medium}</span> &rarr; <span className="after">{result.final_bandit_high_medium}</span>
                  <span className={`delta ${result.final_bandit_high_medium < result.metrics_summary?.initial_bandit_high_medium ? 'good' : (result.final_bandit_high_medium > result.metrics_summary?.initial_bandit_high_medium ? 'bad' : 'neutral')}`}>
                    {result.final_bandit_high_medium - result.metrics_summary?.initial_bandit_high_medium > 0 ? "+" : ""}
                    {result.final_bandit_high_medium - result.metrics_summary?.initial_bandit_high_medium}
                  </span>
                </div>
              </div>
              <div className="metric-card" title="Pylint score rates code quality out of 10. Higher is better.">
                <h4>Code Quality (Pylint)</h4>
                <div className="metric-values">
                  <span className="before">{result.metrics_summary?.initial_pylint_score?.toFixed(1)}</span> &rarr; <span className="after">{result.final_pylint_score?.toFixed(1)}</span>
                  <span className={`delta ${result.final_pylint_score > result.metrics_summary?.initial_pylint_score ? 'good' : (result.final_pylint_score < result.metrics_summary?.initial_pylint_score ? 'bad' : 'neutral')}`}>
                    {result.final_pylint_score - result.metrics_summary?.initial_pylint_score > 0 ? "+" : ""}
                    {(result.final_pylint_score - result.metrics_summary?.initial_pylint_score).toFixed(1)}
                  </span>
                </div>
              </div>
              {result.metrics_summary?.initial_avg_complexity !== null && (
                <div className="metric-card" title="Radon Cyclomatic Complexity. Lower means simpler code.">
                  <h4>Complexity</h4>
                  <div className="metric-values">
                    <span className="before">{result.metrics_summary?.initial_avg_complexity?.toFixed(1)}</span> &rarr; <span className="after">{result.metrics_summary?.final_avg_complexity?.toFixed(1)}</span>
                  </div>
                </div>
              )}
              {result.metrics_summary?.initial_maintainability_index !== null && (
                <div className="metric-card" title="Radon Maintainability Index. Higher means easier to maintain.">
                  <h4>Maintainability</h4>
                  <div className="metric-values">
                    <span className="before">{result.metrics_summary?.initial_maintainability_index?.toFixed(1)}</span> &rarr; <span className="after">{result.metrics_summary?.final_maintainability_index?.toFixed(1)}</span>
                  </div>
                </div>
              )}
            </div>

            {/* 3. Iteration timeline */}
            <div className="card iteration-timeline">
              <h2>Iteration Timeline</h2>
              <div className="timeline-rows">
                {result.iterations?.map((it, idx) => (
                  <div key={idx} className="timeline-row">
                    <div className="timeline-header">
                      <span className="iteration-num">Iteration {it.iteration}</span>
                      <span className={`badge ${it.accepted ? 'accepted' : 'rejected'}`}>
                        {it.accepted ? "Accepted" : "Rejected"}
                      </span>
                    </div>
                    <div className="timeline-details">
                      <span className="reason-text">{it.acceptance_reason || (it.threshold_met ? "Converged" : "Improved metrics")}</span>
                      <div className="timeline-stats">
                        <span className="stat fixed" title="Issues resolved">- {it.issues_eliminated ?? 0}</span>
                        <span className="stat intro" title="New issues introduced">+{it.issues_introduced ?? 0}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 4. Side-by-side diff */}
            <div className="card final-code-card">
              <div className="card-header">
                <h2>Original vs Optimized Code</h2>
                <div className="header-actions">
                  <button className="download-btn" onClick={downloadReport}>Download Report</button>
                  <button className="copy-btn" onClick={() => copyCode(result.final_code)}>
                    {copied ? "Copied!" : "Copy Final Code"}
                  </button>
                </div>
              </div>
              <div className="diff-view-section">
                <div className="side-by-side-diff simplified-diff">
                  <div className="diff-column old-column">
                    <div className="column-title"><span>Original Code</span></div>
                    <div className="diff-code-block">
                      <pre><code>{result.iterations?.[0]?.code || code}</code></pre>
                    </div>
                  </div>
                  <div className="diff-column new-column">
                    <div className="column-title"><span>Optimized Code</span></div>
                    <div className="diff-code-block">
                      <pre><code>{result.final_code}</code></pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 5. Collapsible Details */}
            <details className="card technical-details">
              <summary><h2>Technical Details</h2></summary>
              <div className="details-content">
                <p><strong>Status:</strong> {result.status}</p>
                <p><strong>Total Iterations:</strong> {result.total_iterations}</p>
                <p><strong>Raw Issues (Final):</strong></p>
                <ul>
                  {result.iterations?.[result.iterations.length - 1]?.issues?.map((iss, i) => (
                    <li key={i}>[{iss.severity}] {iss.tool} ({iss.rule_id}): {iss.message} on line {iss.line}</li>
                  ))}
                </ul>
              </div>
            </details>

          </section>
        )}
"""

if start_idx != -1 and end_idx != -1:
    new_app = app_jsx[:start_idx] + new_results + "      " + app_jsx[end_idx:]
    with open("frontend/src/App.jsx", "w", encoding="utf-8") as f:
        f.write(new_app)
    print("Patched App.jsx successfully.")
else:
    print("Could not find boundaries in App.jsx.")
