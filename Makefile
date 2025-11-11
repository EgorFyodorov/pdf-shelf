.PHONY: build up down run logs ps restart migrate

COMPOSE ?= docker compose

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

run:
	$(COMPOSE) up bot

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f bot

ps:
	$(COMPOSE) ps

restart: down up

migrate:
	$(COMPOSE) run --rm bot python scripts/apply_migrations.py
