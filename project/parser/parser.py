import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import Browser, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Base exception for parser errors"""


class InvalidURLError(ParserError):
    """Error when URL is invalid"""


class URLNotAccessibleError(ParserError):
    """Error when URL is not accessible"""


class ParsingError(ParserError):
    """Error during page parsing"""


class Parser:
    def __init__(
        self,
        timeout: Optional[int] = None,
        wait_until: Optional[str] = None,
        pdf_format: Optional[str] = None,
    ):
        self.timeout = timeout if timeout is not None else 120000
        self.wait_until = wait_until if wait_until is not None else "networkidle"
        self.pdf_format = pdf_format if pdf_format is not None else "A4"
        self._browser: Optional[Browser] = None
        self._playwright = None
    
    @classmethod
    def from_config(cls, parser_config):
        """Создаёт Parser из конфигурации."""
        return cls(
            timeout=parser_config.timeout,
            wait_until=parser_config.wait_until,
            pdf_format=parser_config.pdf_format,
        )

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def initialize(self):
        """Публичный метод для инициализации браузера."""
        await self._init_browser()

    async def _init_browser(self):
        if self._browser is None:
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            except Exception as e:
                error_msg = str(e)
                if (
                    "Executable doesn't exist" in error_msg
                    or "playwright install" in error_msg
                ):
                    raise ParsingError(
                        "Playwright browser is not installed. Run: playwright install chromium"
                    ) from e
                raise ParsingError(
                    f"Error during browser initialization: {str(e)}"
                ) from e

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def _is_pdf_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(".pdf") or "application/pdf" in url.lower()

    async def _check_url_accessibility(self, url: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status >= 400:
                        raise URLNotAccessibleError(
                            f"URL is not accessible: HTTP {response.status}"
                        )
        except aiohttp.ClientError as e:
            raise URLNotAccessibleError(
                f"Error during URL accessibility check: {str(e)}"
            )
        except Exception as e:
            raise URLNotAccessibleError(f"Unexpected error during URL check: {str(e)}")

    async def _download_pdf(self, url: str, filepath: Path) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status >= 400:
                        raise URLNotAccessibleError(
                            f"PDF file is not accessible: HTTP {response.status}"
                        )

                    content_type = response.headers.get("Content-Type", "").lower()
                    if (
                        "application/pdf" not in content_type
                        and not url.lower().endswith(".pdf")
                    ):
                        logger.warning(
                            f"Content-Type does not indicate PDF: {content_type}, "
                            f"but continue downloading"
                        )

                    filepath.parent.mkdir(parents=True, exist_ok=True)

                    with open(filepath, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

                    logger.info(f"PDF file successfully downloaded: {filepath}")
        except aiohttp.ClientError as e:
            raise URLNotAccessibleError(f"Error during PDF download: {str(e)}")
        except Exception as e:
            raise ParsingError(f"Unexpected error during PDF download: {str(e)}")

    async def _convert_html_to_pdf(self, url: str, filepath: Path) -> str:
        """Конвертирует HTML в PDF и возвращает заголовок страницы."""
        try:
            await self._init_browser()

            page: Page = await self._browser.new_page()

            try:
                await page.goto(url, wait_until=self.wait_until, timeout=self.timeout)

                # Получаем заголовок страницы
                page_title = await page.title()

                filepath.parent.mkdir(parents=True, exist_ok=True)

                await page.pdf(
                    path=str(filepath),
                    format=self.pdf_format,
                    print_background=True,
                )

                logger.info(f"Page successfully converted to PDF: {filepath}")
                return page_title or ""
            except PlaywrightTimeoutError as e:
                raise ParsingError(f"Timeout during page load: {str(e)}")
            except Exception as e:
                raise ParsingError(f"Error during conversion of page to PDF: {str(e)}")
            finally:
                await page.close()
        except Exception as e:
            if isinstance(e, ParsingError):
                raise
            raise ParsingError(f"Unexpected error during conversion: {str(e)}")

    async def parse(self, url: str, filepath: str | Path) -> str:
        """
        Парсит URL и сохраняет результат в PDF файл.
        
        Returns:
            Заголовок страницы (для HTML) или имя файла из URL (для PDF)
        """
        if not self._is_valid_url(url):
            raise InvalidURLError(f"Invalid URL: {url}")

        filepath = Path(filepath)

        try:
            await self._check_url_accessibility(url)

            if self._is_pdf_url(url):
                logger.info(f"PDF file detected, downloading directly: {url}")
                await self._download_pdf(url, filepath)
                # Извлекаем имя файла из URL
                parsed_url = urlparse(url)
                filename = Path(parsed_url.path).stem
                return filename or "Документ"
            else:
                logger.info(f"Converting web page to PDF: {url}")
                page_title = await self._convert_html_to_pdf(url, filepath)
                return page_title or "Документ"
        except (InvalidURLError, URLNotAccessibleError, ParsingError):
            raise
        except Exception as e:
            raise ParsingError(f"Unexpected error during parsing: {str(e)}")
