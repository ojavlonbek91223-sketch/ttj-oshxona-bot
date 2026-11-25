"""Hisobotlar, qarzdorlar, Excel."""
from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

import cb
import views
from db import Database
from export import build_excel
from handlers.helpers import show
from utils import today

router = Router(name="reports")


@router.callback_query(cb.RepCB.filter(F.k == "w"))
async def cb_week(cq: CallbackQuery, callback_data: cb.RepCB, db: Database) -> None:
    await show(cq, views.week_report(db, callback_data.o))


@router.callback_query(cb.RepCB.filter(F.k == "m"))
async def cb_month(cq: CallbackQuery, callback_data: cb.RepCB, db: Database) -> None:
    await show(cq, views.month_report(db, callback_data.o))


@router.callback_query(cb.RepCB.filter(F.k == "kassa"))
async def cb_kassa(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.kassa(db))


@router.callback_query(cb.RepCB.filter(F.k == "debt"))
async def cb_debtors(cq: CallbackQuery, db: Database) -> None:
    await cq.answer()
    for part in views.debtors_texts(db):
        await cq.bot.send_message(cq.from_user.id, part)


@router.callback_query(cb.RepCB.filter(F.k == "xls"))
async def cb_excel(cq: CallbackQuery, db: Database) -> None:
    await cq.answer("⏳ Excel tayyorlanmoqda...")
    data = build_excel(db)
    await cq.bot.send_document(
        cq.from_user.id,
        BufferedInputFile(data, filename=f"oshxona_hisobot_{today().isoformat()}.xlsx"),
        caption="📥 To'liq hisobot: bolalar, haftalik jadval, to'lovlar, xarajatlar.",
    )
