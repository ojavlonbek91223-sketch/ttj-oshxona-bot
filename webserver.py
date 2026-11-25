"""Telegram Mini App: statik sahifa + JSON API (bot bilan bitta jarayonda ishlaydi).

Har bir /api/ so'rovida Telegram bergan `initData` (X-Init-Data sarlavhasi)
bot tokeni bilan tekshiriladi va foydalanuvchi admin ekanligi aniqlanadi.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

import config
import views
from db import Database
from export import build_excel
from utils import (
    add_months, clean_room, floor_name, fmt_date, fmt_dt, month_label, month_start, now,
    parse_amount, parse_student_line, today, week_label, week_start,
)

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent / "webapp"
DB = web.AppKey("db", Database)
BOT = web.AppKey("bot", Bot)
INIT_DATA_MAX_AGE = 7 * 24 * 3600
STATUS = {"✅": "ok", "🟡": "part", "❌": "bad", "💤": "exempt"}
WEBHOOK_PATH = "/tg/webhook"


def webhook_secret() -> str:
    """Telegram webhook so'rovlarini tekshirish uchun maxfiy kalit (tokendan hosil qilinadi)."""
    return hashlib.sha256(("webhook:" + config.BOT_TOKEN).encode()).hexdigest()[:48]


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- middleware
def _dev_request(request: web.Request) -> bool:
    host = (request.host or "").split(":")[0]
    return (
        config.WEBAPP_DEV
        and request.remote in ("127.0.0.1", "::1")
        and host in ("localhost", "127.0.0.1")
    )


@web.middleware
async def api_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        resp = await handler(request)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    db = request.app[DB]
    init_data = request.headers.get("X-Init-Data", "")
    try:
        if init_data:
            try:
                data = safe_parse_webapp_init_data(config.BOT_TOKEN, init_data)
            except ValueError:
                raise ApiError("Ruxsat yo'q: Telegram ma'lumoti noto'g'ri", 401)
            if not data.user or time.time() - data.auth_date.timestamp() > INIT_DATA_MAX_AGE:
                raise ApiError("Sessiya eskirgan. Ilovani yopib, qayta oching.", 401)
            user_id = data.user.id
            name = " ".join(x for x in (data.user.first_name, data.user.last_name) if x)
        elif _dev_request(request):
            admins = db.list_admins()
            user_id = admins[0]["tg_id"] if admins else 1
            name = "dev"
        else:
            raise ApiError("Ilovani Telegram ichida oching.", 401)

        if not db.is_admin(user_id):
            if db.admin_count() == 0:
                db.add_admin(user_id, name)  # birinchi kirgan — bosh admin
            else:
                raise ApiError(f"Sizda ruxsat yo'q. Telegram ID: {user_id}", 403)
        request["user_id"] = user_id
        return await handler(request)
    except ApiError as e:
        if e.status in (401, 403):
            log.warning("Ilovaga kirish rad etildi (%s): %s", e.status, e)
        return web.json_response({"error": str(e)}, status=e.status)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("API xatosi: %s %s", request.method, request.path)
        return web.json_response({"error": "Serverda xatolik. Qayta urinib ko'ring."}, status=500)


# ---------------------------------------------------------------- helpers
async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ApiError("Noto'g'ri so'rov")
    if not isinstance(data, dict):
        raise ApiError("Noto'g'ri so'rov")
    return data


def _amount(value, allow_zero: bool = False, allow_negative: bool = False) -> int:
    text = str(value if value is not None else "").strip()
    negative = allow_negative and text.startswith("-")
    if negative:
        text = text.lstrip("-").strip()
    if allow_zero and text in ("0", ""):
        return 0
    n = parse_amount(text)
    if n is None:
        raise ApiError("Summani tushunmadim. Masalan: 90000")
    return -n if negative else n


def _int(value, what: str = "id") -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f"Noto'g'ri {what}")


def _student(db: Database, sid: int):
    s = db.get_student(sid)
    if not s:
        raise ApiError("Bola topilmadi", 404)
    return s


def _student_json(s, b, fee: int) -> dict:
    return {
        "id": s["id"],
        "name": s["full_name"],
        "floor_id": s["floor_id"],
        "floor": s["floor_name"],
        "room": s["room"],
        "phone": s["phone"],
        "active": bool(s["active"]),
        "debt": b.debt,
        "paid": b.paid,
        "paid_week": b.paid_week,
        "exempt": b.exempt_now,
        "status": STATUS[views.status_icon(b, fee)] if s["active"] else "left",
        "opening_debt": s["opening_debt"],
    }


