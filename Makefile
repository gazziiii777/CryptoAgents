.DEFAULT_GOAL := help

.PHONY: help install lint format format.check typecheck test test.cov test.integration check clean \
        logs restart rebuild shell db.shell db.url migration nuke init-migration \
        deploy deploy.migrate deploy.logs deploy.status deploy.shell deploy.down

# Подгружаем локальные overrides (IP сервера, юзер) если есть — gitignored
-include .make.local

# Defaults (когда .make.local не задал). Все можно override на CLI:
#   make deploy SERVER_HOST=1.2.3.4
SERVER_USER ?= root
SERVER_HOST ?=
SERVER_DIR  ?= /opt/trading-agents
SSH         := ssh $(SERVER_USER)@$(SERVER_HOST)

# Fail-fast: deploy-команды требуют SERVER_HOST
_require-host:
	@if [ -z "$(SERVER_HOST)" ]; then \
		echo "ERROR: SERVER_HOST not set. Create .make.local with:"; \
		echo "  SERVER_HOST = your.ip.here"; \
		echo "Or pass on CLI: make deploy SERVER_HOST=x.x.x.x"; \
		exit 1; \
	fi

help:
	@grep -E '^[a-zA-Z._-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Docker dev: shortcuts. Основной запуск — docker compose up -d.
# ============================================================

init-migration: ## ОДИН раз перед первым `docker compose up`: создать initial-миграцию
	docker compose up -d db
	@echo "Waiting for db..."
	@for i in $$(seq 1 60); do \
		if docker compose exec -T db healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1; then \
			echo "db ready"; break; \
		fi; sleep 1; \
	done
	docker compose run --rm --entrypoint alembic app revision --autogenerate -m "initial schema"
	@echo ""
	@echo "Initial migration created. Commit migrations/versions/*.py."
	@echo "Next: docker compose up -d"

logs: ## Tail worker logs
	docker compose logs -f worker

restart: ## Перезапустить worker без rebuild
	docker compose restart worker

rebuild: ## Пересобрать образ + перезапустить worker (после изменения Python/Dockerfile)
	docker compose up -d --build worker

shell: ## Bash внутри worker-контейнера
	docker compose exec worker bash

db.shell: ## MariaDB CLI
	docker compose exec db mariadb -u tradingagents -ptradingagents tradingagents

db.url: ## Печатает credentials для Sequel Ace
	@echo "Host:     127.0.0.1"
	@echo "Port:     3306"
	@echo "User:     tradingagents"
	@echo "Password: <DB_PASSWORD из .env>"
	@echo "Database: tradingagents  (вторая connection: research)"

migration: ## Новая миграция: make migration MSG="add foo table"
	@if [ -z "$(MSG)" ]; then echo "Usage: make migration MSG=\"description\""; exit 1; fi
	docker compose run --rm --entrypoint alembic app revision --autogenerate -m "$(MSG)"
	@echo "Review migrations/versions/, then docker compose up -d to apply."

nuke: ## ПОЛНАЯ очистка: контейнеры + ./mariadata + миграции
	docker compose down
	rm -rf ./mariadata
	rm -f migrations/versions/*.py
	@echo "Wiped. Run 'make init-migration' to generate first migration."

# ============================================================
# Deploy на $(SERVER_USER)@$(SERVER_HOST):$(SERVER_DIR)
# Build идёт НА СЕРВЕРЕ из rsync'нутых исходников. Миграции НЕ применяются
# автоматически (на проде нет COMPOSE_PROFILES=init). Для миграций — deploy.migrate.
# ============================================================

deploy: _require-host ## Залить код + перебилдить worker на проде. БЕЗ миграций.
	rsync -avz --delete \
		--exclude='.git' \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='.env' \
		--exclude='mariadata/' \
		--exclude='data/' \
		--exclude='backups/' \
		--exclude='.pytest_cache' \
		--exclude='.ruff_cache' \
		--exclude='.mypy_cache' \
		--exclude='research/data/' \
		--exclude='ReferenceTradingAgents/' \
		./ $(SERVER_USER)@$(SERVER_HOST):$(SERVER_DIR)/
	$(SSH) 'cd $(SERVER_DIR) && docker compose up -d --build worker backup'
	@echo "Deployed. Logs: make deploy.logs"

deploy.migrate: _require-host ## Применить alembic upgrade head на проде (ОТДЕЛЬНО от deploy)
	$(SSH) 'cd $(SERVER_DIR) && docker compose run --rm --entrypoint alembic app upgrade head'

deploy.logs: _require-host ## Tail worker logs на проде
	$(SSH) 'cd $(SERVER_DIR) && docker compose logs -f worker'

deploy.status: _require-host ## docker compose ps на проде
	$(SSH) 'cd $(SERVER_DIR) && docker compose ps'

deploy.shell: _require-host ## SSH в директорию проекта на проде
	ssh -t $(SERVER_USER)@$(SERVER_HOST) 'cd $(SERVER_DIR) && exec bash'

deploy.down: _require-host ## Остановить контейнеры на проде (данные в ./mariadata остаются)
	$(SSH) 'cd $(SERVER_DIR) && docker compose down'

# ============================================================
# Python: lint / type / test (без docker)
# ============================================================

install: ## Sync project + dev/test/typecheck deps via uv
	uv sync --frozen

lint: ## Ruff lint check
	uv run ruff check .

format: ## Ruff format (writes changes)
	uv run ruff format .

format.check: ## Ruff format check (no writes)
	uv run ruff format --check .

typecheck: ## Static type check (mypy over app/core/db)
	uv run mypy

test: ## Unit tests, fast (no coverage gate)
	uv run pytest tests/unit

test.cov: ## Unit tests with coverage gate
	uv run pytest tests/unit --cov=app --cov=core --cov=db --cov-report=term-missing

test.integration: ## Integration tests (opt-in, requires services)
	uv run pytest tests/integration -m integration

check: lint format.check typecheck test.cov ## Full quality gate (used by CI)

clean: ## Remove caches and coverage artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
