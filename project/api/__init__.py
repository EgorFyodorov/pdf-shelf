"""Internal API for Telegram bot integration.

Provides simple async helpers to analyze PDFs from path or URL using the
existing mcp_pdf tools, without running a separate MCP server.
"""

from .pdf_analysis import (  # noqa: F401
    PDFAnalysisError,
    DownloadError,
    NotPDFError,
    LLMError,
    extract_pdf,
    analyze_text,
    analyze_pdf_path,
    analyze_pdf_url,
)
