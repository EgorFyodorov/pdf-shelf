.PHONY: build up down run logs ps restart migrate eval

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

# --- Local evaluation of PDFs in pdf_for_eval (no containers) ---
eval:
	python -m project.cli.eval_pdfs --input-dir pdf_for_eval --out-dir eval_results
