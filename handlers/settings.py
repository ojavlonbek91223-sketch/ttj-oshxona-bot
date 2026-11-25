"""Sozlamalar: haftalik summa, boshlang'ich kassa, adminlar, zaxira."""
from datetime import timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import cb
import views
from db import Database
from handlers.helpers import show
from states import SetStates
from utils import money, now, parse_amount, week_label, week_start

router = Router(name="settings")


def _back_kb():
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Bekor qilish", cb.SetCB(a="main")))
    return kb.as_markup()


@router.callback_query(cb.SetCB.filter(F.a == "main"))
async def cb_main(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.settings_view(db))


# ---------- haftalik to'lov ----------
@router.callback_query(cb.SetCB.filter(F.a == "fee"))
async def cb_fee(cq: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.set_state(SetStates.fee)
    text = (
        f"💵 Hozirgi haftalik to'lov: <b>{money(db.current_fee())}</b>\n\n"
        "Yangi summani yozing (masalan <code>100000</code>):"
    )
    await show(cq, (text, _back_kb()))


@router.message(SetStates.fee, F.text)
async def fee_amount(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if not amount:
        await message.answer("❗ Summani tushunmadim. Masalan: <code>100000</code>")
        return
    await state.update_data(fee=amount)
    await state.set_state(SetStates.fee_when)
    this_w = week_start()
    next_w = this_w + timedelta(days=7)
    kb = InlineKeyboardBuilder()
    kb.row(views.B(f"📅 Shu haftadan ({week_label(this_w)})", cb.SetCB(a="fee_now")))
    kb.row(views.B(f"⏭ Keyingi haftadan ({week_label(next_w)})", cb.SetCB(a="fee_next")))
    kb.row(views.B("⬅️ Bekor qilish", cb.SetCB(a="main")))
    await message.answer(
        f"💵 Yangi summa: <b>{money(amount)}</b>\nQachondan boshlab amal qilsin?\n\n"
        "<i>Oldingi haftalar eski summa bilan hisoblanaveradi.</i>",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(cb.SetCB.filter(F.a.in_({"fee_now", "fee_next"})), SetStates.fee_when)
async def cb_fee_when(cq: CallbackQuery, callback_data: cb.SetCB, state: FSMContext, db: Database) -> None:
    amount = (await state.get_data()).get("fee")
    await state.clear()
    if not amount:
        await cq.answer("Qaytadan boshlang", show_alert=True)
        return
    start = week_start() + (timedelta(days=7) if callback_data.a == "fee_next" else timedelta())
    db.set_fee(amount, start)
    note = f"✅ Haftalik to'lov {money(amount)} — {week_label(start)} haftasidan boshlab."
    await show(cq, views.settings_view(db, note=note))


# ---------- boshlang'ich kassa ----------
@router.callback_query(cb.SetCB.filter(F.a == "cash"))
async def cb_cash(cq: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.set_state(SetStates.cash)
    text = (
        "📒 <b>Boshlang'ich kassa</b>\n\n"
        "Botni ishlata boshlagan paytda qo'lingizda (kassada) qancha pul bor edi? "
        "Daftardagi qoldiqni yozing. Bo'lmasa <code>0</code>.\n\n"
        f"Hozir: {money(db.opening_cash())}"
    )
    await show(cq, (text, _back_kb()))


@router.message(SetStates.cash, F.text)
async def cash_amount(message: Message, state: FSMContext, db: Database) -> None:
    t = message.text.strip()
    amount = 0 if t == "0" else parse_amount(t)
    if amount is None:
        await message.answer("❗ Summani tushunmadim. Masalan: <code>1500000</code> yoki <code>0</code>")
        return
    db.set_setting("opening_cash", amount)
    await state.clear()
    text, kb = views.settings_view(db, note=f"✅ Boshlang'ich kassa: {money(amount)}")
    await message.answer(text, reply_markup=kb)


# ---------- adminlar ----------
@router.callback_query(cb.SetCB.filter(F.a == "admins"))
async def cb_admins(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.admins_view(db, cq.from_user.id))


@router.callback_query(cb.SetCB.filter(F.a == "aadd"))
async def cb_admin_add(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetStates.admin)
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Bekor qilish", cb.SetCB(a="admins")))
    text = (
        "➕ Yangi adminning <b>Telegram ID</b> raqamini yozing.\n\n"
        "U odam botga /start yozsa, bot unga ID raqamini ko'rsatadi."
    )
    await show(cq, (text, kb.as_markup()))


@router.message(SetStates.admin, F.text)
async def admin_add(message: Message, state: FSMContext, db: Database) -> None:
    t = message.text.strip().replace(" ", "")
    if not t.isdigit() or not 5 <= len(t) <= 15:
        await message.answer("❗ ID faqat raqamlardan iborat bo'ladi, masalan: <code>123456789</code>")
        return
    db.add_admin(int(t))
    await state.clear()
    text, kb = views.admins_view(
        db, message.from_user.id,
        note=f"✅ <code>{t}</code> admin qilindi. Endi u botga /start yozsin.",
    )
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.SetCB.filter(F.a == "adel"))
async def cb_admin_del(cq: CallbackQuery, callback_data: cb.SetCB) -> None:
    if callback_data.id == cq.from_user.id:
        await cq.answer("O'zingizni o'chira olmaysiz", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.row(views.B("🗑 Ha, o'chirish", cb.SetCB(a="adel_ok", id=callback_data.id)),
           views.B("❌ Yo'q", cb.SetCB(a="admins")))
    await show(cq, (f"<code>{callback_data.id}</code> adminlikdan olinsinmi?", kb.as_markup()))


@router.callback_query(cb.SetCB.filter(F.a == "adel_ok"))
async def cb_admin_del_ok(cq: CallbackQuery, callback_data: cb.SetCB, db: Database) -> None:
    if callback_data.id == cq.from_user.id:
        await cq.answer("O'zingizni o'chira olmaysiz", show_alert=True)
        return
    db.remove_admin(callback_data.id)
    await show(cq, views.admins_view(db, cq.from_user.id, note=f"🗑 <code>{callback_data.id}</code> o'chirildi."))


# ---------- zaxira ----------
@router.callback_query(cb.SetCB.filter(F.a == "backup"))
async def cb_backup(cq: CallbackQuery, db: Database) -> None:
    await cq.answer("⏳ Tayyorlanmoqda...")
    stamp = now().strftime("%Y-%m-%d_%H-%M")
    await cq.bot.send_document(
        cq.from_user.id,
        BufferedInputFile(db.backup_bytes(), filename=f"oshxona_backup_{stamp}.{db.backup_ext}"),
        caption=(
            "💾 Ma'lumotlar bazasining to'liq nusxasi.\n"
            "Saqlab qo'ying. Kompyuter buzilsa, shu fayldan hammasini tiklash mumkin "
            "(README dagi «Ma'lumotlar xavfsizligi» bo'limi)."
        ),
    )
