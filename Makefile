PYTHON ?= python3

.PHONY: setup test lint demo

setup:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest --cov=pr_review --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check src tests

demo:
	PYTHONPATH=src $(PYTHON) -m pr_review.cli review-diff --file examples/sample.diff
