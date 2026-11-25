"""Xarajat (bozorlik) yozish va o'chirish."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import cb
import views
from db import Database
from handlers.helpers import show
from states import ExpStates
from utils import esc, money, parse_amount

router = Router(name="expenses")


@router.callback_query(cb.Menu.filter(F.a == "exp"))
async def cb_exp_menu(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.expense_menu(db))


@router.callback_query(cb.ExpCatCB.filter())
async def cb_category(cq: CallbackQuery, callback_data: cb.ExpCatCB, state: FSMContext) -> None:
    if not 0 <= callback_data.i < len(views.EXPENSE_CATEGORIES):
        await cq.answer()
        return
    category = views.EXPENSE_CATEGORIES[callback_data.i]
    await state.set_state(ExpStates.amount)
    await state.update_data(category=category)
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Orqaga", cb.Menu(a="exp")))
    text = (
        f"🛒 <b>{esc(category)}</b>\n\n"
        "💵 Qancha pul ketdi? Summani yozing:\n"
        "<i>masalan: 350000, 350 000 yoki 350k</i>"
    )
    await show(cq, (text, kb.as_markup()))


@router.message(ExpStates.amount, F.text)
async def exp_amount(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if not amount:
        await message.answer("❗ Summani tushunmadim. Faqat raqam yozing, masalan: <code>350000</code>")
        return
    await state.update_data(amount=amount)
    await state.set_state(ExpStates.desc)
    category = (await state.get_data())["category"]
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⏭ Izohsiz saqlash", cb.ExpCB(a="skip")))
    await message.answer(
        f"🛒 {esc(category)} — <b>{money(amount)}</b>\n\n"
        "📝 Nima olindi? Qisqacha yozing:\n<i>masalan: 10 kg guruch, 5 kg mol go'shti</i>",
        reply_markup=kb.as_markup(),
    )


async def _save(state: FSMContext, db: Database, user_id: int, desc: str | None) -> int | None:
    data = await state.get_data()
    await state.clear()
    if "category" not in data or "amount" not in data:
        return None
    return db.add_expense(data["category"], data["amount"], desc, user_id)


@router.message(ExpStates.desc, F.text)
async def exp_desc(message: Message, state: FSMContext, db: Database) -> None:
    eid = await _save(state, db, message.from_user.id, message.text.strip()[:200])
    if eid is None:
        await message.answer("Xatolik: qaytadan boshlang (🛒 Xarajat qo'shish).")
        return
    text, kb = views.expense_saved(db, eid)
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.ExpCB.filter(F.a == "skip"), ExpStates.desc)
async def cb_skip(cq: CallbackQuery, state: FSMContext, db: Database) -> None:
    eid = await _save(state, db, cq.from_user.id, None)
    if eid is None:
        await cq.answer("Qaytadan boshlang", show_alert=True)
        return
    await show(cq, views.expense_saved(db, eid), toast="✅ Saqlandi")


@router.callback_query(cb.ExpCB.filter(F.a == "recent"))
async def cb_recent(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.recent_expenses(db))


@router.callback_query(cb.ExpCB.filter(F.a == "del"))
async def cb_delete(cq: CallbackQuery, callback_data: cb.ExpCB, db: Database) -> None:
    view = views.expense_delete_confirm(db, callback_data.id)
    if not view:
        await cq.answer("Allaqachon o'chirilgan", show_alert=True)
        return
    await show(cq, view)


@router.callback_query(cb.ExpCB.filter(F.a == "del_ok"))
async def cb_delete_ok(cq: CallbackQuery, callback_data: cb.ExpCB, db: Database) -> None:
    row = db.delete_expense(callback_data.id)
    if not row:
        await cq.answer("Allaqachon o'chirilgan", show_alert=True)
        return
    note = f"↩️ O'chirildi: {esc(row['category'])} — {money(row['amount'])}"
    await show(cq, views.recent_expenses(db, note=note), toast="O'chirildi")
