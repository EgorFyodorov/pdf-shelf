from __future__ import annotations

PDF_MCP_SYSTEM_PROMPT = (
    "PDF-MCP (объём → сложность → тематика → категория)\n\n"
    "Роль: ты — аккуратный анализатор текстов PDF. Твоя задача — по предоставленному содержимому документа определить его объём, общую сложность текста, тематику и категорию, и вернуть строго валидный JSON.\n\n"
    "Соблюдай схему и правила вывода из ТЗ. Не используй Markdown, возвращай только один JSON-объект."
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
    return (
        "Входные данные для анализа PDF.\n"
        "Важно: TEXT — это только первая страница документа (для экономии контекста).\n"
        "Оцени объём/время чтения по META; если есть precomputed_word_count — используй его как основной источник истины.\n"
        "Не придумывай page_count/byte_size — используй значения из META или null.\n"
        "Определи также категорию документа (category) по TEXT (первой странице) и/или по META.source_name (имя файла или последний сегмент URL).\n"
        "Верни поле category: {label, score, basis, keywords}.\n\n"
        "TEXT (первая страница, может быть обрезан):\n" + text[:20000] + "\n\n"
        "META (JSON):\n" + str(meta)
    )
