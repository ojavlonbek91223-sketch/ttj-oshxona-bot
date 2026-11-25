"""Ilovani brauzerda Telegram'siz ko'rish uchun demo-server (namuna ma'lumotlar, xotirada).

Ishga tushirish:  python tests/dev_server.py   ->  http://localhost:8090
Haqiqiy bazaga tegmaydi. Internetga chiqarmang.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp import web  # noqa: E402

import config  # noqa: E402
from db import Database  # noqa: E402
from webserver import build_app  # noqa: E402

config.WEBAPP_DEV = True
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090


class NoBot:
    async def send_document(self, *a, **k):
        print("[demo] send_document", a[0])

    async def send_message(self, *a, **k):
        print("[demo] send_message", a[0])


def seed(db: Database) -> None:
    random.seed(7)
    db.add_admin(1, "Demo oshpaz")
    first = ["Ali", "Vali", "Sardor", "Jasur", "Bekzod", "Otabek", "Diyor", "Sanjar", "Javohir", "Shoxrux",
             "Aziz", "Bobur", "Islom", "Ulug'bek", "Doston", "Firdavs", "Muhammad", "Abdulloh"]
    last = ["Aliyev", "Karimov", "Toshmatov", "Rahimov", "Nazarov", "Yusupov", "Ergashev", "Qodirov",
            "Sobirov", "Xolmatov", "Mirzayev", "Usmonov"]
    for f in range(1, 4):
        fid = db.add_floor(f"{f}-etaj")
        for i in range(7):
            sid = db.add_student(f"{random.choice(last)} {random.choice(first)}", fid, str(f * 100 + 1 + i // 2))
            r = random.random()
            if r < 0.5:
                db.add_payment(sid, 90000)
            elif r < 0.65:
                db.add_payment(sid, 45000)
            elif r < 0.72:
                from utils import week_start
                db.toggle_exemption(sid, week_start())
    db.add_expense("🥩 Go'sht", 850000, "10 kg mol go'shti")
    db.add_expense("🍚 Guruch, un, don", 420000, "30 kg guruch")
    db.add_expense("🛢 Yog'", 180000, "10 l paxta yog'i")
    db.add_expense("🥕 Sabzavot, meva", 150000, "sabzi, piyoz, kartoshka")
    db.add_expense("🍞 Non", 96000, None)
    db.set_setting("opening_cash", 300000)


if __name__ == "__main__":
    database = Database(":memory:", 90000)
    seed(database)
    print(f"Demo: http://localhost:{PORT}")
    web.run_app(build_app(database, NoBot()), host="127.0.0.1", port=PORT, print=None)
