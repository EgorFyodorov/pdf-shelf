"""Internal API for Telegram bot integration.

Provides simple async helpers to analyze PDFs from path or URL using the
existing mcp_pdf tools, without running a separate MCP server.
"""

from .pdf_analysis import NotPDFError  # noqa: F401
