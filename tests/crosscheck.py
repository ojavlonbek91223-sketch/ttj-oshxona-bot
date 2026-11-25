"""Serversiz ilova (docs/logic.js) server versiyasi (db.py + webserver.py) bilan bir xil hisoblashini tekshirish.

Tasodifiy, lekin takrorlanadigan (seed) ~1500 ta amal: etaj/bola qo'shish, to'lov, o'chirish, ozod hafta,
chiqib ketish/qaytish, xarajat, summa o'zgarishi, xato kiritishlar... Vaqt ham oldinga suriladi (bir necha oy).
Har amal Python API da bajariladi, javoblar yoziladi, so'ng Node.js da JS versiyasi bilan solishtiriladi.

    python tests/crosscheck.py [seed ...]
"""
from __future__ import annotations

import asyncio
import json
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import config  # noqa: E402
import db as db_module  # noqa: E402
import utils  # noqa: E402
import webserver  # noqa: E402
from tests._db import fresh_db  # noqa: E402
from views import EXPENSE_CATEGORIES  # noqa: E402

config.WEBAPP_DEV = True
CLOCK = [datetime(2026, 9, 1, 8, 0, 0, tzinfo=config.TZ)]


def fake_now():
    return CLOCK[0]


utils.now = fake_now
db_module.now = fake_now
webserver.now = fake_now

NAMES = ["Aliyev Vali", "Karimov Sardor", "Toshmatov Jasur", "Oʻrinov Bekzod", "G'aniyev Olim",
         "Rahimov Aziz", "Yusupov Doston", "Qodirov Shoxrux", "Ergashev Nodir", "Mirzayev Ulug'bek",
         "Abdullayev Sanjar", "Xolmatov Ilhom", "Sobirov Javohir", "Nazarov Akmal", "Hamidov Timur"]
BAD_LINES = ["123", "-", "  ", "a", "7.", "x" * 70]
AMOUNTS = [90000, "90 000", "90000", "45 000", "45k", "90 ming", "180000", "1.5 mln", "100 000 so'm",
           "abc", "0", "", "-5000", 30000, 1, "2 000 000 000", "12,5k"]
DEBTS = ["0", "", "180 000", "-90 000", "45k", "xyz", "-0"]


def gen_op(rng: random.Random, known: dict) -> tuple[str, str, dict | None]:
    sids = known["students"] or [1]
    fids = known["floors"] or [1]
    r = rng.random()
    sid = rng.choice(sids + [9999]) if rng.random() < 0.97 else "abc"
    if r < 0.05:
        lines = rng.sample(["1", "2", "3", "4", "5", "Podval", "1", "mansarda", " 2 ", ""], k=rng.randint(1, 4))
        return "POST", "/floors", {"text": "\n".join(lines)}
    if r < 0.13:
        lines = []
        for i in range(rng.randint(1, 5)):
            name = rng.choice(NAMES + BAD_LINES[:2]) if rng.random() < 0.9 else rng.choice(BAD_LINES)
            pref = rng.choice(["", f"{i + 1}. ", "- ", "• "])
            room = rng.choice(["", f", {rng.randint(100, 520)}", f", {rng.randint(100, 520)}-xona", ","])
            lines.append(pref + name + room)
        return "POST", "/students", {"floor_id": rng.choice(fids + [9999]), "text": "\n".join(lines)}
    if r < 0.45:
        return "POST", "/pay", {"student_id": sid, "amount": rng.choice(AMOUNTS if rng.random() < 0.3 else [90000, "90 000"])}
    if r < 0.50:
        return "DELETE", f"/payment/{rng.randint(1, max(known['payments'], 1) + 2)}", None
    if r < 0.55:
        return "POST", "/exempt", {"student_id": sid}
    if r < 0.61:
        body = {}
        for k in rng.sample(["name", "room", "phone", "floor_id", "opening_debt"], k=rng.randint(1, 5)):
            body[k] = {
                "name": rng.choice(NAMES + ["  Yangi   Ism  ", "A", ""]),
                "room": rng.choice(["", "305", "  412-xona ", None]),
                "phone": rng.choice(["", "+998 90 123 45 67", None]),
                "floor_id": rng.choice(fids + [9999]),
                "opening_debt": rng.choice(DEBTS),
            }[k]
        return "PATCH", f"/student/{sid}", body
    if r < 0.65:
        return "POST", f"/student/{sid}/leave", None
    if r < 0.68:
        return "POST", f"/student/{sid}/return", None
    if r < 0.70:
        return "DELETE", f"/student/{sid}", None
    if r < 0.72:
        return "PATCH", f"/floor/{rng.choice(fids + [9999])}", {"name": rng.choice(["7", "Podval", "1", "", "Yangi etaj"])}
    if r < 0.735:
        return "DELETE", f"/floor/{rng.choice(fids + [9999])}", None
    if r < 0.82:
        day = (CLOCK[0] - timedelta(days=rng.choice([0, 0, 1, 3, 40, 95, -1]))).date().isoformat()
        return "POST", "/expenses", {
            "category": rng.choice(EXPENSE_CATEGORIES + ["Noma'lum"]) if rng.random() < 0.95 else "",
            "amount": rng.choice([350000, "120 000", "45k", "abc", 75000]),
            "description": rng.choice(["", "5 kg go'sht", "  non  ", None, "x" * 250]),
            "date": rng.choice([day, day, "", "2026-13-40", "kecha"]),
        }
    if r < 0.85:
        return "DELETE", f"/expense/{rng.randint(1, max(known['expenses'], 1) + 1)}", None
    if r < 0.87:
        return "POST", "/settings/fee", {"amount": rng.choice([90000, "100 000", "95k", "x"]), "when": rng.choice(["now", "next"])}
    if r < 0.88:
        return "POST", "/settings/cash", {"amount": rng.choice(["0", "1 500 000", "", "abc"])}
    if r < 0.91:
        return "GET", f"/student/{sid}", None
    if r < 0.95:
        return "GET", f"/report?k={rng.choice(['w', 'm', 'x'])}&o={rng.choice([0, 0, -1, -2, -5, 1, 'q'])}", None
    if r < 0.97:
        return "GET", "/debtors", None
    if r < 0.985:
        return "GET", "/expenses", None
    return "GET", "/settings", None


