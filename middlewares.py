"""Faqat adminlarga ruxsat + tugma bosilganda yarim qolgan amalni bekor qilish."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from db import Database


class AdminOnly(BaseMiddleware):
    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return None
        if self.db.is_admin(user.id):
            return await handler(event, data)
        if self.db.admin_count() == 0:
            # Hali admin yo'q — botga birinchi yozgan odam bosh admin bo'ladi.
            self.db.add_admin(user.id, user.full_name)
            data["just_became_admin"] = True
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(
                "⛔ Bu bot faqat oshxona mas'ullari uchun.\n\n"
                f"Sizning Telegram ID: <code>{user.id}</code>\n"
                "Botdan foydalanish uchun shu raqamni adminga yuboring."
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Ruxsat yo'q", show_alert=True)
        return None


class ClearStateOnButton(BaseMiddleware):
    """Inline tugma bosilsa, kutilayotgan matn kiritish bekor bo'ladi.

    Istisno: amalning davomi bo'lgan tugmalar (xarajatni izohsiz saqlash,
    yangi summa qachondan boshlanishi).
    """
    KEEP = ("ex:skip", "st:fee_now", "st:fee_next")

    async def __call__(self, handler, event: CallbackQuery, data: dict[str, Any]) -> Any:
        state = data.get("state")
        if state is not None and not (event.data or "").startswith(self.KEEP):
            await state.clear()
        return await handler(event, data)
