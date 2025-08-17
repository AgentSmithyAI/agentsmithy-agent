PYTHON ?= python3
VENV ?= venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: venv install install-dev update-reqs lint format typecheck test run clean

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-dev: install
	$(PIP) install -r requirements-dev.txt

update-reqs:
	$(PIP) install -r requirements.txt -r requirements-dev.txt --upgrade

lint:
	$(VENV)/bin/ruff check . --fix
	$(VENV)/bin/black .
	$(VENV)/bin/mypy agentsmithy_server || true

format:
	$(MAKE) lint

typecheck:
	$(VENV)/bin/mypy agentsmithy_server

test:
	$(VENV)/bin/pytest -q

run:
	$(PY) main.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache __pycache__ **/__pycache__