def _status_counts(db: Database) -> dict:
    fee = db.current_fee()
    bals = db.balances()
    counts = {"ok": 0, "part": 0, "bad": 0, "exempt": 0, "debt": 0, "total": 0}
    for s in db.list_students():
        b = bals[s["id"]]
        counts[STATUS[views.status_icon(b, fee)]] += 1
        counts["debt"] += max(b.debt, 0)
        counts["total"] += 1
    return counts


def _kassa(db: Database) -> dict:
    opening, inc, exp = db.opening_cash(), db.total_income(), db.total_expense()
    students = db.list_students(active=None)
    bals = db.balances()
    return {
        "opening": opening,
        "income": inc,
        "expense": exp,
        "balance": opening + inc - exp,
        "debt": sum(max(bals[s["id"]].debt, 0) for s in students),
        "prepaid": sum(max(-bals[s["id"]].debt, 0) for s in students),
        "debtors": sum(1 for s in students if bals[s["id"]].debt > 0),
    }


# ---------------------------------------------------------------- pages
async def index(request: web.Request) -> web.FileResponse:
    log.info("Ilova sahifasi ochildi")
    return web.FileResponse(STATIC / "index.html")


async def health(request: web.Request) -> web.Response:
    """Server tirikligini tekshirish. ?db=1 — bazaga ham ulanib ko'radi."""
    data = {"ok": True, "db": request.app[DB].kind}
    if request.query.get("db") == "1":
        request.app[DB].admin_count()
        data["db_ok"] = True
    return web.json_response(data)


# ---------------------------------------------------------------- state
async def get_state(request: web.Request) -> web.Response:
    db = request.app[DB]
    fee = db.current_fee()
    students = db.list_students(active=None)
    bals = db.balances()
    me = request["user_id"]
    admin = next((a for a in db.list_admins() if a["tg_id"] == me), None)
    return web.json_response({
        "me": {"id": me, "name": admin["name"] if admin else ""},
        "week": week_label(week_start()),
        "fee": fee,
        "next_fee": db.next_fee(),
        "floors": [{"id": f["id"], "name": f["name"], "cnt": f["cnt"], "total": f["total"]}
                   for f in db.list_floors()],
        "students": [_student_json(s, bals[s["id"]], fee) for s in students],
        "categories": views.EXPENSE_CATEGORIES,
        "counts": _status_counts(db),
    })


# ---------------------------------------------------------------- students & payments
async def get_student(request: web.Request) -> web.Response:
    db = request.app[DB]
    sid = _int(request.match_info["sid"])
    s = _student(db, sid)
    b = db.balances([sid])[sid]
    data = _student_json(s, b, db.current_fee())
    data["joined"] = week_label(date.fromisoformat(s["joined_week"]))
    data["left"] = week_label(date.fromisoformat(s["left_week"])) if s["left_week"] else None
    data["payments"] = [
        {"id": p["id"], "amount": p["amount"], "at": fmt_dt(p["paid_at"]), "note": p["note"]}
        for p in db.student_payments(sid, limit=50)
    ]
    data["exemptions"] = [week_label(w) for w in db.student_exemptions(sid)][-10:]
    data["can_delete"] = db.student_payment_count(sid) == 0
    return web.json_response(data)


async def pay(request: web.Request) -> web.Response:
    db = request.app[DB]
    body = await _body(request)
    s = _student(db, _int(body.get("student_id")))
    amount = _amount(body.get("amount"))
    if db.recent_duplicate(s["id"], amount, seconds=4):
        raise ApiError("Bu to'lov hozirgina yozildi", 409)
    pid = db.add_payment(s["id"], amount, request["user_id"])
    b = db.balances([s["id"]])[s["id"]]
    return web.json_response({"payment_id": pid, "name": s["full_name"], "amount": amount, "debt": b.debt})


async def delete_payment(request: web.Request) -> web.Response:
    row = request.app[DB].delete_payment(_int(request.match_info["pid"]))
    if not row:
        raise ApiError("To'lov topilmadi", 404)
    return web.json_response({"ok": True, "name": row["full_name"], "amount": row["amount"]})


