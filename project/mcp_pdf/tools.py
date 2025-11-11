from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from jsonschema import validate

from .pdf_utils import (
    count_words_and_chars,
    detect_language_safe,
    estimate_reading_time_min,
    extract_from_path_or_url,
    avg_chars_per_word_from_first_page,
    estimate_char_count_from_first,
)
from .schema import ANALYSIS_JSON_SCHEMA, PDF_MCP_SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


# --- Gemini integration (google-genai) -------------------------------------
try:
    # New official client
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    genai = None  # type: ignore


async def _call_gemini(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        raise RuntimeError("Gemini is not configured or google-genai is missing")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # Build prompt
    sys_prompt = PDF_MCP_SYSTEM_PROMPT
    user_prompt = build_user_prompt(text, meta)

    # google-genai client is synchronous; wrap in a thread for async compatibility
    import asyncio

    def _generate_sync() -> str:
        client = genai.Client(api_key=api_key)
        # Try the modern `responses.generate` signature first
        try:
            resp = client.responses.generate(
                model=model_name,
                system_instruction=sys_prompt,
                input=user_prompt,
            )
        except TypeError:
            # Fallback to "contents" param variant
            resp = client.responses.generate(
                model=model_name,
                system_instruction=sys_prompt,
                contents=user_prompt,
            )
        # Extract text robustly across versions
        content = getattr(resp, "output_text", None)
        if not content:
            content = getattr(resp, "text", None)
        if not content:
            try:
                data = resp.to_dict()  # type: ignore[attr-defined]
                content = (
                    data.get("output_text")
                    or data.get("text")
                    or json.dumps(data, ensure_ascii=False)
                )
            except Exception:
                content = "{}"
        return content or "{}"

    content = await asyncio.to_thread(_generate_sync)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("Gemini returned non-JSON, attempting to fix: %s", e)
        # naive repair: locate first JSON object
        import re

        m = re.search(r"\{[\s\S]*\}$", content)
        if not m:
            raise
        data = json.loads(m.group(0))
    validate(instance=data, schema=ANALYSIS_JSON_SCHEMA)
    return data


def _fallback_simple_analysis(text: str, meta: dict[str, Any]) -> dict[str, Any]:
    # TEXT — это первая страница (по умолчанию), META содержит оценку total_words
    w1, _ = count_words_and_chars(text)
    # Используем контент-основанные метрики, если есть
    breakdown = meta.get("__reading_time_breakdown")
    if isinstance(breakdown, dict) and isinstance(breakdown.get("words"), int):
        total_words = int(breakdown.get("words", 0))
        reading = round(float(meta.get("__reading_time_min_host") or 0.0), 2)
        method_wc = "content_based_full_scan"
    else:
        total_words = int(meta.get("precomputed_word_count") or w1)
        lang_tmp = meta.get("lang_hint") or detect_language_safe(text) or "ru"
        reading = estimate_reading_time_min(lang_tmp, total_words)
        method_wc = "precomputed"
    lang = meta.get("lang_hint") or detect_language_safe(text) or "ru"

    # Оценка char_count по первой странице
    avg_cpw = avg_chars_per_word_from_first_page(text, w1)
    cc_est = estimate_char_count_from_first(avg_cpw, total_words)
    # very rough complexity
    if w1 < 150:
        score, level, grade, note = 15, "низкая", "школьный", "мало текста"
    else:
        score, level, grade, note = 40, "средняя", "школьный", "эвристика без LLM"

    # Категория без эвристик: ставим нейтральную заглушку при отсутствии LLM
    category = {"label": "Другое", "score": 0.0, "basis": "none", "keywords": []}

    return {
        "doc_language": lang,
        "volume": {
            "word_count": total_words,
            "char_count": cc_est,
            "page_count": meta.get("page_count"),
            "byte_size": meta.get("byte_size"),
            "reading_time_min": reading,
            "method": {"word_count": method_wc, "char_count": "estimated_no_spaces"},
        },
        "complexity": {
            "score": score,
            "level": level,
            "estimated_grade": grade,
            "drivers": ["эвристическая оценка"],
            "notes": note,
        },
        "topics": [],
        "category": category,
        "limitations": {"short_or_noisy_input": w1 < 150, "comments": note},
    }


# --- MCP tool wrappers (library-agnostic callables) ------------------------


async def extract_pdf_tool(path: Optional[str] = None, url: Optional[str] = None) -> dict[str, Any]:
    ext = await extract_from_path_or_url(path=path, url=url)
    meta = {
        "byte_size": ext.byte_size,
        "page_count": ext.page_count,
        "precomputed_word_count": ext.precomputed_word_count,
        "lang_hint": ext.lang_hint,
        "source_name": ext.source_name,
        "__reading_time_breakdown": ext.reading_time_breakdown,
        "__reading_time_min_host": ext.reading_time_min_host,
    }
    return {"TEXT": ext.text, "META": meta}


async def analyze_text_tool(text: str, meta: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    meta = meta or {}
    wc = meta.get("precomputed_word_count")
    if wc is None:
        wc, cc = count_words_and_chars(text)
        meta["precomputed_word_count"] = wc
        meta.setdefault("char_count", cc)
    llm_meta = {k: v for k, v in meta.items() if not str(k).startswith("__")}
    try:
        data = await _call_gemini(text, llm_meta)
        try:
            breakdown = meta.get("__reading_time_breakdown") or {}
            words = int(meta.get("precomputed_word_count") or breakdown.get("words") or 0)
            doc_lang = (data.get("doc_language") or meta.get("lang_hint") or "ru")
            level = None
            try:
                level = data.get("complexity", {}).get("level")
            except Exception:
                level = None

            base = 200 if str(doc_lang).lower().startswith("en") else 180
            kmap = {
                "очень низкая": 1.10,
                "низкая": 1.00,
                "средняя": 0.85,
                "высокая": 0.70,
                "очень высокая": 0.55,
            }
            eff = max(60, int(base * kmap.get(level or "средняя", 0.85)))
            t_text = round(words / max(1, eff), 2)
            if breakdown:
                t_nontext = round(
                    (int(breakdown.get("slides_s", 0)) + int(breakdown.get("images_s", 0)) + int(breakdown.get("tables_s", 0)) + int(breakdown.get("code_s", 0))) / 60,
                    2,
                )
            else:
                t_nontext = 0.0
            reading_total = round(t_text + t_nontext, 1)
            vol = data.get("volume", {})
            vol["reading_time_min"] = reading_total
            vol["word_count"] = int(words) if words else vol.get("word_count")
            method = vol.get("method", {})
            method["word_count"] = "content_based_full_scan"
            vol["method"] = method
            data["volume"] = vol
        except Exception as e:
            logger.debug("Postprocess reading time failed: %s", e)
        return data
    except Exception as e:
        logger.warning("Gemini analysis failed, falling back. Error: %s", e)
        return _fallback_simple_analysis(text, meta)
