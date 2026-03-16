.PHONY: help install test test-unit test-integration lint format clean

help:
	@echo "Multi-Tunnel VPN Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install libvpnmanager in editable mode with test deps"
	@echo ""
	@echo "Testing:"
	@echo "  make test            Run all unit tests (default)"
	@echo "  make test-unit       Run unit tests only"
	@echo "  make test-integration Run integration tests (requires daemon + sudo)"
	@echo "  make test-coverage   Run tests with coverage report"
	@echo "  make test-watch      Watch mode (rerun on changes)"
	@echo ""
	@echo "Quality:"
	@echo "  make lint            Run linters (black, ruff, mypy)"
	@echo "  make format          Auto-format with black"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           Remove build artifacts, cache, coverage"

install:
	cd src/libvpnmanager && pip install -e ".[test]"
	@echo "✓ libvpnmanager installed. Run tests with: make test"

test: test-unit

test-unit:
	python run_tests.py --unit -v

test-integration:
	@echo "Note: Integration tests require daemon running and may need sudo"
	python run_tests.py --integration -v

test-system:
	@echo "Note: System tests require full system setup and root privileges"
	python run_tests.py --system -v

test-coverage:
	python run_tests.py --unit --coverage
	@echo "Coverage report generated in htmlcov/index.html"

test-watch:
	python run_tests.py --unit --watch

lint:
	cd src/libvpnmanager && black --check .
	cd src/libvpnmanager && ruff check .
	cd src/libvpnmanager && mypy src --ignore-missing-imports || true

format:
	cd src/libvpnmanager && black .
	@echo "Code formatted with black"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".coverage" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	@echo "Cleaned build artifacts and cache"
