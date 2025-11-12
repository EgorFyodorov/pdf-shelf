"""PDF MCP server package.

Экспортирует основные части MCP сервера для анализа PDF:
- tools: инструменты MCP (extract_pdf, analyze_text)
- server: запуск MCP сервера через stdio
"""

from .tools import extract_pdf_tool, analyze_text_tool  # noqa: F401
