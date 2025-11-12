import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional, Iterable
from urllib.parse import urlparse, unquote

import aiohttp
from langdetect import detect as lang_detect, DetectorFactory
from pypdf import PdfReader


logger = logging.getLogger(__name__)

# Ensure langdetect is deterministic
DetectorFactory.seed = 0


@dataclass
class Extracted:
    text: str
    page_count: Optional[int]
    byte_size: Optional[int]
    precomputed_word_count: Optional[int]
    lang_hint: Optional[str]
    source_name: Optional[str]
    reading_time_breakdown: Optional[dict] = None
    reading_time_min_host: Optional[float] = None
    toc_preview: Optional[str] = None


async def _download_bytes(url: str, timeout: int = 20) -> bytes:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status} for URL: {url}")
            data = await resp.read()
            return data


def _is_probably_pdf_bytes(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def _read_pdf_bytes(data: bytes, source_name: Optional[str]) -> Extracted:
    bio = io.BytesIO(data)
    reader = PdfReader(bio)
    total_pages = len(reader.pages) if reader.pages is not None else None

    # Политика выбора объёма текста: по умолчанию только первая страница
    text_pages_policy = os.getenv("PDF_MCP_TEXT_PAGES", "first").lower()

    # Извлекаем первую страницу всегда (нужна для оценки и lang_hint)
    try:
        first_page_text = (reader.pages[0].extract_text() or "") if total_pages else ""
    except Exception as e:
        logger.warning("Text extract failed on first page: %s", e)
        first_page_text = ""

    # Для отладки можно извлечь полный текст, если флагом указано 'full'
    combined = first_page_text
    if text_pages_policy == "full":
        texts = [first_page_text]
        for idx in range(1, total_pages or 0):
            try:
                t = reader.pages[idx].extract_text() or ""
            except Exception as e:  # pypdf can occasionally fail per-page
                logger.warning("Text extract failed on page %s: %s", idx + 1, e)
                t = ""
            if t:
                texts.append(t)
        combined = "\n\n".join(filter(None, texts))

    # Подсчёты на основе первой страницы
    w1, c1_no_spaces = count_words_and_chars(first_page_text)
    c1_no_spaces = len(_normalize_spaces(first_page_text).replace(" ", ""))
    lang = detect_language_safe(first_page_text)

    total_words = estimate_total_words(w1=w1, page_count=total_pages, byte_size=len(data))

    # Попытка детерминистического подсчёта объёма/времени по всему документу (PyMuPDF)
    reading_breakdown: Optional[dict] = None
    reading_total_min: Optional[float] = None
    try:
        from .metrics import estimate_pdf_reading_time_minutes  # lazy import to avoid heavy deps at import time

        mres = estimate_pdf_reading_time_minutes(data=data, lang=lang or "ru", complexity_level=None)
        reading_breakdown = mres.get("breakdown")
        reading_total_min = float(mres.get("total_min", 0.0))
        # words из точного подсчёта
        if isinstance(reading_breakdown, dict) and isinstance(reading_breakdown.get("words"), int):
            total_words = int(reading_breakdown["words"]) or total_words
    except Exception as e:
        logger.debug("Reading-time metrics error, fallback to heuristic words: %s", e)

    # Извлечение оглавления/заголовков (TOC preview)
    toc_preview: Optional[str] = None
    try:
        if _should_include_toc():
            toc_preview = _build_toc_preview(reader)
    except Exception as e:
        logger.debug("TOC preview extraction failed: %s", e)

    return Extracted(
        text=combined,
        page_count=total_pages,
        byte_size=len(data),
        precomputed_word_count=total_words,
        lang_hint=lang,
        source_name=source_name,
        reading_time_breakdown=reading_breakdown,
        reading_time_min_host=reading_total_min,
        toc_preview=toc_preview,
    )


async def extract_from_path_or_url(path: Optional[str] = None, url: Optional[str] = None) -> Extracted:
    if not path and not url:
        raise ValueError("Either 'path' or 'url' must be provided")
    if path:
        with open(path, "rb") as f:
            data = f.read()
        source_name: Optional[str] = os.path.basename(path)
    else:
        data = await _download_bytes(url)  # type: ignore[arg-type]
        # Try to derive a human-friendly name from URL path
        try:
            parsed = urlparse(url or "")
            bn = os.path.basename(parsed.path)
            source_name = unquote(bn) if bn else None
        except Exception:
            source_name = None
    if not _is_probably_pdf_bytes(data):
        raise ValueError("Provided content is not a PDF (missing %PDF header)")
    return _read_pdf_bytes(data, source_name)


# Важно: стандартный модуль re не поддерживает классы Юникода \p{L}/\p{N},
# поэтому используем безопасный диапазон для кириллицы/латиницы/цифр.
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.U)


def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def count_words_and_chars(text: str) -> tuple[int, int]:
    # Rough word count: split on whitespace and drop 1-char tokens and URLs
    tokens = re.split(r"\s+", text)
    word_tokens = []
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        if re.match(r"(?i)https?://", t):
            continue
        if len(re.sub(r"\W+", "", t)) <= 1:
            continue
        word_tokens.append(t)
    word_count = len(word_tokens)
    char_count = len(_normalize_spaces(text).replace(" ", ""))
    return word_count, char_count


def detect_language_safe(text: str) -> Optional[str]:
    sample = text[:5000]
    try:
        code = lang_detect(sample)
        # langdetect returns codes like 'ru', 'en'
        return code
    except Exception:
        return None


