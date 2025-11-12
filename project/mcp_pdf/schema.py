from __future__ import annotations

PDF_MCP_SYSTEM_PROMPT = (
    "PDF-MCP (объём → сложность → тематика → категория)\n\n"
    "Роль: ты — аккуратный анализатор текстов PDF. Твоя задача — по предоставленному содержимому документа определить его объём, общую сложность текста, тематику и категорию, и вернуть строго валидный JSON.\n\n"
    "Соблюдай схему и правила вывода из ТЗ. Не используй Markdown, возвращай только один JSON-объект.\n\n"
    "Важно для категории: используй краткие, стандартизированные названия категорий. Избегай длинных описательных фраз в label категории."
)


ANALYSIS_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "doc_language": {"type": "string"},
        "volume": {
            "type": "object",
            "properties": {
                "word_count": {"type": "integer"},
                "char_count": {"type": "integer"},
                "page_count": {"type": ["integer", "null"]},
                "byte_size": {"type": ["integer", "null"]},
                "reading_time_min": {"type": "number"},
                "method": {
                    "type": "object",
                    "properties": {
                        "word_count": {"type": "string"},
                        "char_count": {"type": "string"},
                    },
                    "required": ["word_count", "char_count"],
                },
            },
            "required": [
                "word_count",
                "char_count",
                "page_count",
                "byte_size",
                "reading_time_min",
                "method",
            ],
        },
        "complexity": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "level": {"type": "string"},
                "estimated_grade": {"type": "string"},
                "drivers": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["score", "level", "estimated_grade", "drivers", "notes"],
        },
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "score": {"type": "number"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "score", "keywords", "rationale"],
            },
            "maxItems": 6,
        },
        "category": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "score": {"type": "number"},
                "basis": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "score", "basis", "keywords"],
        },
        "limitations": {
            "type": "object",
            "properties": {
                "short_or_noisy_input": {"type": "boolean"},
                "comments": {"type": "string"},
            },
            "required": ["short_or_noisy_input", "comments"],
        },
    },
    "required": ["doc_language", "volume", "complexity", "topics", "category", "limitations"],
}


def build_user_prompt(text: str, meta: dict) -> str:
    toc = meta.get("toc_preview")
    source_name = meta.get("source_name")
    parts = [
        "Входные данные для анализа PDF.",
        "Важно: TEXT — это только первая страница документа (для экономии контекста).",
        "Оцени объём/время чтения по META; если есть precomputed_word_count — используй его как основной источник истины.",
        "Не придумывай page_count/byte_size — используй значения из META или null.",
        "Определи также категорию документа (category) по TEXT (первой странице), TOC (если дано) и/или SOURCE_NAME (имя файла/последний сегмент URL).",
        "Верни поле category: {label, score, basis, keywords}.",
        "",
        "SOURCE_NAME: " + (str(source_name) if source_name else "<none>"),
        "TEXT (первая страница, может быть обрезан):\n" + text[:20000],
    ]
    if toc:
        parts.append("TOC PREVIEW (оглавление/заголовки, усечено):\n" + str(toc)[:2000])
    parts.append("\nMETA (JSON):\n" + str(meta))
    return "\n".join(parts)


# ------------------ Категоризация: отдельная схема и промпт -----------------

CATEGORY_DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["matched_existing", "created_new"]},
        "category": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "score": {"type": "number"},
                "basis": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "score", "basis", "keywords"],
        },
        "existing_label": {"type": ["string", "null"]},
        "new_category_def": {
            "type": ["object", "null"],
            "properties": {
                "label": {"type": "string"},
                "description": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "examples": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "description", "keywords"],
        },
    },
    "required": ["decision", "category"],
}


def build_category_prompt(text: str, meta: dict, existing_categories: list[dict] | None) -> str:
    toc = meta.get("toc_preview")
    source_name = meta.get("source_name")
    desc_existing = "\n".join(
        f"- {e.get('label')}: {e.get('description','')} | keywords={e.get('keywords', [])}"
        for e in (existing_categories or [])
    ) or "<none>"
    parts = [
        "Задача: классифицировать документ по первой странице/названию/оглавлению в одну из уже предложенных категорий или создать новую категорию, если подходящей нет.",
        "Если подходящая категория найдена — верни decision=matched_existing, category.label=имя найденной категории и укажи basis (first_page|filename|toc|multi|unknown).",
        "Если подходящей нет — верни decision=created_new и опиши новую категорию в new_category_def (label, description, keywords).",
        "Всегда возвращай строго валидный JSON по схеме.",
        "",
        "EXISTING_CATEGORIES:",
        desc_existing,
        "",
        "SOURCE_NAME: " + (str(source_name) if source_name else "<none>"),
        "TEXT (первая страница):\n" + text[:20000],
    ]
    if toc:
        parts.append("TOC PREVIEW: \n" + str(toc)[:2000])
    return "\n".join(parts)
