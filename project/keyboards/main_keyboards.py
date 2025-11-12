from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup

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
