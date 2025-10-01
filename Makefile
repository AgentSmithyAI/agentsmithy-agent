PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYINSTALLER := $(VENV)/bin/pyinstaller
BIN := agentsmithy
UPX := $(shell command -v upx 2>/dev/null)

.DEFAULT_GOAL := pyinstall

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

test:
	$(VENV)/bin/pytest -q

run:
	$(PY) main.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache __pycache__ **/__pycache__ dist build *.spec

pyinstall: install-dev
	@echo "Building with PyInstaller..."
	@if [ -n "$(UPX)" ]; then \
		echo "UPX found at $(UPX), compression will be enabled"; \
		$(PYINSTALLER) --onefile --name $(BIN) \
			--upx-dir=$$(dirname $(UPX)) \
			--collect-submodules agentsmithy_server.tools \
			--collect-submodules agentsmithy_server.tools.builtin \
			--collect-submodules chromadb \
			--collect-submodules chromadb.telemetry.product \
			--collect-data chromadb \
			--collect-submodules tiktoken \
			--collect-submodules tiktoken_ext \
			--collect-submodules ddgs \
			--collect-submodules ddgs.engines \
			--collect-submodules primp \
			--collect-data ddgs \
			--collect-data primp \
			--exclude-module pytest \
			--exclude-module pytest_asyncio \
			--exclude-module black \
			--exclude-module isort \
			--exclude-module mypy \
			--exclude-module ruff \
			main.py; \
	else \
		echo "UPX not found, building without compression (install upx for smaller binaries)"; \
		$(PYINSTALLER) --onefile --name $(BIN) \
			--collect-submodules agentsmithy_server.tools \
			--collect-submodules agentsmithy_server.tools.builtin \
			--collect-submodules chromadb \
			--collect-submodules chromadb.telemetry.product \
			--collect-data chromadb \
			--collect-submodules tiktoken \
			--collect-submodules tiktoken_ext \
			--collect-submodules ddgs \
			--collect-submodules ddgs.engines \
			--collect-submodules primp \
			--collect-data ddgs \
			--collect-data primp \
			--exclude-module pytest \
			--exclude-module pytest_asyncio \
			--exclude-module black \
			--exclude-module isort \
			--exclude-module mypy \
			--exclude-module ruff \
			main.py; \
	fi
	@echo "Build complete:"
	@ls -lh dist/$(BIN)

build: pyinstall

smoke-test:
	@echo "Running smoke test on binary..."
	@if [ ! -f dist/$(BIN) ]; then \
		echo "❌ Binary not found at dist/$(BIN). Run 'make build' first."; \
		exit 1; \
	fi
	@chmod +x dist/$(BIN)
	@echo "Testing binary: dist/$(BIN)"
	@# Test --help (should work without .env)
	@./dist/$(BIN) --help > /dev/null 2>&1; \
	if [ $$? -ne 0 ]; then \
		echo "❌ Binary --help failed"; \
		exit 1; \
	fi; \
	echo "✓ Binary --help works"
	@# Test running without args (should show usage and exit with code 2)
	@set +e; \
	./dist/$(BIN) > /dev/null 2>&1; \
	exit_code=$$?; \
	set -e; \
	if [ $$exit_code -eq 2 ]; then \
		echo "✓ Binary exits correctly when missing required args"; \
	elif [ $$exit_code -eq 139 ] || [ $$exit_code -eq 137 ]; then \
		echo "❌ Binary crashed (segfault or similar)"; \
		exit 1; \
	else \
		echo "⚠ Binary exited with unexpected code $$exit_code (expected 2), but didn't crash"; \
	fi


