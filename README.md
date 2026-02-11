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

## Running Evaluation (Fake Client)

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

## Running with Live Dot API

### Setup Environment

**PowerShell:**

```powershell
$env:DOT_API_KEY = "your-api-key-here"
$env:DOT_BASE_URL = "https://test.getdot.ai"
```

**Or create a `.env` file** (gitignored):

```
DOT_API_KEY=your-api-key-here
DOT_BASE_URL=https://test.getdot.ai
```

### 1. Smoke Test (dev split, 10 tasks)

```powershell
make run_eval_live_dev
# or directly:
python -m src.runner --client live --dot-mode agentic --source hf --limit 10
```

### 2. Baseline Run (full dev split)

```powershell
make run_eval_live_full
# or directly:
python -m src.runner --client live --dot-mode agentic --source hf
```

### 3. Analyze Results

```powershell
make analyze
# or for a specific run:
make analyze RESULTS=results\my_run.jsonl
```

### CLI Reference

| Flag | Values | Default | Description |
|---|---|---|---|
| `--client` | `live`, `fake` | `fake` | Client implementation |
| `--dot-mode` | `ask`, `agentic` | `agentic` | Dot API endpoint mode |
| `--source` | `hf`, `jsonl` | `hf` | Task source |
| `--limit` | integer | all | Max tasks to evaluate |
| `--run-id` | string | auto | Custom run identifier |

## Results Format

Results are written to `results/<run_id>.jsonl`. Each line contains:

| Field | Description |
|---|---|
| `question_id` | Task identifier |
| `difficulty` | Task difficulty level |
| `guidelines` | Task guidelines text |
| `prompt` | Full prompt sent to Dot |
| `dot_response_raw` | Raw response from Dot |
| `parsed_answer` | Extracted FINAL_ANSWER (or null) |
| `ground_truth` | Expected answer |
| `score` | 0 or 1 |
| `error_type` | `null`, `format_missing`, `wrong_answer`, `dot_http_error`, `dot_timeout`, `dot_empty_response`, or `client_error` |
| `dot_mode` | API mode used (`ask` or `agentic`) |
| `latency_ms` | Response latency in milliseconds (live client only) |
| `retries` | Number of poll retries (live client only) |

## Project Structure

```
src/
  dabstep_loader.py   # Load tasks from HuggingFace or local JSONL
  dot_client.py       # DotClient ABC, FakeDotClient, LiveDotClient
  prompting.py        # Prompt construction + FINAL_ANSWER parsing
  scoring.py          # Answer scoring with normalization
  runner.py           # Evaluation orchestrator with CLI
  analyze_failures.py # Post-hoc failure analysis
tests/
  test_scoring.py     # Scoring unit tests
  test_prompting.py   # Prompt/parse unit tests
  test_runner.py      # Integration tests with fake client
  test_dot_client.py  # LiveDotClient unit tests (mocked HTTP)
  test_dabstep_loader.py # Loader unit + integration tests
notes/
  next_steps.md       # Iteration workflow and experiment ideas
results/              # Eval output (gitignored)
```
