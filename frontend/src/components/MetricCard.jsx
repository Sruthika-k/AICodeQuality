import React from "react";

function displayValue(value, digits) {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number" && typeof digits === "number") {
    return value.toFixed(digits);
  }
  return value;
}

export default function MetricCard({
  title,
  tool,
  before,
  after,
  unit = "",
  higherIsBetter = true,
  digits,
}) {
  const beforeMissing = before === null || before === undefined;
  const afterMissing = after === null || after === undefined;
  const beforeVal = displayValue(before, digits);
  const afterVal = displayValue(after, digits);

  const numeric =
    typeof after === "number" && typeof before === "number";
  const improved = numeric && (higherIsBetter ? after > before : after < before);
  const regressed = numeric && (higherIsBetter ? after < before : after > before);

  return (
    <div className="card metric-card" data-testid={`metric-card-${tool || title}`}>
      <div className="metric-header">
        <h3>{title}</h3>
        <span className="metric-tool">{tool}</span>
      </div>
      <div className="metric-content">
        <div className="metric-comparison">
          <div className="metric-value metric-before">
            <span className="metric-label">Before</span>
            <span className="metric-val">
              {beforeMissing ? "N/A" : `${beforeVal}${unit}`}
            </span>
          </div>
          <div className="metric-arrow">→</div>
          <div
            className={`metric-value metric-after ${improved ? "improvement" : ""} ${regressed ? "regression" : ""}`}
          >
            <span className="metric-label">After</span>
            <span className="metric-val">
              {afterMissing ? "N/A" : `${afterVal}${unit}`}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
