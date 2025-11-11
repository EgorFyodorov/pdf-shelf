# Парсер веб-страниц в PDF

Асинхронный класс для конвертации веб-страниц в PDF и скачивания PDF файлов.

## Установка зависимостей

Перед использованием необходимо установить зависимости:

```bash
pip install -r requirements.txt
```

Также необходимо установить браузеры для Playwright:

```bash
playwright install chromium
```

## Основное использование

### Базовый пример

```python
import asyncio
from project.parser import Parser

async def main():
    parser = Parser()
    try:
        await parser.parse(
            url="https://habr.com",
            filepath="output/habr.pdf"
        )
        print("PDF успешно создан!")
    except ParserError as e:
        print(f"Ошибка: {e}")
    finally:
        await parser.close()

asyncio.run(main())
```

### Использование как контекстный менеджер

```python
import asyncio
from project.parser import Parser

async def main():
    async with Parser() as parser:
        await parser.parse(
            url="https://example.com",
            filepath="output/example.pdf"
        )

asyncio.run(main())
```

### Скачивание PDF файла

Если URL указывает на PDF файл, он будет скачан напрямую:

```python
async with Parser() as parser:
    await parser.parse(
        url="https://example.com/document.pdf",
        filepath="output/document.pdf"
    )
```

### Кастомные настройки

```python
parser = Parser(
    timeout=60000,        # Таймаут 60 секунд
    wait_until="load",    # Ждать только загрузки страницы
    pdf_format="Letter"   # Формат Letter вместо A4
)
```

## Обработка ошибок

Парсер выбрасывает специфичные исключения для разных типов ошибок:

- `InvalidURLError` - невалидный URL
- `URLNotAccessibleError` - URL недоступен (404, таймаут, сетевые ошибки)
- `ParsingError` - ошибка при парсинге или конвертации

Все исключения наследуются от `ParserError`:

```python
from project.parser import Parser, ParserError, InvalidURLError, URLNotAccessibleError, ParsingError

async with Parser() as parser:
    try:
        await parser.parse(url="https://example.com", filepath="output.pdf")
    except InvalidURLError as e:
        print(f"Невалидный URL: {e}")
    except URLNotAccessibleError as e:
        print(f"URL недоступен: {e}")
    except ParsingError as e:
        print(f"Ошибка парсинга: {e}")
    except ParserError as e:
        print(f"Общая ошибка парсера: {e}")
```

## Примеры

Полные примеры использования находятся в файле `examples.py`.

### Способ 1: Запуск без загрузки конфигурации бота (рекомендуется)

Из корня проекта:

```bash
python run_parser_examples.py
```

Этот скрипт импортирует парсер напрямую, минуя `project/__init__.py`, поэтому не требует установки всех зависимостей бота (dotenv, PyYAML и т.д.).

### Способ 2: Через скрипт-обертку

Из корня проекта:

```bash
python run_examples.py
```

**Примечание:** Этот способ требует установки всех зависимостей проекта, включая dotenv и PyYAML.

### Способ 3: Через модуль Python

Из корня проекта:

```bash
python -m project.parser.examples
```

**Примечание:** Этот способ также требует установки всех зависимостей проекта.

## API

### Класс Parser

#### `__init__(timeout=30000, wait_until="networkidle", pdf_format="A4")`

Инициализация парсера.

**Параметры:**
- `timeout` (int): Таймаут для загрузки страницы в миллисекундах (по умолчанию 30000)
- `wait_until` (str): Событие ожидания загрузки страницы (по умолчанию "networkidle")
- `pdf_format` (str): Формат PDF страницы (по умолчанию "A4")

#### `async parse(url: str, filepath: str | Path) -> None`

Основной метод для парсинга URL и сохранения в PDF.

**Параметры:**
- `url` (str): URL для парсинга (веб-страница или PDF файл)
- `filepath` (str | Path): Путь для сохранения PDF файла

**Исключения:**
- `InvalidURLError`: Если URL невалиден
- `URLNotAccessibleError`: Если URL недоступен
- `ParsingError`: Если произошла ошибка при парсинге

#### `async close() -> None`

Закрытие браузера и освобождение ресурсов. Вызывается автоматически при использовании контекстного менеджера.

## Интеграция с ботом

Парсер можно легко интегрировать в бот:

```python
from project.parser import Parser, ParserError

async def handle_url(message: Message, parser: Parser):
    url = message.text
    filepath = f"downloads/{message.from_user.id}_{message.message_id}.pdf"
    
    try:
        await parser.parse(url=url, filepath=filepath)
        await message.reply_document(open(filepath, 'rb'))
    except ParserError as e:
        await message.reply(f"Ошибка: {e}")
```

