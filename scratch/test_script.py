import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path("e:/MiniProject/AICodeQuality").resolve()))

from backend.app.loop_controller import LoopController, ExperimentConfig
from tests.conftest import FakeLLM
from backend.app.static_analyzer import StaticAnalysisResult, StaticAnalysisIssue

class MockAnalyzer:
    def __init__(self, sequence):
        self.sequence = sequence
        self.idx = 0
    def analyze(self, code, enable_radon=False):
        if self.idx >= len(self.sequence):
            val = self.sequence[-1]
        else:
            val = self.sequence[self.idx]
            self.idx += 1
            
        issues = []
        if val == 6:
            issues = [
                StaticAnalysisIssue("bandit", "MEDIUM", 1, "m", "B101"),
                StaticAnalysisIssue("bandit", "LOW", 1, "m", "B102")
            ]
        elif val == 2:
            issues = [
                StaticAnalysisIssue("bandit", "LOW", 1, "m", "B103"),
                StaticAnalysisIssue("bandit", "LOW", 2, "m", "B104")
            ]
        elif val == 15:
            issues = [
                StaticAnalysisIssue("bandit", "HIGH", 1, "m", "B105"),
                StaticAnalysisIssue("bandit", "MEDIUM", 1, "m", "B106")
            ]
            
        return StaticAnalysisResult(
            issues=issues,
            pylint_score=7.0,
            has_syntax_error=False,
            avg_complexity=1.0,
            max_complexity=1,
            maintainability_index=100.0
        )

# Part 1: weighted
print("=== WEIGHTED ===")
cfg = ExperimentConfig(acceptance_rule="weighted", stop_rule="fixed_cap", iteration_cap=3, enable_radon=False)
llm = FakeLLM(["code1", "code2", "code3"])
analyzer = MockAnalyzer([6, 2, 15])
controller = LoopController(llm=llm, config=cfg)
controller.run_logger = MagicMock()
controller.analyzer = analyzer
res = controller.run("test prompt")
print(f"Returned code: {res.final_code}")
final_it = next(it for it in res.iterations if it.code == res.final_code)
print(f"Iteration index: {final_it.iteration}")
print(f"Weighted Score: {final_it.weighted_issue_score}")
print("="*40)

# Part 2: constrained
print("=== CONSTRAINED ===")
cfg2 = ExperimentConfig(acceptance_rule="constrained", stop_rule="fixed_cap", iteration_cap=3, enable_radon=False)
llm2 = FakeLLM(["code1", "code2", "code3"])
analyzer2 = MockAnalyzer([6, 2, 15])
controller2 = LoopController(llm=llm2, config=cfg2)
controller2.run_logger = MagicMock()
controller2.analyzer = analyzer2
res2 = controller2.run("test prompt")
print(f"Returned code: {res2.final_code}")
final_it2 = next(it for it in res2.iterations if it.code == res2.final_code)
print(f"Iteration index: {final_it2.iteration}")
print(f"Weighted Score: {final_it2.weighted_issue_score}")

