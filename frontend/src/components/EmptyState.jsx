import React from "react";

export default function EmptyState() {
  return (
    <div className="card empty-state-card">
      <div className="empty-state-content">
        <p className="explanation">
          Paste or generate Python code → tools find security and quality problems → AI fixes them → we keep a change only if it is actually better
        </p>
        <div className="empty-steps">
          <div className="empty-step">
            <div className="step-number">1</div>
            <div className="step-text">Input or generate code</div>
          </div>
          <div className="empty-arrow">→</div>
          <div className="empty-step">
            <div className="step-number">2</div>
            <div className="step-text">Tools find problems</div>
          </div>
          <div className="empty-arrow">→</div>
          <div className="empty-step">
            <div className="step-number">3</div>
            <div className="step-text">AI fixes issues</div>
          </div>
          <div className="empty-arrow">→</div>
          <div className="empty-step">
            <div className="step-number">4</div>
            <div className="step-text">Keep only improvements</div>
          </div>
        </div>
      </div>
    </div>
  );
}
