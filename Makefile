.PHONY: setup test lint run_eval run_eval_full run_eval_live_dev run_eval_live_full run_eval_live_target30 analyze clean run_async run_async_live_dev run_async_live_target30 iterate iterate_live submission clean

PYTHON := python
PIP := pip

setup:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:
	$(PYTHON) -m ruff check src/ tests/

# --- Synchronous evaluation (original) ---

run_eval:
	$(PYTHON) -m src.runner --source hf --limit 10

run_eval_full:
	$(PYTHON) -m src.runner --source hf

run_eval_live_dev:
	$(PYTHON) -m src.runner --client live --dot-mode agentic --source hf --limit 10

run_eval_live_full:
	$(PYTHON) -m src.runner --client live --dot-mode agentic --source hf

run_eval_live_target30:
	$(PYTHON) -m src.runner --client live --dot-mode agentic --source hf --target30

# --- Async evaluation ---

run_async:
	$(PYTHON) -m src.async_runner --source hf --limit 10

run_async_live_dev:
	$(PYTHON) -m src.async_runner --client live --dot-mode agentic --source hf --split dev --limit 10

run_async_live_target30:
	$(PYTHON) -m src.async_runner --client live --dot-mode agentic --source hf --target30

# --- Iterate loop (analyze -> patch context -> rerun) ---

iterate:
	$(PYTHON) -m src.iterate_loop --source hf --split dev --limit 10

iterate_live:
	$(PYTHON) -m src.iterate_loop --client live --dot-mode agentic --source hf --split dev --limit 10

# --- Submission CSV ---

submission:
	$(PYTHON) -m src.make_submission_csv

# --- Analysis ---

analyze:
ifdef RESULTS
	$(PYTHON) -m src.analyze_failures $(RESULTS)
else
	$(PYTHON) -m src.analyze_failures
endif

# --- Cleanup ---

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.ruff_cache')] if p.exists()]"
