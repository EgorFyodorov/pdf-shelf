.PHONY: build up down run logs logs-bot logs-db logs-all ps restart

COMPOSE ?= docker compose

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

run:
	$(COMPOSE) up pdf-shelf-bot

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f pdf-shelf-bot

logs-bot:
	docker logs pdf_shelf_bot -f

logs-db:
	docker logs pdf_shelf_postgres -f

logs-all:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

restart: down up
