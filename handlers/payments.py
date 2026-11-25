"""To'lov yozish, boshqa summa, ozod qilish, tarix va to'lovni o'chirish."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import cb
import views
from db import Database
from handlers.helpers import show
from states import PayStates
from utils import esc, money, num, parse_amount, week_start

router = Router(name="payments")


def _after_payment(db: Database, sid: int, amount: int, pid: int) -> views.View:
    s = db.get_student(sid)
    b = db.balances([sid])[sid]
    tail = "qarzi yo'q ✅" if b.debt <= 0 else f"qolgan qarz: {money(b.debt)}"
    note = f"✅ <b>{esc(s['full_name'])}</b> — {money(amount)} qabul qilindi ({tail})"
    if s["active"]:
        return views.floor_view(db, s["floor_id"], note=note, undo_pid=pid, focus_sid=sid)
    return views.card(db, sid, note=note)


@router.callback_query(cb.PayCB.filter())
async def cb_pay(cq: CallbackQuery, callback_data: cb.PayCB, db: Database) -> None:
    s = db.get_student(callback_data.id)
    amount = callback_data.amt
    if not s or amount <= 0:
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    if db.recent_duplicate(s["id"], amount):
        await cq.answer("Bu to'lov hozirgina yozildi ✅", show_alert=True)
        return
    pid = db.add_payment(s["id"], amount, cq.from_user.id)
    await show(cq, _after_payment(db, s["id"], amount, pid), toast=f"✅ {num(amount)} so'm yozildi")


@router.callback_query(cb.StuCB.filter(F.a == "custom"))
async def cb_custom(cq: CallbackQuery, callback_data: cb.StuCB, state: FSMContext, db: Database) -> None:
    s = db.get_student(callback_data.id)
    if not s:
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    await state.set_state(PayStates.amount)
    await state.update_data(sid=s["id"])
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Orqaga", cb.CardCB(id=s["id"])))
    text = (
        f"✍️ <b>{esc(s['full_name'])}</b> qancha to'ladi?\n\n"
        "Summani yozing, masalan: <code>45000</code>, <code>45 000</code> yoki <code>45k</code>"
    )
    await show(cq, (text, kb.as_markup()))


@router.message(PayStates.amount, F.text)
async def custom_amount(message: Message, state: FSMContext, db: Database) -> None:
    amount = parse_amount(message.text)
    if not amount:
        await message.answer("❗ Summani tushunmadim. Faqat raqam yozing, masalan: <code>90000</code>")
        return
    sid = (await state.get_data()).get("sid")
    await state.clear()
    if not sid or not db.get_student(sid):
        await message.answer("Bola topilmadi. Qaytadan tanlang.")
        return
    pid = db.add_payment(sid, amount, message.from_user.id)
    text, kb = _after_payment(db, sid, amount, pid)
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.StuCB.filter(F.a == "exempt"))
async def cb_exempt(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    sid = callback_data.id
    if not db.get_student(sid):
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    now_exempt = db.toggle_exemption(sid, week_start())
    note = ("💤 Bu hafta ozod qilindi — haftalik to'lov hisoblanmaydi."
            if now_exempt else "↩️ Ozodlik bekor qilindi — bu hafta to'lov hisoblanadi.")
    await show(cq, views.card(db, sid, note=note))


@router.callback_query(cb.StuCB.filter(F.a == "hist"))
async def cb_history(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    await show(cq, views.history(db, callback_data.id))


@router.callback_query(cb.PayDelCB.filter())
async def cb_pay_delete(cq: CallbackQuery, callback_data: cb.PayDelCB, db: Database) -> None:
    pid = callback_data.id
    if not callback_data.ok:
        view = views.pay_delete_confirm(db, pid)
        if not view:
            await cq.answer("Bu to'lov allaqachon o'chirilgan", show_alert=True)
            return
        await show(cq, view)
        return
    row = db.delete_payment(pid)
    if not row:
        await cq.answer("Bu to'lov allaqachon o'chirilgan", show_alert=True)
        return
    note = f"↩️ Bekor qilindi: <b>{esc(row['full_name'])}</b> — {money(row['amount'])}"
    if callback_data.back and row["active"]:
        view = views.floor_view(db, row["floor_id"], note=note, focus_sid=row["student_id"])
    else:
        view = views.history(db, row["student_id"], note=note)
    await show(cq, view, toast="O'chirildi")
