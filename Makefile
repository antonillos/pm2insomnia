PYTHON ?= python
PYTHON311 ?= python3.11
PYTHON312 ?= python3.12
PYTHON313 ?= python3.13

.PHONY: install-dev lint format format-check test build package-check check check311 check312 check313 clean

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

check311:
	$(MAKE) check PYTHON=$(PYTHON311)

check312:
	$(MAKE) check PYTHON=$(PYTHON312)

check313:
	$(MAKE) check PYTHON=$(PYTHON313)

clean:
	rm -rf build dist .pytest_cache htmlcov
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
