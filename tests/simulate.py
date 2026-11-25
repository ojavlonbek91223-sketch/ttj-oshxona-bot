"""Botni Telegram'siz sinash: soxta server orqali tugmalarni bosib, javoblarni tekshiradi.

Ishga tushirish:  python tests/simulate.py
"""
from __future__ import annotations

import asyncio
import itertools
import sys
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendDocument, SendMessage  # noqa: E402
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

import utils  # noqa: E402
from bot import build_dispatcher  # noqa: E402
from tests._db import fresh_db  # noqa: E402

COOK, STRANGER = 7000000001, 7000000002
_ids = itertools.count(1)

# ---------- vaqtni surish (keyingi haftani sinash uchun) ----------
_real_datetime = utils.datetime
OFFSET = timedelta()


class ShiftedDatetime(_real_datetime):
    @classmethod
    def now(cls, tz=None):
        return _real_datetime.now(tz) + OFFSET


utils.datetime = ShiftedDatetime


# ---------- soxta Telegram server ----------
class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.log: list = []

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.log.append(method)
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot", username="test_bot")
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, (SendMessage, EditMessageText, SendDocument)):
            return Message(
                message_id=next(_ids), date=datetime.now(),
                chat=Chat(id=method.chat_id or COOK, type="private"),
                text=getattr(method, "text", None),
            )
        return True


class Sim:
    def __init__(self):
        self.db = fresh_db()
        self.session = FakeSession()
        self.bot = Bot("123456:TEST", session=self.session,
                       default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = build_dispatcher(self.db)

    def _user(self, uid):
        return User(id=uid, is_bot=False, first_name="Oshpaz" if uid == COOK else "Begona")

    async def say(self, text: str, uid: int = COOK) -> str:
        start = len(self.session.log)
        msg = Message(message_id=next(_ids), date=datetime.now(), chat=Chat(id=uid, type="private"),
                      from_user=self._user(uid), text=text)
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), message=msg))
        return self._out(start)

    async def press(self, label: str, uid: int = COOK) -> str:
        """Oxirgi inline klaviaturadagi `label` ni o'z ichiga olgan tugmani bosish."""
        data = self.find_button(label)
        return await self.press_data(data, uid)

    async def press_data(self, data: str, uid: int = COOK) -> str:
        start = len(self.session.log)
        cq = CallbackQuery(
            id=str(next(_ids)), from_user=self._user(uid), chat_instance="x", data=data,
            message=Message(message_id=next(_ids), date=datetime.now(),
                            chat=Chat(id=uid, type="private"), text="old"),
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), callback_query=cq))
        return self._out(start)

    def _last_kb(self) -> InlineKeyboardMarkup:
        for m in reversed(self.session.log):
            kb = getattr(m, "reply_markup", None)
            if isinstance(kb, InlineKeyboardMarkup):
                return kb
        raise AssertionError("Inline klaviatura yo'q")

    def buttons(self) -> list[str]:
        return [b.text for row in self._last_kb().inline_keyboard for b in row]

    def _find(self, label: str):
        for row in self._last_kb().inline_keyboard:
            for b in row:
                if label in b.text:
                    return b
        raise AssertionError(f"Tugma topilmadi: {label!r}. Bor tugmalar: {self.buttons()}")

    def find_button(self, label: str) -> str:
        return self._find(label).callback_data

    def button_text(self, label: str) -> str:
        return self._find(label).text

    def _out(self, start: int) -> str:
        parts = []
        for m in self.session.log[start:]:
            if isinstance(m, (SendMessage, EditMessageText)):
                parts.append(m.text)
            elif isinstance(m, AnswerCallbackQuery) and m.text:
                parts.append(f"[toast] {m.text}")
            elif isinstance(m, SendDocument):
                parts.append(f"[file] {m.document.filename}")
        return "\n".join(parts)

    def last_document(self) -> bytes:
        for m in reversed(self.session.log):
            if isinstance(m, SendDocument):
                return m.document.data
        raise AssertionError("Fayl yuborilmagan")


def check(cond: bool, what: str, out: str = "") -> None:
    if not cond:
        print(f"\n❌ XATO: {what}\n--- javob ---\n{out}\n-------------")
        raise SystemExit(1)
    print(f"✅ {what}")


