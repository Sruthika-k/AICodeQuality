# Research Evaluation Prompt Set

This directory contains 8 Python code-generation tasks designed for reproducible experimental evaluation of the AICodeQuality system.

## Purpose

These prompts are deliberately designed to test specific quality dimensions of the automated refinement loop. They are **not** software tests - they are research evaluation inputs.

Each prompt can be used across all four experimental conditions (C1-C4) because:
- The same initial prompt produces comparable starting code
- Conditions C1-C4 differ only in refinement strategy, not input
- This enables controlled comparison of effectiveness

## Task Descriptions

### Task 1: Security Vulnerability
**ID:** `task_01_security_vulnerability`
**Quality Dimension:** Security
**Purpose:** Tests detection and repair of a single critical security vulnerability (use of `os.system` with user input).
**Expected Issues:** Bandit HIGH/MEDIUM security findings for unsafe shell execution.
**Why for C1-C4:** All conditions should identify the security issue; C3 (regression-aware) should prevent reintroduction; C4 (constrained) should reject any version with security regression.

### Task 2: Multiple Security Vulnerabilities
**ID:** `task_02_multiple_security`
**Quality Dimension:** Security (multiple)
**Purpose:** Tests handling of multiple distinct security issues (pickle deserialization, subprocess shell=True, eval(), hardcoded secrets).
**Expected Issues:** Multiple Bandit HIGH/MEDIUM findings across different vulnerability types.
**Why for C1-C4:** Tests whether refinement can fix multiple security issues without introducing new ones; C3 regression-aware is critical for tracking multiple fixes.

### Task 3: Poor Code Quality / Pylint Issues
**ID:** `task_03_poor_quality`
**Quality Dimension:** Code Quality
**Purpose:** Tests basic Pylint rule compliance (missing docstrings, poor naming conventions, unused variables).
**Expected Issues:** Multiple Pylint CONVENTION and WARNING issues, low Pylint score.
**Why for C1-C4:** C1 single-shot will produce poor code; C2-C4 should iteratively improve; C4 constrained should reject if Pylint score drops.

### Task 4: High Cyclomatic Complexity
**ID:** `task_04_high_complexity`
**Quality Dimension:** Complexity
**Purpose:** Tests detection and reduction of high cyclomatic complexity through deep nesting.
**Expected Issues:** High average and maximum cyclomatic complexity (via Radon), potential maintainability issues.
**Why for C1-C4:** Tests whether refinement can simplify nested logic; C4 constrained should reject if complexity exceeds thresholds (when Radon enabled).

### Task 5: Low Maintainability
**ID:** `task_05_low_maintainability`
**Quality Dimension:** Maintainability
**Purpose:** Tests identification of code with low maintainability index due to monolithic function design.
**Expected Issues:** Low maintainability index (via Radon), poor code organization.
**Why for C1-C4:** Tests whether refinement can break down monolithic functions; C4 constrained should reject if MI below threshold.

### Task 6: Mixed Security + Quality Issues
**ID:** `task_06_mixed_security_quality`
**Quality Dimension:** Security + Quality
**Purpose:** Tests handling of combined security vulnerabilities and code quality issues.
**Expected Issues:** Bandit security findings (SQL injection, eval) + Pylint issues (missing docs, unused imports, long functions).
**Why for C1-C4:** Tests trade-off between security and quality fixes; C3 regression-aware must track both categories; C4 constrained must evaluate both security and Pylint constraints.

### Task 7: Mixed Quality + Complexity Issues
**ID:** `task_07_mixed_quality_complexity`
**Quality Dimension:** Quality + Complexity
**Purpose:** Tests complex code with quality issues (global variables, mutable defaults, deep nesting).
**Expected Issues:** High complexity (Radon) + Pylint issues (global variables, mutable defaults).
**Why for C1-C4:** Tests whether refinement can address both complexity and quality simultaneously; C4 constrained has multiple constraints to satisfy.

### Task 8: Clean with Minor Issues
**ID:** `task_08_clean_minor`
**Quality Dimension:** Baseline / Easy Case
**Purpose:** Provides a relatively clean baseline to verify the system doesn't over-refactor or introduce issues.
**Expected Issues:** Minimal to no issues; should converge quickly.
**Why for C1-C4:** All conditions should converge in 1-2 iterations; serves as positive control to ensure refinement doesn't break working code.

## Usage

Run evaluation with the experiment harness:

```bash
python scripts/run_matrix.py --iteration-cap 3 --shared-gen research_evaluation/evaluation_prompts.jsonl
```

## File Format

JSONL (JSON Lines) format with one task per line:
- `id`: Unique task identifier
- `prompt`: Natural language description of the Python code to generate

## Reproducibility

Each prompt is deterministic and self-contained:
- No external dependencies beyond standard library
- No randomness in specification
- Same prompt → same initial generation (given same model and temperature)

## Notes

- These are **research evaluation inputs**, not regression tests
- They are designed to stress-test specific quality dimensions
- Results should be analyzed across C1-C4 to compare refinement strategies
- Actual performance depends on Gemini model behavior and configured thresholds
