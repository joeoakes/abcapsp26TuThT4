PYTHON ?= python3
BACKEND_MODULE := src.backend.maze_server
DASHBOARD_URL := https://127.0.0.1:8447/dashboard

.PHONY: run backend dev test lint clean

run: ## Start backend with dashboard route
	MTLS_REQUIRE_CLIENT=0 $(PYTHON) -m $(BACKEND_MODULE)

backend: run ## Alias for run

dev: ## Start backend in HTTP mode for quick local dev
	uvicorn src.backend.maze_server:app --host 0.0.0.0 --port 8447

test: ## Run Python test suite
	pytest tests -q

lint: ## Placeholder lint hook
	@echo "No linter configured yet."

clean: ## Remove Python cache artifacts
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
