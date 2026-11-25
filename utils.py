"""Yordamchi funksiyalar: sana, hafta, pul formatlash, summa o'qish."""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta

from config import TZ

MONTHS = [
    "", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]
DT_FMT = "%Y-%m-%d %H:%M:%S"


# ---------- vaqt ----------
def now() -> datetime:
    return datetime.now(TZ)


def now_str() -> str:
    return now().strftime(DT_FMT)


def today() -> date:
    return now().date()


def week_start(d: date | None = None) -> date:
    """Haftaning dushanbasi."""
    d = d or today()
    return d - timedelta(days=d.weekday())


def week_label(ws: date) -> str:
    """23–29 noyabr  yoki  30 noyabr – 6 dekabr"""
    we = ws + timedelta(days=6)
    if ws.month == we.month:
        return f"{ws.day}–{we.day} {MONTHS[ws.month]}"
    return f"{ws.day} {MONTHS[ws.month]} – {we.day} {MONTHS[we.month]}"


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    """Oyning 1-sanasi uchun n oy qo'shish/ayirish."""
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def month_label(d: date) -> str:
    return f"{MONTHS[d.month].capitalize()} {d.year}"


def fmt_dt(s: str) -> str:
    """'2026-11-24 14:05:33' -> '24.11.2026 14:05'"""
    try:
        return datetime.strptime(s, DT_FMT).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return s or ""


def fmt_date(s: str) -> str:
    """'2026-11-24' -> '24.11.2026'"""
    try:
        return date.fromisoformat(s[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return s or ""


def short_date(s: str) -> str:
    """'2026-11-24 ...' -> '24.11'"""
    try:
        return date.fromisoformat(s[:10]).strftime("%d.%m")
    except (TypeError, ValueError):
        return s or ""


# ---------- pul ----------
def num(n: int) -> str:
    """90000 -> '90 000'"""
    s = f"{abs(int(n)):,}".replace(",", " ")
    return f"-{s}" if n < 0 else s


def money(n: int) -> str:
    return f"{num(n)} so'm"


def short_money(n: int) -> str:
    """90000 -> '90k', 45500 -> '45.5k', 1200000 -> '1.2mln'"""
    a = abs(n)
    if a >= 1_000_000:
        s = f"{a / 1_000_000:.1f}".rstrip("0").rstrip(".") + "mln"
    elif a >= 1000:
        s = f"{a / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    else:
        s = str(a)
    return f"-{s}" if n < 0 else s


_AMOUNT_RE = re.compile(r"^([\d\s.,]+?)\s*(k|к|ming|минг|тыс|mln|million|млн)?\.?$")


def parse_amount(text: str) -> int | None:
    """'90000', '90 000', '90.000', '90k', '90 ming', '1.5 mln' -> int. Noto'g'ri bo'lsa None."""
    t = (text or "").lower().replace(" ", " ")
    for w in ("so'm", "so‘m", "soʻm", "сўм", "сум", "som", "sum"):
        t = t.replace(w, "")
    t = t.strip()
    m = _AMOUNT_RE.match(t)
    if not m:
        return None
    digits, suffix = m.group(1).replace(" ", ""), m.group(2)
    if suffix:
        mult = 1_000_000 if suffix in ("mln", "million", "млн") else 1000
        try:
            n = round(float(digits.replace(",", ".")) * mult)
        except ValueError:
            return None
    else:
        digits = digits.replace(",", "").replace(".", "")
        if not digits.isdigit():
            return None
        n = int(digits)
    return n if 0 < n <= 1_000_000_000 else None


def esc(s) -> str:
    # Matn ichida faqat & < > ni kodlash kifoya (atributlarga foydalanuvchi matni qo'yilmaydi).
    return html.escape(str(s if s is not None else ""), quote=False)


_HAS_LETTER = re.compile(r"[^\W\d_]")


def clean_room(room: str | None) -> str | None:
    if not room:
        return None
    return re.sub(r"[-\s]*xona$", "", room.strip(), flags=re.IGNORECASE).strip()[:16] or None


def parse_student_line(raw: str) -> tuple[str, str | None] | None:
    """'1. Aliyev Vali, 305-xona' -> ('Aliyev Vali', '305'). Ism bo'lmasa None."""
    line = re.sub(r"^\s*(\d+[.)]|[•\-–—*])\s*", "", raw).strip()
    if not line:
        return None
    name, room = line, None
    if "," in line:
        name, room = (x.strip() for x in line.rsplit(",", 1))
        room = clean_room(room)
    name = " ".join(name.split())
    if not (2 <= len(name) <= 64) or not _HAS_LETTER.search(name):
        return None
    return name, room


def floor_name(raw: str) -> str:
    """'1' -> '1-etaj', aks holda bo'shliqlari tozalangan nom."""
    name = " ".join(raw.split())[:32]
    return f"{name}-etaj" if name.isdigit() else name


def floor_sort_key(name: str) -> int:
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 999


def chunk_lines(lines: list[str], limit: int = 3800) -> list[str]:
    """Uzun matnni Telegram chegarasiga (4096) sig'adigan bo'laklarga bo'lish."""
    parts, cur, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > limit and cur:
            parts.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts
