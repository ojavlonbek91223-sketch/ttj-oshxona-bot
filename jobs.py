"""Yakshanba kechqurun adminlarga avtomatik hisobot + Excel + zaxira nusxa.

Bazaga faqat yakshanba kechqurun murojaat qilinadi — bepul Postgres (Neon)
qolgan vaqtda "uxlay" olsin. Har daqiqada bo'sh turgan ulanish yopiladi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile

import config
import views
from db import Database
from export import build_excel
from utils import now, today, week_start

log = logging.getLogger(__name__)


async def send_weekly_report(bot: Bot, db: Database) -> None:
    text, _ = views.week_report(db, 0)
    xls = build_excel(db)
    backup = db.backup_bytes()
    stamp = today().isoformat()
    for admin in db.list_admins():
        chat = admin["tg_id"]
        try:
            await bot.send_message(chat, "🗓 <b>Hafta yakuni — avtomatik hisobot</b>\n\n" + text)
            await bot.send_document(
                chat, BufferedInputFile(xls, f"oshxona_hisobot_{stamp}.xlsx"), caption="📥 Excel hisobot"
            )
            await bot.send_document(
                chat, BufferedInputFile(backup, f"oshxona_backup_{stamp}.{db.backup_ext}"),
                caption="💾 Zaxira nusxa — saqlab qo'ying",
            )
        except Exception as e:  # admin botni bloklagan yoki hali /start yozmagan
            log.warning("Hisobotni %s ga yuborib bo'lmadi: %s", chat, e)


async def weekly_report_loop(bot: Bot, db: Database) -> None:
    sent_for: str | None = None  # shu jarayonda yuborilgan hafta (bazaga ortiqcha murojaat qilmaslik uchun)
    while True:
        try:
            n = now()
            key = week_start().isoformat()
            if n.weekday() == 6 and n.hour >= config.WEEKLY_REPORT_HOUR and sent_for != key:
                if db.get_setting("last_auto_report") != key:
                    await send_weekly_report(bot, db)
                    db.set_setting("last_auto_report", key)
                sent_for = key
            db.close_if_idle()
        except Exception:
            log.exception("Haftalik hisobotda xato")
        await asyncio.sleep(60)
