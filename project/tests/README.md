# Тесты и скрипты для оценки

Эта папка содержит тестовые скрипты и утилиты для проверки функциональности PDF Shelf.

## Доступные команды

Все команды запускаются **внутри Docker контейнера** через Makefile в корне проекта.

### 1. Массовая оценка PDF файлов

Запускает анализ всех PDF файлов из указанной директории:

```bash
make eval
```

**Параметры по умолчанию:**
- `--input-dir project/tests/pdf_for_eval` - директория с PDF файлами
- `--out-dir project/tests/eval_results` - куда сохранять JSON результаты
- `--concurrency 1` - количество одновременных задач
- `--timeout 300` - таймаут на один файл (секунды)

**Что делает:**
- Сканирует все PDF файлы в `project/tests/pdf_for_eval/`
- Анализирует каждый файл (объем, сложность, категория)
- Сохраняет результаты в JSON в `project/tests/eval_results/`
- Выводит сводную таблицу результатов

### 2. Тестирование парсера URL → PDF

Запускает набор примеров использования парсера:

```bash
make test-parser
```

**Что проверяет:**
- Базовое использование парсера
- Работа как контекстного менеджера
- Скачивание PDF файлов
- Обработка ошибок (невалидные URL, 404, недоступные домены)
- Обработка нескольких URL
- Кастомные настройки парсера

### 3. Тестирование категоризации

Проверяет качество категоризации для конкретного PDF:

```bash
make test-category PDF=project/tests/pdf_for_eval/my-document.pdf
```

**Что проверяет:**
- Базовую категоризацию документа
- Категоризацию с существующими категориями
- Консистентность (повторяет анализ 3 раза и проверяет стабильность результатов)

**Пример:**
```bash
make test-category PDF=project/tests/pdf_for_eval/llm-as-judge.pdf
```

### 4. Запуск всех pytest тестов

Запускает все unit-тесты с помощью pytest:

```bash
make test
```

**Что проверяет:**
- Работу всех модулей проекта
- LLM провайдеров (Gemini, GigaChat, Perplexity)
- Корректность форматирования и обработки данных

### 5. Тестирование LLM провайдеров

Запускает только тесты для проверки работы LLM провайдеров:

```bash
make test-llm
```

**Что проверяет:**
- Подключение к Gemini API
- Подключение к GigaChat API
- Подключение к Perplexity API
- Fallback механизмы при недоступности сервисов

⚠️ **Требуются API ключи** в `.env`:
- `GEMINI_API_KEY` для Gemini
- `GIGACHAT_AUTH_KEY` для GigaChat
- `PERPLEXITY_API_KEY` для Perplexity

## Структура папки

```
project/tests/
├── README.md                   # Этот файл
├── __init__.py                 # Инициализация пакета
├── eval_pdfs.py               # Массовая оценка PDF
├── test_parser_examples.py    # Примеры парсера
├── test_category.py           # Тесты категоризации
├── test_llm_providers.py      # Pytest тесты для LLM провайдеров
├── pdf_for_eval/              # PDF файлы для тестирования
├── eval_results/              # Результаты анализа (JSON)
└── output/                    # Результаты работы парсера
```

## Запуск вне Docker

Если нужно запустить тесты локально (не в контейнере):

```bash
# Из корня проекта (/home/egorf/projs/pdf-shelf/)

# Массовая оценка
python -m project.tests.eval_pdfs

# Тесты парсера
python -m project.tests.test_parser_examples

# Тесты категоризации
python -m project.tests.test_category project/tests/pdf_for_eval/my-document.pdf

# Все pytest тесты
pytest project/tests/ -v -s

# Только LLM провайдеры
pytest project/tests/test_llm_providers.py -v -s
```

⚠️ **Важно:** При локальном запуске убедитесь, что:
- Установлены все зависимости из `requirements.txt`
- Установлен Chromium для Playwright: `playwright install chromium`
- Настроены переменные окружения (`.env`)
- База данных доступна

## Добавление новых тестов

При добавлении новых тестовых скриптов:

1. Создайте файл в `project/tests/`
2. Используйте правильные импорты: `from project.module import ...`
3. Добавьте команду в `Makefile` в корне проекта
4. Обновите этот README

## Структура результатов

После запуска `make eval` в `eval_results/` появятся JSON файлы с полными результатами анализа:

```json
{
  "doc_language": "ru",
  "volume": {
    "page_count": 10,
    "word_count": 2500,
    "reading_time_min": 13.9
  },
  "complexity": {
    "score": 45,
    "level": "средняя",
    "grade": "университетский"
  },
  "category": {
    "label": "Технологии",
    "score": 0.85,
    "basis": "...",
    "keywords": ["программирование", "разработка"]
  }
}
```