def estimate_reading_time_min(lang: Optional[str], word_count: int) -> float:
    wpm = 180
    if lang and lang.startswith("en"):
        wpm = 200
    elif lang and lang.startswith("ru"):
        wpm = 180
    return round(word_count / max(wpm, 1), 1)


# --- Эвристики для оценки объёма по первой странице ------------------------


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def estimate_total_words(w1: int, page_count: Optional[int], byte_size: Optional[int]) -> int:
    """Оценка общего числа слов по правилам из ТЗ.

    - Если w1 >= 30 и известен page_count:
        words_per_page = clamp(w1, 60..900); total = words_per_page * page_count
    - Иначе, если известны page_count и byte_size:
        words_per_page ≈ clamp(byte_size/page_count/6, 60..900)
    - Иначе: total = 300 × page_count (или 300, если page_count неизвестно)
    """
    if page_count and w1 >= 30:
        words_per_page = int(_clamp(float(w1), 60.0, 900.0))
        return words_per_page * page_count
    if page_count and byte_size:
        approx_wpp = float(byte_size) / max(page_count, 1) / 6.0
        words_per_page = int(_clamp(approx_wpp, 60.0, 900.0))
        return words_per_page * page_count
    if page_count:
        return 300 * page_count
    return 300


def estimate_char_count_from_first(avg_chars_per_word: float, total_words: int) -> int:
    return int(round(total_words * avg_chars_per_word))


def avg_chars_per_word_from_first_page(first_page_text: str, w1: int) -> float:
    no_spaces = len(_normalize_spaces(first_page_text).replace(" ", ""))
    base = no_spaces / max(w1, 1)
    return _clamp(base, 4.5, 6.5)


# Категоризация по ключевым словам намеренно удалена согласно требованию.


# ----------------------- TOC extraction helpers -----------------------------

def _should_include_toc() -> bool:
    return str(os.getenv("PDF_MCP_INCLUDE_TOC", "true")).strip().lower() != "false"


def _toc_pages_limit() -> int:
    try:
        return max(1, int(os.getenv("PDF_MCP_TOC_PAGES", "3")))
    except Exception:
        return 3


def _toc_chars_limit() -> int:
    try:
        return max(200, int(os.getenv("PDF_MCP_TOC_LIMIT", "2000")))
    except Exception:
        return 2000


def _flatten_outlines(items: Iterable) -> list[str]:
    lines: list[str] = []
    stack = list(items) if items is not None else []
    while stack:
        it = stack.pop(0)
        try:
            # pypdf Destination or dict-like
            title = None
            if hasattr(it, "title"):
                title = getattr(it, "title")
            elif isinstance(it, dict) and it.get("/Title"):
                title = str(it.get("/Title"))
            elif isinstance(it, str):
                title = it
            if title:
                title = _normalize_spaces(str(title))
                if title:
                    lines.append(title)
            # Children
            kids = None
            if hasattr(it, "children"):
                kids = getattr(it, "children")
            elif isinstance(it, dict) and it.get("/First"):
                kids = [it.get("/First")]
            if kids:
                # ensure iterable
                try:
                    stack[0:0] = list(kids)
                except Exception:
                    pass
        except Exception:
            continue
    return lines


_HDR_NUM_RE = re.compile(r"^\s*(?:\d+\.){1,3}\s+.+")
_DOTS_PAGE_RE = re.compile(r"^.+\.{3,}\s*\d+\s*$")


def _extract_titles_from_pages(reader: PdfReader, limit_pages: int) -> list[str]:
    lines: list[str] = []
    pages = min(limit_pages, len(reader.pages) if reader.pages is not None else 0)
    for i in range(pages):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception as e:
            logger.debug("TOC: page extract failed p%s: %s", i + 1, e)
            continue
        for raw in text.splitlines():
            s = _normalize_spaces(raw)
            if not s or len(s) < 4:
                continue
            if s.lower() in ("contents", "table of contents", "содержание"):
                lines.append(s)
                continue
            # числовые заголовки или строки с точками и номером страницы
            if _HDR_NUM_RE.match(s) or _DOTS_PAGE_RE.match(s):
                lines.append(s)
                continue
            # сильный заголовок: много заглавных букв, мало знаков пунктуации
            upper_ratio = sum(1 for ch in s if ch.isupper()) / max(1, len(s))
            if upper_ratio > 0.5 and len(s) <= 120:
                lines.append(s)
    # Дедупликация, ограничение длины строки
    seen = set()
    norm_lines: list[str] = []
    for s in lines:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        if len(s) > 160:
            s = s[:157] + "…"
        norm_lines.append(s)
    return norm_lines


def _build_toc_preview(reader: PdfReader) -> str:
    limit_chars = _toc_chars_limit()
    # 1) попытка извлечь outlines
    outlines = None
    for attr in ("outline", "outlines"):
        try:
            outlines = getattr(reader, attr)
            if outlines:
                break
        except Exception:
            continue
    lines: list[str] = []
    if outlines:
        try:
            lines = _flatten_outlines(outlines)
        except Exception as e:
            logger.debug("TOC: outlines flatten failed: %s", e)
            lines = []
    # 2) фолбэк по первым страницам
    if not lines:
        lines = _extract_titles_from_pages(reader, _toc_pages_limit())
    if not lines:
        return ""
    preview = "\n".join(lines)
    if len(preview) > limit_chars:
        preview = preview[: limit_chars - 1] + "…"
    return preview
