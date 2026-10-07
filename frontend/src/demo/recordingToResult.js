import { RECORDING_LOAD_ERROR, validateRecording } from "./validateRecording";

function issueKey(issue) {
  return `${issue?.tool || ""}:${issue?.rule_id || ""}`;
}

function countEliminated(prev, curr) {
  if (!Array.isArray(prev) || !Array.isArray(curr)) return null;
  const next = new Set(curr.map(issueKey));
  return prev.filter((issue) => !next.has(issueKey(issue))).length;
}

function countIntroduced(prev, curr) {
  if (!Array.isArray(prev) || !Array.isArray(curr)) return null;
  const previous = new Set(prev.map(issueKey));
  return curr.filter((issue) => !previous.has(issueKey(issue))).length;
}

export function recordingToUiResult(recording) {
  const check = validateRecording(recording);
  if (!check.ok) {
    throw new Error(check.error || RECORDING_LOAD_ERROR);
  }

  const sourceIterations = recording.result?.iterations || recording.iterations;
  const iterations = sourceIterations.map((it, idx) => {
    const prev = idx > 0 ? sourceIterations[idx - 1] : null;
    const eliminated =
      it.issues_eliminated ??
      (prev ? countEliminated(prev.issues, it.issues) : 0);
    const introduced =
      it.issues_introduced ??
      (prev ? countIntroduced(prev.issues, it.issues) : 0);
    return {
      ...it,
      accepted: it.accepted ?? (idx === 0 ? true : Boolean(it.threshold_met)),
      acceptance_reason: it.acceptance_reason ?? (idx === 0 ? "ACCEPTED_INITIAL" : it.threshold_met ? "Converged" : undefined),
      issues_eliminated: eliminated,
      issues_introduced: introduced,
    };
  });

  const first = iterations[0];
  const last = iterations[iterations.length - 1];
  const summary = recording.result?.metrics_summary || {};
  const finalMetrics = recording.final?.metrics || {};

  const initialBandit =
    summary.initial_bandit_high_medium ?? first?.bandit_high_medium_count ?? null;
  const finalBandit =
    recording.result?.final_bandit_high_medium ??
    finalMetrics.bandit_high_medium ??
    summary.final_bandit_high_medium ??
    last?.bandit_high_medium_count ??
    null;
  const initialPylint = summary.initial_pylint_score ?? first?.pylint_score ?? null;
  const finalPylint =
    recording.result?.final_pylint_score ??
    finalMetrics.pylint_score ??
    summary.final_pylint_score ??
    last?.pylint_score ??
    null;

  return {
    prompt: recording.result?.prompt ?? recording.input?.prompt ?? "",
    final_code: recording.result?.final_code ?? recording.final?.code ?? last?.code ?? "",
    converged: recording.result?.converged ?? recording.final?.converged ?? Boolean(last?.threshold_met),
    total_iterations: recording.result?.total_iterations ?? iterations.length,
    final_pylint_score: finalPylint,
    final_bandit_high_medium: finalBandit,
    status: recording.result?.status ?? recording.final?.status ?? "",
    iteration_cap: recording.result?.iteration_cap ?? recording.metadata?.iteration_cap,
    pylint_threshold: recording.result?.pylint_threshold ?? recording.configuration?.pylint_threshold,
    unified_diff: recording.diffs?.unified ?? last?.diff ?? null,
    original_code: recording.diffs?.original_code ?? recording.input?.original_code ?? first?.code ?? "",
    issue_evolution: recording.issue_evolution || { resolved: null, introduced: null, persistent: null },
    decision: recording.final?.decision ?? (last?.accepted ? "accepted" : "rejected"),
    decision_reason: recording.final?.decision_reason ?? last?.acceptance_reason ?? null,
    iterations,
    metrics_summary: {
      ...summary,
      initial_pylint_score: initialPylint,
      final_pylint_score: finalPylint,
      initial_bandit_high_medium: initialBandit,
      final_bandit_high_medium: finalBandit,
      initial_avg_complexity: summary.initial_avg_complexity ?? first?.avg_complexity ?? null,
      final_avg_complexity: summary.final_avg_complexity ?? last?.avg_complexity ?? null,
      initial_maintainability_index:
        summary.initial_maintainability_index ?? first?.maintainability_index ?? null,
      final_maintainability_index:
        summary.final_maintainability_index ?? last?.maintainability_index ?? null,
    },
  };
}

export function sliceResultThroughIteration(fullResult, visibleCount) {
  if (!fullResult || visibleCount <= 0) return null;
  const iterations = fullResult.iterations.slice(0, visibleCount);
  const last = iterations[iterations.length - 1];
  const first = iterations[0];
  const complete = visibleCount >= fullResult.iterations.length;
  if (complete) return fullResult;
  return {
    ...fullResult,
    final_code: last.code,
    converged: false,
    total_iterations: iterations.length,
    final_pylint_score: last.pylint_score,
    final_bandit_high_medium: last.bandit_high_medium_count,
    status: "PLAYBACK",
    iterations,
    unified_diff: last.diff ?? null,
    metrics_summary: {
      ...fullResult.metrics_summary,
      final_pylint_score: last.pylint_score,
      final_bandit_high_medium: last.bandit_high_medium_count,
      final_avg_complexity: last.avg_complexity ?? null,
      final_maintainability_index: last.maintainability_index ?? null,
      initial_pylint_score: first.pylint_score,
      initial_bandit_high_medium: first.bandit_high_medium_count,
    },
    decision: last.accepted ? "accepted" : "rejected",
    decision_reason: last.acceptance_reason ?? null,
  };
}
