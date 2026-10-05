"""Experiment flags. Defaults match current LoopController behavior."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional
import os


@dataclass
class ExperimentConfig:
    """Flags that vary across experiment runs.

    Defaults reproduce existing behavior:
    detailed feedback, top-5 issues, stop on quality threshold, iterative
    repair, model-default temperature (unset), 3-iteration cap.
    """

    feedback_mode: str = "detailed"
    top_k: int = 5
    stop_rule: str = "threshold"
    strategy: str = "iterative"
    temperature: Optional[float] = None
    iteration_cap: int = 3
    pylint_threshold: float = 8.0
    max_bandit_high_med: int = 0
    plateau_window: int = 3
    plateau_threshold: float = 0.1
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

    @classmethod
    def from_env(cls) -> "ExperimentConfig":
        temp_raw = os.getenv("EXPERIMENT_TEMPERATURE")
        temperature = float(temp_raw) if temp_raw not in (None, "") else None
        return cls(
            feedback_mode=os.getenv("EXPERIMENT_FEEDBACK_MODE", "detailed"),
            top_k=int(os.getenv("EXPERIMENT_TOP_K", "5")),
            stop_rule=os.getenv("EXPERIMENT_STOP_RULE", "threshold"),
            strategy=os.getenv("EXPERIMENT_STRATEGY", "iterative"),
            temperature=temperature,
            iteration_cap=int(os.getenv("EXPERIMENT_ITERATION_CAP", "3")),
            pylint_threshold=float(os.getenv("EXPERIMENT_PYLINT_THRESHOLD", "8.0")),
            max_bandit_high_med=int(os.getenv("EXPERIMENT_MAX_BANDIT_HIGH_MED", "0")),
            plateau_window=int(os.getenv("EXPERIMENT_PLATEAU_WINDOW", "3")),
            plateau_threshold=float(os.getenv("EXPERIMENT_PLATEAU_THRESHOLD", "0.1")),
            model=os.getenv("EXPERIMENT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


default_config = ExperimentConfig()
