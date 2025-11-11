from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup

menu = [[InlineKeyboardButton(text="Мой аккаунт", callback_data="account")]]

main_kb = [
    [KeyboardButton(text="👤 Мой аккаунт"), KeyboardButton(text="⭐️ Баланс")],
    [KeyboardButton(text="🎭 Настройки"), KeyboardButton(text="📌 Инфо")],
]
main = ReplyKeyboardMarkup(
    keyboard=main_kb,
    resize_keyboard=True,
    input_field_placeholder="Напишите сюда что-нибудь...",
)
