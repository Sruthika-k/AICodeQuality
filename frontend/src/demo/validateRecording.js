const LOAD_ERROR = "Recorded run could not be loaded.";

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function metricsLookValid(metrics) {
  if (!isObject(metrics)) return false;
  const keys = [
    "initial_pylint_score",
    "final_pylint_score",
    "initial_bandit_high_medium",
    "final_bandit_high_medium",
    "pylint_score",
    "bandit_high_medium",
  ];
  return keys.some((key) => key in metrics);
}

export function validateRecording(recording) {
  if (!isObject(recording)) {
    return { ok: false, error: LOAD_ERROR };
  }
  if (!recording.recording_version) {
    return { ok: false, error: LOAD_ERROR };
  }
  if (!recording.recording_type) {
    return { ok: false, error: LOAD_ERROR };
  }

  const iterations = recording.iterations;
  if (!Array.isArray(iterations) || iterations.length === 0) {
    return { ok: false, error: LOAD_ERROR };
  }
  for (const iteration of iterations) {
    if (!isObject(iteration) || typeof iteration.iteration !== "number") {
      return { ok: false, error: LOAD_ERROR };
    }
  }

  const result = recording.result;
  const finalBlock = recording.final;
  const hasFinalCode =
    (isObject(finalBlock) && typeof finalBlock.code === "string") ||
    (isObject(result) && typeof result.final_code === "string");
  if (!hasFinalCode) {
    return { ok: false, error: LOAD_ERROR };
  }

  const metrics =
    (isObject(result) && result.metrics_summary) ||
    (isObject(finalBlock) && finalBlock.metrics) ||
    null;
  if (!metricsLookValid(metrics) && !isObject(result?.metrics_summary) && !isObject(finalBlock?.metrics)) {
    return { ok: false, error: LOAD_ERROR };
  }
  if (!isObject(metrics)) {
    return { ok: false, error: LOAD_ERROR };
  }

  return { ok: true, error: null };
}

export const RECORDING_LOAD_ERROR = LOAD_ERROR;
