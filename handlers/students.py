"""Etajlar, bolalar ro'yxati, qo'shish, tahrirlash, qidirish."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import cb
import views
from db import Database
from handlers.helpers import show
from states import AddStates, EditStates, FloorStates, SearchStates
from utils import clean_room, esc, floor_name, money, parse_amount, parse_student_line

router = Router(name="students")


# ---------------- navigatsiya ----------------
@router.callback_query(cb.Menu.filter(F.a == "noop"))
async def cb_noop(cq: CallbackQuery) -> None:
    await cq.answer()


@router.callback_query(cb.Menu.filter(F.a == "pay"))
async def cb_pay_floors(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.floor_picker(db))


@router.callback_query(cb.Menu.filter(F.a == "students"))
async def cb_students(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.students_menu(db))


@router.callback_query(cb.FloorCB.filter())
async def cb_floor(cq: CallbackQuery, callback_data: cb.FloorCB, db: Database) -> None:
    await show(cq, views.floor_view(db, callback_data.id, callback_data.p))


@router.callback_query(cb.CardCB.filter())
async def cb_card(cq: CallbackQuery, callback_data: cb.CardCB, db: Database) -> None:
    await show(cq, views.card(db, callback_data.id))


@router.callback_query(cb.Menu.filter(F.a == "inactive"))
async def cb_inactive(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.inactive_list(db))


# ---------------- qidirish ----------------
@router.callback_query(cb.Menu.filter(F.a == "search"))
async def cb_search(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchStates.query)
    await show(cq, views.search_prompt())


@router.message(SearchStates.query, F.text)
async def search_query(message: Message, db: Database) -> None:
    # Holat saqlanadi — keyingi yozilgan ism ham qidiriladi.
    text, kb = views.search_results(db, message.text.strip()[:50])
    await message.answer(text, reply_markup=kb)


# ---------------- bola qo'shish ----------------
@router.callback_query(cb.Menu.filter(F.a == "add"))
async def cb_add(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.add_pick_floor(db))


@router.callback_query(cb.AddToCB.filter())
async def cb_add_to(cq: CallbackQuery, callback_data: cb.AddToCB, state: FSMContext, db: Database) -> None:
    f = db.get_floor(callback_data.f)
    if not f:
        await show(cq, views.students_menu(db), toast="Etaj topilmadi")
        return
    await state.set_state(AddStates.names)
    await state.update_data(floor_id=f["id"])
    await show(cq, views.add_prompt(f["name"], f["id"]))


@router.message(AddStates.names, F.text)
async def add_names(message: Message, state: FSMContext, db: Database) -> None:
    floor_id = (await state.get_data()).get("floor_id")
    f = db.get_floor(floor_id) if floor_id else None
    if not f:
        await state.clear()
        await message.answer("Etaj topilmadi. Qaytadan boshlang.")
        return
    added, bad = [], []
    for raw in message.text.splitlines():
        if not raw.strip():
            continue
        parsed = parse_student_line(raw)
        if not parsed:
            bad.append(raw.strip())
            continue
        name, room = parsed
        dup = db.same_name_exists(f["id"], name)
        db.add_student(name, f["id"], room)
        label = esc(name) + (f" ({esc(room)})" if room else "")
        if dup:
            label += " ⚠️ <i>shu ism avval ham bor edi</i>"
        added.append(label)
    if not added:
        await message.answer("❗ Ism topilmadi. Ism-familiyani harflar bilan yozing, masalan: <code>Aliyev Vali</code>")
        return
    await state.clear()
    lines = [f"✅ <b>{esc(f['name'])}</b> ga {len(added)} ta bola qo'shildi:"]
    lines += [f"• {x}" for x in added[:60]]
    if bad:
        lines.append(f"\n⚠️ Tushunilmagan qatorlar ({len(bad)}): " + ", ".join(esc(b) for b in bad[:10]))
    kb = InlineKeyboardBuilder()
    kb.row(views.B("➕ Yana qo'shish", cb.AddToCB(f=f["id"])),
           views.B(f"🏢 {f['name']} ro'yxati", cb.FloorCB(id=f["id"])))
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


# ---------------- tahrirlash ----------------
PROMPTS = {
    "name": "✏️ Yangi ism-familiyani yozing:",
    "room": "🚪 Xona raqamini yozing.\nO'chirish uchun <code>-</code> yuboring.",
    "phone": "📞 Telefon raqamini yozing.\nO'chirish uchun <code>-</code> yuboring.",
    "debt": (
        "📒 Bot ishlatilishidan <b>oldingi</b> (daftardagi) qarzini yozing.\n"
        "Qarzi yo'q bo'lsa <code>0</code>.\n"
        "Oldindan to'lab qo'ygan bo'lsa minus bilan: <code>-90000</code>"
    ),
}
FIELD = {"name": "full_name", "room": "room", "phone": "phone", "debt": "opening_debt"}


@router.callback_query(cb.StuCB.filter(F.a == "edit"))
async def cb_edit(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    await show(cq, views.edit_menu(db, callback_data.id))


@router.callback_query(cb.StuCB.filter(F.a.in_(set(PROMPTS))))
async def cb_edit_field(cq: CallbackQuery, callback_data: cb.StuCB, state: FSMContext, db: Database) -> None:
    s = db.get_student(callback_data.id)
    if not s:
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    await state.set_state(EditStates.value)
    await state.update_data(sid=s["id"], field=callback_data.a)
    current = s[FIELD[callback_data.a]]
    cur_text = ""
    if callback_data.a == "debt":
        cur_text = f"\n\nHozir: {money(current or 0)}"
    elif current:
        cur_text = f"\n\nHozir: <code>{esc(current)}</code>"
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Bekor qilish", cb.StuCB(a="edit", id=s["id"])))
    await show(cq, (f"⚙️ <b>{esc(s['full_name'])}</b>\n\n{PROMPTS[callback_data.a]}{cur_text}", kb.as_markup()))


@router.message(EditStates.value, F.text)
async def edit_value(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    sid, field = data.get("sid"), data.get("field")
    if not sid or not db.get_student(sid):
        await state.clear()
        await message.answer("Bola topilmadi.")
        return
    t = message.text.strip()
    if field == "name":
        name = " ".join(t.split())
        if not (2 <= len(name) <= 64):
            await message.answer("❗ Ism 2–64 belgi bo'lishi kerak. Qaytadan yozing:")
            return
        db.update_student(sid, full_name=name)
    elif field in ("room", "phone"):
        value = None if t in ("-", "—", "–") else t[:32]
        if field == "room" and value:
            value = clean_room(value)
        db.update_student(sid, **{field: value})
    elif field == "debt":
        negative = t.startswith("-")
        body = t.lstrip("-–— ").strip()
        if body in ("0", ""):
            value = 0
        else:
            value = parse_amount(body)
            if value is None:
                await message.answer("❗ Summani tushunmadim. Masalan: <code>180000</code> yoki <code>0</code>")
                return
        db.update_student(sid, opening_debt=-value if negative else value)
    await state.clear()
    text, kb = views.card(db, sid, note="✅ Saqlandi")
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.StuCB.filter(F.a == "floor"))
async def cb_move_pick(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    await show(cq, views.move_picker(db, callback_data.id))


@router.callback_query(cb.MoveCB.filter())
async def cb_move(cq: CallbackQuery, callback_data: cb.MoveCB, db: Database) -> None:
    f = db.get_floor(callback_data.f)
    if not f or not db.get_student(callback_data.id):
        await cq.answer("Topilmadi", show_alert=True)
        return
    db.update_student(callback_data.id, floor_id=f["id"])
    await show(cq, views.card(db, callback_data.id, note=f"✅ {esc(f['name'])} ga ko'chirildi"))


@router.callback_query(cb.StuCB.filter(F.a == "leave"))
async def cb_leave(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    await show(cq, views.leave_confirm(db, callback_data.id))


@router.callback_query(cb.StuCB.filter(F.a == "leave_ok"))
async def cb_leave_ok(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    s = db.get_student(callback_data.id)
    if not s:
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    db.deactivate_student(s["id"])
    note = f"🚶 <b>{esc(s['full_name'])}</b> ro'yxatdan chiqarildi."
    await show(cq, views.floor_view(db, s["floor_id"], note=note))


@router.callback_query(cb.StuCB.filter(F.a == "return"))
async def cb_return(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    if not db.get_student(callback_data.id):
        await cq.answer("Bola topilmadi", show_alert=True)
        return
    db.reactivate_student(callback_data.id)
    await show(cq, views.card(db, callback_data.id, note="↩️ Qaytib keldi — yana ro'yxatda."))


@router.callback_query(cb.StuCB.filter(F.a == "del"))
async def cb_delete(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    if db.student_payment_count(callback_data.id):
        await cq.answer(
            "Bu bolaning to'lovlari bor — o'chirib bo'lmaydi (hisobot buziladi). "
            "U «Chiqib ketganlar» ro'yxatida qolaveradi.",
            show_alert=True,
        )
        return
    await show(cq, views.delete_confirm(db, callback_data.id))


@router.callback_query(cb.StuCB.filter(F.a == "del_ok"))
async def cb_delete_ok(cq: CallbackQuery, callback_data: cb.StuCB, db: Database) -> None:
    s = db.get_student(callback_data.id)
    if not s or not db.delete_student(s["id"]):
        await cq.answer("O'chirib bo'lmadi", show_alert=True)
        return
    await show(cq, views.inactive_list(db, note=f"🗑 {esc(s['full_name'])} o'chirildi."))


# ---------------- etajlarni sozlash ----------------
@router.callback_query(cb.Menu.filter(F.a == "floors"))
async def cb_floors(cq: CallbackQuery, db: Database) -> None:
    await show(cq, views.floors_admin(db))


@router.callback_query(cb.FloorAdmCB.filter(F.a == "add"))
async def cb_floor_add(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FloorStates.add)
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Bekor qilish", cb.Menu(a="floors")))
    text = (
        "🏢 Etaj nomini yozing.\n\n"
        "Bir nechtasini birdaniga qo'shish mumkin — har birini yangi qatordan:\n"
        "<code>1-etaj\n2-etaj\n3-etaj</code>\n\n"
        "Faqat raqam yozsangiz ham bo'ladi: <code>1</code> → «1-etaj»"
    )
    await show(cq, (text, kb.as_markup()))


@router.message(FloorStates.add, F.text)
async def floor_add(message: Message, state: FSMContext, db: Database) -> None:
    added, exists = [], []
    for raw in message.text.splitlines():
        name = floor_name(raw)
        if not name:
            continue
        (added if db.add_floor(name) else exists).append(esc(name))
    await state.clear()
    note = ""
    if added:
        note += "✅ Qo'shildi: " + ", ".join(added)
    if exists:
        note += ("\n" if note else "") + "⚠️ Avvaldan bor: " + ", ".join(exists)
    text, kb = views.floors_admin(db, note=note or None)
    if added:
        text += "\n\nEndi bolalarni qo'shing: 👥 Bolalar → ➕ Bola qo'shish"
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.FloorAdmCB.filter(F.a == "ren"))
async def cb_floor_rename(cq: CallbackQuery, callback_data: cb.FloorAdmCB, state: FSMContext, db: Database) -> None:
    f = db.get_floor(callback_data.id)
    if not f:
        await cq.answer("Etaj topilmadi", show_alert=True)
        return
    await state.set_state(FloorStates.rename)
    await state.update_data(floor_id=f["id"])
    kb = InlineKeyboardBuilder()
    kb.row(views.B("⬅️ Bekor qilish", cb.Menu(a="floors")))
    await show(cq, (f"✏️ <b>{esc(f['name'])}</b> uchun yangi nom yozing:", kb.as_markup()))


@router.message(FloorStates.rename, F.text)
async def floor_rename(message: Message, state: FSMContext, db: Database) -> None:
    fid = (await state.get_data()).get("floor_id")
    name = floor_name(message.text)
    if not name:
        await message.answer("❗ Nom bo'sh bo'lmasin.")
        return
    if not db.rename_floor(fid, name):
        await message.answer("❗ Bunday nomli etaj bor. Boshqa nom yozing:")
        return
    await state.clear()
    text, kb = views.floors_admin(db, note=f"✅ Nomi o'zgardi: {esc(name)}")
    await message.answer(text, reply_markup=kb)


@router.callback_query(cb.FloorAdmCB.filter(F.a == "del"))
async def cb_floor_delete(cq: CallbackQuery, callback_data: cb.FloorAdmCB, db: Database) -> None:
    f = db.get_floor(callback_data.id)
    if not f:
        await cq.answer("Etaj topilmadi", show_alert=True)
        return
    if db.floor_student_total(f["id"]):
        await cq.answer(
            "Bu etajda bolalar bor (yoki bo'lgan). Avval ularni boshqa etajga ko'chiring.",
            show_alert=True,
        )
        return
    kb = InlineKeyboardBuilder()
    kb.row(views.B("🗑 Ha, o'chirish", cb.FloorAdmCB(a="del_ok", id=f["id"])),
           views.B("❌ Yo'q", cb.Menu(a="floors")))
    await show(cq, (f"🗑 <b>{esc(f['name'])}</b> o'chirilsinmi?", kb.as_markup()))


@router.callback_query(cb.FloorAdmCB.filter(F.a == "del_ok"))
async def cb_floor_delete_ok(cq: CallbackQuery, callback_data: cb.FloorAdmCB, db: Database) -> None:
    f = db.get_floor(callback_data.id)
    if not f or not db.delete_floor(f["id"]):
        await cq.answer("O'chirib bo'lmadi", show_alert=True)
        return
    await show(cq, views.floors_admin(db, note=f"🗑 {esc(f['name'])} o'chirildi."))
