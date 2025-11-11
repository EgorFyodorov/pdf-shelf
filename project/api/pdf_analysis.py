from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional, Tuple

from project.mcp_pdf.tools import analyze_text_tool, extract_pdf_tool


# --- Exceptions -------------------------------------------------------------


class PDFAnalysisError(Exception):
    """Base error for PDF analysis API."""


class DownloadError(PDFAnalysisError):
    """Raised when a URL cannot be downloaded or times out."""


class NotPDFError(PDFAnalysisError):
    """Raised when provided content is not recognized as a PDF."""


class LLMError(PDFAnalysisError):
    """Raised when LLM analysis fails in a non-recoverable way."""


# --- Public API -------------------------------------------------------------


async def extract_pdf(*, path: Optional[str] = None, url: Optional[str] = None, timeout: float | None = 60.0) -> Tuple[str, dict[str, Any]]:
    """Extrac@t first-page TEXT and META from a PDF.

    Returns (TEXT, META).
    - path: local file path
    - url: http(s) URL
    - timeout: total timeout in seconds for network-bound operations
    """

    if not path and not url:
        raise PDFAnalysisError("Either 'path' or 'url' must be provided")

    if path:
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise PDFAnalysisError(f"File not found: {path}")

    try:
        coro = extract_pdf_tool(path=path, url=url)
        result = await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
        return result["TEXT"], result["META"]
    except asyncio.TimeoutError as e:
        raise DownloadError("Operation timed out during PDF extraction") from e
    except ValueError as e:
        msg = str(e)
        if "not a PDF" in msg or "%PDF header" in msg:
            raise NotPDFError(msg) from e
        if msg.startswith("HTTP "):
            raise DownloadError(msg) from e
        raise PDFAnalysisError(msg) from e
    except Exception as e:  # pragma: no cover - passthrough
        raise PDFAnalysisError(str(e)) from e


async def analyze_text(text: str, meta: Optional[dict[str, Any]] = None, timeout: float | None = 60.0) -> dict[str, Any]:
    """Analyze provided TEXT (typically first page) with META and return JSON by schema.

    This API relies on the underlying tool's fallback: if LLM is unavailable, a
    heuristic analysis is returned.
    """

    try:
        coro = analyze_text_tool(text=text, meta=meta)
        return await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
    except asyncio.TimeoutError as e:
        raise LLMError("Operation timed out during analysis") from e
    except Exception as e:  # pragma: no cover - unexpected failures
        # analyze_text_tool already falls back if Gemini fails, so here treat as fatal
        raise LLMError(str(e)) from e


async def analyze_pdf_path(path: str, *, timeout: float | None = 60.0) -> dict[str, Any]:
    """Convenience: extract from local file then analyze."""

    text, meta = await extract_pdf(path=path, timeout=timeout)
    return await analyze_text(text, meta, timeout=timeout)


async def analyze_pdf_url(url: str, *, timeout: float | None = 60.0) -> dict[str, Any]:
    """Convenience: download/extract from URL then analyze."""

    if not (url.startswith("http://") or url.startswith("https://")):
        raise PDFAnalysisError("URL must start with http:// or https://")
    text, meta = await extract_pdf(url=url, timeout=timeout)
    return await analyze_text(text, meta, timeout=timeout)


__all__ = [
    "PDFAnalysisError",
    "DownloadError",
    "NotPDFError",
    "LLMError",
    "extract_pdf",
    "analyze_text",
    "analyze_pdf_path",
    "analyze_pdf_url",
]
