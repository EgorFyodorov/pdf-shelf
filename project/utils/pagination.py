"""Утилиты для пагинации списков файлов."""

from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from project.database.models import File


def translate_complexity(level: str) -> str:
    """Переводит уровень сложности на русский язык."""
    mapping = {
        "low": "низкая",
        "medium": "средняя",
        "high": "высокая",
        "very high": "очень высокая",
    }
    return mapping.get(level.lower(), level)


def format_files_page(
    files: List[File], page: int = 0, page_size: int = 10, header: str = ""
) -> tuple[str, int]:
    """
    Форматирует страницу со списком файлов.
    
    Args:
        files: Список всех файлов
        page: Номер страницы (начинается с 0)
        page_size: Количество файлов на странице
        header: Заголовок сообщения
    
    Returns:
        Tuple[отформатированный текст, общее количество страниц]
    """
    total_files = len(files)
    total_pages = (total_files + page_size - 1) // page_size
    
    # Проверяем валидность страницы
    if page < 0:
        page = 0
    if page >= total_pages and total_pages > 0:
        page = total_pages - 1
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_files)
    
    page_files = files[start_idx:end_idx]
    
    response = header
    
    for idx, file in enumerate(page_files, start=start_idx + 1):
        tags_str = ", ".join(file.tags) if file.tags else "Без тегов"
        complexity_level = translate_complexity(
            file.analysis_json.get("complexity", {}).get("level", "средняя")
        )
        
        response += f"{idx}. 📄 {file.title}\n"
        response += f"   ⏱ {float(file.reading_time_min):.0f} мин • 📊 {complexity_level} • 🏷 {tags_str}\n"
        
        if file.source_url:
            url_display = (
                file.source_url[:50] + "..."
                if len(file.source_url) > 50
                else file.source_url
            )
            response += f"   🔗 {url_display}\n"
        
        response += "\n"

    return response, total_pages


def create_pagination_keyboard(
    current_page: int, total_pages: int, prefix: str = "page"
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками пагинации.
    
    Args:
        current_page: Текущая страница (начинается с 0)
        total_pages: Общее количество страниц
        prefix: Префикс для callback_data (например, "lib_page" или "exp_page")
    
    Returns:
        InlineKeyboardMarkup с кнопками навигации
    """
    if total_pages <= 1:
        return None
    
    buttons = []
    
    # Кнопка "Назад"
    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад", callback_data=f"{prefix}:{current_page - 1}"
            )
        )
    
    # Индикатор страницы
    buttons.append(
        InlineKeyboardButton(
            text=f"{current_page + 1}/{total_pages}", callback_data="noop"
        )
    )
    
    # Кнопка "Вперед"
    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️", callback_data=f"{prefix}:{current_page + 1}"
            )
        )
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

