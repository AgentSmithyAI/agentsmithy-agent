PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYINSTALLER := $(VENV)/bin/pyinstaller
BIN := agentsmithy
UPX := $(shell command -v upx 2>/dev/null)
UPX_DIR := $(shell dirname $(UPX) 2>/dev/null)

# Extra flags for PyInstaller; add --upx-dir when UPX is available
PYI_FLAGS :=
ifneq ($(UPX),)
	PYI_FLAGS += --upx-dir=$(UPX_DIR)
endif

.DEFAULT_GOAL := build

.PHONY: venv install install-dev update-reqs lint format typecheck test run clean pyinstall build smoke-test

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

typecheck:
	$(PY) -m mypy agentsmithy_server

test:
	$(VENV)/bin/pytest -q

run:
	$(PY) main.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache __pycache__ **/__pycache__ dist build

pyinstall: install-dev
	@echo "Building with PyInstaller using spec file..."
	@if [ -n "$(UPX)" ]; then \
		echo "UPX found at $(UPX), compression enabled via spec"; \
	else \
		echo "UPX not found, building without compression (install upx for smaller binaries)"; \
	fi
	$(PYINSTALLER) $(PYI_FLAGS) agentsmithy.spec
	@echo "Build complete:"
	@ls -lh dist/$(BIN)

build:
	$(MAKE) format
	$(MAKE) lint || exit 1
	$(MAKE) test || exit 1
	$(MAKE) pyinstall || exit 1

