# acceptance_rule (weighted vs constrained) Implementation Plan

## Repository Research

### Current Acceptance Flow
- `LoopController.run()` in [loop_controller.py](file:///e:/MiniProject/AICodeQuality/backend/app/loop_controller.py#L326-L578) performs iterations 1..cap.
- Each iteration:
  1. If no current_code → generate from prompt.
  2. Analyze with Bandit/Pylint (+ Radon optional).
  3. Build `IterationData` and append to `iterations_history` unconditionally → **every candidate is accepted**.
  4. Check stop rule (threshold / cap / plateau) — decision only affects early exit, not acceptance.
  5. If continuing, build refinement prompt from the SAME current_code and call LLM to produce next candidate.
- Final outputs:
  - `LoopResult.final_code = iterations_history[-1].code` → **always uses the last iteration**, never the best.
  - `LoopResult.iterations` = all iterations with `threshold_met` flag.
- `rejected_iterations` in run_logger CSV currently counts `sum(1 for it in history if not it.threshold_met)` — it counts threshold failures, not constraint rejections.

### Existing Config (ExperimentConfig)
- Fields: `feedback_mode`, `top_k`, `stop_rule`, `strategy`, `temperature`, `iteration_cap`, `pylint_threshold`, `max_bandit_high_med`, `plateau_window`, `plateau_threshold`, `model`, `enable_radon`.
- No acceptance rule or complexity/MI limit fields.

### IterationData
- Carries: `weighted_issue_score`, `pylint_score`, `avg_complexity`, `max_complexity`, `maintainability_index`, `raw_issues`, `threshold_met`, `feedback_text`.
- Does NOT carry: acceptance decision, acceptance reason.

### Weighted Score
- `weighted_issue_score()` in loop_controller.py L33-L44 uses `SEVERITY_WEIGHTS` from config (HIGH/ERROR=10, MEDIUM=5, ...).

## Files and Modules

1. **[config.py](file:///e:/MiniProject/AICodeQuality/backend/app/config.py)** — Add acceptance_rule flag + constants; add complexity/MI limit defaults; wire to `from_env()`.
2. **[loop_controller.py](file:///e:/MiniProject/AICodeQuality/backend/app/loop_controller.py)** — Core change: acceptance evaluation per candidate, logging, best-code tracking, and code-path selection for next-feedback generation.
3. **[run_logger.py](file:///e:/MiniProject/AICodeQuality/backend/app/run_logger.py)** — Optionally expand CSV columns with acceptance summary columns (best_iteration, last_acceptance_reason).
4. **[tests/test_loop_controller.py](file:///e:/MiniProject/AICodeQuality/tests/test_loop_controller.py)** — Add tests for each rejection reason + the AC test.

## Implementation Steps (dependency order)

### Step 1 — Config layer (config.py)
- Add constants:
  - `ACCEPTANCE_RULE_WEIGHTED = "weighted"`
  - `ACCEPTANCE_RULE_CONSTRAINED = "constrained"`
  - `ACCEPTANCE_RULES = (..., ...)`
  - Default limits for constrained mode:
    - `DEFAULT_MAX_AVG_COMPLEXITY = 10`
    - `DEFAULT_MAX_MAX_COMPLEXITY = 15`
    - `DEFAULT_MIN_MAINTAINABILITY_INDEX = 65.0`
- Add `acceptance_rule: str = ACCEPTANCE_RULE_WEIGHTED` to `ExperimentConfig`.
- Add limit fields: `max_avg_complexity`, `max_max_complexity`, `min_maintainability_index` with the defaults above.
- Add `__post_init__` handling: if acceptance_rule string comes in via env, normalize lowercase.
- Wire in `from_env()` with env vars:
  - `EXPERIMENT_ACCEPTANCE_RULE`
  - `EXPERIMENT_MAX_AVG_COMPLEXITY`, `EXPERIMENT_MAX_MAX_COMPLEXITY`, `EXPERIMENT_MIN_MI`

### Step 2 — Acceptance primitives (loop_controller.py)
- Define a helper `security_weighted_score(issues)` returning weighted sum of ONLY Bandit issues (security), using SEVERITY_WEIGHTS.
- Add to `IterationData`:
  - `accepted: bool = True`
  - `acceptance_reason: str = "ACCEPTED_INITIAL"`
- Reason vocabulary (constant-like strings, one per trigger so tests can assert exactly):
  - `ACC_REASON_INITIAL = "ACCEPTED_INITIAL"` — first iteration, always accepted as baseline
  - `ACC_REASON_WEIGHTED = "ACCEPTED_WEIGHTED"` — weighted rule, accepted
  - `ACC_REASON_CONSTRAINED_OK = "ACCEPTED_CONSTRAINED_OK"` — all constraints satisfied
  - `REJ_SECURITY_WORSE = "REJECTED_SECURITY_WEIGHT_INCREASED"`
  - `REJ_PYLINT_DROP = "REJECTED_PYLINT_SCORE_DROPPED"`
  - `REJ_AVG_COMPLEXITY = "REJECTED_AVG_COMPLEXITY_EXCEEDED_LIMIT"`
  - `REJ_MAX_COMPLEXITY = "REJECTED_MAX_COMPLEXITY_EXCEEDED_LIMIT"`
  - `REJ_MAINTAINABILITY = "REJECTED_MAINTAINABILITY_BELOW_LIMIT"`
- Function `_evaluate_acceptance(cfg, previous_data, current_data) -> (bool, str)`:
  - If `previous_data is None` (first iteration): `(True, ACC_REASON_INITIAL)`.
  - If `cfg.acceptance_rule == weighted`: `(True, ACC_REASON_WEIGHTED)`.
  - If `constrained`: apply each constraint in the above list order; return `(False, first_matching_reason)` if any fails.
  - Constraints (AND):
    1. `security_weighted_score(current.raw_issues) > security_weighted_score(previous.raw_issues)` → `REJ_SECURITY_WORSE`
    2. `current.pylint_score < previous.pylint_score` (and previous wasn't None/0 — require strict drop) → `REJ_PYLINT_DROP`. Use strict < so same-or-better is OK.
    3. If `enable_radon`:
       - `avg_complexity > max_avg_complexity` → `REJ_AVG_COMPLEXITY`
       - `max_complexity > max_max_complexity` → `REJ_MAX_COMPLEXITY`
       - `maintainability_index < min_maintainability_index` → `REJ_MAINTAINABILITY`
       - **Note**: when Radon is off but acceptance_rule=constrained, these still need to fire. Since analyzer produces None when off, we interpret `None` as "not measured so can't reject" for radon-based constraints (skip silently). If user wants them checked, they must enable Radon — we'll document this behavior in the constant docstrings / tests.
  - If all passed → `(True, ACC_REASON_CONSTRAINED_OK)`.

### Step 3 — Main loop rework (LoopController.run in loop_controller.py)
Before the iteration for-loop:
- Init `best_iter_data: Optional[IterationData] = None` (the best **accepted** IterationData).
- Init `accepted_codes: List[str]` is not needed; `best_iter_data` is enough.

Inside iteration i:
- After generating/refining into `current_code`, do analysis and compute `raw_issues`, `pylint_score`, `weighted`, `threshold_met` — keep existing.
- Build `candidate_iter_data` **without** appending yet: create IterationData with all computed fields, `accepted=True/False` placeholder, `acceptance_reason=""` placeholder.
- Get `prev_accepted_data`:
  - If `best_iter_data is None` (first iteration) → `prev = None`.
  - Else → `prev = best_iter_data` (compare against the last accepted, not the last generated — so rejected candidates don't slide the baseline).
- Call `(accepted, reason) = _evaluate_acceptance(config, prev, candidate_iter_data)`.
- Set `candidate_iter_data.accepted = accepted`, `candidate_iter_data.acceptance_reason = reason`.
- **Append candidate_iter_data to iterations_history** (so we log every candidate with its acceptance decision — per requirement).
- **Acceptance acceptance branch**:
  - If ACCEPTED:
    - If `best_iter_data is None` OR candidate improves over best (use same ordering as `weighted_issue_score`: lower `weighted_issue_score` is better; tie-break by higher `pylint_score`):
      - `best_iter_data = candidate_iter_data`
    - `current_code_for_next_feedback = candidate_iter_data.code` (the newly accepted code becomes the working base)
  - If REJECTED:
    - **Do NOT** update `best_iter_data`.
    - `current_code_for_next_feedback = best_iter_data.code` — the next iteration must try to repair from the last **accepted** baseline (since the rejected code was bad, we shouldn't feed it back into the LLM to build upon).
- Compute diff / diff_lines **relative to best_iter_data.code (or previous in history order if you prefer existing semantics)** — keep existing "vs iterations_history[-1]" for simplicity (diff is informational; acceptance logic is separate).
- Stop-rule evaluation:
  - Apply `_evaluate_stopping()` using **candidate_iter_data.threshold_met + history** as today — still evaluates on actual generated candidates to decide when to stop.
  - Important: if candidate was rejected but happened to pass thresholds, it still won't be output as best (that's correct per constrained safety — the output is the last accepted version which might not have converged thresholds, so `converged` flag reflects best_iter_data, not last).
- Build feedback_text for next iteration (if continuing):
  - IMPORTANT: use `current_code_for_next_feedback` as the source code sent to LLM (the last accepted code).
  - The analysis shown in feedback is still the newly analyzed issues on `current_code`... actually the right semantics: we want the LLM to fix the issues present in the accepted baseline + tell it what the rejected candidate did wrong. To keep scope sane, we'll follow the same flow as today but pass `current_code_for_next_feedback` to the refinement prompt (the code block), and use `extracted_issues` from `current_code` (which might be the rejected candidate's issues — including newly introduced security issues the LLM must avoid).
  - Simplification that matches user intent: **prompt code block = `best_iter_data.code`**, **feedback generated from rejected candidate's analysis if current was rejected OR else from accepted candidate's analysis**. Actually simpler and matches today: analyze always `current_code` (the just-generated candidate), which produces the issues list for feedback generation — but send `best_iter_data.code` in the prompt's code block, because building on rejected code is unsafe.

At loop end (after break):
- Pick `final_iter_for_output = best_iter_data or iterations_history[-1]` (defensive).
- Set:
  - `final_code = final_iter_for_output.code`
  - `final_pylint_score = final_iter_for_output.pylint_score`
  - `final_bandit_high_medium = final_iter_for_output.bandit_high_medium_count`
  - `converged = final_iter_for_output.threshold_met` (not last iteration's)
  - In `LoopResult`, `before_after_summary` should be computed from best_iter_data's issues too — use the final_iter_for_output's raw_issues.
- Update run_logger.csv call: keep existing; optionally log summary (new CSV columns are optional, not adding to keep run_logger CSV backward compat unless strictly needed — requirement says "log acceptance decision and reason for every candidate" which we already satisfy in IterationData.accepted/reason persisted inside LoopResult). The per-candidate logging is visible in `iterations_history` + any IterationLogger that iterates it (like the standalone rule_level_analysis' IterationLogger). We'll also update `rejected_iterations` count passed to `log_run` to count **acceptance-rejected** iterations (not just threshold-failed ones): new helper `sum(1 for it in iterations_history if not it.accepted)`.

### Step 4 — IterationData.to_dict + before_after summary
- Add `accepted` and `acceptance_reason` keys to `IterationData.to_dict()`.
- Update `MetricsTracker.record()` / `get_before_after_summary()` to operate on the best-accepted iteration's data instead of the final-history iteration (currently tracker records every iteration; we'll keep recording all, but the final LoopResult.before_after_summary uses `best_iter_data`).

### Step 5 — Tests (test_loop_controller.py)
Add these tests (order matches constraints list):

1. **test_constrained_rejects_security_weight_increase** — Previous has 1 B105 (MEDIUM → 5). Candidate fixes W0611 (style) but adds B602 (HIGH → 10). Security weighted (5 vs 15) increases → `REJ_SECURITY_WORSE`. Checks `candidate.accepted=False`, `acceptance_reason==REJ_SECURITY_WORSE`, `best_iter_data.code == prev_code` (rejected code not output).

2. **test_constrained_rejects_pylint_score_drop** — Previous pylint=7.5, Candidate=6.8 (both failing convergence thresholds, but constrained rejects). Reason=REJ_PYLINT_DROP.

3. **test_constrained_rejects_avg_complexity_over_limit** — enable_radon=True, candidate avg_cc = 12 > default 10 → REJ_AVG_COMPLEXITY. Use code with many branches.

4. **test_constrained_rejects_max_complexity_over_limit** — enable_radon=True, candidate max_cc = 18 > default 15 → REJ_MAX_COMPLEXITY.

5. **test_constrained_rejects_mi_below_limit** — enable_radon=True, candidate MI = 50 < default 65 → REJ_MAINTAINABILITY.

6. **test_constrained_accepts_when_all_constraints_satisfied** — Reason==ACCEPTED_CONSTRAINED_OK, accepted=True, best_iter_data is the (accepted) candidate.

7. **test_weighted_accepts_candidate_that_constrained_rejects** — **Acceptance Criterion test.**
   - Previous code: has unused import (W0611, WARNING=3) + missing docstring (C0116, CONVENTION=1). Security weighted = 0. Weighted total = 4.
   - Candidate code: removes W0611 (fixes style), removes C0116, but introduces a `B602` subprocess shell=True (security HIGH=10). Security weighted was 0, now 10 → increase.
   - Run with `acceptance_rule=weighted` first → Final code IS the candidate (fixes style, weighted score might have dropped from 4 to 1+10=11 — wait, weighted total is overall score not security. Need to choose numbers carefully so weighted *overall* is acceptable by current logic, then constrained rejects on security grounds.)
   - Actually the test name says "fixes style but adds a security issue is accepted under weighted and rejected under constrained". Weighted mode has no acceptance rejections so every candidate is accepted (history[-1] == candidate output). Constrained rejects it so best_iter_data stays at previous, hence output != candidate code.
   - Exact assertions:
     - weighted run: `result.final_code == candidate_code` and `it.accepted == True`, `acceptance_reason == ACC_REASON_WEIGHTED`
     - constrained run: `final_iter_for_output.code == previous_code` (best stays at previous), `candidate_iter.accepted == False`, `candidate_iter.acceptance_reason == REJ_SECURITY_WORSE`
   - Achieve this via mock LLM that returns `prev_code` first iteration then `candidate_code` second iteration with cap=2.

## Dependencies and Considerations

- **Baseline comparison uses last-accepted, not last-generated.** Prevents a pathological "slide" where iteration 2 is rejected on security but then iteration 3's "increase" check compares against the rejected 2's 10 — which would spuriously accept 3 if it dropped back to 8 (still worse than original baseline 0). The correct baseline is the last accepted version.
- **Radon gating**: Constrained MI/CC checks only fire when enable_radon=True (since analyzer returns None otherwise). Tests for those must set `enable_radon=True`.
- **Stop-rule timing**: stop rules evaluate on the actual iteration history (including rejected entries). This preserves the existing behavior that plateau/cap/convergence checks see every generation attempt.
- **Converged flag on LoopResult**: derived from the best accepted iteration's `threshold_met`, not the last generated iteration — otherwise a rejected convergence-threshold-meeting candidate would incorrectly report converged.
- **API call count unchanged**: we still perform LLM calls identically — acceptance doesn't reduce API calls, only what code is output and what baseline is fed back to the LLM.
- **`IterationData` diff semantics**: diff is still computed vs immediately preceding entry in history (i.e., between iteration i-1 and i generated codes). Acceptance is orthogonal to diff.

## Validation

1. Run `pytest tests/test_loop_controller.py -v` — all original 7 tests + new acceptance tests pass.
2. Run `pytest tests/test_feedback.py -v` — ensure regression_aware mode remains passing (no break from acceptance logic).
3. Manually inspect the AC test once: run it standalone with `-s` to print acceptance_reason strings.
4. Run `GetDiagnostics` on modified files to catch lint/type issues.

## Risks

- **Stop rule / acceptance interaction could surprise users.** e.g., plateau fires and stops even though recent iterations were all rejected — handled by reporting `best_iter_data` as output regardless.
- **Pylint None/0 on syntax error:** the score drops to 0.0 for syntax errors. First iteration can legitimately have pylint_score=0.0 and it's accepted as baseline. Risk: iteration 2 syntax error → 0.0 compare vs prev 0.0 → not strict drop, so passes constraint (acceptable; syntax error already surfaces via raw_issues and other checks).
- **MetricsTracker.before_after_summary:** verify that `final_iter` for summary is the accepted-best (the code uses final_iter for summary check). After the rework, ensure `before_after_summary` pulls from best-accepted iteration data, not last history entry (update the for-loop-exit section).
- **`single_shot` strategy**: in single_shot, first iteration must be accepted as initial regardless of rule. Implementation handles this via `prev=None -> ACC_REASON_INITIAL`.
