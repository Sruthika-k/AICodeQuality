import React from "react";

export default function CodeComparison({
  originalCode,
  finalCode,
  unifiedDiff,
  diffMode,
  onDiffModeChange,
  onCopy,
  copied,
  onDownloadReport,
  allowReportDownload = true,
}) {
  return (
    <div className="card final-code-card" data-testid="code-comparison">
      <div className="card-header">
        <h2>Original vs Optimized Code</h2>
        <div className="header-actions">
          {allowReportDownload && (
            <button className="download-btn" onClick={onDownloadReport}>
              Download Report
            </button>
          )}
          <button className="copy-btn" onClick={() => onCopy(finalCode)}>
            {copied ? "Copied!" : "Copy Final Code"}
          </button>
          <div className="diff-mode-toggle">
            <button
              type="button"
              className={`toggle-btn ${diffMode === "side-by-side" ? "active" : ""}`}
              onClick={() => onDiffModeChange("side-by-side")}
            >
              Side-by-side
            </button>
            <button
              type="button"
              className={`toggle-btn ${diffMode === "unified" ? "active" : ""}`}
              onClick={() => onDiffModeChange("unified")}
            >
              Unified
            </button>
          </div>
        </div>
      </div>
      <div className="diff-view-section">
        {diffMode === "unified" ? (
          <div className="unified-diff-view" data-testid="unified-diff">
            <pre className="unified-diff-pre">
              <code>{unifiedDiff || "N/A"}</code>
            </pre>
          </div>
        ) : (
          <div className="side-by-side-diff simplified-diff">
            <div className="diff-column old-column">
              <div className="column-title">
                <span>Original Code</span>
              </div>
              <div className="diff-code-block">
                <pre>
                  <code data-testid="original-code">{originalCode}</code>
                </pre>
              </div>
            </div>
            <div className="diff-column new-column">
              <div className="column-title">
                <span>Optimized Code</span>
              </div>
              <div className="diff-code-block">
                <pre>
                  <code data-testid="final-code">{finalCode}</code>
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