async def record(seed: int, steps: int) -> list[dict]:
    rng = random.Random(seed)
    CLOCK[0] = datetime(2026, 9, 1, 8, 0, 0, tzinfo=config.TZ) + timedelta(days=rng.randint(0, 6))
    db = fresh_db()
    client = TestClient(TestServer(webserver.build_app(db, None)))
    await client.start_server()
    known = {"students": [], "floors": [], "payments": 0, "expenses": 0}
    out = []
    try:
        for i in range(steps):
            r = rng.random()
            if r < 0.02:
                CLOCK[0] += timedelta(seconds=2)          # tez ikki marta bosish (takror to'lov)
            elif r < 0.75:
                CLOCK[0] += timedelta(minutes=rng.randint(1, 240))
            else:
                CLOCK[0] += timedelta(hours=rng.randint(4, 60))
            if i % 25 == 0:
                method, path, body = "GET", "/state", None
            else:
                method, path, body = gen_op(rng, known)
            resp = await client.request(method, "/api" + path, json=body)
            data = await resp.json()
            if resp.status == 500:
                raise SystemExit(f"Python serverda xato: {method} {path} {body}")
            if method == "POST" and path == "/students" and resp.status == 200:
                known["students"] = [s["id"] for s in db.list_students(active=None)]
            if method == "POST" and path == "/floors" and resp.status == 200:
                known["floors"] = [f["id"] for f in db.list_floors()]
            if method == "POST" and path == "/pay" and resp.status == 200:
                known["payments"] = data["payment_id"]
            if method == "POST" and path == "/expenses" and resp.status == 200:
                known["expenses"] = data["id"]
            out.append({
                "t": int(CLOCK[0].timestamp() * 1000), "m": method, "p": path, "b": body,
                "status": resp.status, "res": data,
            })
    finally:
        await client.close()
    return out


def main() -> None:
    seeds = [int(x) for x in sys.argv[1:]] or [1, 2, 3, 4, 5]
    for seed in seeds:
        steps = asyncio.run(record(seed, 1500))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(steps, f, ensure_ascii=False)
            path = f.name
        ok = sum(1 for s in steps if s["status"] == 200)
        print(f"seed {seed}: {len(steps)} ta amal ({ok} ta muvaffaqiyatli, {len(steps) - ok} ta xato kiritish)")
        r = subprocess.run(["node", str(ROOT / "tests" / "crosscheck.js"), path], capture_output=True, text=True,
                           encoding="utf-8")
        print(r.stdout.strip())
        Path(path).unlink(missing_ok=True)
        if r.returncode != 0:
            print(r.stderr.strip())
            raise SystemExit(f"❌ seed {seed}: JS va Python natijalari farq qiladi")
    print("✅ JS va Python bir xil hisobladi")


if __name__ == "__main__":
    main()
