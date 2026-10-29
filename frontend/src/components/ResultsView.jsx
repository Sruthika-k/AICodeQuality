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

  // Honest status detection
  const totalIters = result.total_iterations ?? result.iterations?.length ?? 1;
  const isInitialOnly = totalIters <= 1;
  const initBandit = summary.initial_bandit_high_medium ?? result.iterations?.[0]?.bandit_high_medium_count;
  const finalBandit = result.final_bandit_high_medium;
  const initPylint = summary.initial_pylint_score ?? result.iterations?.[0]?.pylint_score;
  const finalPylint = result.final_pylint_score;

  const banditDiff = (typeof initBandit === "number" && typeof finalBandit === "number") ? initBandit - finalBandit : 0;
  const pylintDiff = (typeof initPylint === "number" && typeof finalPylint === "number") ? finalPylint - initPylint : 0;
  const hasMeasurableImprovement = banditDiff > 0 || pylintDiff > 0.05;

  let bannerClass = "warning";
  let bannerPrefix = "⚠️ Refinement Ended without Improvement: ";
  if (isInitialOnly) {
    bannerClass = "neutral";
    bannerPrefix = "ℹ️ Initial Analysis Complete (No Refinement Attempted): ";
  } else if (result.converged) {
    bannerClass = "success";
    bannerPrefix = "✨ Converged (Quality Threshold Satisfied): ";
  } else if (hasMeasurableImprovement) {
    bannerClass = "warning";
    bannerPrefix = "⚠️ Partial Improvement: ";
  }

  return (
    <section className="results-container" data-testid="results">
      <div className={`verdict-banner ${bannerClass}`}>
        <h2>
          {bannerPrefix}
          {initBandit ?? "N/A"} security issues &rarr;{" "}
          {finalBandit ?? "N/A"}, Pylint{" "}
          {typeof initPylint === "number"
            ? initPylint.toFixed(1)
            : "N/A"}{" "}
          &rarr;{" "}
          {typeof finalPylint === "number"
            ? finalPylint.toFixed(1)
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
          before={summary.initial_pylint_score ?? result.iterations?.[0]?.pylint_score}
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
