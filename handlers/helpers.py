"""Handlerlar uchun umumiy yordamchilar."""
from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from views import View


async def show(cq: CallbackQuery, view: View, toast: str | None = None, alert: bool = False) -> None:
    """Inline xabarni yangi ekran bilan almashtirish (iloji bo'lmasa — yangi xabar)."""
    text, kb = view
    try:
        await cq.answer(toast, show_alert=alert)
    except TelegramBadRequest:
        pass
    if isinstance(cq.message, Message) and cq.message.text is not None:
        try:
            await cq.message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
            logging.debug("edit failed, sending new message: %s", e)
    await cq.bot.send_message(cq.from_user.id, text, reply_markup=kb)
