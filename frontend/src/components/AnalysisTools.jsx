import React from "react";

export default function AnalysisTools({ activeTool = null }) {
  const tools = [
    { name: "Bandit", id: "bandit", description: "Security analysis" },
    { name: "Pylint", id: "pylint", description: "Code quality" },
    { name: "Radon", id: "radon", description: "Complexity & maintainability" },
  ];

  return (
    <div className="analysis-tools" data-testid="analysis-tools">
      {tools.map((tool) => (
        <div
          key={tool.name}
          className={`analysis-tool-card ${activeTool === tool.id ? "active" : ""}`}
          data-testid={`analysis-tool-${tool.id}`}
        >
          <div className="tool-name">{tool.name}</div>
          <div className="tool-desc">{tool.description}</div>
        </div>
      ))}
    </div>
  );
}
