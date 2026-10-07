import React from "react";

function formatCount(value) {
  return value === null || value === undefined ? "N/A" : value;
}

export default function IterationTimeline({ iterations = [] }) {
  if (!iterations.length) return null;

  return (
    <div className="card iteration-timeline" data-testid="iteration-timeline">
      <h2>Iteration Timeline</h2>
      <div className="timeline-rows">
        {iterations.map((it, idx) => {
          const initial = idx === 0;
          const label = initial
            ? "Initial Candidate"
            : it.accepted
              ? "Candidate Evaluated"
              : "Candidate Rejected";
          return (
            <div key={idx} className="timeline-row" data-testid={`iteration-row-${it.iteration}`}>
              <div className="timeline-header">
                <span className="iteration-num">Iteration {it.iteration}</span>
                <span className="iteration-label">{label}</span>
                <span className={`badge ${it.accepted ? "accepted" : "rejected"}`}>
                  {it.accepted ? "Accepted" : "Rejected"}
                </span>
              </div>
              <div className="timeline-details">
                <span className="reason-text">
                  {it.acceptance_reason || (it.threshold_met ? "Converged" : "Improved metrics")}
                </span>
                <div className="timeline-stats">
                  <span className="stat fixed" title="Issues resolved">
                    resolved {formatCount(it.issues_eliminated)}
                  </span>
                  <span className="stat intro" title="New issues introduced">
                    introduced {formatCount(it.issues_introduced)}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
