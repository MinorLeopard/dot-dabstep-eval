# Dot x DABStep Evaluation Harness

Reproducible evaluation harness for testing [Dot](https://dot.ai) on the
[DABStep](https://huggingface.co/datasets/ServiceNow/dabstep) benchmark
(Data Analysis Benchmark for Step-by-step reasoning).

## Setup

```bash
pip install -e ".[dev]"
# or
make setup
```

## Running Tests

```bash
make test
```

Tests use a deterministic `FakeDotClient` — no API keys required.

## Running Evaluation

**Sample run (10 tasks):**

```bash
make run_eval
```

**Full benchmark:**

```bash
make run_eval_full
```

**Custom options:**

```bash
python -m src.runner --source hf --limit 50 --run-id my_experiment
python -m src.runner --source jsonl --jsonl-path data/tasks.jsonl
```

Results are written to `results/<run_id>.jsonl`. Each line contains:

| Field | Description |
|---|---|
| `question_id` | Task identifier |
| `difficulty` | Task difficulty level |
| `prompt` | Full prompt sent to Dot |
| `dot_response_raw` | Raw response from Dot |
| `parsed_answer` | Extracted FINAL_ANSWER (or null) |
| `ground_truth` | Expected answer |
| `score` | 0 or 1 |
| `error_type` | `null`, `format_missing`, or `wrong_answer` |

## Analyzing Results

```bash
make analyze                          # analyzes most recent results file
make analyze RESULTS=results/my_run.jsonl  # specific file
```

Produces accuracy breakdowns by difficulty and failure clustering.

## Project Structure

```
src/
  dabstep_loader.py   # Load tasks from HuggingFace or local JSONL
  dot_client.py       # Dot API client (stub) + FakeDotClient for tests
  prompting.py        # Prompt construction + FINAL_ANSWER parsing
  scoring.py          # Answer scoring with normalization
  runner.py           # Evaluation orchestrator
  analyze_failures.py # Post-hoc failure analysis
tests/
  test_scoring.py     # Scoring unit tests
  test_prompting.py   # Prompt/parse unit tests
  test_runner.py      # Integration tests with fake client
results/              # Eval output (gitignored)
```

## Connecting a Real Dot Client

Edit `src/dot_client.py` — implement `LiveDotClient.query()` using the Dot API,
then update `src/runner.py:main()` to instantiate it instead of `FakeDotClient`.
