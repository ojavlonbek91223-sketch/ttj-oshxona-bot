"""Bot sozlamalari (.env faylidan o'qiladi)."""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Vergul bilan ajratilgan Telegram ID lar. Bo'sh bo'lsa, botga birinchi
# /start yozgan odam bosh admin bo'ladi.
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}

DB_PATH = Path(os.getenv("DB_PATH") or BASE_DIR / "data" / "oshxona.db")

# Serverda: Postgres manzili (Neon va h.k.). Bo'sh bo'lsa — kompyuterdagi SQLite fayl.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Render serveri o'zi RENDER=true qo'yadi.
ON_RENDER = os.getenv("RENDER", "").lower() == "true"

# Webhook rejimi: Telegram xabarlarni serverga o'zi yuboradi (uxlab qolgan bepul serverni uyg'otadi).
# Kompyuterda — polling (bot o'zi so'rab turadi).
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "1" if ON_RENDER else "0") == "1"

# Boshlang'ich haftalik to'lov. Keyin botdagi Sozlamalar orqali o'zgartiriladi.
DEFAULT_WEEKLY_FEE = int(os.getenv("WEEKLY_FEE", "90000"))

# Yakshanba kuni shu soatdan keyin adminlarga haftalik hisobot + zaxira yuboriladi.
WEEKLY_REPORT_HOUR = int(os.getenv("WEEKLY_REPORT_HOUR", "20"))

# ---------- Telegram Mini App (veb-ilova) ----------
# Ilovaning internetdagi HTTPS manzili, masalan https://app.oshpaz.uz
# Bo'sh bo'lsa, ilova tugmasi botda ko'rsatilmaydi (veb-server baribir ishlaydi).
WEBAPP_URL = (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
WEBAPP_HOST = os.getenv("WEBAPP_HOST") or ("0.0.0.0" if ON_RENDER else "127.0.0.1")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT") or os.getenv("PORT") or "8080")
# Faqat dasturchi uchun: brauzerda http://localhost:8080 ni Telegram'siz ochish.
# Internetga chiqarilgan serverda HECH QACHON yoqmang.
WEBAPP_DEV = os.getenv("WEBAPP_DEV", "") == "1"

# O'zbekiston vaqti (UTC+5, yozgi vaqt yo'q).
TZ = timezone(timedelta(hours=5), "Asia/Tashkent")
