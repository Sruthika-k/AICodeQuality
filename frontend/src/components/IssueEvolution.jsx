import React from "react";

function IssueList({ title, items, testId }) {
  const missing = items === null || items === undefined;
  return (
    <div className="issue-evo-col" data-testid={testId}>
      <h4>{title}</h4>
      {missing ? (
        <p className="na-text">N/A</p>
      ) : items.length === 0 ? (
        <p className="na-text">None</p>
      ) : (
        <ul>
          {items.map((item, idx) => (
            <li key={idx}>
              {item.tool} ({item.rule_id}): {item.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function IssueEvolution({ evolution }) {
  const resolved = evolution?.resolved;
  const introduced = evolution?.introduced;
  const persistent = evolution?.persistent;
  return (
    <div className="card issue-evolution-card" data-testid="issue-evolution">
      <div className="card-header">
        <h2>Issue Evolution</h2>
      </div>
      <div className="issue-evo-grid">
        <IssueList title="Resolved" items={resolved} testId="issues-resolved" />
        <IssueList title="Introduced" items={introduced} testId="issues-introduced" />
        <IssueList title="Persistent" items={persistent} testId="issues-persistent" />
      </div>
    </div>
  );
}
