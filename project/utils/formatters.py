import re
from typing import Any, List

from project.database.models import File


def format_analysis_card(file: File, include_url: bool = True) -> str:
    """Форматирование карточки анализа файла для отправки пользователю."""

    analysis = file.analysis_json
    title = file.title
    source_url = file.source_url

    volume = analysis.get("volume", {})
    complexity = analysis.get("complexity", {})

    page_count = volume.get("page_count") or "?"
    byte_size = volume.get("byte_size") or 0
    size_mb = byte_size / (1024 * 1024) if byte_size else 0
    word_count = volume.get("word_count", 0)
    reading_time = volume.get("reading_time_min", 0)

    complexity_level = complexity.get("level", "Неизвестно")

    tags_str = ", ".join(file.tags) if file.tags else "Без тегов"

    lines = [
        f'📄 "{title}"',
    ]

    if include_url and source_url:
        lines.append(source_url)
        lines.append("")

    if size_mb > 0:
        lines.append(
            f"Объём: {page_count} стр. ({size_mb:.1f} МБ) • "
            f"{word_count} слов ({reading_time:.0f} мин)"
        )
    else:
        lines.append(
            f"Объём: {page_count} стр. • " f"{word_count} слов ({reading_time:.0f} мин)"
        )

    lines.append(f"Сложность: {complexity_level}")
    lines.append(f"Темы: {tags_str}")

    return "\n".join(lines)


def extract_urls(text: str) -> List[str]:
    """Извлечение всех URL из текста."""

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)

    return list(set(urls))


def extract_tags_from_analysis(analysis_json: dict[str, Any]) -> List[str]:
    """Извлечение тегов из analysis_json (из topics)."""

    topics = analysis_json.get("topics", [])
    tags = []

    for topic in topics:
        label = topic.get("label")
        if label:
            tags.append(label)

    return tags


def format_multiple_files_summary(
    files: List[tuple[str, float, str, str]], total_time: float
) -> str:
    """
    Форматирование итогового сообщения при загрузке нескольких файлов.

    Args:
        files: список кортежей (url, reading_time_min, main_topic, complexity_level)
        total_time: общее время чтения в минутах
    """

    count = len(files)

    lines = [
        (
            f"✓ Добавлено {count} материала:"
            if count < 5
            else f"✓ Добавлено {count} материалов:"
        ),
        "",
    ]

    for idx, (url, time, topic, complexity) in enumerate(files, 1):
        domain = url.split("//")[-1].split("/")[0] if url else "unknown"
        lines.append(f"{idx}. {domain} ({time:.0f} мин, {complexity}) — {topic}")

    lines.append("")
    lines.append(f"Всего: {total_time:.0f} минут чтения")

    return "\n".join(lines)


def format_file_list_for_export(files: List[File], total_time: float) -> str:
    """
    Форматирование списка файлов для выгрузки (итоговое сообщение).

    Args:
        files: список файлов File
        total_time: общее время чтения в минутах
    """

    count = len(files)

    return (
        f"✅ Отправлено {count} материала ({total_time:.0f} минут чтения)"
        if count < 5
        else f"✅ Отправлено {count} материалов ({total_time:.0f} минут чтения)"
    )
