from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

menu = [[InlineKeyboardButton(text="Мой аккаунт", callback_data="account")]]

main_kb = [
    [
        KeyboardButton(text="📚 Моя библиотека"),
        KeyboardButton(text="📤 Выгрузить материалы"),
    ],
    [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="❓ Помощь")],
]
main = ReplyKeyboardMarkup(
    keyboard=main_kb,
    resize_keyboard=True,
    input_field_placeholder="Отправьте PDF или URL...",
)

time_selection_kb = [
    [KeyboardButton(text="15 минут"), KeyboardButton(text="30 минут")],
    [KeyboardButton(text="1 час"), KeyboardButton(text="2 часа")],
]
time_selection = ReplyKeyboardMarkup(
    keyboard=time_selection_kb,
    resize_keyboard=True,
    one_time_keyboard=True,
    input_field_placeholder="Выберите время или напишите свое...",
)


def create_tags_keyboard(tags: list[str]) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с доступными тематиками."""
    keyboard = []

    # Добавляем кнопку "Все темы"
    keyboard.append([KeyboardButton(text="📚 Все темы")])

    # Добавляем теги по 2 в ряд
    row = []
    for tag in sorted(tags):
        row.append(KeyboardButton(text=f"🏷 {tag}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []

    # Добавляем оставшиеся теги
    if row:
        keyboard.append(row)

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите тему...",
    )


def create_pagination_keyboard(
    page: int, total_pages: int, prefix: str = "page"
) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру с кнопками пагинации.
    
    Args:
        page: Текущая страница (начинается с 0)
        total_pages: Общее количество страниц
        prefix: Префикс для callback_data
    
    Returns:
        InlineKeyboardMarkup с кнопками навигации
    """
    buttons = []
    
    if total_pages <= 1:
        return None
    
    # Кнопки навигации
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}:{page-1}")
        )
    
    # Показываем текущую страницу
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"· {page + 1}/{total_pages} ·", callback_data="noop"
        )
    )
    
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{prefix}:{page+1}")
        )
    
    buttons.append(nav_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
