# PDF Shelf Bot

Telegram бот для управления персональной библиотекой PDF материалов с автоматическим анализом содержимого через LLM.

[Презентация проекта](https://docs.google.com/presentation/d/1jfDQFeJKATL7zgq9ytUFwtt9JEbMpN3_/edit?usp=sharing&ouid=111177648626939678344&rtpof=true&sd=true)

## Функционал

Бот позволяет добавлять PDF файлы напрямую или конвертировать веб-страницы в PDF по URL. Каждый документ автоматически анализируется для извлечения метаданных: время чтения, сложность текста, тематические теги. На основе этих данных реализован подбор материалов по заданному времени и темам.

Поддерживается пакетная обработка нескольких URL, просмотр библиотеки с пагинацией, удаление файлов, статистика использования. При загрузке URL проверяется наличие дубликатов.

Для анализа PDF используется LLM роутер с поддержкой нескольких провайдеров (GigaChat, Gemini, Perplexity) и автоматическим fallback при ошибках.

---

## Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- Токен Telegram бота (от @BotFather)
- API ключ хотя бы одного LLM провайдера

### 1. Настройка окружения

Создайте файл `.env` в корне проекта:

```bash
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token

# Database
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=bot_password
POSTGRES_DB=bot_db

# Logs
LOG_DIR=/var/log/bot

# LLM Providers (установите хотя бы один)
GIGACHAT_AUTH_KEY=your_gigachat_auth_key  # Base64 encoded client_id:client_secret
# GEMINI_API_KEY=your_gemini_api_key      # опционально
# PERPLEXITYAI_API_KEY=your_perplexity_key # опционально
```

### 2. Запуск

```bash
# Сборка образов
make build

# Запуск в фоновом режиме
make up

# Просмотр логов
make logs
```

### 3. Управление

```bash
# Перезапуск бота (быстрый, без пересборки)
make dev-restart

# Остановка
make down

# Проверка статуса
make ps

# Подключение к БД
make psql
```

---

### Ключевые компоненты

**FSM (Finite State Machine)**:
- `ExportStates.waiting_for_time` - ожидание ввода времени
- `ExportStates.viewing_export` - просмотр выгрузки материалов
- `ExportStates.viewing_library` - просмотр библиотеки

**Алгоритм подбора материалов**:
- Жадный алгоритм: выбирает материалы, максимально заполняющие указанное время
- Поддержка фильтрации по тегам
- Fallback: если точного совпадения нет, показывает последние запрошенные материалы

**Парсер URL**:
- Playwright для рендеринга страниц
- Извлечение заголовка страницы
- Конвертация в PDF с настраиваемыми параметрами

---

## Тестирование

### Запуск всех тестов
```bash
make test
```

### Тестирование LLM провайдеров
```bash
# Убедитесь, что API ключи установлены в .env
make test-llm
```

### Пакетный анализ PDF
```bash
# Анализирует все PDF из project/tests/pdf_for_eval/
# Результаты сохраняются в project/tests/eval_results/
make eval
```

### Тестирование парсера URL
```bash
make test-parser
```

### Тестирование категоризации конкретного PDF
```bash
make test-category PDF=project/tests/pdf_for_eval/example.pdf
```

### Ручной запуск в контейнере
```bash
# Подключиться к контейнеру
make shell-bot

# Запустить любой скрипт
python -m project.tests.eval_pdfs --help
```

---

## Конфигурация

### config.yaml
Основная конфигурация приложения:
```yaml
parser:
  timeout: 120000           # Таймаут парсера (мс)
  wait_until: networkidle   # Условие готовности страницы
  pdf_format: A4            # Формат PDF
```

### Переменные окружения (.env)
Все значения из `config.yaml` можно переопределить через переменные окружения.

### LLM провайдеры
Система автоматически выбирает доступные провайдеры в порядке приоритета:
1. **GigaChat** (приоритет 1) - если `GIGACHAT_AUTH_KEY` установлен
2. **Gemini** (приоритет 2) - если `GEMINI_API_KEY` установлен
3. **Perplexity** (приоритет 3) - если `PERPLEXITYAI_API_KEY` установлен

При ошибке одного провайдера автоматически переключается на следующий.

---

## Миграции БД

### Применение миграций
```bash
# Автоматически применяется при запуске контейнера
# Ручной запуск:
make migrate
```

### Добавление новой миграции
1. Создайте SQL файл в `migrations/`
2. Обновите `init.sql` или создайте отдельную миграцию
3. Примените через `make migrate`

---

## Мониторинг

### Логи
```bash
# Просмотр логов в реальном времени
make logs

# Логи хранятся в /var/log/bot/bot.log внутри контейнера
```

### База данных
```bash
# Подключение к PostgreSQL
make psql

# Полезные команды:
# \dt - список таблиц
# \d+ files - описание таблицы files
# SELECT * FROM files LIMIT 10;
```

---

## Разработка

### Быстрый перезапуск после изменений
```bash
# Перезапуск только бота (без пересборки)
make dev-restart
```

### Подключение к контейнеру
```bash
# Bash в контейнере бота
make shell-bot

# Bash в контейнере БД
make shell-db
```

### Структура FSM
- Используется `aiogram` FSM для управления состояниями
- Все состояния определены в `main_handlers.py`
- Состояния сохраняются в памяти (при перезапуске сбрасываются)

---

## Примеры использования

### Python API
```python
from project.api.pdf_analysis import analyze_pdf_path, analyze_pdf_url

# Анализ локального PDF
result = await analyze_pdf_path("/path/to/file.pdf", timeout=120.0)

# Анализ PDF по URL
result = await analyze_pdf_url("https://example.com/doc.pdf", timeout=120.0)

# Результат содержит:
# - volume: {reading_time_min, word_count}
# - complexity: {level, score}
# - category: {label, confidence}
# - topics: [список тегов]
```

### CLI
```bash
# Анализ папки с PDF
docker exec -it pdf_shelf_bot python -m project.tests.eval_pdfs \
  --input-dir project/tests/pdf_for_eval \
  --out-dir project/tests/eval_results
```

---

## Структура проекта

```
pdf-shelf/
├── project/
│   ├── api/                      # API для анализа PDF
│   │   └── pdf_analysis.py       # Функции analyze_pdf_path, analyze_pdf_url
│   │
│   ├── database/                 # Работа с БД
│   │   ├── models.py             # SQLAlchemy модели (User, File, Request)
│   │   ├── engine.py             # Инициализация БД
│   │   ├── file_repository.py    # Репозиторий для файлов
│   │   ├── user_repository.py    # Репозиторий для пользователей
│   │   └── request_repository.py # Репозиторий для запросов
│   │
│   ├── handlers/                 # Обработчики Telegram
│   │   └── main_handlers.py      # Все хэндлеры бота + FSM
│   │
│   ├── keyboards/                # Клавиатуры Telegram
│   │   └── main_keyboards.py     # Reply и Inline клавиатуры
│   │
│   ├── mcp_pdf/                  # Анализ PDF через LLM
│   │   ├── llm_router.py         # Роутер с fallback между провайдерами
│   │   ├── gigachat_client.py    # Клиент для GigaChat API
│   │   ├── pdf_utils.py          # Извлечение текста из PDF
│   │   ├── schema.py             # Схема результата анализа
│   │   └── tools.py              # LLM инструменты для анализа
│   │
│   ├── parser/                   # Конвертация URL → PDF
│   │   └── parser.py             # Playwright-based parser
│   │
│   ├── services/                 # Бизнес-логика
│   │   └── material_selector.py  # Жадный алгоритм подбора материалов
│   │
│   ├── tests/                    # Тесты и утилиты
│   │   ├── eval_pdfs.py          # Пакетный анализ PDF из папки
│   │   ├── test_parser_examples.py # Примеры использования парсера
│   │   ├── test_category.py      # Тест категоризации одного PDF
│   │   ├── test_llm_providers.py # Тесты LLM провайдеров
│   │   ├── pdf_for_eval/         # Тестовые PDF файлы
│   │   └── eval_results/         # Результаты анализа
│   │
│   ├── text/                     # Текстовые сообщения
│   │   └── main_text.py          # Все сообщения бота на русском
│   │
│   ├── utils/                    # Утилиты
│   │   ├── formatters.py         # Форматирование сообщений
│   │   ├── pagination.py         # Пагинация списков
│   │   └── request_parser.py     # Парсинг пользовательских запросов
│   │
│   ├── bot.py                    # Точка входа бота
│   └── config.py                 # Загрузка конфигурации
│
├── migrations/                   # SQL миграции
│   └── init.sql                  # Начальная схема БД
│
├── config.yaml                   # YAML конфигурация
├── docker-compose.yml            # Docker Compose конфигурация
├── Dockerfile                    # Dockerfile для бота
├── Makefile                      # Make команды
└── requirements.txt              # Python зависимости
```

---

## Лицензия

MIT License