async def toggle_exempt(request: web.Request) -> web.Response:
    db = request.app[DB]
    s = _student(db, _int((await _body(request)).get("student_id")))
    return web.json_response({"exempt": db.toggle_exemption(s["id"], week_start())})


async def add_students(request: web.Request) -> web.Response:
    db = request.app[DB]
    body = await _body(request)
    f = db.get_floor(_int(body.get("floor_id"), "etaj"))
    if not f:
        raise ApiError("Etaj topilmadi", 404)
    added, bad, dup = [], [], []
    for raw in str(body.get("text", "")).splitlines():
        if not raw.strip():
            continue
        parsed = parse_student_line(raw)
        if not parsed:
            bad.append(raw.strip()[:40])
            continue
        name, room = parsed
        if db.same_name_exists(f["id"], name):
            dup.append(name)
        db.add_student(name, f["id"], room)
        added.append(name)
    if not added:
        raise ApiError("Ism topilmadi. Har bir qatorga bitta ism-familiya yozing.")
    return web.json_response({"added": added, "bad": bad, "dup": dup, "floor": f["name"]})


async def update_student(request: web.Request) -> web.Response:
    db = request.app[DB]
    s = _student(db, _int(request.match_info["sid"]))
    body = await _body(request)
    fields = {}
    if "name" in body:
        name = " ".join(str(body["name"]).split())
        if not 2 <= len(name) <= 64:
            raise ApiError("Ism 2–64 belgi bo'lishi kerak")
        fields["full_name"] = name
    if "room" in body:
        fields["room"] = clean_room(str(body["room"] or ""))
    if "phone" in body:
        fields["phone"] = str(body["phone"] or "").strip()[:32] or None
    if "floor_id" in body:
        f = db.get_floor(_int(body["floor_id"], "etaj"))
        if not f:
            raise ApiError("Etaj topilmadi", 404)
        fields["floor_id"] = f["id"]
    if "opening_debt" in body:
        fields["opening_debt"] = _amount(body["opening_debt"], allow_zero=True, allow_negative=True)
    db.update_student(s["id"], **fields)
    return web.json_response({"ok": True})


async def student_leave(request: web.Request) -> web.Response:
    db = request.app[DB]
    s = _student(db, _int(request.match_info["sid"]))
    db.deactivate_student(s["id"])
    return web.json_response({"ok": True})


async def student_return(request: web.Request) -> web.Response:
    db = request.app[DB]
    s = _student(db, _int(request.match_info["sid"]))
    db.reactivate_student(s["id"])
    return web.json_response({"ok": True})


async def delete_student(request: web.Request) -> web.Response:
    db = request.app[DB]
    s = _student(db, _int(request.match_info["sid"]))
    if not db.delete_student(s["id"]):
        raise ApiError("Bu bolaning to'lovlari bor — o'chirib bo'lmaydi. «Chiqib ketdi» qiling.")
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- floors
async def add_floors(request: web.Request) -> web.Response:
    db = request.app[DB]
    added, exists = [], []
    for raw in str((await _body(request)).get("text", "")).splitlines():
        name = floor_name(raw)
        if name:
            (added if db.add_floor(name) else exists).append(name)
    if not added and not exists:
        raise ApiError("Etaj nomini yozing")
    return web.json_response({"added": added, "exists": exists})


async def rename_floor(request: web.Request) -> web.Response:
    db = request.app[DB]
    fid = _int(request.match_info["fid"])
    if not db.get_floor(fid):
        raise ApiError("Etaj topilmadi", 404)
    name = floor_name(str((await _body(request)).get("name", "")))
    if not name:
        raise ApiError("Nom bo'sh bo'lmasin")
    if not db.rename_floor(fid, name):
        raise ApiError("Bunday nomli etaj bor")
    return web.json_response({"ok": True})


async def delete_floor(request: web.Request) -> web.Response:
    db = request.app[DB]
    fid = _int(request.match_info["fid"])
    if not db.get_floor(fid):
        raise ApiError("Etaj topilmadi", 404)
    if not db.delete_floor(fid):
        raise ApiError("Bu etajda bolalar bor (yoki bo'lgan). Avval ularni boshqa etajga ko'chiring.")
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- expenses
async def get_expenses(request: web.Request) -> web.Response:
    db = request.app[DB]
    ws, ms = week_start(), month_start(today())
    return web.json_response({
        "week": db.expense_between(ws, ws + timedelta(days=7))[0],
        "month": db.expense_between(ms, add_months(ms, 1))[0],
        "today": today().isoformat(),
        "items": [
            {"id": e["id"], "category": e["category"], "description": e["description"],
             "amount": e["amount"], "date": fmt_date(e["spent_at"])}
            for e in db.recent_expenses(40)
        ],
    })


