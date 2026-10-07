import React from "react";

export default function AcceptanceCard({ decision, reason }) {
  const accepted = String(decision || "").toLowerCase() === "accepted";
  const label = accepted ? "ACCEPTED" : String(decision || "").toLowerCase() === "rejected" ? "REJECTED" : "N/A";
  return (
    <div
      className={`card acceptance-card ${accepted ? "accepted" : "rejected"}`}
      data-testid="acceptance-card"
    >
      <div className="card-header">
        <h2>Acceptance</h2>
        <span className={`badge ${accepted ? "accepted" : "rejected"}`} data-testid="acceptance-decision">
          {label}
        </span>
      </div>
      <p className="acceptance-reason" data-testid="acceptance-reason">
        {reason || "N/A"}
      </p>
    </div>
  );
}
