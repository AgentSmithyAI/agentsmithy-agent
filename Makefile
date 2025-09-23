PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYINSTALLER := $(VENV)/bin/pyinstaller
BIN := agentsmithy

.DEFAULT_GOAL := pyinstall

.PHONY: venv install install-dev update-reqs lint format typecheck test run clean pyinstall build

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
	@bash -c '\
	ec=0; \
	$(PY) -m ruff check . || ec=1; \
	$(PY) -m black --check . || ec=1; \
	$(PY) -m isort --check-only . || ec=1; \
	$(PY) -m mypy . || ec=1; \
	exit $$ec'

format:
	$(PY) -m ruff check . --fix --exit-zero
	$(PY) -m black .
	$(PY) -m isort .

test:
	$(VENV)/bin/pytest -q

run:
	$(PY) main.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache __pycache__ **/__pycache__ dist build *.spec

pyinstall: install-dev
	$(PYINSTALLER) --onefile --name $(BIN) main.py

build: pyinstall


