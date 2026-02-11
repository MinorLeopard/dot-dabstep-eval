.PHONY: setup test lint run_eval run_eval_full run_eval_live_dev run_eval_live_full analyze clean

PYTHON := python
PIP := pip

setup:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:
	$(PYTHON) -m ruff check src/ tests/

run_eval:
	$(PYTHON) -m src.runner --source hf --limit 10

run_eval_full:
	$(PYTHON) -m src.runner --source hf

run_eval_live_dev:
	$(PYTHON) -m src.runner --client live --dot-mode agentic --source hf --limit 10

run_eval_live_full:
	$(PYTHON) -m src.runner --client live --dot-mode agentic --source hf

analyze:
ifdef RESULTS
	$(PYTHON) -m src.analyze_failures $(RESULTS)
else
	$(PYTHON) -m src.analyze_failures
endif

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.ruff_cache')] if p.exists()]"
