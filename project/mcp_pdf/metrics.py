from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

try:  # PyMuPDF
    import fitz  # type: ignore
except Exception as _e:  # pragma: no cover - optional at runtime
    fitz = None  # type: ignore

logger = logging.getLogger(__name__)

LEVEL = Literal["очень низкая", "низкая", "средняя", "высокая", "очень высокая"]

WPM_BY_LANG: Dict[str, int] = {"ru": 180, "en": 200}
K_BY_LEVEL: Dict[str, float] = {
    "очень низкая": 1.10,
    "низкая": 1.00,
    "средняя": 0.85,
    "высокая": 0.70,
    "очень высокая": 0.55,
}

# Regexes
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\u0400-\u04FF]+", re.U)
TABLE_RE = re.compile(r"\b(table|таблица|табл\.)\b", re.I | re.U)
CODE_LINE_RE = re.compile(
    r"[;{}()\[\]]|^\s*(def|class|#include|for\s*\(|while\s*\()", re.I | re.M
)


def _parse_per_image_seconds(env_val: Optional[str]) -> Tuple[int, int]:
    if not env_val:
        return (3, 10)
    try:
        parts = [int(x.strip()) for x in env_val.split(",")]
        if len(parts) != 2:
            return (3, 10)
        return (max(0, parts[0]), max(0, parts[1]))
    except Exception:
        return (3, 10)


def _base_wpm(lang: str | None) -> int:
    if not lang:
        return 180
    lang = lang.lower()
    for key, val in WPM_BY_LANG.items():
        if lang.startswith(key):
            return val
    return 180


def _effective_wpm(base: int, level: Optional[LEVEL]) -> int:
    k = K_BY_LEVEL.get(level or "средняя", 0.85)
    return max(60, int(base * k))


def _count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _classify_page(words: int, imgs: int) -> str:
    if words >= 200:
        return "text"
    if words >= 80:
        return "mixed"
    if words >= 20 and imgs > 0:
        return "slide"
    if imgs > 0:
        return "slide"
    return "empty"


@dataclass
class ReadTimeResult:
    total_min: float
    text_min: float
    nontext_min: float
    breakdown: dict


def _accurate_estimate(
    *,
    doc: "fitz.Document",
    lang: str,
    complexity_level: Optional[LEVEL],
    per_image_seconds: Tuple[int, int],
) -> ReadTimeResult:
    total_words = 0
    images_s = tables_s = code_s = slides_s = 0
    pages_counter = {"text": 0, "mixed": 0, "slide": 0, "empty": 0}

    for page in doc:  # type: ignore[union-attr]
        try:
            text = page.get_text("text") or ""
        except Exception as e:
            logger.debug("fitz.get_text() failed on page: %s", e)
            text = ""
        words = _count_words(text)
        try:
            imgs = len(page.get_images(full=True))
        except Exception:
            imgs = 0
        tables = len(TABLE_RE.findall(text))
        code_lines = len([l for l in text.splitlines() if CODE_LINE_RE.search(l)])

        cls = _classify_page(words, imgs)
        pages_counter[cls] += 1

        if cls in ("text", "mixed"):
            total_words += words
            images_s += imgs * per_image_seconds[0]
        elif cls == "slide":
            slide_time = max(8, min(25, 6 + words / 10))
            slides_s += int(slide_time)

        if tables:
            tables_s += tables * 12
        if code_lines:
            code_s += int(code_lines * 0.6)

    eff_wpm = _effective_wpm(_base_wpm(lang), complexity_level)
    text_min = round(total_words / max(1, eff_wpm), 2)
    nontext_min = round((images_s + tables_s + code_s + slides_s) / 60, 2)
    total_min = round(text_min + nontext_min, 2)

    breakdown = {
        "words": total_words,
        "effective_wpm": eff_wpm,
        "slides_s": slides_s,
        "images_s": images_s,
        "tables_s": tables_s,
        "code_s": code_s,
        "pages": pages_counter,
    }
    return ReadTimeResult(total_min, text_min, nontext_min, breakdown)


