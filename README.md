# pdf-shelf-bot

## 🚀 Быстрый старт

- **`server`** (`project/mcp_pdf/server.py`) — MCP-сервер
- **`api`** (`project/api/pdf_analysis.py`) — Python API для использования внутри бота
- **`cli`** (`project/cli/eval_pdfs.py`) — CLI-утилита для тестирования анализа PDF из папки

### Как запустить

**1. MCP-сервер (для тестирования через MCP-клиент):**
```bash
export GIGACHAT_AUTH_KEY="ваш_authorization_key"  # Base64 encoded authorization key
export GIGACHAT_MODEL="GigaChat-2"  # опционально, по умолчанию GigaChat-2
python -m project.mcp_pdf.server
```

**2. Python API (для использования в боте):**
```python
from project.api.pdf_analysis import analyze_pdf_path, analyze_pdf_url

result = await analyze_pdf_path("/path/to/file.pdf")
# result содержит JSON по схеме из project/mcp_pdf/schema.py
```

**3. CLI-тестирование (прогон PDF из папки):**
```bash
export GIGACHAT_AUTH_KEY="ваш_authorization_key"  # Base64 encoded authorization key
export GIGACHAT_MODEL="GigaChat-2"  # опционально, по умолчанию GigaChat-2
make eval
# или напрямую:
python -m project.cli.eval_pdfs --input-dir pdf_for_eval --out-dir eval_results
```

---

## Настройка окружения

### Настройка GigaChat API

1. Получите Authorization key в [личном кабинете GigaChat](https://developers.sber.ru/portal/products/gigachat)
2. Установите переменную окружения:
   ```bash
   export GIGACHAT_AUTH_KEY="ваш_authorization_key"  # Base64 encoded ключ
   ```
3. Опционально укажите модель (по умолчанию `GigaChat-2`):
   ```bash
   export GIGACHAT_MODEL="GigaChat-2"  # или другая доступная модель
   ```

### Общие настройки

1. Скопируйте `.env.example` в `.env` и укажите значения (`BOT_TOKEN`, параметры Postgres и путь к логам).
2. При необходимости скорректируйте `config.yaml` — он описывает приложение в формате YAML и парсится в датаклассы (см. `project/config.py`). Все параметры можно перекрыть переменными окружения из `.env`.

## Запуск в контейнерах
```
make build   # сборка образов
make up      # запускает bot + postgres в фоне
make logs    # поток логов бота из /var/log/bot/bot.log
make down    # остановить и удалить стэк
```
`make run` оставляет контейнеры в первом плане (`docker compose up bot`).

## Миграции
Схема описана в raw SQL `migrations/init.sql`. Скрипт запуска применяет этот файл при каждом старте контейнера.
- `make migrate` — вручную выполнить SQL из `migrations/init.sql` внутри контейнера.
- При необходимости обновляйте `migrations/init.sql` (например, добавляя `ALTER TABLE ...`) — entrypoint выполнит изменения на следующем запуске.
