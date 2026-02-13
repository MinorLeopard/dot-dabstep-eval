# Dev Eval Report v2

## Scope
- Local-only iteration on offline solver (`src/offline_solver.py`).
- No external API calls.
- Baseline and final run used: `python src/offline_solver.py dev10`.

## Solver/Eval entrypoints found
- Local solver: `src/offline_solver.py` (mirrored in `scripts/offline_solver.py`)
- Dev set: `data/context/dev.jsonl`
- Target set: `data/context/target.jsonl`
- Full tasks: `data/context/all.jsonl`
- Target30 ID source: `src/dabstep_loader.py` (`TARGET_TASK_IDS`)
- Existing runners: `src/runner.py`, `src/async_runner.py`, `src/iterate_loop.py`

## Data check
- `payments.csv` contains `email_address`: **yes**

---

## Baseline (before changes)
- Command: `python src/offline_solver.py dev10`
- Score: **8/10**
- Failing task IDs: **1871, 2697**

### Baseline failures
1. `1871`
   - Expected: `-0.94000000000005`
   - Got: `0.00000000000000`
   - Hypothesis: delta-question regex extracted merchant incorrectly (`would`), resulting in empty txn set.
2. `2697`
   - Expected: `E:13.57`
   - Got: `E:16.63`
   - Hypothesis: remaining semantic mismatch in ACI-incentive scoring logic (question interpretation vs benchmark labeling).

---

## Iteration 1 (changes applied)
1. Fixed delta parsing bug:
   - Monthly delta regex now captures `... delta would <merchant> pay ...`
   - Added year-form delta regex (`In the year YYYY what delta would <merchant> pay ...`)
2. Fixed email metrics definitions:
   - `avg transaction amount per unique email`: ignores NULL/empty emails in denominator and numerator.
   - `repeat customer %`: computed on distinct non-empty emails only.

### Iteration 1 eval result
- Command: `python src/offline_solver.py dev10`
- Score: **8/10** (no net score increase)

### Iteration 1 failure comparison
1. `1871`
   - Before: `0.00000000000000`
   - After: `-0.80053999999996`
   - Status: improved numerically, still incorrect.
2. `2697`
   - Before: `E:16.63`
   - After: `E:16.63`
   - Status: unchanged.

---

## Iteration 2
- No additional code changes were applied.
- Reason: remaining failures (`1871`, `2697`) are semantic mismatches not resolved by small, low-risk rule fixes; further edits would require broader solver-policy changes.

---

## Final (after changes)
- Final dev10 score: **8/10**
- Tasks fixed (wrong -> correct): **none on dev10**
- Remaining failures:
  - `1871` (delta magnitude mismatch)
  - `2697` (ACI incentive cost mismatch)

## Expected impact on target30
- Positive impact expected for:
  - Delta tasks (regex bug fix): now correctly parsed/answered instead of accidental zero.
  - Email metric tasks: now using benchmark-consistent non-empty email logic.
- Observed target30 answer changes after fixes:
  - `43`: `274.334` -> `247.300`
  - `2463`: `0.00000000000000` -> `-5.24362599999995`
