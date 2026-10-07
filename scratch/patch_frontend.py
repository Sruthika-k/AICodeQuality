import os
import re

app_jsx_path = r"e:\MiniProject\AICodeQuality\frontend\src\App.jsx"
css_path = r"e:\MiniProject\AICodeQuality\frontend\src\index.css"

with open(app_jsx_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

# 1. Imports and state
app_content = app_content.replace(
    'import React, { useState } from "react";',
    'import React, { useState, useEffect } from "react";'
)

state_addition = """  const [backendStatus, setBackendStatus] = useState("checking");
  
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (response.ok) {
          setBackendStatus("connected");
        } else {
          setBackendStatus("offline");
        }
      } catch (err) {
        setBackendStatus("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);
"""
app_content = app_content.replace(
    'const [pylintThreshold, setPylintThreshold] = useState(8.0);',
    'const [pylintThreshold, setPylintThreshold] = useState(8.0);\n' + state_addition
)

# 2. Header
header_replacement = """      <header className="app-header">
        <div className="header-brand">
          <div className="logo-badge">AI</div>
          <div>
            <h1>AICodeQuality</h1>
            <p className="subtitle">
              AI-Assisted Code Quality & Security Refinement
            </p>
            <div className="tech-badges">
              <span className="badge">Gemini</span>
              <span className="badge">Bandit</span>
              <span className="badge">Pylint</span>
              <span className="badge">Radon</span>
            </div>
          </div>
        </div>
        <div className="header-meta">
          <div className={`status-indicator ${backendStatus}`}>
            <span className="status-dot">●</span> 
            {backendStatus === "connected" ? "Backend Connected" : backendStatus === "offline" ? "Backend Offline" : "Checking Backend..."}
          </div>
        </div>
      </header>"""

app_content = re.sub(
    r'<header className="app-header">.*?</header>',
    header_replacement,
    app_content,
    flags=re.DOTALL
)

# 3. Error Handling and Pipeline
error_view_replacement = """        {backendStatus === "offline" && (
          <section className="card error-card offline">
            <div className="error-title">Backend Offline</div>
            <div className="error-body">Unable to reach the FastAPI server at {API_BASE_URL}.</div>
            <button className="retry-btn" onClick={() => window.location.reload()}>Retry</button>
          </section>
        )}

        {error && backendStatus === "connected" && (
          <section className="card error-card">
            <div className="error-title">Optimization Error</div>
            <div className="error-body">{error}</div>
          </section>
        )}

        {/* Refinement Pipeline */}
        <section className="card pipeline-card">
          <div className="card-header">
            <h2>Refinement Pipeline</h2>
          </div>
          <div className="pipeline-flow">
            <div className="pipeline-stage">Input</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Gemini Generation</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Static Analysis</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Issue Extraction</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Feedback Generation</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">LLM Refinement</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Regression Check</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Acceptance</div>
            <div className="pipeline-arrow">↓</div>
            <div className="pipeline-stage">Best Candidate</div>
          </div>
        </section>"""

app_content = re.sub(
    r'\{\/\*\s*Error View\s*\*\/\}.*?\{\/\*\s*Results Section\s*\*\/\}',
    error_view_replacement + '\n\n        {/* Results Section */}',
    app_content,
    flags=re.DOTALL
)

# 4. Results Section Research Info
research_info = """            {/* Research Information */}
            <div className="card research-info-card">
              <div className="card-header">
                <h2>Research / Experiment Information</h2>
              </div>
              <div className="research-grid">
                <div><strong>Model:</strong> {result.model || "N/A"}</div>
                <div><strong>Iteration Cap:</strong> {result.iteration_cap || "N/A"}</div>
                <div><strong>Acceptance Rule:</strong> {result.config?.acceptance_rule || "N/A"}</div>
                <div><strong>Feedback Mode:</strong> {result.config?.feedback_mode || "N/A"}</div>
                <div><strong>Stopping Mode:</strong> {result.config?.stopping_mode || "N/A"}</div>
                <div><strong>API Calls:</strong> {result.api_calls ?? "N/A"}</div>
                <div><strong>Iterations:</strong> {result.total_iterations ?? "N/A"}</div>
              </div>
            </div>
            
            {/* Regression Info */}
            <div className="card regression-card">
              <div className="card-header">
                <h2>Regression Information</h2>
              </div>
              <div className="regression-grid">
                <div className="reg-box resolved"><strong>Resolved:</strong> {result.resolved ?? "N/A"}</div>
                <div className="reg-box introduced"><strong>Introduced:</strong> {result.introduced ?? "N/A"}</div>
                <div className="reg-box persistent"><strong>Persistent:</strong> {result.persistent ?? "N/A"}</div>
              </div>
            </div>
"""
app_content = app_content.replace(
    '{/* Before / After Metrics Table */}',
    research_info + '\n            {/* Before / After Metrics Table */}'
)

# 5. Fix Iteration details
iteration_details_replace = """                      <div className="meta-badge">
                        <span>Decision:</span>
                        <strong className={result.iterations[activeTab].accepted ? "good" : "bad"}>
                          {result.iterations[activeTab].accepted ? "Accepted" : "Rejected"}
                        </strong>
                      </div>
                      {result.iterations[activeTab].rejected_reason && (
                        <div className="meta-badge">
                          <span>Reason:</span>
                          <strong>{result.iterations[activeTab].rejected_reason}</strong>
                        </div>
                      )}"""

app_content = app_content.replace(
    '                        <span>Threshold Met:</span>',
    iteration_details_replace + '\n                        <span>Threshold Met:</span>'
)

# Fix N/A for complexity metrics
app_content = app_content.replace(
    'result.metrics_summary.initial_avg_complexity.toFixed(2)',
    '(result.metrics_summary.initial_avg_complexity !== null && result.metrics_summary.initial_avg_complexity !== undefined ? result.metrics_summary.initial_avg_complexity.toFixed(2) : "N/A")'
)
app_content = app_content.replace(
    'result.metrics_summary.final_avg_complexity.toFixed(2)',
    '(result.metrics_summary.final_avg_complexity !== null && result.metrics_summary.final_avg_complexity !== undefined ? result.metrics_summary.final_avg_complexity.toFixed(2) : "N/A")'
)

with open(app_jsx_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

# Now inject CSS
with open(css_path, 'r', encoding='utf-8') as f:
    css_content = f.read()

new_css = """
/* Added for Professional Dashboard UI */
.tech-badges {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.badge {
  background: #333;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
  border: 1px solid #555;
}
.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-weight: bold;
  font-size: 0.9rem;
}
.status-indicator.connected {
  background: rgba(39, 174, 96, 0.2);
  color: #2ecc71;
}
.status-indicator.offline {
  background: rgba(231, 76, 60, 0.2);
  color: #e74c3c;
}
.status-indicator.checking {
  background: rgba(241, 196, 15, 0.2);
  color: #f1c40f;
}
.status-dot {
  font-size: 1.2rem;
}

.pipeline-card {
  margin-bottom: 2rem;
}
.pipeline-flow {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 1rem;
  background: #1e1e1e;
  border-radius: 8px;
}
.pipeline-stage {
  background: #2c3e50;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #34495e;
  font-size: 0.9rem;
  font-weight: bold;
}
.pipeline-arrow {
  color: #7f8c8d;
  font-weight: bold;
  transform: rotate(-90deg); /* Make it point right */
}
@media (max-width: 768px) {
  .pipeline-flow {
    flex-direction: column;
  }
  .pipeline-arrow {
    transform: rotate(0deg); /* Point down */
  }
}

.research-info-card, .regression-card {
  margin-bottom: 2rem;
}
.research-grid, .regression-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  padding: 1rem;
}
.research-grid div {
  background: #252526;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #333;
}
.reg-box {
  padding: 1rem;
  border-radius: 6px;
  text-align: center;
  font-weight: bold;
  font-size: 1.1rem;
}
.reg-box.resolved { background: rgba(39, 174, 96, 0.1); border: 1px solid #27ae60; color: #2ecc71; }
.reg-box.introduced { background: rgba(231, 76, 60, 0.1); border: 1px solid #e74c3c; color: #e74c3c; }
.reg-box.persistent { background: rgba(241, 196, 15, 0.1); border: 1px solid #f39c12; color: #f1c40f; }

.error-card.offline {
  border-left: 4px solid #e74c3c;
  background: rgba(231, 76, 60, 0.05);
}
.retry-btn {
  margin-top: 1rem;
  background: #e74c3c;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}
.retry-btn:hover { background: #c0392b; }
"""

with open(css_path, 'a', encoding='utf-8') as f:
    f.write(new_css)
