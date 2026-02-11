# Iteration Workflow

## Experiment Loop

1. **Baseline run** — establish accuracy on dev split with default agentic mode
   ```
   make run_eval_live_full
   ```

2. **Analyze** — review accuracy by difficulty, error breakdown, sample failures
   ```
   make analyze
   ```

3. **Hypothesize** — based on failure patterns, decide what to change:
   - Prompt wording (edit `src/prompting.py`)
   - API mode (agentic vs ask)
   - Answer parsing logic (`src/prompting.py:parse_final_answer`)
   - Scoring tolerance (`src/scoring.py`)

4. **Change config** — make the change, assign a descriptive run_id
   ```
   python -m src.runner --client live --dot-mode ask --run-id "ask_mode_v1"
   ```

5. **Compare** — load both results files and diff accuracy
   ```
   python -m src.analyze_failures results\baseline.jsonl
   python -m src.analyze_failures results\ask_mode_v1.jsonl
   ```

6. **Repeat** until accuracy targets are met.

## Potential Experiments

- **Agentic vs Ask mode** — does the agentic endpoint produce more structured answers?
- **Prompt engineering** — add few-shot examples, chain-of-thought instructions
- **Guidelines emphasis** — put guidelines before or after the question
- **Answer parsing** — handle more edge cases in `parse_final_answer`
- **Retry logic** — retry on `dot_timeout` or `dot_empty_response` errors
- **Difficulty filtering** — focus experiments on hard tasks only

## Comparing Runs

Results are stored as JSONL in `results/`. To compare two runs side-by-side,
load both into pandas DataFrames and merge on `question_id`:

```python
import json
import pandas as pd
from pathlib import Path

def load(p):
    return pd.DataFrame([json.loads(l) for l in Path(p).read_text().splitlines() if l])

a = load("results/run_a.jsonl")
b = load("results/run_b.jsonl")
merged = a.merge(b, on="question_id", suffixes=("_a", "_b"))
improved = merged[(merged.score_a == 0) & (merged.score_b == 1)]
regressed = merged[(merged.score_a == 1) & (merged.score_b == 0)]
print(f"Improved: {len(improved)}, Regressed: {len(regressed)}")
```
