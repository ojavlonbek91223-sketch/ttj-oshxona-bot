"""Mini App API sinovi (Telegram'siz). Ishga tushirish:  python tests/test_api.py"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import config  # noqa: E402
from tests._db import fresh_db  # noqa: E402
from webserver import build_app  # noqa: E402

TOKEN = "123456:TEST-TOKEN"
config.BOT_TOKEN = TOKEN
config.WEBAPP_DEV = False
COOK = {"id": 7000000001, "first_name": "Oshpaz", "last_name": "Aka"}
OTHER = {"id": 7000000002, "first_name": "Begona"}


def init_data(user: dict, token: str = TOKEN, age: int = 0) -> str:
    data = {
        "auth_date": str(int(time.time()) - age),
        "query_id": "AAHtest",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_document(self, chat, doc, caption=None):
        self.sent.append(("doc", chat, doc.filename))

    async def send_message(self, chat, text):
        self.sent.append(("msg", chat, text[:30]))


def check(cond, what, extra=""):
    if not cond:
        print(f"\n❌ XATO: {what}\n{extra}")
        raise SystemExit(1)
    print(f"✅ {what}")


async def main():
    db = fresh_db()
    bot = FakeBot()
    client = TestClient(TestServer(build_app(db, bot)))
    await client.start_server()
    cook = {"X-Init-Data": init_data(COOK)}

    async def call(method, path, body=None, headers=cook):
        r = await client.request(method, "/api" + path, json=body, headers=headers)
        return r.status, await r.json()

    # --- sahifa ---
    r = await client.get("/")
    html = await r.text()
    check(r.status == 200 and "telegram-web-app.js" in html, "Bosh sahifa ochiladi")
    r = await client.get("/static/app.js")
    check(r.status == 200, "app.js yuklanadi")

    # --- kirish ---
    st, d = await call("GET", "/state", headers={})
    check(st == 401 and "Telegram" in d["error"], "initData'siz — 401", d)
    st, d = await call("GET", "/state", headers={"X-Init-Data": init_data(COOK, token="999:WRONG")})
    check(st == 401, "Soxta imzo — 401", d)
    st, d = await call("GET", "/state", headers={"X-Init-Data": init_data(COOK, age=8 * 24 * 3600)})
    check(st == 401 and "eskirgan" in d["error"], "Eski initData — 401", d)
    st, d = await call("GET", "/state")
    check(st == 200 and db.is_admin(COOK["id"]), "Birinchi kirgan bosh admin bo'ldi")
    check(d["me"]["name"] == "Oshpaz Aka", "Ism Telegram'dan olindi", d["me"])
    st, d = await call("GET", "/state", headers={"X-Init-Data": init_data(OTHER)})
    check(st == 403 and str(OTHER["id"]) in d["error"], "Begona — 403 va ID ko'rsatiladi", d)

    # --- etajlar va bolalar ---
    st, d = await call("POST", "/floors", {"text": "1\n2\n1-etaj"})
    check(d["added"] == ["1-etaj", "2-etaj"] and d["exists"] == ["1-etaj"], "Etajlar qo'shildi", d)
    floors = (await call("GET", "/state"))[1]["floors"]
    f1, f2 = floors[0]["id"], floors[1]["id"]
    st, d = await call("POST", "/students", {"floor_id": f1, "text": "Aliyev Vali, 305\nKarimov Sardor, 305-xona\n\n12345\nToshmatov Jasur"})
    check(len(d["added"]) == 3 and d["bad"] == ["12345"], "3 ta bola qo'shildi, 1 qator rad", d)
    st, d = await call("POST", "/students", {"floor_id": f2, "text": "Nazarov Otabek"})
    s = {x["name"]: x for x in (await call("GET", "/state"))[1]["students"]}
    ali, kar, tosh, naz = (s[n]["id"] for n in ("Aliyev Vali", "Karimov Sardor", "Toshmatov Jasur", "Nazarov Otabek"))
    check(s["Karimov Sardor"]["room"] == "305" and s["Aliyev Vali"]["status"] == "bad", "Xona tozalandi, yangi bola ❌")

    # --- to'lovlar ---
    st, d = await call("POST", "/pay", {"student_id": ali, "amount": 90000})
    check(st == 200 and d["debt"] == 0, "90 000 to'lov", d)
    st, d2 = await call("POST", "/pay", {"student_id": ali, "amount": 90000})
    check(st == 409, "Ketma-ket ikki bosish bloklandi", d2)
    st, d3 = await call("DELETE", f"/payment/{d['payment_id']}")
    check(st == 200 and db.total_income() == 0, "Bekor qilish (undo)")
    db.add_payment(ali, 90000)
    st, d = await call("POST", "/pay", {"student_id": kar, "amount": "45 000"})
    check(st == 200 and d["debt"] == 45000, "Matnli summa '45 000' — qisman", d)
    st, d = await call("POST", "/pay", {"student_id": kar, "amount": "abc"})
    check(st == 400 and "Summani" in d["error"], "Noto'g'ri summa — 400", d)
    st, d = await call("POST", "/exempt", {"student_id": tosh})
    check(d["exempt"] is True, "Bu hafta ozod")
    st, d = await call("GET", "/state")
    c = d["counts"]
    check((c["ok"], c["part"], c["bad"], c["exempt"], c["debt"]) == (1, 1, 1, 1, 135000), "Holat hisoblagichlari", c)

    st, d = await call("GET", f"/student/{kar}")
    check(d["debt"] == 45000 and len(d["payments"]) == 1 and not d["can_delete"], "Bola kartochkasi", d)

    # --- tahrirlash ---
    st, d = await call("PATCH", f"/student/{kar}", {"name": "Karimov  Sardorbek", "room": "306", "phone": "+998901234567",
                                                     "floor_id": f2, "opening_debt": "-20 000"})
    st, d = await call("GET", f"/student/{kar}")
    check(d["name"] == "Karimov Sardorbek" and d["floor_id"] == f2 and d["opening_debt"] == -20000 and d["debt"] == 25000,
          "Tahrirlash (ism, etaj, eski qarz minus)", d)
    st, d = await call("PATCH", f"/student/{kar}", {"name": "A"})
    check(st == 400, "Juda qisqa ism rad etildi")

    # --- chiqib ketdi / qaytdi / o'chirish ---
    st, _ = await call("POST", f"/student/{naz}/leave")
    st, d = await call("GET", f"/student/{naz}")
    check(not d["active"] and d["status"] == "left" and d["can_delete"], "Chiqib ketdi")
    st, d = await call("DELETE", f"/student/{kar}")
    check(st == 400, "To'lovi bor bola o'chirilmaydi", d)
    st, d = await call("DELETE", f"/student/{naz}")
    check(st == 200 and db.get_student(naz) is None, "To'lovsiz bola o'chirildi")
    st, d = await call("DELETE", f"/floor/{f1}")
    check(st == 400, "Bolasi bor etaj o'chirilmaydi")
    st, d = await call("PATCH", f"/floor/{f2}", {"name": "1-etaj"})
    check(st == 400, "Takroriy etaj nomi rad etildi")
    st, d = await call("PATCH", f"/floor/{f2}", {"name": "Ikkinchi qavat"})
    check(st == 200, "Etaj nomi o'zgardi")

    # --- xarajatlar ---
    st, d = await call("POST", "/expenses", {"category": "🥩 Go'sht", "amount": "350 000", "description": "5 kg"})
    check(st == 200, "Xarajat qo'shildi")
    st, d = await call("POST", "/expenses", {"category": "Noma'lum", "amount": "1000"})
    check(st == 400, "Noma'lum toifa rad etildi")
    st, d = await call("POST", "/expenses", {"category": "🍞 Non", "amount": "50k", "date": "2099-01-01"})
    check(st == 400 and "Sana" in d["error"], "Kelajak sanasi rad etildi", d)
    st, d = await call("GET", "/expenses")
    check(d["week"] == 350000 and len(d["items"]) == 1, "Xarajatlar ro'yxati", d)
    st, d = await call("POST", "/expenses", {"category": "🍞 Non", "amount": "50k"})
    st, d = await call("DELETE", f"/expense/{d['id']}")
    check(st == 200 and db.total_expense() == 350000, "Xarajat o'chirildi")

    # --- hisobot ---
    st, d = await call("GET", "/report?k=w&o=0")
    check(d["income"] == 135000 and d["expense"] == 350000 and d["diff"] == -215000 and d["status"], "Haftalik hisobot", d)
    check(d["kassa"]["balance"] == -215000, "Kassa")
    st, d = await call("GET", "/report?k=m&o=-1")
    check(d["income"] == 0 and d["status"] is None, "O'tgan oy hisobot")
    st, d = await call("GET", "/debtors")
    check(d["count"] == 1 and d["total"] == 25000, "Qarzdorlar", d)

    # --- sozlamalar ---
    st, d = await call("POST", "/settings/fee", {"amount": "100 000", "when": "next"})
    st, d = await call("GET", "/settings")
    check(d["fee"] == 90000 and d["next_fee"] == 100000, "Haftalik summa keyingi haftadan", d)
    st, d = await call("POST", "/settings/cash", {"amount": "0"})
    check(st == 200, "Boshlang'ich kassa 0")
    st, d = await call("POST", "/admins", {"id": "12"})
    check(st == 400, "Noto'g'ri admin ID rad etildi")
    st, d = await call("POST", "/admins", {"id": str(OTHER["id"])})
    st, d = await call("GET", "/state", headers={"X-Init-Data": init_data(OTHER)})
    check(st == 200, "Yangi admin kira oladi")
    st, d = await call("DELETE", f"/admins/{COOK['id']}")
    check(st == 400, "O'zini o'chira olmaydi")

    # --- chatga yuborish ---
    for what in ("excel", "backup", "debtors"):
        st, d = await call("POST", f"/send/{what}")
        check(st == 200, f"Chatga yuborish: {what}")
    check([x[0] for x in bot.sent] == ["doc", "doc", "msg"] and all(x[1] == COOK["id"] for x in bot.sent),
          "Fayllar foydalanuvchining o'ziga yuborildi", bot.sent)

    await client.close()
    print("\n🎉 API: hamma tekshiruvlar o'tdi.")


if __name__ == "__main__":
    asyncio.run(main())