async def add_expense(request: web.Request) -> web.Response:
    db = request.app[DB]
    body = await _body(request)
    category = str(body.get("category", ""))
    if category not in views.EXPENSE_CATEGORIES:
        raise ApiError("Toifani tanlang")
    amount = _amount(body.get("amount"))
    spent = today()
    if body.get("date"):
        try:
            spent = date.fromisoformat(str(body["date"]))
        except ValueError:
            raise ApiError("Sana noto'g'ri")
        if spent > today() or spent < today() - timedelta(days=90):
            raise ApiError("Sana bugundan keyin yoki 90 kundan eski bo'lmasin")
    desc = str(body.get("description") or "").strip()[:200] or None
    eid = db.add_expense(category, amount, desc, request["user_id"], spent)
    return web.json_response({"id": eid})


async def delete_expense(request: web.Request) -> web.Response:
    row = request.app[DB].delete_expense(_int(request.match_info["eid"]))
    if not row:
        raise ApiError("Xarajat topilmadi", 404)
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- reports
async def get_report(request: web.Request) -> web.Response:
    db = request.app[DB]
    kind = request.query.get("k", "w")
    offset = min(_int(request.query.get("o", "0"), "davr"), 0)
    if kind == "m":
        d1 = add_months(month_start(today()), offset)
        d2, label = add_months(d1, 1), month_label(d1)
    else:
        kind = "w"
        d1 = week_start() + timedelta(weeks=offset)
        d2, label = d1 + timedelta(days=7), week_label(d1)
    inc, n_pay = db.income_between(d1, d2)
    exp, n_exp = db.expense_between(d1, d2)
    return web.json_response({
        "kind": kind,
        "offset": offset,
        "label": label,
        "income": inc,
        "n_pay": n_pay,
        "expense": exp,
        "n_exp": n_exp,
        "diff": inc - exp,
        "by_floor": [{"name": r["name"], "total": r["total"]} for r in db.income_by_floor(d1, d2)],
        "by_cat": [{"name": r["category"], "total": r["total"]} for r in db.expense_by_category(d1, d2)],
        "status": _status_counts(db) if offset == 0 else None,
        "kassa": _kassa(db),
    })


async def get_debtors(request: web.Request) -> web.Response:
    db = request.app[DB]
    fee = db.current_fee()
    bals = db.balances()
    groups: list[dict] = []
    left: list[dict] = []
    total = 0
    for s in db.list_students(active=None):
        b = bals[s["id"]]
        if b.debt <= 0:
            continue
        item = {"id": s["id"], "name": s["full_name"], "room": s["room"], "debt": b.debt,
                "status": STATUS[views.status_icon(b, fee)] if s["active"] else "left",
                "floor": s["floor_name"]}
        total += b.debt
        if not s["active"]:
            left.append(item)
        elif groups and groups[-1]["floor"] == s["floor_name"]:
            groups[-1]["items"].append(item)
        else:
            groups.append({"floor": s["floor_name"], "items": [item]})
    count = sum(len(g["items"]) for g in groups) + len(left)
    return web.json_response({"groups": groups, "left": left, "total": total, "count": count})


async def send_file(request: web.Request) -> web.Response:
    """Excel / zaxira / qarzdorlar ro'yxatini bot orqali foydalanuvchi chatiga yuborish."""
    db, bot = request.app[DB], request.app[BOT]
    what = request.match_info["what"]
    chat = request["user_id"]
    stamp = now().strftime("%Y-%m-%d_%H-%M")
    try:
        if what == "excel":
            await bot.send_document(chat, BufferedInputFile(build_excel(db), f"oshxona_hisobot_{stamp}.xlsx"),
                                    caption="📥 To'liq hisobot (Excel)")
        elif what == "backup":
            await bot.send_document(chat, BufferedInputFile(db.backup_bytes(), f"oshxona_backup_{stamp}.{db.backup_ext}"),
                                    caption="💾 Zaxira nusxa — saqlab qo'ying")
        elif what == "debtors":
            for part in views.debtors_texts(db):
                await bot.send_message(chat, part)
        else:
            raise ApiError("Noma'lum fayl", 404)
    except ApiError:
        raise
    except Exception as e:
        log.warning("Faylni yuborib bo'lmadi: %s", e)
        raise ApiError("Chatga yuborib bo'lmadi. Avval botga /start yozing.")
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- settings
async def get_settings(request: web.Request) -> web.Response:
    db = request.app[DB]
    return web.json_response({
        "fee": db.current_fee(),
        "next_fee": db.next_fee(),
        "this_week": week_label(week_start()),
        "next_week": week_label(week_start() + timedelta(days=7)),
        "opening_cash": db.opening_cash(),
        "admins": [{"id": a["tg_id"], "name": a["name"]} for a in db.list_admins()],
        "me": request["user_id"],
    })


