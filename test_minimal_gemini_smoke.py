"""Minimal real Gemini smoke test: maximum 2 API calls."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv()

from backend.app.config import ExperimentConfig
from backend.app.loop_controller import LoopController
from backend.app.llm_interface import LLMInterface
from backend.app.static_analyzer import StaticAnalyzer
from backend.app.issue_extractor import IssueExtractor
from backend.app.feedback_generator import FeedbackGenerator

PROMPT = "Write a Python function called count_vowels(text) that returns the number of vowels (a, e, i, o, u) in the given string. Treat uppercase and lowercase vowels the same."

MAX_CALLS = 2

class CallTrackingLLM:
    """Track and limit API calls."""
    def __init__(self, llm, max_calls):
        self.llm = llm
        self.max_calls = max_calls
        self.call_count = 0

    def generate(self, prompt: str, temperature: float = 0.0) -> str:
        if self.call_count >= self.max_calls:
            raise RuntimeError(f"Max calls ({self.max_calls}) reached. Cannot make additional API calls.")
        self.call_count += 1
        print(f"[API CALL #{self.call_count}/{self.max_calls}] Making Gemini request...")
        return self.llm.generate(prompt, temperature=temperature)

    @property
    def model_name(self) -> str:
        return getattr(self.llm, "model_name", "unknown")

def main():
    print("="*60)
    print("REAL GEMINI MINIMAL SMOKE TEST")
    print("="*60)
    print(f"Model: gemini-3.8-flash")
    print(f"Max API calls: {MAX_CALLS}")
    print(f"Iteration cap: 2")
    print("="*60)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set")
        return 1

    try:
        # Initialize LLM with call tracking
        real_llm = LLMInterface(model_name="gemini-3.8-flash")
        llm = CallTrackingLLM(real_llm, max_calls=MAX_CALLS)

        # CALL 1: Initial generation
        print("\n[CALL 1] Initial generation...")
        try:
            initial_code = llm.generate(PROMPT, temperature=0.0)
            print(f"[CALL 1] SUCCESS - Generated {len(initial_code)} characters")
            print(f"[CALL 1] Code preview: {initial_code[:100]}...")
        except Exception as e:
            print(f"[CALL 1] FAILED: {e}")
            print("\nSTOPPING - API authentication or generation failed")
            return 1

        # Static analysis on initial code
        print("\n[LOCAL] Running static analysis on initial code...")
        analyzer = StaticAnalyzer()
        try:
            analysis1 = analyzer.analyze(initial_code)
            print(f"[LOCAL] Bandit: {len([i for i in analysis1.issues if i.tool == 'bandit'])} issues")
            print(f"[LOCAL] Pylint: {len([i for i in analysis1.issues if i.tool == 'pylint'])} issues")
            print(f"[LOCAL] Radon: avg_complexity={analysis1.avg_complexity:.2f}, mi={analysis1.maintainability_index:.2f}")
            print("[LOCAL] Static analysis: PASS")
        except Exception as e:
            print(f"[LOCAL] Static analysis FAILED: {e}")
            return 1

        # Issue extraction
        print("\n[LOCAL] Extracting issues...")
        try:
            extractor = IssueExtractor(max_issues=10)
            extracted1 = extractor.extract(analysis1.issues)
            print(f"[LOCAL] Extracted {len(extracted1)} issues")
            print("[LOCAL] Issue extraction: PASS")
        except Exception as e:
            print(f"[LOCAL] Issue extraction FAILED: {e}")
            return 1

        # CALL 2: Refinement
        print("\n[CALL 2] Refinement...")
        try:
            # Generate feedback prompt
            feedback_gen = FeedbackGenerator()
            feedback = feedback_gen.generate_feedback(initial_code, extracted1)
            print(f"[LOCAL] Generated feedback: {len(feedback)} characters")

            # Make refinement call
            refined_code = llm.generate(feedback, temperature=0.0)
            print(f"[CALL 2] SUCCESS - Refined code: {len(refined_code)} characters")
            print(f"[CALL 2] Code preview: {refined_code[:100]}...")
        except Exception as e:
            print(f"[CALL 2] FAILED: {e}")
            print("\nSTOPPING - Refinement failed")
            return 1

        # Static analysis on refined code
        print("\n[LOCAL] Running static analysis on refined code...")
        try:
            analysis2 = analyzer.analyze(refined_code)
            print(f"[LOCAL] Bandit: {len([i for i in analysis2.issues if i.tool == 'bandit'])} issues")
            print(f"[LOCAL] Pylint: {len([i for i in analysis2.issues if i.tool == 'pylint'])} issues")
            print(f"[LOCAL] Radon: avg_complexity={analysis2.avg_complexity:.2f}, mi={analysis2.maintainability_index:.2f}")
            print("[LOCAL] Static analysis: PASS")
        except Exception as e:
            print(f"[LOCAL] Static analysis FAILED: {e}")
            return 1

        # Issue extraction on refined code
        print("\n[LOCAL] Extracting issues from refined code...")
        try:
            extracted2 = extractor.extract(analysis2.issues)
            print(f"[LOCAL] Extracted {len(extracted2)} issues")
            print("[LOCAL] Issue extraction: PASS")
        except Exception as e:
            print(f"[LOCAL] Issue extraction FAILED: {e}")
            return 1

        # Issue diff
        print("\n[LOCAL] Computing issue diff...")
        try:
            e1_set = {(i.tool or "", i.rule_id or "") for i in extracted1}
            e2_set = {(i.tool or "", i.rule_id or "") for i in extracted2}
            resolved = len(e1_set - e2_set)
            introduced = len(e2_set - e1_set)
            print(f"[LOCAL] Resolved: {resolved}, Introduced: {introduced}")
            print("[LOCAL] Issue diff: PASS")
        except Exception as e:
            print(f"[LOCAL] Issue diff FAILED: {e}")
            return 1

        print(f"\n[API BUDGET] Used {llm.call_count}/{MAX_CALLS} calls")
        print("[API BUDGET] PASS")

        print("\n" + "="*60)
        print("REAL GEMINI GENERATION AND REFINEMENT VERIFIED.")
        print("="*60)

        return 0

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
