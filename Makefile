.PHONY: setup test lint run_eval run_eval_full analyze clean

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

analyze:
ifdef RESULTS
	$(PYTHON) -m src.analyze_failures $(RESULTS)
else
	$(PYTHON) -m src.analyze_failures
endif

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache *.egg-info
