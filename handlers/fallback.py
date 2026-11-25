"""Hech bir handler mos kelmasa (eng oxirida ulanadi)."""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import main_menu

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await message.answer("❗ Iltimos, matn ko'rinishida yozing yoki pastdagi menyudan tanlang.")
        return
    await message.answer("Quyidagi menyudan tanlang 👇", reply_markup=main_menu())


@router.callback_query()
async def stale_button(cq: CallbackQuery) -> None:
    await cq.answer("Bu tugma eskirgan. Pastdagi menyudan qaytadan tanlang.", show_alert=True)
