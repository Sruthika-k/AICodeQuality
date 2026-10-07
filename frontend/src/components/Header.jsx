import React from "react";

export default function Header({
  backendStatus = "unknown",
  geminiStatus = "unknown",
  toolVersions,
  extra,
}) {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="logo-badge">AI</div>
        <div>
          <h1>AICodeQuality</h1>
          <p className="subtitle">
            AI-Assisted Code Quality &amp; Security Refinement
          </p>
        </div>
      </div>
      <div className="header-meta">
        <div className="status-badges">
          <div className={`status-badge backend ${backendStatus}`}>
            <span className="badge-dot"></span>
            <span className="badge-label">Backend</span>
            <span className="badge-status">
              {backendStatus === "connected"
                ? "OK"
                : backendStatus === "offline"
                  ? "Offline"
                  : backendStatus === "demo"
                    ? "Playback"
                    : "Idle"}
            </span>
          </div>
          <div className={`status-badge gemini ${geminiStatus}`}>
            <span className="badge-dot"></span>
            <span className="badge-label">Gemini</span>
            <span className="badge-status">
              {geminiStatus === "ok"
                ? "OK"
                : geminiStatus === "quota"
                  ? "Quota"
                  : geminiStatus === "demo"
                    ? "Not called"
                    : geminiStatus === "unknown"
                      ? "Idle"
                      : "Error"}
            </span>
          </div>
        </div>
        <div className="tech-badges">
          <span className="tech-badge">Gemini Flash</span>
          <span className="tech-badge">Bandit</span>
          <span className="tech-badge">Pylint</span>
          <span className="tech-badge">Radon</span>
        </div>
        {toolVersions && (
          <div className="version-info">
            <span className="version-text">{toolVersions}</span>
          </div>
        )}
        {extra}
      </div>
    </header>
  );
}
