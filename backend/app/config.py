"""Experiment flags. Defaults match current LoopController behavior."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional
import os

STRATEGY_LOOP = "loop"
STRATEGY_SINGLE_SHOT = "single_shot"
STRATEGY_SINGLE_SHOT_SECURE = "single_shot_secure"
STRATEGIES = (STRATEGY_SINGLE_SHOT, STRATEGY_SINGLE_SHOT_SECURE, STRATEGY_LOOP)
SINGLE_SHOT_STRATEGIES = {STRATEGY_SINGLE_SHOT, STRATEGY_SINGLE_SHOT_SECURE}

STOP_RULE_THRESHOLD = "threshold"
STOP_RULE_CAP = "cap"
STOP_RULE_FIXED_CAP = "fixed_cap"
STOP_RULE_PLATEAU = "plateau"
STOP_RULES = (STOP_RULE_THRESHOLD, STOP_RULE_CAP, STOP_RULE_FIXED_CAP, STOP_RULE_PLATEAU)

STOP_REASON_CONVERGED = "CONVERGED_THRESHOLD"
STOP_REASON_CAP = "STOP_CAP"
STOP_REASON_FIXED_CAP = "STOP_FIXED_CAP"
STOP_REASON_PLATEAU = "STOP_PLATEAU_WEIGHTED"
STOP_REASON_SINGLE_SHOT = "SINGLE_SHOT"
STOP_REASON_PLATEAU_LEGACY = "STOP_PLATEAU_PYLINT"

ACCEPTANCE_RULE_WEIGHTED = "weighted"
ACCEPTANCE_RULE_CONSTRAINED = "constrained"
ACCEPTANCE_RULES = (ACCEPTANCE_RULE_WEIGHTED, ACCEPTANCE_RULE_CONSTRAINED)

DEFAULT_MAX_AVG_COMPLEXITY = 10
DEFAULT_MAX_MAX_COMPLEXITY = 15
DEFAULT_MIN_MAINTAINABILITY_INDEX = 65.0

SECURE_CODE_INSTRUCTION = (
    "Write secure, clean, lint-free Python. Follow PEP 8, include appropriate "
    "docstrings, avoid eval/exec/os.system and subprocess shell=True, and do not "
    "hardcode secrets."
)

SEVERITY_WEIGHTS: Dict[str, int] = {
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 1,
    "ERROR": 10,
    "WARNING": 3,
    "CONVENTION": 1,
    "REFACTOR": 2,
}
DEFAULT_SEVERITY_WEIGHT = 1
PLATEAU_MIN_STRIKES = 2


def normalize_strategy(strategy: str) -> str:
    if strategy == "iterative":
        return STRATEGY_LOOP
    return strategy


def normalize_stop_rule(stop_rule: str) -> str:
    s = (stop_rule or "").strip().lower()
    if s in ("fixedcap", "fixed-cap", "fixed_cap"):
        return STOP_RULE_FIXED_CAP
    if s == STOP_RULE_FIXED_CAP:
        return STOP_RULE_FIXED_CAP
    if s == STOP_RULE_CAP:
        return STOP_RULE_CAP
    if s == STOP_RULE_PLATEAU:
        return STOP_RULE_PLATEAU
    return STOP_RULE_THRESHOLD


@dataclass
class ExperimentConfig:
    """Flags that vary across experiment runs.

    Defaults reproduce existing behavior:
    detailed feedback, top-5 issues, stop on quality threshold, iterative
    repair loop, model-default temperature (unset), 3-iteration cap,
    weighted acceptance (no rejection).
    """

    feedback_mode: str = "detailed"
    top_k: int = 5
    stop_rule: str = "threshold"
    strategy: str = STRATEGY_LOOP
    temperature: Optional[float] = None
    iteration_cap: int = 3
    pylint_threshold: float = 8.0
    max_bandit_high_med: int = 0
    plateau_window: int = 3
    plateau_threshold: float = 0.1
    model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    enable_radon: bool = False
    acceptance_rule: str = ACCEPTANCE_RULE_WEIGHTED
    max_avg_complexity: int = DEFAULT_MAX_AVG_COMPLEXITY
    max_max_complexity: int = DEFAULT_MAX_MAX_COMPLEXITY
    min_maintainability_index: float = DEFAULT_MIN_MAINTAINABILITY_INDEX
    # Experimental runs flag: when True, quality-convergence (threshold_met) does NOT
    # short-circuit fixed_cap / cap / plateau runs (keeps default threshold rule behavior).
    disable_convergence_stop: bool = False

    def __post_init__(self) -> None:
        self.strategy = normalize_strategy(self.strategy)
        self.stop_rule = normalize_stop_rule(self.stop_rule)
        ar = (self.acceptance_rule or "").strip().lower()
        if ar in ACCEPTANCE_RULES:
            self.acceptance_rule = ar
        else:
            self.acceptance_rule = ACCEPTANCE_RULE_WEIGHTED
        if isinstance(self.enable_radon, str):
            self.enable_radon = self.enable_radon.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(self.max_avg_complexity, str):
            self.max_avg_complexity = int(self.max_avg_complexity)
        if isinstance(self.max_max_complexity, str):
            self.max_max_complexity = int(self.max_max_complexity)
        if isinstance(self.min_maintainability_index, str):
            self.min_maintainability_index = float(self.min_maintainability_index)
        if isinstance(self.disable_convergence_stop, str):
            self.disable_convergence_stop = (
                str(self.disable_convergence_stop).strip().lower() in ("1", "true", "yes", "on")
            )

    @property
    def is_single_shot(self) -> bool:
        return self.strategy in SINGLE_SHOT_STRATEGIES

    @classmethod
    def from_env(cls) -> "ExperimentConfig":
        temp_raw = os.getenv("EXPERIMENT_TEMPERATURE")
        temperature = float(temp_raw) if temp_raw not in (None, "") else None
        radon_raw = os.getenv("EXPERIMENT_ENABLE_RADON")
        enable_radon = radon_raw is not None and radon_raw.strip().lower() in ("1", "true", "yes", "on")
        ar_raw = os.getenv("EXPERIMENT_ACCEPTANCE_RULE", ACCEPTANCE_RULE_WEIGHTED)
        max_avg_cc_raw = os.getenv("EXPERIMENT_MAX_AVG_COMPLEXITY")
        max_max_cc_raw = os.getenv("EXPERIMENT_MAX_MAX_COMPLEXITY")
        min_mi_raw = os.getenv("EXPERIMENT_MIN_MI")
        return cls(
            feedback_mode=os.getenv("EXPERIMENT_FEEDBACK_MODE", "detailed"),
            top_k=int(os.getenv("EXPERIMENT_TOP_K", "5")),
            stop_rule=os.getenv("EXPERIMENT_STOP_RULE", "threshold"),
            strategy=os.getenv("EXPERIMENT_STRATEGY", STRATEGY_LOOP),
            temperature=temperature,
            iteration_cap=int(os.getenv("EXPERIMENT_ITERATION_CAP", "3")),
            pylint_threshold=float(os.getenv("EXPERIMENT_PYLINT_THRESHOLD", "8.0")),
            max_bandit_high_med=int(os.getenv("EXPERIMENT_MAX_BANDIT_HIGH_MED", "0")),
            plateau_window=int(os.getenv("EXPERIMENT_PLATEAU_WINDOW", "3")),
            plateau_threshold=float(os.getenv("EXPERIMENT_PLATEAU_THRESHOLD", "0.1")),
            model=os.getenv("EXPERIMENT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")),
            enable_radon=enable_radon,
            acceptance_rule=ar_raw,
            max_avg_complexity=int(max_avg_cc_raw) if max_avg_cc_raw not in (None, "") else DEFAULT_MAX_AVG_COMPLEXITY,
            max_max_complexity=int(max_max_cc_raw) if max_max_cc_raw not in (None, "") else DEFAULT_MAX_MAX_COMPLEXITY,
            min_maintainability_index=float(min_mi_raw) if min_mi_raw not in (None, "") else DEFAULT_MIN_MAINTAINABILITY_INDEX,
            disable_convergence_stop=(
                os.getenv("EXPERIMENT_DISABLE_CONVERGENCE_STOP", "").strip().lower() in ("1", "true", "yes", "on")
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


default_config = ExperimentConfig()
