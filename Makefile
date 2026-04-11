PYTHON ?= python

.PHONY: install-dev lint format format-check test build package-check check clean

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

test:
	pytest

build:
	$(PYTHON) -m build

package-check:
	$(PYTHON) -m twine check dist/*

check: lint format-check test build package-check

clean:
	rm -rf build dist .pytest_cache htmlcov
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
