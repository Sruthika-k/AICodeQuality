import React from "react";
import { PIPELINE_STAGES } from "../demo/playbackEngine";

export default function Pipeline({ activeStage = null, completedStages = [] }) {
  const completed = new Set(completedStages);
  const stages = PIPELINE_STAGES;

  const statusFor = (stageId) => {
    if (completed.has(stageId) && activeStage !== stageId) return "done";
    if (activeStage === stageId) return "running";
    return "waiting";
  };

  return (
    <div className="card pipeline-card" data-testid="pipeline">
      <div className="card-header">
        <h2>REFINEMENT PIPELINE</h2>
      </div>
      <div className="pipeline-stages">
        {stages.map((stage, idx) => {
          const status = statusFor(stage.id);
          return (
            <React.Fragment key={stage.num}>
              <div className={`pipeline-stage ${status}`} data-testid={`pipeline-stage-${stage.id}`}>
                <span className="stage-num">{stage.num}</span>
                <span className="stage-name">{stage.name}</span>
                <span className={`stage-status ${status}`}>
                  {status === "waiting" && "○"}
                  {status === "running" && "⟳"}
                  {status === "done" && "✓"}
                </span>
              </div>
              {idx < stages.length - 1 && <div className="pipeline-arrow">→</div>}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