async def set_fee(request: web.Request) -> web.Response:
    db = request.app[DB]
    body = await _body(request)
    amount = _amount(body.get("amount"))
    start = week_start() + (timedelta(days=7) if body.get("when") == "next" else timedelta())
    db.set_fee(amount, start)
    return web.json_response({"ok": True, "from": week_label(start)})


async def set_cash(request: web.Request) -> web.Response:
    db = request.app[DB]
    amount = _amount((await _body(request)).get("amount"), allow_zero=True)
    db.set_setting("opening_cash", amount)
    return web.json_response({"ok": True})


async def add_admin(request: web.Request) -> web.Response:
    text = str((await _body(request)).get("id", "")).replace(" ", "")
    if not text.isdigit() or not 5 <= len(text) <= 15:
        raise ApiError("ID faqat raqamlardan iborat bo'ladi, masalan: 123456789")
    request.app[DB].add_admin(int(text))
    return web.json_response({"ok": True})


async def remove_admin(request: web.Request) -> web.Response:
    aid = _int(request.match_info["aid"])
    if aid == request["user_id"]:
        raise ApiError("O'zingizni o'chira olmaysiz")
    request.app[DB].remove_admin(aid)
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- app
def build_app(db: Database, bot: Bot | None) -> web.Application:
    app = web.Application(middlewares=[api_middleware], client_max_size=256 * 1024)
    app[DB] = db
    if bot is not None:
        app[BOT] = bot
    r = app.router
    r.add_get("/", index)
    r.add_get("/health", health)
    r.add_static("/static/", STATIC)
    r.add_get("/api/state", get_state)
    r.add_get("/api/student/{sid}", get_student)
    r.add_patch("/api/student/{sid}", update_student)
    r.add_delete("/api/student/{sid}", delete_student)
    r.add_post("/api/student/{sid}/leave", student_leave)
    r.add_post("/api/student/{sid}/return", student_return)
    r.add_post("/api/students", add_students)
    r.add_post("/api/pay", pay)
    r.add_delete("/api/payment/{pid}", delete_payment)
    r.add_post("/api/exempt", toggle_exempt)
    r.add_post("/api/floors", add_floors)
    r.add_patch("/api/floor/{fid}", rename_floor)
    r.add_delete("/api/floor/{fid}", delete_floor)
    r.add_get("/api/expenses", get_expenses)
    r.add_post("/api/expenses", add_expense)
    r.add_delete("/api/expense/{eid}", delete_expense)
    r.add_get("/api/report", get_report)
    r.add_get("/api/debtors", get_debtors)
    r.add_post("/api/send/{what}", send_file)
    r.add_get("/api/settings", get_settings)
    r.add_post("/api/settings/fee", set_fee)
    r.add_post("/api/settings/cash", set_cash)
    r.add_post("/api/admins", add_admin)
    r.add_delete("/api/admins/{aid}", remove_admin)
    return app


async def start_webserver(db: Database, bot: Bot, dp: Dispatcher | None = None) -> web.AppRunner:
    app = build_app(db, bot)
    if dp is not None:
        # Webhook: Telegram xabarlarini qabul qilish (maxfiy kalit bilan tekshiriladi).
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=webhook_secret()).register(app, path=WEBHOOK_PATH)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT).start()
    log.info("Veb-ilova: http://%s:%s  (tashqi manzil: %s)", config.WEBAPP_HOST, config.WEBAPP_PORT,
             config.WEBAPP_URL or "o'rnatilmagan")
    if config.WEBAPP_DEV:
        log.warning("WEBAPP_DEV=1 — localhost dan Telegram'siz kirish yoqilgan. Internetga chiqarishdan oldin o'chiring!")
    return runner
