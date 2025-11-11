from __future__ import annotations

import asyncio
import logging

from typing import Any

try:
    # FastMCP provides a very small helper over stdio server
    from mcp.server.fastmcp import FastMCP  # type: ignore
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore

from .tools import analyze_text_tool, extract_pdf_tool

logger = logging.getLogger(__name__)


def _build_server():
    if FastMCP is None:
        raise RuntimeError(
            "mcp.server.fastmcp is not available. Please install 'mcp' package."
        )
    app = FastMCP("pdf-mcp")

    @app.tool()
    async def extract_pdf(path: str | None = None, url: str | None = None) -> dict[str, Any]:
        """Извлекает TEXT и META из PDF. Требуется один из аргументов: path или url."""
        return await extract_pdf_tool(path=path, url=url)

    @app.tool()
    async def analyze_text(TEXT: str, META: dict | None = None) -> dict:
        """Возвращает строго валидный JSON-объект анализа по схеме из ТЗ."""
        return await analyze_text_tool(text=TEXT, meta=META)

    return app


def run():
    app = _build_server()
    app.run()


if __name__ == "__main__":
    run()
