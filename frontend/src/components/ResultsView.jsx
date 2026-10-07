import React from "react";
import Charts from "../Charts";
import MetricCard from "./MetricCard";
import IterationTimeline from "./IterationTimeline";
import CodeComparison from "./CodeComparison";
import AcceptanceCard from "./AcceptanceCard";
import IssueEvolution from "./IssueEvolution";

export default function ResultsView({
  result,
  diffMode,
  onDiffModeChange,
  onCopy,
  copied,
  onDownloadReport,
  allowReportDownload = true,
  originalFallback = "",
}) {
  if (!result) return null;
  const summary = result.metrics_summary || {};
  const originalCode = result.original_code || result.iterations?.[0]?.code || originalFallback || "";

  return (
    <section className="results-container" data-testid="results">
      <div className={`verdict-banner ${result.converged ? "success" : "warning"}`}>
        <h2>
          {result.converged ? "✨ Improved: " : "⚠️ Partial Improvement: "}
          {summary.initial_bandit_high_medium ?? "N/A"} security issues &rarr;{" "}
          {result.final_bandit_high_medium ?? "N/A"}, Pylint{" "}
          {typeof summary.initial_pylint_score === "number"
            ? summary.initial_pylint_score.toFixed(1)
            : "N/A"}{" "}
          &rarr;{" "}
          {typeof result.final_pylint_score === "number"
            ? result.final_pylint_score.toFixed(1)
            : "N/A"}
        </h2>
      </div>

      <div className="metrics-dashboard simplified-metrics" data-testid="metrics-dashboard">
        <MetricCard
          title="Bandit"
          tool="Bandit"
          before={summary.initial_bandit_high_medium ?? result.iterations?.[0]?.bandit_high_medium_count}
          after={result.final_bandit_high_medium}
          higherIsBetter={false}
        />
        <MetricCard
          title="Pylint"
          tool="Pylint"
          before={summary.initial_pylint_score}
          after={result.final_pylint_score}
          higherIsBetter
          digits={1}
        />
        <MetricCard
          title="Radon Complexity"
          tool="Radon"
          before={summary.initial_avg_complexity}
          after={summary.final_avg_complexity}
          higherIsBetter={false}
          digits={1}
        />
        <MetricCard
          title="Maintainability"
          tool="Radon MI"
          before={summary.initial_maintainability_index}
          after={summary.final_maintainability_index}
          higherIsBetter
          digits={1}
        />
      </div>

      <AcceptanceCard decision={result.decision} reason={result.decision_reason} />
      <IssueEvolution evolution={result.issue_evolution} />
      <IterationTimeline iterations={result.iterations || []} />
      <Charts result={result} />
      <CodeComparison
        originalCode={originalCode}
        finalCode={result.final_code}
        unifiedDiff={result.unified_diff}
        diffMode={diffMode}
        onDiffModeChange={onDiffModeChange}
        onCopy={onCopy}
        copied={copied}
        onDownloadReport={onDownloadReport}
        allowReportDownload={allowReportDownload}
      />

      <details className="card technical-details">
        <summary>
          <h2>Technical Details</h2>
        </summary>
        <div className="details-content">
          <p>
            <strong>Status:</strong> {result.status}
          </p>
          <p>
            <strong>Total Iterations:</strong> {result.total_iterations}
          </p>
          <p>
            <strong>Raw Issues (Final):</strong>
          </p>
          <ul>
            {result.iterations?.[result.iterations.length - 1]?.issues?.map((iss, i) => (
              <li key={i}>
                [{iss.severity}] {iss.tool} ({iss.rule_id}): {iss.message} on line {iss.line}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </section>
  );
}