def _fast_fallback(
    *,
    doc: "fitz.Document",
    lang: str,
    complexity_level: Optional[LEVEL],
) -> ReadTimeResult:
    # Быстрый режим: оцениваем по первой странице/количеству страниц без надбавок
    try:
        first_text = doc[0].get_text("text") or ""
    except Exception:
        first_text = ""
    page_count = int(getattr(doc, "page_count", len(doc) if doc is not None else 0))  # type: ignore[arg-type]

    w1 = _count_words(first_text)

    # Эвристика как в ранней версии: clamp w1→words/page, затем умножаем
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    if page_count > 0 and w1 >= 30:
        wpp = int(_clamp(float(w1), 60.0, 900.0))
        total_words = wpp * page_count
    elif page_count > 0:
        # грубая оценка: 300 слов на страницу
        total_words = 300 * page_count
    else:
        total_words = max(w1, 300)

    eff_wpm = _effective_wpm(_base_wpm(lang), complexity_level)
    text_min = round(total_words / max(1, eff_wpm), 2)
    nontext_min = 0.0
    total_min = round(text_min + nontext_min, 2)

    breakdown = {
        "words": total_words,
        "effective_wpm": eff_wpm,
        "slides_s": 0,
        "images_s": 0,
        "tables_s": 0,
        "code_s": 0,
        "pages": {"text": 0, "mixed": 0, "slide": 0, "empty": 0},
    }
    return ReadTimeResult(total_min, text_min, nontext_min, breakdown)


def estimate_pdf_reading_time_minutes(
    path: str | Path | None = None,
    data: bytes | None = None,
    *,
    lang: str = "ru",
    complexity_level: Optional[LEVEL] = None,
    per_image_seconds: Tuple[int, int] | None = None,
) -> dict:
    """Определяет время чтения PDF и возвращает словарь с результатом и разбиением.

    Возвращает dict:
    {
      'total_min': float,
      'text_min': float,
      'nontext_min': float,
      'breakdown': {
        'words': int, 'effective_wpm': int,
        'slides_s': int, 'images_s': int, 'tables_s': int, 'code_s': int,
        'pages': {'text':int,'mixed':int,'slide':int,'empty':int}
      }
    }
    """
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF (pymupdf) is not installed; cannot estimate reading time"
        )
    if not path and data is None:
        raise ValueError("Provide either 'path' or 'data'")

    mode = os.getenv("PDF_MCP_READTIME_MODE", "accurate").lower().strip()
    max_pages_env = os.getenv("PDF_MCP_MAX_PAGES", "200")
    try:
        max_pages = int(max_pages_env)
    except Exception:
        max_pages = 200
    per_image_seconds = per_image_seconds or _parse_per_image_seconds(
        os.getenv("PDF_MCP_PER_IMAGE_SECONDS")
    )

    # Open document
    try:
        if data is not None:
            doc = fitz.open(stream=data, filetype="pdf")
        else:
            doc = fitz.open(str(path))
    except Exception as e:
        logger.debug("fitz.open failed: %s", e)
        raise

    try:
        # If too large and accurate requested, fallback to fast
        if mode == "accurate" and len(doc) > max_pages:
            logger.debug(
                "PDF_MCP_READTIME_MODE=accurate but pages=%s>max=%s → using fast fallback",
                len(doc),
                max_pages,
            )
            mode = "fast"

        if mode == "accurate":
            res = _accurate_estimate(
                doc=doc,
                lang=lang,
                complexity_level=complexity_level,
                per_image_seconds=per_image_seconds,
            )
        else:
            res = _fast_fallback(doc=doc, lang=lang, complexity_level=complexity_level)
    finally:
        try:
            doc.close()
        except Exception:
            pass

    logger.debug(
        "readtime mode=%s pages=%s words=%s text_min=%.2f nontext_min=%.2f total=%.2f breakdown=%s",
        mode,
        res.breakdown.get("pages"),
        res.breakdown.get("words"),
        res.text_min,
        res.nontext_min,
        res.total_min,
        json.dumps(res.breakdown, ensure_ascii=False),
    )

    return {
        "total_min": res.total_min,
        "text_min": res.text_min,
        "nontext_min": res.nontext_min,
        "breakdown": res.breakdown,
    }


__all__ = [
    "estimate_pdf_reading_time_minutes",
]