async def main() -> None:
    global OFFSET
    s = Sim()

    out = await s.say("/start")
    check("bosh admin" in out, "Birinchi /start yozgan odam bosh admin bo'ladi", out)
    out = await s.say("/start", uid=STRANGER)
    check(str(STRANGER) in out and "faqat oshxona" in out, "Begona odamga ruxsat yo'q, ID ko'rsatiladi", out)

    # --- etajlar ---
    await s.say("👥 Bolalar")
    await s.press("Etaj qo'shish")
    out = await s.say("1\n2\n3-etaj")
    check("1-etaj" in out and "2-etaj" in out and "3-etaj" in out, "Etajlar qo'shildi (raqam → 'N-etaj')", out)
    out = await s.say("1")
    check("Menyudan" in out or "menyudan" in out, "Holat tugagach oddiy matn menyuga yo'naltiradi", out)

    # --- bolalar ---
    await s.say("👥 Bolalar")
    await s.press("Bola qo'shish")
    await s.press("1-etaj")
    out = await s.say("Aliyev Vali, 305\nKarimov Sardor, 305-xona\n1. Toshmatov Jasur\n12345")
    check("3 ta bola qo'shildi" in out and "Tushunilmagan" in out, "Bir yo'la 3 ta bola qo'shildi, noto'g'ri qator ajratildi", out)
    st = s.db.search_students("karimov")[0]
    check(st["room"] == "305", "Xona '305-xona' → '305' ga tozalandi")

    # --- to'lov ---
    out = await s.say("💵 To'lov qabul qilish")
    check(s.button_text("1-etaj") == "🏢 1-etaj — 3 ta · ❌ 3", "Etaj tugmasida qarzdorlar soni", str(s.buttons()))
    await s.press("1-etaj")
    out = await s.press("Aliyev Vali")
    check("Qarz: 90 000 so'm" in out, "Yangi bola shu hafta 90 000 qarz", out)
    out = await s.press("90 000 to'ladi")
    check("qabul qilindi" in out and "qarzi yo'q" in out, "90 000 to'lov yozildi", out)
    check(s.button_text("Aliyev") == "✅ Aliyev Vali", "Ro'yxatda ✅ belgisi chiqdi", str(s.buttons()))
    # ikki marta bosish himoyasi
    await s.press("Aliyev Vali")
    out = await s.press("90 000 to'ladi")
    check("hozirgina yozildi" in out, "Tasodifiy ikkinchi bosish yozilmadi", out)
    check(s.db.total_income() == 90000, "Kassada 90 000")

    # bekor qilish
    await s.press("⬅️ 1-etaj")
    await s.press("Aliyev")
    # duplikat oynasidan chiqish uchun vaqtni 10 soniya suramiz
    OFFSET += timedelta(seconds=10)
    await s.press("90 000 to'ladi")
    out = await s.press("Oxirgi to'lovni bekor qilish")
    check("Bekor qilindi" in out and s.db.total_income() == 90000, "Oxirgi to'lov bekor qilindi", out)

    # boshqa summa
    await s.press("Karimov")
    await s.press("Boshqa summa")
    out = await s.say("45k")
    check("45 000 so'm qabul qilindi" in out and "qolgan qarz: 45 000" in out, "Qisman to'lov (45k)", out)
    check(s.button_text("Karimov") == "🟡 Karimov Sardor", "Qisman to'lovchi 🟡", str(s.buttons()))
    out = await s.say("abc")
    check("menyudan" in out.lower(), "Holat tugagandan keyin noto'g'ri matn", out)

    # ozod
    await s.press("Toshmatov")
    out = await s.press("Bu hafta ozod")
    check("ozod qilindi" in out and "Qarzi yo'q" in out, "Bu hafta ozod → qarz 0", out)

    # menyu tugmasi holatni bekor qiladi
    await s.press("⬅️ 1-etaj")
    await s.press("Karimov")
    await s.press("Boshqa summa")
    out = await s.say("📊 Hisobot")
    check("Haftalik hisobot" in out, "Summa kutilayotganda menyu tugmasi ishlaydi", out)
    out = await s.say("50000")
    check("menyudan" in out.lower() and s.db.total_income() == 135000, "Bekor qilingan amal to'lov yozmadi", out)

    # --- xarajat ---
    await s.say("🛒 Xarajat qo'shish")
    await s.press("Go'sht")
    out = await s.say("350 000")
    check("350 000 so'm" in out, "Xarajat summasi o'qildi", out)
    out = await s.say("5 kg mol go'shti")
    check("Xarajat yozildi" in out and "5 kg mol go&#x27;shti" in out or "5 kg mol go'shti" in out, "Xarajat izoh bilan saqlandi", out)
    await s.say("🛒 Xarajat qo'shish")
    await s.press("Non")
    await s.say("50k")
    out = await s.press("Izohsiz saqlash")
    check("Xarajat yozildi" in out and "400 000" in out, "Izohsiz xarajat, haftalik jami 400 000", out)
    out = await s.press("Bekor qilish")
    check("O'chirildi" in out and s.db.total_expense() == 350000, "Xarajat bekor qilindi", out)

    # --- hisobot ---
    out = await s.say("📊 Hisobot")
    check("Kirim: 135 000 so'm" in out and "Chiqim: 350 000 so'm" in out and "Farq: -215 000" in out,
          "Haftalik hisobot: kirim/chiqim/farq", out)
    out = await s.press("Kassa")
    check("Kassada bo'lishi kerak: -215 000" in out, "Kassa qoldig'i", out)
    out = await s.press("Haftalik hisobot")
    out = await s.press("Oylik hisobot")
    check("Oylik hisobot" in out, "Oylik hisobot", out)
    out = await s.press("Oldingi oy")
    check("Kirim: 0 so'm" in out, "O'tgan oy bo'sh", out)

    out = await s.say("❗ Qarzdorlar")
    check("Karimov Sardor (305) — 45 000" in out and "Aliyev" not in out and "Jami: <b>1 ta</b>" in out,
          "Qarzdorlar ro'yxati", out)

    # --- Excel ---
    await s.say("📊 Hisobot")
    out = await s.press("Excel")
    check("[file]" in out and ".xlsx" in out, "Excel fayl yuborildi", out)
    wb = load_workbook(BytesIO(s.last_document()))
    check(wb.sheetnames == ["Xulosa", "Bolalar", "Haftalik jadval", "To'lovlar", "Xarajatlar", "Haftalar"],
          f"Excel varaqlari: {wb.sheetnames}")
    check(wb["To'lovlar"].max_row == 3, "Excel: 2 ta to'lov")

    # --- sozlamalar ---
    await s.say("⚙️ Sozlamalar")
    await s.press("Haftalik to'lovni")
    await s.say("100 000")
    out = await s.press("Keyingi haftadan")
    check("100 000" in out and "Keyingi haftadan" in out, "Haftalik to'lov keyingi haftadan 100 000", out)
    await s.press("Boshlang'ich kassa")
    out = await s.say("500000")
    check("500 000" in out, "Boshlang'ich kassa 500 000", out)
    out = await s.press("Zaxira nusxa")
    if s.db.is_pg:
        import json
        dump = json.loads(s.last_document())
        check(".json" in out and len(dump["tables"]["students"]) == 3 and len(dump["tables"]["payments"]) == 2,
              "Zaxira (Postgres → JSON fayl) yuborildi", out)
    else:
        check(".db" in out and s.last_document()[:15] == b"SQLite format 3", "Zaxira (SQLite fayl) yuborildi", out)
    await s.press("Adminlar")
    await s.press("Admin qo'shish")
    out = await s.say("12")
    check("faqat raqamlardan" in out, "Noto'g'ri ID rad etildi", out)
    out = await s.say(str(STRANGER))
    check("admin qilindi" in out, "Yangi admin qo'shildi", out)
    out = await s.say("/start", uid=STRANGER)
    check("xush kelibsiz" in out, "Yangi admin endi foydalana oladi", out)

    # --- keyingi hafta ---
    OFFSET += timedelta(days=7)
    out = await s.say("❗ Qarzdorlar")
    check("Aliyev Vali (305) — 100 000" in out, "Keyingi hafta: Aliyev 100 000 (yangi summa)", out)
    check("Karimov Sardor (305) — 145 000" in out, "Karimov: eski 45 000 + 100 000", out)
    check("Toshmatov Jasur — 100 000" in out, "Toshmatov: ozod hafta hisoblanmadi", out)

    # chiqib ketdi / qaytib keldi
    await s.say("💵 To'lov qabul qilish")
    await s.press("1-etaj")
    await s.press("Toshmatov")
    await s.press("Tahrirlash")
    await s.press("chiqib ketdi")
    out = await s.press("Ha, chiqib ketdi")
    check("ro'yxatdan chiqarildi" in out and not any("Toshmatov" in b for b in s.buttons()),
          "Bola ro'yxatdan chiqdi", out)
    OFFSET += timedelta(days=14)  # 2 hafta yo'q edi
    await s.say("👥 Bolalar")
    await s.press("Chiqib ketganlar")
    out = await s.press("Toshmatov")
    check("Chiqib ketgan" in out and "Qarz: 100 000" in out, "Chiqib ketgandan keyin qarz o'smaydi", out)
    out = await s.press("Qaytib keldi")
    check("Qarz: 200 000" in out, "Qaytib keldi: oradagi haftalar ozod, faqat joriy hafta qo'shildi", out)

    # tahrirlash: eski qarz, ism
    await s.press("Tahrirlash")
    await s.press("Daftardagi eski qarz")
    out = await s.say("50000")
    check("Qarz: 250 000" in out and "Daftardagi eski qarz: 50 000" in out, "Daftardagi eski qarz qo'shildi", out)
    await s.press("Tahrirlash")
    await s.press("Ism-familiya")
    out = await s.say("Toshmatov  Jasurbek")
    check("Toshmatov Jasurbek" in out, "Ism o'zgardi", out)
    await s.press("Tahrirlash")
    await s.press("Etajni almashtirish")
    out = await s.press("2-etaj")
    check("2-etaj ga ko'chirildi" in out, "Etaj almashtirildi", out)

    # qidiruv, tarix, to'lovni o'chirish
    await s.say("💵 To'lov qabul qilish")
    await s.press("qidirish")
    out = await s.say("sard")
    check("1 ta topildi" in out, "Qidiruv ishladi", out)
    await s.press("Karimov")
    out = await s.press("Tarix")
    check("45 000 so'm" in out, "To'lovlar tarixi", out)
    await s.press("🗑")
    out = await s.press("Ha, o'chirish")
    check("Bekor qilindi" in out and "Hali to'lov yo'q" in out, "Tarixdan to'lov o'chirildi", out)

    # bo'sh bo'lmagan etajni o'chirib bo'lmaydi
    await s.say("👥 Bolalar")
    await s.press("Etajlarni sozlash")
    out = await s.press_data(s.find_button("🗑"))
    check("bolalar bor" in out, "Bolasi bor etaj o'chirilmaydi", out)

    # eskirgan tugma
    out = await s.press_data("zzz:1")
    check("eskirgan" in out, "Noma'lum tugma — tushunarli xabar", out)

    # ko'p bolali etaj (sahifalash)
    f = s.db.add_floor("9-etaj")
    for i in range(45):
        s.db.add_student(f"Talaba {i:02d}", f)
    await s.say("💵 To'lov qabul qilish")
    out = await s.press("9-etaj")
    check("1/2" in s.buttons() and not any("Talaba 44" in b for b in s.buttons()),
          "45 ta bola: 1-sahifada 30 ta, sahifalash bor", str(s.buttons()))
    out = await s.press("▶️")
    check("2/2" in s.buttons() and any("Talaba 44" in b for b in s.buttons()), "2-sahifa ochildi")

    # avtomatik haftalik hisobot
    from jobs import send_weekly_report
    before = len(s.session.log)
    await send_weekly_report(s.bot, s.db)
    sent = s.session.log[before:]
    check(sum(isinstance(m, SendDocument) for m in sent) == 4 and sum(isinstance(m, SendMessage) for m in sent) == 2,
          "Yakshanba hisoboti 2 adminga (matn + Excel + zaxira)")

    print("\n🎉 Hamma tekshiruvlar o'tdi.")


if __name__ == "__main__":
    asyncio.run(main())
