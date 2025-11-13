.PHONY: build up down run logs ps restart migrate shell-bot shell-db psql dev-restart eval test-parser test-category test test-llm

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

migrate:
	docker cp migrations/init.sql pdf_shelf_postgres:/tmp/init.sql
	docker exec -it pdf_shelf_postgres psql -U bot_user -d bot_db -f /tmp/init.sql

eval:
	docker exec -it pdf_shelf_bot python -m project.tests.eval_pdfs --input-dir project/tests/pdf_for_eval --out-dir project/tests/eval_results

test-parser:
	docker exec -it pdf_shelf_bot python -m project.tests.test_parser_examples

test-category:
	@if [ -z "$(PDF)" ]; then \
		echo "Использование: make test-category PDF=<путь_к_pdf>"; \
		echo "Пример: make test-category PDF=project/tests/pdf_for_eval/llm-as-judge.pdf"; \
		exit 1; \
	fi
	docker exec -it pdf_shelf_bot python -m project.tests.test_category $(PDF)

test:
	docker exec -it pdf_shelf_bot pytest project/tests/ -v -s

test-llm:
	docker exec -it pdf_shelf_bot pytest project/tests/test_llm_providers.py -v -s
