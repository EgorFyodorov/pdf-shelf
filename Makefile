.PHONY: build up down run logs ps restart migrate shell-bot shell-db psql dev-restart eval

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

ps:
	$(COMPOSE) ps

restart: down up

shell-bot:
	docker exec -it pdf_shelf_bot /bin/bash

shell-db:
	docker exec -it pdf_shelf_postgres /bin/bash

psql:
	docker exec -it pdf_shelf_postgres psql -U bot_user -d bot_db

dev-restart:
	$(COMPOSE) restart pdf-shelf-bot

eval:
	python -m project.cli.eval_pdfs --input-dir pdf_for_eval --out-dir eval_results