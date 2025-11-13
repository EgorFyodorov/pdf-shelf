import asyncio
import logging
from pathlib import Path

from project.parser.parser import (
    InvalidURLError,
    Parser,
    ParserError,
    ParsingError,
    URLNotAccessibleError,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def example_basic_usage():
    """Базовый пример использования парсера"""
    print("\n=== Пример 1: Базовое использование ===")

    parser = Parser()

    try:
        await parser.parse(
            url="https://habr.com/ru/articles/764582/",
            filepath="project/tests/project/tests/output/example_basic.pdf",
        )
        print("✓ Успешно: example_basic.pdf создан")
    except (ParserError, Exception) as e:
        print(f"✗ Ошибка: {e}")
    finally:
        try:
            await parser.close()
        except Exception:
            pass


async def example_context_manager():
    """Пример использования парсера как контекстного менеджера"""
    print("\n=== Пример 2: Использование как контекстный менеджер ===")

    try:
        async with Parser() as parser:
            try:
                await parser.parse(
                    url="https://www.python.org", filepath="project/tests/output/python_org.pdf"
                )
                print("✓ Успешно: python_org.pdf создан")
            except (ParserError, Exception) as e:
                print(f"✗ Ошибка: {e}")
    except Exception as e:
        print(f"✗ Ошибка при создании парсера: {e}")


async def example_pdf_download():
    """Пример скачивания PDF файла напрямую"""
    print("\n=== Пример 3: Скачивание PDF файла ===")

    try:
        async with Parser() as parser:
            try:
                await parser.parse(
                    url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                    filepath="project/tests/output/dummy.pdf",
                )
                print("✓ Успешно: dummy.pdf скачан")
            except (ParserError, Exception) as e:
                print(f"✗ Ошибка: {e}")
    except Exception as e:
        print(f"✗ Ошибка при создании парсера: {e}")


async def example_error_handling():
    """Пример обработки различных типов ошибок"""
    print("\n=== Пример 4: Обработка ошибок ===")

    try:
        async with Parser() as parser:
            test_cases = [
                ("invalid-url", InvalidURLError, "Невалидный URL"),
                (
                    "https://httpstat.us/404",
                    URLNotAccessibleError,
                    "Недоступный URL",
                ),
                (
                    "https://this-domain-definitely-does-not-exist-12345.com",
                    URLNotAccessibleError,
                    "Несуществующий домен",
                ),
            ]

            for url, expected_error, description in test_cases:
                try:
                    await parser.parse(url=url, filepath="project/tests/output/test.pdf")
                    print(f"✗ Неожиданный успех для: {description}")
                except expected_error as e:
                    print(
                        f"✓ Правильно обработана ошибка ({description}): {type(e).__name__}"
                    )
                except ParserError as e:
                    print(
                        f"⚠ Другая ошибка парсера ({description}): {type(e).__name__} - {e}"
                    )
                except Exception as e:
                    print(
                        f"✗ Неожиданная ошибка ({description}): {type(e).__name__} - {e}"
                    )
    except Exception as e:
        print(f"✗ Ошибка при создании парсера: {e}")


async def example_multiple_urls():
    """Пример обработки нескольких URL"""
    print("\n=== Пример 5: Обработка нескольких URL ===")

    urls = [
        ("https://example.com", "project/tests/output/multiple_example.pdf"),
        ("https://www.python.org", "project/tests/output/multiple_python.pdf"),
    ]

    try:
        async with Parser() as parser:
            for url, filepath in urls:
                try:
                    await parser.parse(url=url, filepath=filepath)
                    print(f"✓ Успешно обработан: {url} -> {filepath}")
                except (ParserError, Exception) as e:
                    print(f"✗ Ошибка для {url}: {e}")
    except Exception as e:
        print(f"✗ Ошибка при создании парсера: {e}")


async def example_custom_settings():
    """Пример использования с кастомными настройками"""
    print("\n=== Пример 6: Кастомные настройки ===")

    parser = Parser(
        timeout=60000,
        wait_until="load",
        pdf_format="Letter",
    )

    try:
        await parser.parse(
            url="https://example.com", filepath="project/tests/output/custom_settings.pdf"
        )
        print("✓ Успешно: custom_settings.pdf создан с кастомными настройками")
    except (ParserError, Exception) as e:
        print(f"✗ Ошибка: {e}")
    finally:
        try:
            await parser.close()
        except Exception:
            pass


async def main():
    """Запуск всех примеров"""
    output_dir = Path("project/tests/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Запуск примеров использования парсера...")
    print("(Парсер запущен без загрузки конфигурации бота)")
    print("\n⚠ ВАЖНО: Убедитесь, что установлены браузеры Playwright:")
    print("   playwright install chromium\n")

    examples = [
        example_basic_usage,
        example_context_manager,
        example_pdf_download,
        example_error_handling,
        example_multiple_urls,
        example_custom_settings,
    ]

    for example_func in examples:
        try:
            await example_func()
        except Exception as e:
            print(f"✗ Критическая ошибка в {example_func.__name__}: {e}")

    print("\n=== Все примеры завершены ===")


if __name__ == "__main__":
    asyncio.run(main())

