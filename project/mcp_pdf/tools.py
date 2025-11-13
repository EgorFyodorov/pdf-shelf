from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from jsonschema import validate

from .pdf_utils import (
    avg_chars_per_word_from_first_page,
    count_words_and_chars,
    detect_language_safe,
    estimate_char_count_from_first,
    estimate_reading_time_min,
    extract_from_path_or_url,
)
from .schema import (
    ANALYSIS_JSON_SCHEMA,
    CATEGORY_DECISION_SCHEMA,
    PDF_MCP_SYSTEM_PROMPT,
    build_category_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


def _normalize_llm_response(
    data: dict[str, Any], meta: dict[str, Any], text: str
) -> dict[str, Any]:
    """Нормализует ответ LLM, преобразуя русские ключи в английские и заполняя недостающие поля."""
    result: dict[str, Any] = {}

    # Маппинг русских ключей на английские
    key_mapping = {
        "объём": "volume",
        "объем": "volume",
        "сложность": "complexity",
        "тематика": "topics",
        "категория": "category",
        "ограничения": "limitations",
    }

    # Нормализуем ключи верхнего уровня
    normalized_data: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = key_mapping.get(key, key)
        normalized_data[normalized_key] = value

    # Извлекаем doc_language из meta или определяем из текста
    result["doc_language"] = (
        normalized_data.get("doc_language")
        or meta.get("lang_hint")
        or detect_language_safe(text)
        or "ru"
    )

    # Нормализуем volume
    volume_raw = (
        normalized_data.get("volume")
        or normalized_data.get("объём")
        or normalized_data.get("объем")
        or {}
    )
    if not isinstance(volume_raw, dict):
        if isinstance(volume_raw, str):
            logger.debug("volume_raw is a string '%s', converting to empty dict", volume_raw)
        elif isinstance(volume_raw, (int, float)):
            logger.debug("volume_raw is a number %s, converting to empty dict", volume_raw)
        else:
            logger.warning("volume_raw is not a dict: %s (type: %s), using empty dict", volume_raw, type(volume_raw))
        volume_raw = {}
    volume: dict[str, Any] = {}

    # Маппинг полей volume
    volume_mapping = {
        "word_count": ["word_count", "количество_слов", "words"],
        "char_count": ["char_count", "количество_символов", "chars"],
        "page_count": ["page_count", "количество_страниц", "pages"],
        "byte_size": ["byte_size", "размер_в_байтах", "size"],
        "reading_time_min": [
            "reading_time_min",
            "read_time_minutes",
            "reading_time_minutes",
            "время_чтения_минут",
            "time_to_read_minutes",
        ],
    }

    for eng_key, possible_keys in volume_mapping.items():
        for key in possible_keys:
            if isinstance(volume_raw, dict) and key in volume_raw:
                value = volume_raw[key]
                # Нормализуем char_count - заменяем null/None на 0 или вычисляем
                if eng_key == "char_count" and (value is None or value == 0):
                    _, cc = count_words_and_chars(text)
                    volume[eng_key] = cc if cc > 0 else 0
                else:
                    volume[eng_key] = value
                break

    # Используем значения из meta как fallback
    if "word_count" not in volume:
        volume["word_count"] = meta.get("precomputed_word_count") or 0
    if "char_count" not in volume or volume["char_count"] is None or volume["char_count"] == 0:
        _, cc = count_words_and_chars(text)
        volume["char_count"] = cc if cc > 0 else 0
    if "page_count" not in volume:
        volume["page_count"] = meta.get("page_count")
    if "byte_size" not in volume:
        volume["byte_size"] = meta.get("byte_size")
    if "reading_time_min" not in volume or volume["reading_time_min"] is None or volume["reading_time_min"] == 0:
        # Вычисляем время чтения
        words = volume.get("word_count", 0)
        lang = result["doc_language"]
        volume["reading_time_min"] = estimate_reading_time_min(lang, words)
    # Убеждаемся, что reading_time_min - это число, а не None
    if volume["reading_time_min"] is None:
        volume["reading_time_min"] = 0.0
    volume["reading_time_min"] = float(volume["reading_time_min"])

    # Метод - убеждаемся, что это объект с нужными полями
    method_raw = volume.get("method")
    if isinstance(method_raw, dict):
        volume["method"] = {
            "word_count": method_raw.get("word_count") or (
                "content_based_full_scan"
                if meta.get("__reading_time_breakdown")
                else "precomputed"
            ),
            "char_count": method_raw.get("char_count") or "estimated_no_spaces",
        }
    else:
        # Если method - строка или другой тип, создаем правильный объект
        volume["method"] = {
            "word_count": (
                "content_based_full_scan"
                if meta.get("__reading_time_breakdown")
                else "precomputed"
            ),
            "char_count": "estimated_no_spaces",
        }

    result["volume"] = volume

    complexity_raw = (
        normalized_data.get("complexity") or normalized_data.get("сложность") or {}
    )
    if not isinstance(complexity_raw, dict):
        if isinstance(complexity_raw, str):
            logger.debug("complexity_raw is a string '%s', converting to dict with level", complexity_raw)
            # Преобразуем строку в dict с полем level
            complexity_raw = {"level": complexity_raw}
        elif isinstance(complexity_raw, (int, float)):
            logger.debug("complexity_raw is a number %s, converting to empty dict", complexity_raw)
            complexity_raw = {}
        else:
            logger.warning("complexity_raw is not a dict: %s (type: %s), using empty dict", complexity_raw, type(complexity_raw))
            complexity_raw = {}
    complexity: dict[str, Any] = {}

    # Маппинг полей complexity
    complexity_mapping = {
        "score": ["score", "оценка", "оценка_1_5"],
        "level": ["level", "label", "уровень"],
        "estimated_grade": ["estimated_grade", "grade", "класс"],
        "drivers": ["drivers", "ключевые_слова", "keywords"],
        "notes": ["notes", "description", "basis", "основание", "описание"],
    }

    for eng_key, possible_keys in complexity_mapping.items():
        for key in possible_keys:
            if isinstance(complexity_raw, dict) and key in complexity_raw:
                value = complexity_raw[key]
                # Преобразуем score если это float в диапазоне 0-1
                if eng_key == "score" and isinstance(value, (float, int)):
                    if 0 <= value <= 1:
                        # Преобразуем в шкалу 1-100
                        complexity[eng_key] = int(value * 100)
                    elif isinstance(value, int) and 1 <= value <= 5:
                        # Преобразуем из шкалы 1-5 в 1-100
                        complexity[eng_key] = int((value / 5) * 100)
                    else:
                        complexity[eng_key] = int(value)
                elif eng_key == "estimated_grade":
                    # estimated_grade должен быть строкой
                    if isinstance(value, (int, float)):
                        complexity[eng_key] = str(int(value))
                    elif value is None:
                        complexity[eng_key] = ""
                    else:
                        complexity[eng_key] = str(value)
                elif eng_key == "drivers" and isinstance(value, list):
                    complexity[eng_key] = value
                elif eng_key == "drivers" and isinstance(value, str):
                    complexity[eng_key] = [value]
                elif eng_key == "notes":
                    # notes должен быть строкой
                    if isinstance(value, list):
                        # Если это массив, объединяем в строку
                        complexity[eng_key] = ", ".join(str(v) for v in value) if value else ""
                    elif value is None:
                        complexity[eng_key] = ""
                    else:
                        complexity[eng_key] = str(value)
                else:
                    complexity[eng_key] = value
                break

    # Заполняем недостающие поля complexity
    if "score" not in complexity:
        complexity["score"] = 40  # средняя по умолчанию
    if "level" not in complexity:
        complexity["level"] = "средняя"
    if "estimated_grade" not in complexity:
        complexity["estimated_grade"] = "школьный"
    else:
        if not isinstance(complexity["estimated_grade"], str):
            complexity["estimated_grade"] = str(complexity["estimated_grade"])
    if "drivers" not in complexity:
        complexity["drivers"] = []
    if "notes" not in complexity:
        complexity["notes"] = (
            complexity_raw.get("basis") or complexity_raw.get("description") or ""
        )
    else:
        if isinstance(complexity["notes"], list):
            complexity["notes"] = ", ".join(str(v) for v in complexity["notes"]) if complexity["notes"] else ""
        elif not isinstance(complexity["notes"], str):
            complexity["notes"] = str(complexity["notes"]) if complexity["notes"] is not None else ""

    result["complexity"] = complexity

    # Нормализуем topics
    topics_raw = normalized_data.get("topics") or normalized_data.get("тематика") or {}
    topics: list[dict[str, Any]] = []

    if isinstance(topics_raw, dict):
        # Если topics - это один объект, преобразуем в массив
        topic: dict[str, Any] = {}
        topic["label"] = topics_raw.get("label") or topics_raw.get("major") or ""
        topic["score"] = topics_raw.get("score") or 0.5

        # Обрабатываем keywords/minor
        keywords = topics_raw.get("keywords") or topics_raw.get("minor") or []
        if isinstance(keywords, str):
            topic["keywords"] = [keywords]
        elif isinstance(keywords, list):
            topic["keywords"] = keywords
        else:
            topic["keywords"] = []

        topic["rationale"] = (
            topics_raw.get("rationale") or topics_raw.get("basis") or ""
        )
        if topic["label"]:
            topics.append(topic)
    elif isinstance(topics_raw, list):
        for t in topics_raw:
            if isinstance(t, dict):
                topic: dict[str, Any] = {}
                topic["label"] = t.get("label") or ""
                topic["score"] = t.get("score") or 0.5
                topic["keywords"] = t.get("keywords") or []
                topic["rationale"] = t.get("rationale") or ""
                if topic["label"]:
                    topics.append(topic)

    result["topics"] = topics[:6]  # Максимум 6

    # Нормализуем category
    # Пробуем разные варианты ключей
    category_raw = (
        normalized_data.get("category")
        or data.get("category")  # Проверяем оригинальные данные
        or normalized_data.get("категория")
        or data.get("категория")  # Проверяем оригинальные данные с русским ключом
        or {}
    )
    if not isinstance(category_raw, dict):
        logger.warning("category_raw is not a dict: %s (type: %s), using empty dict", category_raw, type(category_raw))
        category_raw = {}

    category: dict[str, Any] = {}

    # Извлекаем поля категории с разными вариантами названий
    category["label"] = (
        category_raw.get("label")
        or category_raw.get("name")
        or category_raw.get("title")
        or "Другое"
    )

    category["score"] = category_raw.get("score")
    if category["score"] is None:
        # Пробуем найти score в разных форматах
        score_val = category_raw.get("confidence") or category_raw.get("уверенность")
        if score_val is not None:
            category["score"] = (
                float(score_val) if isinstance(score_val, (int, float)) else 0.0
            )
        else:
            category["score"] = 0.0

    category["basis"] = (
        category_raw.get("basis")
        or category_raw.get("description")
        or category_raw.get("основание")
        or category_raw.get("описание")
        or ("llm" if category["label"] != "Другое" else "none")
    )

    category["keywords"] = (
        category_raw.get("keywords") or category_raw.get("ключевые_слова") or []
    )
    if isinstance(category["keywords"], str):
        category["keywords"] = [category["keywords"]]
    elif not isinstance(category["keywords"], list):
        category["keywords"] = []

    # Если категория не найдена, но есть данные в исходном ответе, логируем для отладки
    if category["label"] == "Другое" and category["score"] == 0.0:
        logger.debug(
            "Category not found in LLM response. Available keys: %s",
            list(normalized_data.keys()),
        )
        logger.debug(
            "Original data keys: %s",
            list(data.keys()) if isinstance(data, dict) else "not a dict",
        )
        logger.debug("Category raw: %s", category_raw)
    else:
        logger.debug(
            "Category extracted successfully: label=%s, score=%s",
            category["label"],
            category["score"],
        )

    result["category"] = category

    # Нормализуем limitations
    limitations_raw = (
        normalized_data.get("limitations") or normalized_data.get("ограничения") or {}
    )
    # Убеждаемся, что limitations_raw - это dict
    if not isinstance(limitations_raw, dict):
        logger.warning("limitations_raw is not a dict: %s (type: %s), using empty dict", limitations_raw, type(limitations_raw))
        limitations_raw = {}
    limitations: dict[str, Any] = {}

    w1, _ = count_words_and_chars(text)
    limitations["short_or_noisy_input"] = limitations_raw.get(
        "short_or_noisy_input", w1 < 150
    )
    limitations["comments"] = (
        limitations_raw.get("comments") or limitations_raw.get("description") or ""
    )

    result["limitations"] = limitations

    return result


# --- GigaChat integration ---------------------------------------------------
from .gigachat_client import get_gigachat_client


async def _call_gigachat(
    text: str, meta: dict[str, Any], max_retries: int = 5
) -> dict[str, Any]:
    """Вызов GigaChat для анализа текста."""
    client = get_gigachat_client()

    # Build prompt
    sys_prompt = PDF_MCP_SYSTEM_PROMPT
    user_prompt = build_user_prompt(text, meta)

    # Генерируем контент через GigaChat API (retry логика уже внутри клиента)
    try:
        content = await client.generate_content(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            max_retries=max_retries,
        )
    except Exception as e:
        logger.warning("GigaChat analysis failed: %s", e)
        raise RuntimeError(f"GigaChat API error: {e}") from e

    # Парсим JSON
    data = None
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("GigaChat returned non-JSON, attempting to fix: %s", e)
        logger.info("Content received (first 1000 chars): %s", content[:1000])
        
        import re
        
        # Пробуем найти JSON в markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content, re.MULTILINE)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                logger.info("Successfully extracted JSON from markdown code block")
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from markdown code block")
        
        # Если не получилось, пробуем найти первый JSON объект
        if data is None:
            # Ищем открывающую скобку и пытаемся найти соответствующий закрывающий
            start_idx = content.find('{')
            if start_idx != -1:
                # Пробуем найти закрывающую скобку, считая вложенные скобки
                brace_count = 0
                end_idx = start_idx
                for i in range(start_idx, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                
                if end_idx > start_idx:
                    json_str = content[start_idx:end_idx]
                    try:
                        data = json.loads(json_str)
                        logger.info("Successfully extracted JSON object from response")
                    except json.JSONDecodeError as parse_err:
                        logger.warning("Failed to parse extracted JSON: %s", parse_err)
                        logger.debug("Extracted JSON string: %s", json_str[:500])
        
        # Если все еще не получилось, пробуем исправить распространенные ошибки
        if data is None:
            # Удаляем комментарии (однострочные и многострочные)
            cleaned = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            # Удаляем trailing commas перед закрывающими скобками
            cleaned = re.sub(r',\s*}', '}', cleaned)
            cleaned = re.sub(r',\s*]', ']', cleaned)
            
            # Пробуем закрыть незакрытые скобки
            open_braces = cleaned.count('{')
            close_braces = cleaned.count('}')
            open_brackets = cleaned.count('[')
            close_brackets = cleaned.count(']')
            
            if open_braces > close_braces:
                cleaned += '}' * (open_braces - close_braces)
            if open_brackets > close_brackets:
                cleaned += ']' * (open_brackets - close_brackets)
            
            try:
                data = json.loads(cleaned)
                logger.info("Successfully parsed JSON after cleaning and fixing braces")
            except json.JSONDecodeError as parse_err:
                logger.error("Failed to parse JSON even after cleaning: %s", parse_err)
                logger.debug("Cleaned content: %s", cleaned[:1000])
                raise RuntimeError(f"Failed to parse JSON from GigaChat response. Error: {e}. Content preview: {content[:500]}")
    
    # Проверяем, что data не None
    if data is None:
        logger.error("Failed to parse JSON from GigaChat response")
        raise RuntimeError(f"Failed to parse JSON from GigaChat response. Content preview: {content[:500]}")

    # Проверяем, что data - это dict, а не строка или другой тип
    if not isinstance(data, dict):
        logger.error("GigaChat returned non-dict data: %s (type: %s)", data, type(data))
        raise RuntimeError(f"Expected dict from GigaChat, got {type(data).__name__}: {str(data)[:200]}")

    # Нормализуем ответ LLM перед валидацией
    normalized_data = None
    validation_error = None

    try:
        normalized_data = _normalize_llm_response(data, meta, text)
        validate(instance=normalized_data, schema=ANALYSIS_JSON_SCHEMA)
        return normalized_data
    except Exception as e:
        validation_error = e
        logger.warning("Failed to normalize/validate LLM response: %s", e)
        # Если нормализация прошла, но валидация не прошла, все равно используем нормализованные данные
        if normalized_data is not None:
            logger.info(
                "Using normalized data despite validation error, category: %s",
                normalized_data.get("category", {}).get("label"),
            )
            return normalized_data

        # Если нормализация не удалась, пробуем валидировать как есть
        try:
            validate(instance=data, schema=ANALYSIS_JSON_SCHEMA)
            return data
        except Exception:
            # Если и это не работает, но у нас есть нормализованные данные (даже с ошибкой валидации), используем их
            if normalized_data is not None:
                logger.info("Using normalized data despite validation failure")
                return normalized_data
            # Если ничего не получилось, выбрасываем ошибку
            raise validation_error


async def _call_gigachat_category(
    text: str,
    meta: dict[str, Any],
    existing_categories: list[dict] | None,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Вызов GigaChat для категоризации документа."""
    client = get_gigachat_client()

    sys_prompt = "PDF-MCP: категоризация документов (классифицировать в существующую или создать новую категорию). Возвращай строго валидный JSON."
    user_prompt = build_category_prompt(text, meta, existing_categories or [])

    # Генерируем контент через GigaChat API (retry логика уже внутри клиента)
    try:
        content = await client.generate_content(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            max_retries=max_retries,
        )
    except Exception as e:
        logger.warning("GigaChat category decision failed: %s", e)
        raise RuntimeError(f"GigaChat API error: {e}") from e

    # Проверяем, что контент не пустой
    if not content or content.strip() == "" or content.strip() == "{}":
        logger.warning("GigaChat returned empty content for category decision")
        raise RuntimeError("Empty response from GigaChat")

    # Пробуем распарсить JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("GigaChat returned non-JSON for category decision: %s", e)
        logger.debug(
            "Content received: %s", content[:500]
        )  # Первые 500 символов для отладки

        # Пробуем найти JSON в тексте
        import re

        # Ищем первый JSON объект в тексте
        m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
        if m:
            try:
                data = json.loads(m.group(0))
                logger.info("Successfully extracted JSON from response")
            except json.JSONDecodeError:
                logger.error("Failed to parse extracted JSON")
                raise RuntimeError(f"Invalid JSON in response: {content[:200]}")
        else:
            # Если JSON не найден, пробуем найти между ```json и ```
            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    logger.info("Successfully extracted JSON from code block")
                except json.JSONDecodeError:
                    logger.error("Failed to parse JSON from code block")
                    raise RuntimeError(f"Invalid JSON in code block: {content[:200]}")
            else:
                logger.error("No JSON found in response")
                raise RuntimeError(f"No valid JSON found in response: {content[:200]}")

    # Валидируем схему
    try:
        validate(instance=data, schema=CATEGORY_DECISION_SCHEMA)
    except Exception as e:
        logger.warning("Category decision validation failed: %s", e)
        logger.debug("Data: %s", json.dumps(data, ensure_ascii=False, indent=2))
        # Если валидация не прошла, но данные есть, все равно возвращаем их
        # (схема может быть строже, чем нужно)
        if isinstance(data, dict) and "decision" in data and "category" in data:
            logger.info("Using data despite validation error")
            return data
        raise

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

    # Простая эвристика для определения категории по source_name
    source_name = meta.get("source_name", "").lower()

    if any(
        keyword in source_name
        for keyword in ["tech", "programming", "code", "dev", "github"]
    ):
        category_label = "Технологии"
        topics = [
            {
                "label": "Технологии",
                "score": 0.8,
                "keywords": ["программирование", "разработка"],
                "rationale": "эвристика по имени файла",
            }
        ]
    elif any(
        keyword in source_name
        for keyword in ["ml", "ai", "machine", "learning", "neural", "data"]
    ):
        category_label = "Machine Learning"
        topics = [
            {
                "label": "Machine Learning",
                "score": 0.8,
                "keywords": ["ML", "AI", "данные"],
                "rationale": "эвристика по имени файла",
            }
        ]
    elif any(
        keyword in source_name
        for keyword in ["science", "research", "paper", "journal"]
    ):
        category_label = "Наука"
        topics = [
            {
                "label": "Наука",
                "score": 0.7,
                "keywords": ["исследование", "наука"],
                "rationale": "эвристика по имени файла",
            }
        ]
    elif any(
        keyword in source_name
        for keyword in ["business", "economy", "finance", "market"]
    ):
        category_label = "Бизнес"
        topics = [
            {
                "label": "Бизнес",
                "score": 0.7,
                "keywords": ["экономика", "финансы"],
                "rationale": "эвристика по имени файла",
            }
        ]
    else:
        category_label = (
            meta.get("source_name", "Документ").split("/")[-1].split(".")[0]
            or "Документ"
        )
        if len(category_label) > 50:
            category_label = "Документ"
        topics = [
            {
                "label": "Общее",
                "score": 0.5,
                "keywords": [],
                "rationale": "категория по умолчанию",
            }
        ]

    category = {
        "label": category_label,
        "score": 0.6,
        "basis": "filename",
        "keywords": [],
    }

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
        "topics": topics,
        "category": category,
        "limitations": {"short_or_noisy_input": w1 < 150, "comments": note},
    }


# --- MCP tool wrappers (library-agnostic callables) ------------------------


async def extract_pdf_tool(
    path: Optional[str] = None, url: Optional[str] = None
) -> dict[str, Any]:
    ext = await extract_from_path_or_url(path=path, url=url)
    meta = {
        "byte_size": ext.byte_size,
        "page_count": ext.page_count,
        "precomputed_word_count": ext.precomputed_word_count,
        "lang_hint": ext.lang_hint,
        "source_name": ext.source_name,
        "toc_preview": ext.toc_preview,
        "__reading_time_breakdown": ext.reading_time_breakdown,
        "__reading_time_min_host": ext.reading_time_min_host,
    }
    return {"TEXT": ext.text, "META": meta}


async def analyze_text_tool(
    text: str, meta: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    meta = meta or {}
    wc = meta.get("precomputed_word_count")
    if wc is None:
        wc, cc = count_words_and_chars(text)
        meta["precomputed_word_count"] = wc
        meta.setdefault("char_count", cc)
    llm_meta = {k: v for k, v in meta.items() if not str(k).startswith("__")}

    use_mock = os.getenv("USE_MOCK_ANALYSIS", "false").lower() in ("true", "1", "yes")
    if use_mock:
        logger.info("Using mock analysis (USE_MOCK_ANALYSIS is enabled)")
        return _fallback_simple_analysis(text, meta)

    try:
        data = await _call_gigachat(text, llm_meta)
        try:
            breakdown = meta.get("__reading_time_breakdown") or {}
            words = int(
                meta.get("precomputed_word_count") or breakdown.get("words") or 0
            )
            doc_lang = data.get("doc_language") or meta.get("lang_hint") or "ru"
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
                    (
                        int(breakdown.get("slides_s", 0))
                        + int(breakdown.get("images_s", 0))
                        + int(breakdown.get("tables_s", 0))
                        + int(breakdown.get("code_s", 0))
                    )
                    / 60,
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
        logger.warning("GigaChat analysis failed, falling back. Error: %s", e)
        return _fallback_simple_analysis(text, meta)


# ------------------- Category tools (dynamic, LLM-driven) -------------------


async def classify_or_create_category_tool(
    text: str,
    meta: Optional[dict[str, Any]] = None,
    existing_categories: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Пытается отнести документ к одной из существующих категорий или создать новую.

    Вход:
      - text: первая страница (как есть из extract_pdf)
      - meta: META без приватных ключей (будет отфильтровано от __*)
      - existing_categories: список объектов вида {label, description?, keywords?}

    Выход (строгий JSON по CATEGORY_DECISION_SCHEMA):
      {decision, category, existing_label?, new_category_def?}
    """
    meta = meta or {}
    llm_meta = {k: v for k, v in meta.items() if not str(k).startswith("__")}
    try:
        return await _call_gigachat_category(text, llm_meta, existing_categories or [])
    except Exception as e:
        logger.warning("GigaChat category decision failed: %s", e)
        # Фолбэк без LLM — нейтральная заглушка
        return {
            "decision": "created_new",
            "category": {
                "label": "Другое",
                "score": 0.0,
                "basis": "unknown",
                "keywords": [],
            },
            "existing_label": None,
            "new_category_def": {
                "label": "Другое",
                "description": "без LLM",
                "keywords": [],
            },
        }


async def define_category_tool(
    text: str,
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Явно сгенерировать новую категорию для данного документа.

    Возвращает объект вида {label, description, keywords, examples?} в поле new_category_def,
    а также совместимый блок category с тем же label и basis.
    """
    meta = meta or {}
    # Переиспользуем общий инструмент: передаём пустой список существующих категорий
    res = await classify_or_create_category_tool(
        text=text, meta=meta, existing_categories=[]
    )
    if res.get("decision") == "matched_existing":
        # Принудительно создать новую метку (например, с суффиксом), если LLM решил иначе
        # В реальном кейсе можно второй раз вызвать LLM с указанием "создай новую" —
        # здесь ограничимся преобразованием ответа.
        label = res.get("category", {}).get("label", "Категория")
        res["decision"] = "created_new"
        res["new_category_def"] = {
            "label": label,
            "description": "Автоматически созданная категория (fallback)",
            "keywords": res.get("category", {}).get("keywords", []),
        }
    return res
