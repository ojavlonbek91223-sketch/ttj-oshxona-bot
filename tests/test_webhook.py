"""Server (webhook) rejimi sinovi: Telegram yuborgan /start ni qabul qilish va /health.

Ishga tushirish:  python tests/test_webhook.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402
from aiogram.webhook.aiohttp_server import SimpleRequestHandler  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import config  # noqa: E402

config.BOT_TOKEN = "123456:TEST-TOKEN"

from bot import build_dispatcher  # noqa: E402
from tests._db import fresh_db  # noqa: E402
from tests.simulate import FakeSession  # noqa: E402
from webserver import WEBHOOK_PATH, build_app, webhook_secret  # noqa: E402


def check(cond, what, extra=""):
    if not cond:
        print(f"\n❌ XATO: {what}\n{extra}")
        raise SystemExit(1)
    print(f"✅ {what}")


START = {
    "update_id": 1001,
    "message": {
        "message_id": 1, "date": 1764000000, "text": "/start",
        "chat": {"id": 7000000001, "type": "private"},
        "from": {"id": 7000000001, "is_bot": False, "first_name": "Oshpaz"},
        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
    },
}


async def main():
    db = fresh_db()
    session = FakeSession()
    bot = Bot(config.BOT_TOKEN, session=session)
    dp = build_dispatcher(db)
    app = build_app(db, bot)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=webhook_secret()).register(app, path=WEBHOOK_PATH)
    client = TestClient(TestServer(app))
    await client.start_server()

    r = await client.get("/health")
    check(r.status == 200 and (await r.json())["ok"], "/health ishlaydi")
    r = await client.get("/health?db=1")
    check((await r.json()).get("db_ok"), "/health?db=1 — baza ulanadi")

    r = await client.post(WEBHOOK_PATH, json=START)
    check(r.status == 401, "Maxfiy kalitsiz webhook rad etildi", r.status)
    r = await client.post(WEBHOOK_PATH, json=START, headers={"X-Telegram-Bot-Api-Secret-Token": "noto'g'ri"})
    check(r.status == 401, "Noto'g'ri kalit rad etildi", r.status)

    r = await client.post(WEBHOOK_PATH, json=START, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret()})
    check(r.status == 200, "To'g'ri kalit bilan /start qabul qilindi", r.status)
    for _ in range(50):  # xabar fonda qayta ishlanadi
        if any(isinstance(m, SendMessage) for m in session.log):
            break
        await asyncio.sleep(0.05)
    sent = [m.text for m in session.log if isinstance(m, SendMessage)]
    check(sent and "bosh admin" in sent[0], "Bot javob berdi va yozgan odam bosh admin bo'ldi", sent)
    check(db.is_admin(7000000001), "Admin bazaga yozildi")

    await client.close()
    print("\n🎉 Webhook: hamma tekshiruvlar o'tdi.")


if __name__ == "__main__":
    asyncio.run(main())
