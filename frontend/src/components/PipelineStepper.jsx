import React from "react";

export default function PipelineStepper({ activeStep = null }) {
  const steps = [
    { id: "input", icon: "📝", caption: "Input or generate code" },
    { id: "gemini", icon: "🤖", caption: "AI analyzes and fixes" },
    { id: "analysis", icon: "🔍", caption: "Static analysis scan" },
    { id: "feedback", icon: "💬", caption: "Feedback on issues" },
    { id: "refinement", icon: "✏️", caption: "Refinement attempt" },
    { id: "regression", icon: "⚠️", caption: "Regression check" },
    { id: "acceptance", icon: "✓", caption: "Accept if better" },
    { id: "best", icon: "★", caption: "Return best code" },
  ];

  const getStepStatus = (stepId) => {
    if (!activeStep) return "waiting";
    const stepIndex = steps.findIndex(s => s.id === stepId);
    const activeIndex = steps.findIndex(s => s.id === activeStep);
    if (stepIndex < activeIndex) return "done";
    if (stepIndex === activeIndex) return "running";
    return "waiting";
  };

  return (
    <div className="card pipeline-stepper-card">
      <div className="card-header">
        <h2>REFINEMENT PIPELINE</h2>
      </div>
      <div className="stepper">
        {steps.map((step, idx) => {
          const status = getStepStatus(step.id);
          return (
            <React.Fragment key={step.id}>
              <div className={`stepper-step ${status}`}>
                <div className="step-icon">{step.icon}</div>
                <div className="step-caption">{step.caption}</div>
                <div className={`step-status ${status}`}>
                  {status === "waiting" && "○"}
                  {status === "running" && "⟳"}
                  {status === "done" && "✓"}
                  {status === "skipped" && "⊘"}
                </div>
              </div>
              {idx < steps.length - 1 && <div className="stepper-arrow">→</div>}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}