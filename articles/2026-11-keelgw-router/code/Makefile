# One entry point for everything. Nothing here calls a paid API except
# test-live, which says so.
.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help setup model lint fmt test test-model train build up down logs e2e test-live test-all clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-11s %s\n", $$1, $$2}'

setup: ## install the Python dependencies (uv.lock)
	uv sync --frozen

model: ## download the pinned embedding model into .cache/model (~470 MB, sha256-checked)
	uv run --frozen python -m keelgw_router.fetch_model

lint: ## check formatting and lint
	uv run --frozen ruff format --check .
	uv run --frozen ruff check .

fmt: ## format the sources
	uv run --frozen ruff format .
	uv run --frozen ruff check --fix .

test: ## unit tests: no model, no network, seconds
	uv run --frozen pytest

test-model: model ## the real model in process: pins, a prompt per Tier, eval accuracy and retraining
	uv run --frozen pytest -m model

train: model ## retrain model/head.json and model/metrics.json from dataset/prompts.jsonl (no API calls)
	uv run --frozen python -m keelgw_router.train

build: ## build the router image and the e2e runner
	$(COMPOSE) --profile e2e build

up: ## start router (:18080) and router-tight (:18081), wait until healthy
	$(COMPOSE) up -d --build --wait router router-tight

down: ## stop and remove the services
	$(COMPOSE) --profile e2e down --remove-orphans

logs: ## follow the services' logs
	$(COMPOSE) logs -f router router-tight

e2e: ## build, start, run tests/e2e from a container, tear down
	$(COMPOSE) --profile e2e build
	$(COMPOSE) up -d --wait router router-tight
	$(COMPOSE) --profile e2e run --rm e2e; status=$$?; $(COMPOSE) --profile e2e down --remove-orphans; exit $$status

# The only target that sets KEELGW_ROUTER_LIVE=1. It makes ONE real Anthropic
# API call (a fraction of a cent) and needs ANTHROPIC_API_KEY or
# ANTHROPIC_API_KEY_FILE, from the environment or .env.
test-live: ## ONE real Anthropic API call: Claude labels a prompt, the router must agree
	$(COMPOSE) up -d --build --wait router
	set -a; [ -f .env ] && . ./.env; set +a; \
	KEELGW_ROUTER_LIVE=1 uv run --frozen pytest -m live -s; status=$$?; \
	$(COMPOSE) down --remove-orphans; exit $$status

test-all: lint test test-model e2e ## everything except test-live

clean: ## remove caches, the venv and the compose images
	$(COMPOSE) --profile e2e down --remove-orphans --rmi local || true
	rm -rf .venv .pytest_cache .ruff_cache .cache/embeddings
