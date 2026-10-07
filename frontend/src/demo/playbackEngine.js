export const PIPELINE_STAGES = [
  { id: "input", name: "INPUT", num: "01" },
  { id: "gemini", name: "GEMINI", num: "02" },
  { id: "analysis", name: "STATIC ANALYSIS", num: "03" },
  { id: "feedback", name: "FEEDBACK", num: "04" },
  { id: "refinement", name: "REFINEMENT", num: "05" },
  { id: "regression", name: "REGRESSION CHECK", num: "06" },
  { id: "acceptance", name: "ACCEPTANCE", num: "07" },
  { id: "best", name: "BEST CODE", num: "08" },
];

const STAGE_ALIASES = {
  input: "input",
  generation: "gemini",
  gemini: "gemini",
  bandit: "analysis",
  pylint: "analysis",
  radon: "analysis",
  issue_extraction: "analysis",
  static_analysis: "analysis",
  analysis: "analysis",
  feedback: "feedback",
  refinement: "refinement",
  regression: "regression",
  regression_check: "regression",
  acceptance: "acceptance",
  best: "best",
  best_code: "best",
};

export const DEFAULT_TIMING_EVENTS = [
  { stage: "input", duration_ms: 400 },
  { stage: "gemini", duration_ms: 1400 },
  { stage: "bandit", duration_ms: 500 },
  { stage: "pylint", duration_ms: 700 },
  { stage: "radon", duration_ms: 500 },
  { stage: "issue_extraction", duration_ms: 400 },
  { stage: "feedback", duration_ms: 800 },
  { stage: "refinement", duration_ms: 1200 },
  { stage: "regression", duration_ms: 600 },
  { stage: "acceptance", duration_ms: 700 },
  { stage: "best", duration_ms: 400 },
];

export function mapEventToPipelineStage(stage) {
  const key = String(stage || "").toLowerCase();
  return STAGE_ALIASES[key] || null;
}

export function scaleTimings(events, { minTotal = 8000, maxTotal = 15000 } = {}) {
  if (!events.length) return events;
  const sum = events.reduce((acc, event) => acc + Number(event.duration_ms || 0), 0);
  if (sum <= 0) return events;
  let factor = 1;
  if (sum > maxTotal) factor = maxTotal / sum;
  else if (sum < minTotal) factor = minTotal / sum;
  if (factor === 1) return events;
  return events.map((event) => ({
    ...event,
    duration_ms: Math.max(80, Math.round(Number(event.duration_ms || 0) * factor)),
  }));
}

export function visibleIterationsForStage(stageId, totalIterations) {
  if (!totalIterations) return 0;
  if (stageId === "best" || stageId === "acceptance") return totalIterations;
  if (stageId === "refinement" || stageId === "regression") {
    return Math.min(totalIterations, 2);
  }
  return 1;
}

export function createPlayback({
  timingEvents,
  speed = 1,
  iterationCount = 1,
  onStage,
  onTool,
  onVisibleIterations,
  onComplete,
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
} = {}) {
  const events = scaleTimings(
    timingEvents && timingEvents.length ? timingEvents : DEFAULT_TIMING_EVENTS
  );
  const factor = Math.max(0.25, Number(speed) || 1);
  let cancelled = false;
  let timer = null;
  let index = 0;
  const completedStages = new Set();

  const finish = () => {
    PIPELINE_STAGES.forEach((stage) => completedStages.add(stage.id));
    onStage?.({ active: "best", completed: Array.from(completedStages) });
    onVisibleIterations?.(iterationCount);
    onComplete?.();
  };

  const tick = () => {
    if (cancelled) return;
    if (index >= events.length) {
      finish();
      return;
    }
    const event = events[index];
    const pipelineStage = mapEventToPipelineStage(event.stage);
    if (pipelineStage) {
      const prior = PIPELINE_STAGES.findIndex((s) => s.id === pipelineStage);
      PIPELINE_STAGES.forEach((stage, idx) => {
        if (idx < prior) completedStages.add(stage.id);
      });
      onStage?.({ active: pipelineStage, completed: Array.from(completedStages) });
      onVisibleIterations?.(visibleIterationsForStage(pipelineStage, iterationCount));
    }
    const tool = String(event.stage || "").toLowerCase();
    if (["bandit", "pylint", "radon"].includes(tool)) {
      onTool?.(tool);
    }
    const delay = Math.max(40, Math.round(Number(event.duration_ms || 0) / factor));
    timer = setTimeoutFn(() => {
      if (pipelineStage) completedStages.add(pipelineStage);
      index += 1;
      tick();
    }, delay);
  };

  return {
    start() {
      cancelled = false;
      index = 0;
      completedStages.clear();
      tick();
    },
    skip() {
      cancelled = true;
      if (timer) clearTimeoutFn(timer);
      finish();
    },
    stop() {
      cancelled = true;
      if (timer) clearTimeoutFn(timer);
    },
  };
}
