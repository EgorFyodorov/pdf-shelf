import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError


logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Base exception for parser errors"""
    pass


class InvalidURLError(ParserError):
    """Error when URL is invalid"""
    pass


class URLNotAccessibleError(ParserError):
    """Error when URL is not accessible"""
    pass


class ParsingError(ParserError):
    """Error during page parsing"""
    pass


class Parser:
    def __init__(
        self,
        timeout: int = 120000,
        wait_until: str = "networkidle",
        pdf_format: str = "A4",
    ):
        self.timeout = timeout
        self.wait_until = wait_until
        self.pdf_format = pdf_format
        self._browser: Optional[Browser] = None
        self._playwright = None
    
    async def __aenter__(self):
        await self._init_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _init_browser(self):
        if self._browser is None:
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            except Exception as e:
                error_msg = str(e)
                if "Executable doesn't exist" in error_msg or "playwright install" in error_msg:
                    raise ParsingError(
                        "Playwright browser is not installed. Run: playwright install chromium"
                    ) from e
                raise ParsingError(f"Error during browser initialization: {str(e)}") from e
    
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
        return path.endswith('.pdf') or 'application/pdf' in url.lower()
    
    async def _check_url_accessibility(self, url: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status >= 400:
                        raise URLNotAccessibleError(
                            f"URL is not accessible: HTTP {response.status}"
                        )
        except aiohttp.ClientError as e:
            raise URLNotAccessibleError(f"Error during URL accessibility check: {str(e)}")
        except Exception as e:
            raise URLNotAccessibleError(f"Unexpected error during URL check: {str(e)}")
    
    async def _download_pdf(self, url: str, filepath: Path) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status >= 400:
                        raise URLNotAccessibleError(
                            f"PDF file is not accessible: HTTP {response.status}"
                        )
                    
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                        logger.warning(
                            f"Content-Type does not indicate PDF: {content_type}, "
                            f"but continue downloading"
                        )
                    
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    
                    logger.info(f"PDF file successfully downloaded: {filepath}")
        except aiohttp.ClientError as e:
            raise URLNotAccessibleError(f"Error during PDF download: {str(e)}")
        except Exception as e:
            raise ParsingError(f"Unexpected error during PDF download: {str(e)}")
    
    async def _convert_html_to_pdf(self, url: str, filepath: Path) -> None:
        try:
            await self._init_browser()
            
            page: Page = await self._browser.new_page()
            
            try:
                await page.goto(url, wait_until=self.wait_until, timeout=self.timeout)
                
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                await page.pdf(
                    path=str(filepath),
                    format=self.pdf_format,
                    print_background=True,
                )
                
                logger.info(f"Page successfully converted to PDF: {filepath}")
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
    
    async def parse(self, url: str, filepath: str | Path) -> None:
        if not self._is_valid_url(url):
            raise InvalidURLError(f"Invalid URL: {url}")
        
        filepath = Path(filepath)
        
        try:
            await self._check_url_accessibility(url)
            
            if self._is_pdf_url(url):
                logger.info(f"PDF file detected, downloading directly: {url}")
                await self._download_pdf(url, filepath)
            else:
                logger.info(f"Converting web page to PDF: {url}")
                await self._convert_html_to_pdf(url, filepath)
        except (InvalidURLError, URLNotAccessibleError, ParsingError):
            raise
        except Exception as e:
            raise ParsingError(f"Unexpected error during parsing: {str(e)}")
