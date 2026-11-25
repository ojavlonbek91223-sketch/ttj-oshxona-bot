"""Pastki asosiy menyu."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_PAY = "💵 To'lov qabul qilish"
BTN_EXP = "🛒 Xarajat qo'shish"
BTN_REPORT = "📊 Hisobot"
BTN_DEBTORS = "❗ Qarzdorlar"
BTN_STUDENTS = "👥 Bolalar"
BTN_SETTINGS = "⚙️ Sozlamalar"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PAY), KeyboardButton(text=BTN_EXP)],
            [KeyboardButton(text=BTN_REPORT), KeyboardButton(text=BTN_DEBTORS)],
            [KeyboardButton(text=BTN_STUDENTS), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
