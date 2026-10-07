# Plateau Stop-Rule Best-So-Far + Replay Script Implementation Plan

## Repository Research

### 1. `stop_rule` flag EXISTS with four values (no new flag constants needed)
- Verified in [config.py](file:///e:/MiniProject/AICodeQuality/backend/app/config.py#L13-L17):
  `STOP_RULE_FIXED_CAP="fixed_cap"`, `STOP_RULE_PLATEAU="plateau"` (plus `threshold`, `cap`).
- `STOP_RULES` tuple normalizes both.
- `ExperimentConfig.stop_rule` field (default `"threshold"`) wired via `from_env()` → `EXPERIMENT_STOP_RULE`.

### 2. `PLATEAU_MIN_STRIKES=2` EXISTS ([config.py:50](file:///e:/MiniProject/AICodeQuality/backend/app/config.py#L50))

### 3. `stop_reason` + `api_calls_used` LOGGING EXISTS
- [run_logger.py](file:///e:/MiniProject/AICodeQuality/backend/app/run_logger.py#L26-L48) CSV_FIELDS has `stop_reason`, `api_calls`, `final_weighted_score`.
- [loop_controller.py:676-692](file:///e:/MiniProject/AICodeQuality/backend/app/loop_controller.py#L676-L692) passes both.
- `LoopResult` has `stop_reason: str` + `api_calls_used: int` fields.
- `STOP_REASON_PLATEAU="STOP_PLATEAU_WEIGHTED"`, `STOP_REASON_FIXED_CAP="STOP_FIXED_CAP"`, `STOP_REASON_CAP="STOP_CAP"`, `STOP_REASON_CONVERGED="CONVERGED_THRESHOLD"`, `STOP_REASON_SINGLE_SHOT="SINGLE_SHOT"` defined.

### 4. ⚠️ EXISTING plateau SEMANTICS ARE DIFFERENT from user's request (BUG)
Current `plateau_strikes_weighted()` at [loop_controller.py:71-85](file:///e:/MiniProject/AICodeQuality/backend/app/loop_controller.py#L71-L85):
```python
# Compares ADJACENT iterations — cur >= prev → non-improvement strike
for idx in range(len(history)-1, 0, -1):
    prev = history[idx-1].weighted_issue_score   # ← previous in list, NOT best-so-far
    cur  = history[idx].weighted_issue_score
    if cur >= prev: strikes += 1
    else: break
```
User request says: **"N consecutive iterations without improvement of the best-so-far score"**.
So if best ever was iteration 1 (weighted=20), then iterations 2=25, 3=22, 4=21 → all 3 "did not improve best-so-far (20)" → that's 3 strikes. The current implementation would record: 25<20? No → strike 1; 22≥25? No → reset → 0 strikes. They're different semantics.

### 5. Existing demo validates flag but the semantics need fixing
`scripts/demo_plateau_stop.py` passes because STUCK_CODE returns IDENTICAL weighted every iteration (adjacent ≥ AND best-so-far ≥ both trigger). So the demo doesn't reveal the semantic gap.

### 6. Logged iteration data for the replay script
- **`logs/iterations.csv`** exists — granular schema (one row per issue-rule-per-iteration, per prompt_id) via `scripts/rule_level_analysis.py:IterationLogger` standalone class: [rule_level_analysis.py:47-64](file:///e:/MiniProject/AICodeQuality/scripts/rule_level_analysis.py#L47-L64).
  Has `prompt_id, iteration, tool, severity, rule_id` rows.
- **`logs/runs.csv`** has per-run data: `prompt_id, stop_rule, iterations, api_calls, stop_reason, final_weighted_score, pylint_score`.
- Iterations.csv is only populated by **standalone** IterationLogger (not the main pipeline). Replay script should build `weighted_score_per_iteration` by re-scoring every issue-row using the same severity weights as the controller (SEVERITY_WEIGHTS dict pattern).

### 7. SEVERITY WEIGHTS reference
Per `project_memory.md` + loop_controller `security_weighted_score()`: HIGH/ERROR=10, MEDIUM=5, WARNING=3, REFACTOR=2, CONVENTION/LOW=1. The plateau metric is **total weighted_issue_score (all tools)** not just Bandit.

## Files and Modules

### Modified files
- `backend/app/loop_controller.py` — Replace plateau strike semantics from "adjacent iteration >= prev iteration" to "current iteration >= best_so_far BEFORE this iteration". Also expose a pure `compute_best_so_far_strikes()` helper (used by the replay script) for testability and reuse.
- `tests/test_loop_controller.py` — Update existing plateau test (`test_plateau_stops_earlier_than_cap_on_stuck_run`) to still pass (it will), then ADD ONE NEW TEST that distinguishes the two semantics: scenario where "adjacent scores oscillate but never beat old best → plateau must fire even though adjacent pairs sometimes improve".

### New files
- `scripts/replay_plateau_stop.py` — Standalone script that:
  1. Reads `logs/runs.csv`, filters rows where `stop_rule == "fixed_cap"`.
  2. For each such run, loads the per-iteration weighted_issue_score trace from `logs/iterations.csv` (recomputes by aggregating severity weights grouped by (prompt_id, iteration); if iterations.csv doesn't have the prompt, skips with a note and --seed fallback).
  3. Runs the SAME `compute_best_so_far_strikes(trace, N=PLATEAU_MIN_STRIKES)` logic against the FULL trace (simulating what plateau stop_rule WOULD have done at each iteration).
  4. For each prompt reports:
     - plateau_stop_iteration = first i where strikes ≥ N (or `iterations` if never triggered)
     - quality_at_stop = weighted_issue_score AT plateau_stop_iteration (compare vs final weighted)
     - api_calls_at_plateau = `plateau_stop_iteration` (1 API call per iteration)
     - api_calls_saved = actual_api_calls - api_calls_at_plateau
     - quality_retained = "SAME" if weighted_at_stop == final_weighted else f"stop={wstop} final={wfinal}"
  5. Prints one line per prompt like: `[prompt=abc123] stopped-at-iter=3 / quality-keep=SAME / api-saved=2`.
  6. Takes CLI args: `--csv runs.csv`, `--min-strikes N (default 2)`, `--seed` to synthesize demo data if none exists.
- Optional: `--jsonl logs/iterations.jsonl` fallback if CSV is missing.

### NOT modified
- `backend/app/config.py` — No new flag constants needed.
- `backend/app/run_logger.py` — stop_reason / api_calls / final_weighted_score columns already present.

## Dependency-ordered Implementation Steps

1. **Step 1 — Fix plateau strike semantics in `loop_controller.py`.**
   - Add new pure helper: `plateau_strikes_best_so_far(history: List[IterationData], required: int = PLATEAU_MIN_STRIKES) -> Tuple[int, int]` returning `(strikes, best_so_far_weighted)`. Semantics:
     ```
     best = inf
     strikes_latest = 0
     for i, item in enumerate(history):
         # "improvement vs best_so_far" means item.weighted < best (strict lower)
         if item.weighted_issue_score < best:
             best = item.weighted_issue_score
             strikes_latest = 0
         else:
             strikes_latest += 1
     ```
   - Rename old helper to `plateau_strikes_adjacent()` (keep as private fallback if needed), or just rewire `_is_plateau_weighted()` to use the new best-so-far helper.
   - Update `_evaluate_stopping` plateau branch to check the new strikes.
   - Update the print diagnostic block (line 618-631) to also print `best-so-far=X` next to the sequence.

2. **Step 2 — Add 1+ tests in `tests/test_loop_controller.py`.**
   - Existing `test_plateau_stops_earlier_than_cap_on_stuck_run` must still pass (identical weights every iter → adjacent AND best-so-far both count strikes).
   - New test `test_plateau_stops_when_best_so_far_not_improved_despite_adjacent_dips`:
     - Scenario 5-iter cap: weighted = [30, 28, 29, 28, 27]. Best=30→28 at it1→it2. Iter3 (29)≥28 → strike 1; iter4 (28≥28, not strict lower) → strike 2 → TRIGGER. Current adjacent logic would reset on iter4 because 28<29, so this test distinguishes the two.
     - Use mock LLM with 5 snippets crafted to give those exact weighted scores.
     - Assert: total_iterations == 4, stop_reason == STOP_REASON_PLATEAU.

3. **Step 3 — Write the replay script `scripts/replay_plateau_stop.py`:**
   - Reuse patterns from `scripts/rule_level_analysis.py`: `severity_weight = {HIGH:10, MEDIUM:5, ...}` lookup.
   - Top-level functions:
     - `load_fixed_cap_runs(runs_csv) -> List[dict]` returns rows with stop_rule=fixed_cap + parsed ints/floats.
     - `load_iteration_weighted_traces(iter_csv, prompt_ids) -> Dict[prompt_id, Dict[int, int]]` builds per-(prompt,iteration) total_weighted map by aggregating CSV issue rows.
     - `simulate_plateau_stop(trace_by_iter: Dict[int,int], min_strikes=2) -> (stop_iteration:int, best_weight:int)` pure function using the SAME best-so-far algorithm from Step 1. Returns final iter if plateau never triggers.
     - `print_report(runs, traces, min_strikes)` pretty-prints per-prompt: `prompt=… | actual_iter=… | plateau_would_stop=… | quality_at_stop=… | final_quality=… | quality=RETAINED/SAME/LOSS | api_used=… | api_at_stop=… | api_saved=…`.
     - `seed_synthetic_data(iter_csv, runs_csv)` (--seed flag) writes a tiny fixed-cap run with 5 iterations where weighted drops to [20, 15, 16, 15, 14] — so replay reports stop at iter=4 with 1 saved.
   - No new API calls. Pure offline analysis.

4. **Step 4 — Update `demo_plateau_stop.py`** (only the printed strings) to reflect "best-so-far" wording; no behavior change needed.

5. **Step 5 — Run tests + replay demo:**
   - `python -m pytest tests/test_loop_controller.py tests/test_run_logger.py tests/test_feedback.py -v` (no regressions)
   - Run the replay script twice: first without data (graceful "no fixed_cap runs in runs.csv"), then with `--seed` which should print `api-saved=1` for the seeded prompt.
   - Run `demo_plateau_stop.py` to confirm still passing.

6. **Step 6 — GetDiagnostics on 2 modified + 1 new file for lint/type issues.**

## Dependencies and Considerations

- **Acceptance asymmetry with stop**: `_evaluate_stopping` always wins with STOP_CONVERGED before plateau check (line 336-338). Replay script should SIMULATE this order too: "if at any iter the weighted_score=0 AND pylint_score≥pylint_threshold AND bandit_hm≤max — converged would have fired first; report CONVERGED at that iter instead of plateau". We'll add convergence simulation in the `simulate_plateau_stop` so results are accurate.
- **No pylint_score / bandit counts in iterations.csv**: iterations.csv only has issue rows → to "simulate convergence" we approximate by `weighted_score == 0 AND no Bandit issue rows` as convergence stand-in for replay; else we skip converged-detection and report just plateau quality relative to final weighted.
- **Data-availability graceful fallback**: if a run's prompt_id exists in runs.csv but iterations.csv has no rows, we print `SKIP: no iteration data` and continue. User instructed DONE when script prints calls saved + quality retained PER PROMPT, so --seed ensures we always have a demonstrable case.
- **Best-so-far strictness**: per earlier acceptance_rule weighted_issue_score semantics, "improvement" = STRICT lower (not ≤) so ties count as no-improvement → strike. We keep this consistent in both controller and replay.

## Validation

- At least one test PROVES best-so-far vs adjacent semantics (Step 2).
- All original tests pass (Step 5).
- `scripts/replay_plateau_stop.py --seed` prints lines containing `api-saved=` and `quality=RETAINED/SAME/LOSS`.
- 0 lint / type diagnostics (Step 6).

## Risks

1. **Regression risk on existing plateau tests** → The 5-iteration stuck scenario in demo_plateau_stop has identical weights always; both semantics produce strikes=2 at iter=3, so it will still pass. We additionally add the new differentiating test to confirm.
2. **Replay script flakiness when csvs have partial data** → Guard every aggregation with defaultdict(int); return "SKIP" per run instead of crashing.
3. **Number of iterations ≠ api_calls** — rare. In the main pipeline every iteration uses exactly one `_generate()` call (1 per iter). Replay approximates `api_calls_at_stop = plateau_stop_iteration`. We note this assumption in script output; default runs.csv has `api_calls=iterations` so it's fine.
4. **Weight recomputation mismatch** if severity names differ (e.g. "informational"). We treat unknown severity as weight=DEFAULT_SEVERITY_WEIGHT=1, matching `security_weighted_score()` pattern.
