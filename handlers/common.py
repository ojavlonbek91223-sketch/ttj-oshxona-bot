"""/start, yordam va pastki menyu tugmalari.

Bu router birinchi ulanadi: menyu tugmasi har qanday holatda (masalan, summa
kutilayotganda ham) ishlaydi va boshlangan amalni bekor qiladi.
"""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import config
import views
from db import Database
from keyboards import (
    BTN_DEBTORS, BTN_EXP, BTN_PAY, BTN_REPORT, BTN_SETTINGS, BTN_STUDENTS, main_menu,
)

router = Router(name="common")

GUIDE = (
    "<b>Bot nima qiladi:</b>\n"
    "💵 <b>To'lov qabul qilish</b> — etaj → bola → «90 000 to'ladi»\n"
    "🛒 <b>Xarajat qo'shish</b> — bozorlikka ketgan pulni yozish\n"
    "📊 <b>Hisobot</b> — hafta/oy bo'yicha kirim-chiqim, kassa, Excel\n"
    "❗ <b>Qarzdorlar</b> — kim to'lamagan\n"
    "👥 <b>Bolalar</b> — etaj va bolalarni qo'shish, tahrirlash\n"
    "⚙️ <b>Sozlamalar</b> — haftalik summa, adminlar, zaxira nusxa\n\n"
    "<b>Belgilar:</b> ✅ to'lagan · 🟡 qisman · ❌ to'lamagan · 💤 bu hafta ozod\n\n"
    "<b>Boshlash:</b> 👥 Bolalar → 🏢 Etajlarni sozlash → etajlarni qo'shing → "
    "keyin har bir etajga bolalarni qo'shing.\n\n"
    "Har dushanba har bir bolaga haftalik to'lov qo'shiladi. "
    "Yakshanba kechqurun bot hisobot va zaxira faylni o'zi yuboradi."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database,
                    just_became_admin: bool = False) -> None:
    await state.clear()
    db.add_admin(message.from_user.id, message.from_user.full_name)  # ismni yangilab qo'yamiz
    text = "Assalomu alaykum! 👋\n<b>TTJ oshxona hisobi</b> botiga xush kelibsiz.\n\n" + GUIDE
    if just_became_admin:
        text += "\n\n👑 Siz birinchi foydalanuvchisiz — <b>bosh admin</b> qilib belgilandingiz."
    await message.answer(text, reply_markup=main_menu())
    if config.WEBAPP_URL.startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📱 Ilovani ochish", web_app=WebAppInfo(url=config.WEBAPP_URL))
        ]])
        await message.answer(
            "📱 Qulayroq ishlash uchun <b>ilovani</b> oching — jadval, qidiruv va hisobotlar bir joyda.\n"
            "Ilovani chat pastidagi <b>«📱 Ochish»</b> tugmasidan ham ochsa bo'ladi.",
            reply_markup=kb,
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(GUIDE, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi. Menyudan tanlang 👇", reply_markup=main_menu())


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Sizning Telegram ID: <code>{message.from_user.id}</code>")


@router.message(F.text == BTN_PAY)
async def m_pay(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = views.floor_picker(db)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_EXP)
async def m_exp(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = views.expense_menu(db)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_REPORT)
async def m_report(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = views.week_report(db)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_DEBTORS)
async def m_debtors(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    for part in views.debtors_texts(db):
        await message.answer(part)


@router.message(F.text == BTN_STUDENTS)
async def m_students(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = views.students_menu(db)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_SETTINGS)
async def m_settings(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = views.settings_view(db)
    await message.answer(text, reply_markup=kb)
