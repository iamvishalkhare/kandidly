# Kandidly infra targets (SPEC §3.5 rule 8). Wrap `podman compose` so
# contributors never type engine-specific commands. Override ENGINE=docker on
# CI runners that lack Podman (the compose file is engine-agnostic).
ENGINE ?= podman
COMPOSE ?= $(ENGINE) compose
FILE := -f compose.yml

.DEFAULT_GOAL := help
.PHONY: help up down logs ps test migrate seed shell-backend fmt

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Build + start the full stack (detached)
	$(COMPOSE) $(FILE) up --build -d

down: ## Stop and remove containers (keeps named volumes)
	$(COMPOSE) $(FILE) down

logs: ## Tail logs from all services
	$(COMPOSE) $(FILE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) $(FILE) ps

migrate: ## Apply DB migrations inside the backend container
	$(COMPOSE) $(FILE) exec backend uv run alembic upgrade head

seed: ## Load dev seed data (SPEC §18.4)
	$(COMPOSE) $(FILE) exec backend uv run python -m app.db.seed

test: ## Run backend test suite in a one-off container
	$(COMPOSE) $(FILE) run --rm backend uv run pytest -q

shell-backend: ## Open a shell in the backend container
	$(COMPOSE) $(FILE) exec backend bash

fmt: ## Format + lint the backend
	$(COMPOSE) $(FILE) run --rm backend sh -c "uv run ruff format . && uv run ruff check --fix ."
