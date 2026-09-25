SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= python3
UV ?= uv
COMPOSE ?= docker compose

.PHONY: help install dev down up test test-unit test-integration lint format migrate revision demo health dashboard clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Create the local virtualenv and install dependencies (dev)
	$(UV) sync --extra dev

dev: ## Run the full local stack (api, postgres, redis, prometheus, grafana)
	$(COMPOSE) up --build

up: ## Start the stack in the background
	$(COMPOSE) up -d --build

down: ## Stop and remove the stack
	$(COMPOSE) down

test: ## Run the full test suite
	$(PYTHON) -m pytest

test-unit: ## Run unit tests
	$(PYTHON) -m pytest tests/unit

test-integration: ## Run integration tests
	$(PYTHON) -m pytest tests/integration

lint: ## Lint the codebase
	$(PYTHON) -m ruff check packages apps tests
	$(PYTHON) -m ruff format --check packages apps tests

format: ## Auto-format and fix lint issues
	$(PYTHON) -m ruff check --fix packages apps tests
	$(PYTHON) -m ruff format packages apps tests

migrate: ## Apply database migrations
	$(PYTHON) -m alembic upgrade head

revision: ## Create a new migration (use: make revision m="message")
	$(PYTHON) -m alembic revision --autogenerate -m "$(m)"

health: ## Run the DecisionOS health command
	$(PYTHON) -m decisionos.cli health

dashboard: ## Run the dashboard dev server
	cd apps/dashboard && npm run dev

demo: ## Run the AgentGuard flagship demo
	$(PYTHON) -m decisionos.cli demo agent_guard

demo-rollback: ## Run the deployment rollback simulator
	$(PYTHON) -m decisionos.cli demo deployment_rollback

evaluate: ## Evaluate the AgentGuard merge context (flagship example)
	$(PYTHON) -m decisionos.cli evaluate \
		--schema ToolAuthorization \
		--context examples/agent_guard/merge.json \
		--policy examples/agent_guard/policy.yaml

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache .hypothesis
