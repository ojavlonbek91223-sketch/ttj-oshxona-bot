"""Ekranlar: har bir funksiya (matn, inline tugmalar) qaytaradi."""
from __future__ import annotations

from datetime import date, timedelta
from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import cb
from db import Balance, Database
from utils import (
    add_months, chunk_lines, esc, fmt_date, fmt_dt, money, month_label, month_start,
    num, short_date, short_money, today, week_label, week_start,
)

View = tuple[str, InlineKeyboardMarkup]
PAGE_SIZE = 30
LINE = "━━━━━━━━━━━━━━"

EXPENSE_CATEGORIES = [
    "🥩 Go'sht",
    "🍚 Guruch, un, don",
    "🛢 Yog'",
    "🥕 Sabzavot, meva",
    "🍞 Non",
    "🧂 Ziravor, tuz, shakar",
    "🥛 Sut mahsulotlari",
    "🥚 Tuxum, tovuq",
    "🔥 Gaz, ko'mir, o'tin",
    "🧽 Xo'jalik buyumlari",
    "🚕 Yo'l kira",
    "📦 Boshqa",
]


def B(text: str, data: cb.CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def status_icon(b: Balance, fee: int) -> str:
    if b.debt <= 0:
        return "💤" if b.exempt_now else "✅"
    return "🟡" if b.debt < fee else "❌"


def debt_line(b: Balance, fee: int) -> str:
    if b.debt > 0:
        return f"{status_icon(b, fee)} <b>Qarz: {money(b.debt)}</b>"
    if b.debt < 0:
        return f"✅ <b>Qarzi yo'q</b> · oldindan to'lagan: {money(-b.debt)}"
    return "✅ <b>Qarzi yo'q</b>"


# =====================================================================
#  To'lov: etajlar -> etaj ro'yxati -> bola kartochkasi
# =====================================================================
def _floor_stats(db: Database) -> dict[int, tuple[int, int]]:
    bals = db.balances()
    stats: dict[int, tuple[int, int]] = {}
    for s in db.list_students():
        cnt, debtors = stats.get(s["floor_id"], (0, 0))
        stats[s["floor_id"]] = (cnt + 1, debtors + (bals[s["id"]].debt > 0))
    return stats


def floor_picker(db: Database) -> View:
    floors = db.list_floors()
    kb = InlineKeyboardBuilder()
    if not floors:
        kb.row(B("👥 Bolalar bo'limiga o'tish", cb.Menu(a="students")))
        return (
            "💵 <b>To'lov qabul qilish</b>\n\n"
            "Hali etaj va bolalar kiritilmagan.\n"
            "Avval <b>👥 Bolalar</b> bo'limida etaj va bolalarni qo'shing.",
            kb.as_markup(),
        )
    stats = _floor_stats(db)
    for f in floors:
        cnt, debtors = stats.get(f["id"], (0, 0))
        mark = f"❌ {debtors}" if debtors else ("✅" if cnt else "bo'sh")
        kb.row(B(f"🏢 {f['name']} — {cnt} ta · {mark}", cb.FloorCB(id=f["id"])))
    kb.row(B("🔍 Ism bo'yicha qidirish", cb.Menu(a="search")))
    text = (
        "💵 <b>To'lov qabul qilish</b>\n"
        f"📅 Hafta: {week_label(week_start())}\n"
        f"💵 Haftalik to'lov: {money(db.current_fee())}\n\n"
        "Etajni tanlang 👇"
    )
    return text, kb.as_markup()


def floor_view(db: Database, floor_id: int, page: int = 0, note: str | None = None,
               undo_pid: int | None = None, focus_sid: int | None = None) -> View:
    kb = InlineKeyboardBuilder()
    f = db.get_floor(floor_id)
    if not f:
        kb.row(B("⬅️ Etajlar", cb.Menu(a="pay")))
        return "Etaj topilmadi.", kb.as_markup()

    students = db.list_students(floor_id=floor_id)
    bals = db.balances([s["id"] for s in students])
    fee = db.current_fee()
    counts = {"✅": 0, "🟡": 0, "❌": 0, "💤": 0}
    icons: dict[int, str] = {}
    total_debt = 0
    for s in students:
        b = bals[s["id"]]
        icons[s["id"]] = ic = status_icon(b, fee)
        counts[ic] += 1
        total_debt += max(b.debt, 0)

    pages = max(1, ceil(len(students) / PAGE_SIZE))
    if focus_sid is not None:
        for i, s in enumerate(students):
            if s["id"] == focus_sid:
                page = i // PAGE_SIZE
                break
    page = min(max(page, 0), pages - 1)

    lines = [note, ""] if note else []
    lines.append(f"🏢 <b>{esc(f['name'])}</b> · {len(students)} ta bola")
    lines.append(f"📅 {week_label(week_start())} · 💵 {money(fee)}")
    if students:
        stat = f"✅ {counts['✅']} to'lagan · 🟡 {counts['🟡']} qisman · ❌ {counts['❌']} to'lamagan"
        if counts["💤"]:
            stat += f" · 💤 {counts['💤']} ozod"
        lines.append(stat)
        if total_debt:
            lines.append(f"💸 Etaj bo'yicha qarz: {money(total_debt)}")
        lines.append("\nBolani tanlang 👇")
    else:
        lines.append("\nBu etajda hali bola yo'q. Pastdagi tugma bilan qo'shing.")

    chunk = students[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    btns = [B(f"{icons[s['id']]} {s['full_name']}", cb.CardCB(id=s["id"])) for s in chunk]
    for i in range(0, len(btns), 2):
        kb.row(*btns[i:i + 2])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(B("◀️", cb.FloorCB(id=floor_id, p=page - 1)))
        nav.append(B(f"{page + 1}/{pages}", cb.Menu(a="noop")))
        if page < pages - 1:
            nav.append(B("▶️", cb.FloorCB(id=floor_id, p=page + 1)))
        kb.row(*nav)
    if undo_pid:
        kb.row(B("↩️ Oxirgi to'lovni bekor qilish", cb.PayDelCB(id=undo_pid, ok=1, back=1)))
    kb.row(B("➕ Bola qo'shish", cb.AddToCB(f=floor_id)), B("⬅️ Etajlar", cb.Menu(a="pay")))
    return "\n".join(lines), kb.as_markup()


def card(db: Database, sid: int, note: str | None = None) -> View:
    kb = InlineKeyboardBuilder()
    s = db.get_student(sid)
    if not s:
        kb.row(B("⬅️ Etajlar", cb.Menu(a="pay")))
        return "Bola topilmadi (o'chirilgan bo'lishi mumkin).", kb.as_markup()
    b = db.balances([sid])[sid]
    fee = db.current_fee()

    lines = [note, ""] if note else []
    lines.append(f"👤 <b>{esc(s['full_name'])}</b>")
    info = f"🏢 {esc(s['floor_name'])}"
    if s["room"]:
        info += f" · 🚪 {esc(s['room'])}-xona"
    lines.append(info)
    if s["phone"]:
        lines.append(f"📞 {esc(s['phone'])}")
    lines.append(LINE)
    if not s["active"]:
        left = week_label(date.fromisoformat(s["left_week"])) if s["left_week"] else ""
        lines.append(f"🚶 <b>Chiqib ketgan</b> ({left})")
    lines.append(debt_line(b, fee))
    if s["active"] and b.exempt_now:
        lines.append("💤 Bu hafta ozod — to'lov hisoblanmaydi")
    lines.append(f"💵 Bu hafta to'lagan: {money(b.paid_week)}")
    lines.append(f"🧾 Jami to'lagan: {money(b.paid)}")
    if s["opening_debt"]:
        lines.append(f"📒 Daftardagi eski qarz: {money(s['opening_debt'])}")
    lines.append(f"📅 Ro'yxatga olingan: {week_label(date.fromisoformat(s['joined_week']))} haftasi")

    if s["active"]:
        kb.row(B(f"✅ {num(fee)} to'ladi", cb.PayCB(id=sid, amt=fee)))
        if b.debt > 0 and b.debt != fee:
            kb.row(B(f"✅ Qarzini to'liq to'ladi: {num(b.debt)}", cb.PayCB(id=sid, amt=b.debt)))
        kb.row(
            B("✍️ Boshqa summa", cb.StuCB(a="custom", id=sid)),
            B("↩️ Ozodni bekor qilish" if b.exempt_now else "💤 Bu hafta ozod",
              cb.StuCB(a="exempt", id=sid)),
        )
        kb.row(B("📜 Tarix", cb.StuCB(a="hist", id=sid)), B("⚙️ Tahrirlash", cb.StuCB(a="edit", id=sid)))
        kb.row(B(f"⬅️ {s['floor_name']}", cb.FloorCB(id=s["floor_id"])))
    else:
        if b.debt > 0:
            kb.row(
                B(f"✅ Qarzini to'ladi: {num(b.debt)}", cb.PayCB(id=sid, amt=b.debt)),
                B("✍️ Boshqa summa", cb.StuCB(a="custom", id=sid)),
            )
        kb.row(B("↩️ Qaytib keldi", cb.StuCB(a="return", id=sid)), B("📜 Tarix", cb.StuCB(a="hist", id=sid)))
        kb.row(B("🗑 Butunlay o'chirish", cb.StuCB(a="del", id=sid)))
        kb.row(B("⬅️ Chiqib ketganlar", cb.Menu(a="inactive")))
    return "\n".join(lines), kb.as_markup()


def history(db: Database, sid: int, note: str | None = None) -> View:
    kb = InlineKeyboardBuilder()
    s = db.get_student(sid)
    if not s:
        kb.row(B("⬅️ Etajlar", cb.Menu(a="pay")))
        return "Bola topilmadi.", kb.as_markup()
    pays = db.student_payments(sid, limit=15)
    exs = db.student_exemptions(sid)
    lines = [note, ""] if note else []
    lines.append(f"📜 <b>{esc(s['full_name'])}</b> — to'lovlar tarixi")
    if not pays:
        lines.append("\nHali to'lov yo'q.")
    else:
        lines.append("")
        for p in pays:
            extra = f" <i>({esc(p['note'])})</i>" if p["note"] else ""
            lines.append(f"• {fmt_dt(p['paid_at'])} — <b>{money(p['amount'])}</b>{extra}")
        if len(pays) == 15:
            lines.append("<i>(oxirgi 15 tasi. To'liq ro'yxat — Excel faylda)</i>")
    if exs:
        lines.append("\n💤 Ozod haftalar: " + ", ".join(week_label(w) for w in exs[-8:]))
    if pays:
        lines.append("\nXato yozilgan to'lovni o'chirish uchun 🗑 tugmasini bosing.")
        btns = [
            B(f"🗑 {short_date(p['paid_at'])} · {short_money(p['amount'])}", cb.PayDelCB(id=p["id"]))
            for p in pays[:6]
        ]
        for i in range(0, len(btns), 2):
            kb.row(*btns[i:i + 2])
    kb.row(B("⬅️ Orqaga", cb.CardCB(id=sid)))
    return "\n".join(lines), kb.as_markup()


def pay_delete_confirm(db: Database, pid: int) -> View | None:
    p = db.get_payment(pid)
    if not p:
        return None
    kb = InlineKeyboardBuilder()
    kb.row(
        B("✅ Ha, o'chirish", cb.PayDelCB(id=pid, ok=1)),
        B("❌ Yo'q", cb.StuCB(a="hist", id=p["student_id"])),
    )
    text = (
        "🗑 <b>Bu to'lovni o'chirasizmi?</b>\n\n"
        f"👤 {esc(p['full_name'])}\n"
        f"💵 {money(p['amount'])}\n"
        f"🕒 {fmt_dt(p['paid_at'])}"
    )
    return text, kb.as_markup()


# =====================================================================
#  Bolalar bo'limi
# =====================================================================
def students_menu(db: Database, note: str | None = None) -> View:
    floors = db.list_floors()
    active = sum(f["cnt"] for f in floors)
    inactive = db.count_inactive()
    kb = InlineKeyboardBuilder()
    lines = [note, ""] if note else []
    lines += ["👥 <b>Bolalar</b>", f"Faol: <b>{active}</b> ta · Etajlar: {len(floors)} ta"]
    if not floors:
        lines.append("\nBoshlash uchun avval etaj qo'shing 👇")
        kb.row(B("➕ Etaj qo'shish", cb.FloorAdmCB(a="add")))
        return "\n".join(lines), kb.as_markup()
    lines.append("\nEtajni tanlang yoki amalni bajaring 👇")
    for f in floors:
        kb.row(B(f"🏢 {f['name']} — {f['cnt']} ta", cb.FloorCB(id=f["id"])))
    kb.row(B("➕ Bola qo'shish", cb.Menu(a="add")), B("🔍 Qidirish", cb.Menu(a="search")))
    kb.row(B("🏢 Etajlarni sozlash", cb.Menu(a="floors")),
           B(f"🚶 Chiqib ketganlar ({inactive})", cb.Menu(a="inactive")))
    return "\n".join(lines), kb.as_markup()


def add_pick_floor(db: Database) -> View:
    floors = db.list_floors()
    kb = InlineKeyboardBuilder()
    if not floors:
        kb.row(B("➕ Etaj qo'shish", cb.FloorAdmCB(a="add")))
        return "Avval etaj qo'shing.", kb.as_markup()
    for f in floors:
        kb.row(B(f"🏢 {f['name']} ({f['cnt']} ta)", cb.AddToCB(f=f["id"])))
    kb.row(B("⬅️ Orqaga", cb.Menu(a="students")))
    return "➕ <b>Bola qo'shish</b>\n\nQaysi etajga?", kb.as_markup()


def add_prompt(floor_name: str, floor_id: int) -> View:
    kb = InlineKeyboardBuilder()
    kb.row(B("⬅️ Bekor qilish", cb.FloorCB(id=floor_id)))
    text = (
        f"➕ <b>{esc(floor_name)}</b> ga bola qo'shish\n\n"
        "Ism-familiyani yozib yuboring.\n\n"
        "Bir nechta bolani <b>birdaniga</b> qo'shish mumkin — har birini yangi qatordan yozing. "
        "Xona raqamini vergul bilan qo'shsa bo'ladi:\n\n"
        "<code>Aliyev Vali, 305\nKarimov Sardor, 305\nToshmatov Jasur</code>"
    )
    return text, kb.as_markup()


def edit_menu(db: Database, sid: int) -> View:
    s = db.get_student(sid)
    kb = InlineKeyboardBuilder()
    if not s:
        kb.row(B("⬅️ Etajlar", cb.Menu(a="pay")))
        return "Bola topilmadi.", kb.as_markup()
    kb.row(B("✏️ Ism-familiya", cb.StuCB(a="name", id=sid)), B("🚪 Xona", cb.StuCB(a="room", id=sid)))
    kb.row(B("📞 Telefon", cb.StuCB(a="phone", id=sid)), B("🏢 Etajni almashtirish", cb.StuCB(a="floor", id=sid)))
    kb.row(B("📒 Daftardagi eski qarz", cb.StuCB(a="debt", id=sid)))
    if s["active"]:
        kb.row(B("🚶 TTJdan chiqib ketdi", cb.StuCB(a="leave", id=sid)))
    kb.row(B("⬅️ Orqaga", cb.CardCB(id=sid)))
    return f"⚙️ <b>{esc(s['full_name'])}</b> — tahrirlash\n\nNimani o'zgartirasiz?", kb.as_markup()


def move_picker(db: Database, sid: int) -> View:
    s = db.get_student(sid)
    kb = InlineKeyboardBuilder()
    for f in db.list_floors():
        if s and f["id"] != s["floor_id"]:
            kb.row(B(f"🏢 {f['name']}", cb.MoveCB(id=sid, f=f["id"])))
    kb.row(B("⬅️ Orqaga", cb.StuCB(a="edit", id=sid)))
    name = esc(s["full_name"]) if s else ""
    return f"🏢 <b>{name}</b> qaysi etajga o'tdi?", kb.as_markup()


def leave_confirm(db: Database, sid: int) -> View:
    s = db.get_student(sid)
    kb = InlineKeyboardBuilder()
    kb.row(B("✅ Ha, chiqib ketdi", cb.StuCB(a="leave_ok", id=sid)), B("❌ Yo'q", cb.StuCB(a="edit", id=sid)))
    text = (
        f"🚶 <b>{esc(s['full_name'] if s else '')}</b> TTJdan chiqib ketdimi?\n\n"
        "• Keyingi haftadan boshlab to'lov hisoblanmaydi.\n"
        "• Qarzi bo'lsa — saqlanib qoladi.\n"
        "• Keyin «Qaytib keldi» tugmasi bilan qaytarsa bo'ladi."
    )
    return text, kb.as_markup()


def delete_confirm(db: Database, sid: int) -> View:
    s = db.get_student(sid)
    kb = InlineKeyboardBuilder()
    kb.row(B("🗑 Ha, o'chirish", cb.StuCB(a="del_ok", id=sid)), B("❌ Yo'q", cb.CardCB(id=sid)))
    return (
        f"🗑 <b>{esc(s['full_name'] if s else '')}</b> butunlay o'chirilsinmi?\n"
        "Bu amalni qaytarib bo'lmaydi.",
        kb.as_markup(),
    )


def inactive_list(db: Database, note: str | None = None) -> View:
    students = db.list_students(active=False)
    bals = db.balances([s["id"] for s in students])
    kb = InlineKeyboardBuilder()
    lines = [note, ""] if note else []
    lines.append("🚶 <b>Chiqib ketganlar</b>")
    if not students:
        lines.append("\nHozircha yo'q.")
    else:
        with_debt = [s for s in students if bals[s["id"]].debt > 0]
        if with_debt:
            total = sum(bals[s["id"]].debt for s in with_debt)
            lines.append(f"❌ Qarzi qolganlar: {len(with_debt)} ta · {money(total)}")
        for s in students[:60]:
            d = bals[s["id"]].debt
            label = f"🚶 {s['full_name']} · {s['floor_name']}" + (f" · ❌ {short_money(d)}" if d > 0 else "")
            kb.row(B(label, cb.CardCB(id=s["id"])))
    kb.row(B("⬅️ Orqaga", cb.Menu(a="students")))
    return "\n".join(lines), kb.as_markup()


def search_prompt() -> View:
    kb = InlineKeyboardBuilder()
    kb.row(B("⬅️ Orqaga", cb.Menu(a="pay")))
    return "🔍 Bolaning ismi yoki familiyasidan bir qismini yozing (yoki xona raqamini):", kb.as_markup()


def search_results(db: Database, query: str) -> View:
    found = db.search_students(query)
    bals = db.balances([s["id"] for s in found])
    fee = db.current_fee()
    kb = InlineKeyboardBuilder()
    for s in found:
        icon = status_icon(bals[s["id"]], fee) if s["active"] else "🚶"
        kb.row(B(f"{icon} {s['full_name']} · {s['floor_name']}", cb.CardCB(id=s["id"])))
    kb.row(B("⬅️ Etajlar", cb.Menu(a="pay")))
    if not found:
        text = f"🔍 «{esc(query)}» bo'yicha hech kim topilmadi.\nBoshqacha yozib ko'ring:"
    else:
        text = f"🔍 «{esc(query)}» — {len(found)} ta topildi.\nYana qidirish uchun ism yozing:"
    return text, kb.as_markup()


def floors_admin(db: Database, note: str | None = None) -> View:
    floors = db.list_floors()
    kb = InlineKeyboardBuilder()
    lines = [note, ""] if note else []
    lines.append("🏢 <b>Etajlar</b>\n")
    if not floors:
        lines.append("Hali etaj yo'q.")
    for f in floors:
        lines.append(f"• {esc(f['name'])} — {f['cnt']} ta bola")
        kb.row(B(f"✏️ {f['name']}", cb.FloorAdmCB(a="ren", id=f["id"])),
               B("🗑", cb.FloorAdmCB(a="del", id=f["id"])))
    kb.row(B("➕ Etaj qo'shish", cb.FloorAdmCB(a="add")))
    kb.row(B("⬅️ Orqaga", cb.Menu(a="students")))
    return "\n".join(lines), kb.as_markup()


# =====================================================================
#  Xarajatlar
# =====================================================================
def expense_menu(db: Database) -> View:
    ws = week_start()
    ms = month_start(today())
    w_sum = db.expense_between(ws, ws + timedelta(days=7))[0]
    m_sum = db.expense_between(ms, add_months(ms, 1))[0]
    kb = InlineKeyboardBuilder()
    btns = [B(c, cb.ExpCatCB(i=i)) for i, c in enumerate(EXPENSE_CATEGORIES)]
    for i in range(0, len(btns), 2):
        kb.row(*btns[i:i + 2])
    kb.row(B("📋 Oxirgi xarajatlar", cb.ExpCB(a="recent")))
    text = (
        "🛒 <b>Xarajat qo'shish</b>\n\n"
        f"Bu hafta: {money(w_sum)}\n"
        f"Bu oy: {money(m_sum)}\n\n"
        "Nima uchun pul sarflandi? 👇"
    )
    return text, kb.as_markup()


def expense_saved(db: Database, eid: int) -> View:
    e = db.get_expense(eid)
    ws = week_start()
    w_sum = db.expense_between(ws, ws + timedelta(days=7))[0]
    kb = InlineKeyboardBuilder()
    kb.row(B("↩️ Bekor qilish", cb.ExpCB(a="del_ok", id=eid)), B("➕ Yana xarajat", cb.Menu(a="exp")))
    lines = [
        "✅ <b>Xarajat yozildi</b>\n",
        f"{esc(e['category'])} — <b>{money(e['amount'])}</b>",
    ]
    if e["description"]:
        lines.append(f"📝 {esc(e['description'])}")
    lines += [f"📅 {fmt_date(e['spent_at'])}", "", f"Bu haftadagi jami xarajat: {money(w_sum)}"]
    return "\n".join(lines), kb.as_markup()


def recent_expenses(db: Database, note: str | None = None) -> View:
    rows = db.recent_expenses(10)
    kb = InlineKeyboardBuilder()
    lines = [note, ""] if note else []
    lines.append("📋 <b>Oxirgi xarajatlar</b>\n")
    if not rows:
        lines.append("Hali xarajat yozilmagan.")
    for e in rows:
        desc = f" — {esc(e['description'])}" if e["description"] else ""
        lines.append(f"• {fmt_date(e['spent_at'])} · {esc(e['category'])} · <b>{num(e['amount'])}</b>{desc}")
        kb.row(B(f"🗑 {short_date(e['spent_at'])} · {e['category']} · {short_money(e['amount'])}",
                 cb.ExpCB(a="del", id=e["id"])))
    if rows:
        lines.append("\nXato yozilganini o'chirish uchun 🗑 ni bosing.")
    kb.row(B("⬅️ Orqaga", cb.Menu(a="exp")))
    return "\n".join(lines), kb.as_markup()


def expense_delete_confirm(db: Database, eid: int) -> View | None:
    e = db.get_expense(eid)
    if not e:
        return None
    kb = InlineKeyboardBuilder()
    kb.row(B("✅ Ha, o'chirish", cb.ExpCB(a="del_ok", id=eid)), B("❌ Yo'q", cb.ExpCB(a="recent")))
    desc = f"\n📝 {esc(e['description'])}" if e["description"] else ""
    return (
        f"🗑 <b>Bu xarajatni o'chirasizmi?</b>\n\n{esc(e['category'])} — {money(e['amount'])}{desc}\n"
        f"📅 {fmt_date(e['spent_at'])}",
        kb.as_markup(),
    )


# =====================================================================
#  Hisobotlar
# =====================================================================
def _period_text(db: Database, d1: date, d2: date, title: str, label: str) -> list[str]:
    inc, n_pay = db.income_between(d1, d2)
    exp, n_exp = db.expense_between(d1, d2)
    lines = [title, f"📅 {label}", "", f"💰 <b>Kirim: {money(inc)}</b> ({n_pay} ta to'lov)"]
    for r in db.income_by_floor(d1, d2):
        lines.append(f"      🏢 {esc(r['name'])}: {num(r['total'])}")
    lines.append(f"🛒 <b>Chiqim: {money(exp)}</b> ({n_exp} ta xarid)")
    for r in db.expense_by_category(d1, d2):
        lines.append(f"      {esc(r['category'])}: {num(r['total'])}")
    diff = inc - exp
    sign = "+" if diff > 0 else ""
    lines += [LINE, f"{'📈' if diff >= 0 else '📉'} <b>Farq: {sign}{money(diff)}</b>"]
    return lines


def current_status_lines(db: Database) -> list[str]:
    students = db.list_students()
    bals = db.balances()
    fee = db.current_fee()
    counts = {"✅": 0, "🟡": 0, "❌": 0, "💤": 0}
    debt = 0
    for s in students:
        b = bals[s["id"]]
        counts[status_icon(b, fee)] += 1
        debt += max(b.debt, 0)
    return [
        f"👥 <b>Hozirgi holat</b> ({len(students)} ta bola):",
        f"✅ To'lagan: {counts['✅']} · 🟡 Qisman: {counts['🟡']} · ❌ To'lamagan: {counts['❌']}"
        + (f" · 💤 Ozod: {counts['💤']}" if counts["💤"] else ""),
        f"💸 Faol bolalar qarzi: {money(debt)}",
    ]


def _report_kb(kind: str, offset: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    prev_t, next_t = ("◀️ Oldingi hafta", "Keyingi hafta ▶️") if kind == "w" else ("◀️ Oldingi oy", "Keyingi oy ▶️")
    nav = [B(prev_t, cb.RepCB(k=kind, o=offset - 1))]
    if offset < 0:
        nav.append(B(next_t, cb.RepCB(k=kind, o=offset + 1)))
    kb.row(*nav)
    if kind == "w":
        kb.row(B("🗓 Oylik hisobot", cb.RepCB(k="m")), B("🏦 Kassa", cb.RepCB(k="kassa")))
    else:
        kb.row(B("📅 Haftalik hisobot", cb.RepCB(k="w")), B("🏦 Kassa", cb.RepCB(k="kassa")))
    kb.row(B("❗ Qarzdorlar", cb.RepCB(k="debt")), B("📥 Excel fayl", cb.RepCB(k="xls")))
    return kb


def week_report(db: Database, offset: int = 0) -> View:
    offset = min(offset, 0)
    ws = week_start() + timedelta(weeks=offset)
    label = week_label(ws) + (" (joriy hafta)" if offset == 0 else "")
    lines = _period_text(db, ws, ws + timedelta(days=7), "📊 <b>Haftalik hisobot</b>", label)
    if offset == 0:
        lines += [""] + current_status_lines(db)
    lines += ["", f"🏦 Kassada hozir: <b>{money(db.cash_balance())}</b>"]
    return "\n".join(lines), _report_kb("w", offset).as_markup()


def month_report(db: Database, offset: int = 0) -> View:
    offset = min(offset, 0)
    ms = add_months(month_start(today()), offset)
    label = month_label(ms) + (" (joriy oy)" if offset == 0 else "")
    lines = _period_text(db, ms, add_months(ms, 1), "🗓 <b>Oylik hisobot</b>", label)
    lines += ["", f"🏦 Kassada hozir: <b>{money(db.cash_balance())}</b>"]
    return "\n".join(lines), _report_kb("m", offset).as_markup()


def kassa(db: Database) -> View:
    opening = db.opening_cash()
    inc = db.total_income()
    exp = db.total_expense()
    students = db.list_students(active=None)
    bals = db.balances()
    debt = sum(max(bals[s["id"]].debt, 0) for s in students)
    prepaid = sum(max(-bals[s["id"]].debt, 0) for s in students)
    debtors = sum(1 for s in students if bals[s["id"]].debt > 0)
    lines = [
        "🏦 <b>Kassa (umumiy)</b>\n",
        f"📒 Boshlang'ich (daftardan): {money(opening)}",
        f"💰 Jami kirim: {money(inc)}",
        f"🛒 Jami chiqim: {money(exp)}",
        LINE,
        f"💵 <b>Kassada bo'lishi kerak: {money(opening + inc - exp)}</b>",
        "",
        f"❌ Qarzdorlar: {debtors} ta · jami {money(debt)}",
        f"✅ Oldindan to'langan: {money(prepaid)}",
    ]
    kb = InlineKeyboardBuilder()
    kb.row(B("📅 Haftalik hisobot", cb.RepCB(k="w")), B("📥 Excel fayl", cb.RepCB(k="xls")))
    return "\n".join(lines), kb.as_markup()


def debtors_texts(db: Database) -> list[str]:
    fee = db.current_fee()
    students = db.list_students(active=None)
    bals = db.balances()
    lines = [f"❗ <b>Qarzdorlar</b> — {week_label(week_start())}", f"Haftalik to'lov: {money(fee)}"]
    total, count = 0, 0
    cur_floor = None
    inactive_debtors = []
    for s in students:
        d = bals[s["id"]].debt
        if d <= 0:
            continue
        if not s["active"]:
            inactive_debtors.append((s, d))
            continue
        if s["floor_name"] != cur_floor:
            cur_floor = s["floor_name"]
            lines.append(f"\n🏢 <b>{esc(cur_floor)}</b>")
        room = f" ({esc(s['room'])})" if s["room"] else ""
        lines.append(f"{status_icon(bals[s['id']], fee)} {esc(s['full_name'])}{room} — {num(d)}")
        total += d
        count += 1
    if inactive_debtors:
        lines.append("\n🚶 <b>Chiqib ketganlar</b>")
        for s, d in inactive_debtors:
            lines.append(f"❌ {esc(s['full_name'])} ({esc(s['floor_name'])}) — {num(d)}")
            total += d
            count += 1
    if count == 0:
        lines.append("\n🎉 Hamma to'lagan! Qarzdor yo'q.")
    else:
        lines += [LINE, f"Jami: <b>{count} ta</b> bola · <b>{money(total)}</b>"]
    return chunk_lines(lines)


# =====================================================================
#  Sozlamalar
# =====================================================================
def settings_view(db: Database, note: str | None = None) -> View:
    fee, nxt = db.current_fee(), db.next_fee()
    lines = [note, ""] if note else []
    lines += ["⚙️ <b>Sozlamalar</b>\n", f"💵 Haftalik to'lov: <b>{money(fee)}</b>"]
    if nxt != fee:
        lines.append(f"      ⏭ Keyingi haftadan: {money(nxt)}")
    lines += [
        f"📒 Boshlang'ich kassa: {money(db.opening_cash())}",
        f"👤 Adminlar: {db.admin_count()} ta",
    ]
    kb = InlineKeyboardBuilder()
    kb.row(B("💵 Haftalik to'lovni o'zgartirish", cb.SetCB(a="fee")))
    kb.row(B("📒 Boshlang'ich kassa", cb.SetCB(a="cash")))
    kb.row(B("👤 Adminlar", cb.SetCB(a="admins")), B("💾 Zaxira nusxa", cb.SetCB(a="backup")))
    return "\n".join(lines), kb.as_markup()


def admins_view(db: Database, me: int, note: str | None = None) -> View:
    kb = InlineKeyboardBuilder()
    lines = [note, ""] if note else []
    lines += ["👤 <b>Adminlar</b> — botdan foydalana oladiganlar\n"]
    for a in db.list_admins():
        name = esc(a["name"] or "nomi noma'lum")
        mine = " (siz)" if a["tg_id"] == me else ""
        lines.append(f"• {name} — <code>{a['tg_id']}</code>{mine}")
        if a["tg_id"] != me:
            kb.row(B(f"🗑 {a['name'] or a['tg_id']}", cb.SetCB(a="adel", id=a["tg_id"])))
    lines.append(
        "\nYangi odam qo'shish: u botga /start yozsin — bot unga ID raqamini ko'rsatadi. "
        "So'ng shu raqamni «➕ Admin qo'shish» orqali kiriting."
    )
    kb.row(B("➕ Admin qo'shish", cb.SetCB(a="aadd")))
    kb.row(B("⬅️ Orqaga", cb.SetCB(a="main")))
    return "\n".join(lines), kb.as_markup()
