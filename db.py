"""Ma'lumotlar bazasi: kompyuterda SQLite, serverda Postgres (DATABASE_URL bo'lsa).

Hisob-kitob mantig'i:
  * Har bir bola har hafta (dushanbadan) haftalik to'lovga qarzdor bo'ladi.
  * Kutilgan summa = eski qarz + (ro'yxatga olingan haftadan joriy haftagacha,
    ozod haftalardan tashqari, har haftaning to'lovi).
  * Qarz = kutilgan summa - jami to'lagan. Manfiy bo'lsa — oldindan to'lagan.

SQL bir xil yoziladi (`?` belgilari bilan); Postgres uchun avtomatik `%s` ga
almashtiriladi. Sana/vaqtlar matn ko'rinishida saqlanadi (YYYY-MM-DD ...).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
from bisect import bisect_right
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from utils import floor_sort_key, now, now_str, today, week_start

log = logging.getLogger(__name__)

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    tg_id    INTEGER PRIMARY KEY,
    name     TEXT,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS fee_history (
    week_start TEXT PRIMARY KEY,
    amount     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS floors (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sort INTEGER NOT NULL DEFAULT 999
);
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name    TEXT NOT NULL,
    floor_id     INTEGER NOT NULL REFERENCES floors(id),
    room         TEXT,
    phone        TEXT,
    joined_week  TEXT NOT NULL,
    left_week    TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    opening_debt INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_students_floor ON students(floor_id, active);
CREATE TABLE IF NOT EXISTS payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    amount     INTEGER NOT NULL,
    paid_at    TEXT NOT NULL,
    added_by   INTEGER,
    note       TEXT
);
CREATE INDEX IF NOT EXISTS ix_payments_student ON payments(student_id);
CREATE INDEX IF NOT EXISTS ix_payments_date ON payments(paid_at);
CREATE TABLE IF NOT EXISTS exemptions (
    student_id INTEGER NOT NULL REFERENCES students(id),
    week_start TEXT NOT NULL,
    PRIMARY KEY (student_id, week_start)
);
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    description TEXT,
    amount      INTEGER NOT NULL,
    spent_at    TEXT NOT NULL,
    added_by    INTEGER,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(spent_at);
"""

# Telegram ID lari 32-bitga sig'maydi — Postgres'da BIGINT.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    tg_id    BIGINT PRIMARY KEY,
    name     TEXT,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS fee_history (
    week_start TEXT PRIMARY KEY,
    amount     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS floors (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    sort INTEGER NOT NULL DEFAULT 999
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_floors_name ON floors (lower(name));
CREATE TABLE IF NOT EXISTS students (
    id           SERIAL PRIMARY KEY,
    full_name    TEXT NOT NULL,
    floor_id     INTEGER NOT NULL REFERENCES floors(id),
    room         TEXT,
    phone        TEXT,
    joined_week  TEXT NOT NULL,
    left_week    TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    opening_debt INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_students_floor ON students(floor_id, active);
CREATE TABLE IF NOT EXISTS payments (
    id         SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    amount     INTEGER NOT NULL,
    paid_at    TEXT NOT NULL,
    added_by   BIGINT,
    note       TEXT
);
CREATE INDEX IF NOT EXISTS ix_payments_student ON payments(student_id);
CREATE INDEX IF NOT EXISTS ix_payments_date ON payments(paid_at);
CREATE TABLE IF NOT EXISTS exemptions (
    student_id INTEGER NOT NULL REFERENCES students(id),
    week_start TEXT NOT NULL,
    PRIMARY KEY (student_id, week_start)
);
CREATE TABLE IF NOT EXISTS expenses (
    id          SERIAL PRIMARY KEY,
    category    TEXT NOT NULL,
    description TEXT,
    amount      INTEGER NOT NULL,
    spent_at    TEXT NOT NULL,
    added_by    BIGINT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(spent_at);
"""

TABLES = ["admins", "settings", "fee_history", "floors", "students", "payments", "exemptions", "expenses"]
WEEK = timedelta(days=7)
_STUDENT_SELECT = (
    "SELECT s.*, f.name AS floor_name, f.sort AS floor_sort "
    "FROM students s JOIN floors f ON f.id = s.floor_id"
)
_STUDENT_ORDER = " ORDER BY f.sort, f.name, lower(s.full_name)"


@dataclass
class Balance:
    expected: int = 0      # jami to'lashi kerak edi
    paid: int = 0          # jami to'lagan
    paid_week: int = 0     # shu hafta to'lagan
    exempt_now: bool = False

    @property
    def debt(self) -> int:
        """Musbat — qarz, manfiy — oldindan to'lagan."""
        return self.expected - self.paid


class Row:
    """Postgres qatori: sqlite3.Row kabi row[0] ham, row['nomi'] ham ishlaydi."""
    __slots__ = ("_index", "_values")

    def __init__(self, index: dict[str, int], values):
        self._index = index
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._index)


def _pg_row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    index = {n: i for i, n in enumerate(names)}
    return lambda values: Row(index, values)


class Database:
    def __init__(self, path: Path | str = "", default_fee: int = 90000, url: str | None = None):
        self.default_fee = default_fee
        self.url = url or ""
        self.is_pg = self.url.startswith(("postgres://", "postgresql://"))
        self._pg = None
        self._pg_used = 0.0
        if self.is_pg:
            import psycopg  # faqat serverda kerak
            self._psycopg = psycopg
            self.IntegrityError = psycopg.IntegrityError
            self.kind = "postgres"
            with self._tx() as cur:
                for stmt in POSTGRES_SCHEMA.split(";"):
                    if stmt.strip():
                        cur.execute(stmt)
        else:
            path = Path(path or "data/oshxona.db")
            if str(path) != ":memory:":
                path.parent.mkdir(parents=True, exist_ok=True)
            self.path = path
            self.IntegrityError = sqlite3.IntegrityError
            self.kind = "sqlite"
            self.conn = sqlite3.connect(str(path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.executescript(SQLITE_SCHEMA)
            self.conn.commit()
        if not self._one("SELECT 1 FROM fee_history LIMIT 1"):
            # 2000-01-03 — dushanba; "boshidan beri shu summa" degani.
            self._exec("INSERT INTO fee_history(week_start, amount) VALUES (?, ?)", ("2000-01-03", default_fee))

    # ---------- ulanish (Postgres) ----------
    def _pg_conn(self):
        if self._pg is None or self._pg.closed:
            self._pg = self._psycopg.connect(self.url, autocommit=True, row_factory=_pg_row_factory,
                                             connect_timeout=15)
        self._pg_used = time.monotonic()
        return self._pg

    def close_if_idle(self, seconds: int = 120) -> None:
        """Bo'sh turgan Postgres ulanishini yopish (Neon bepul serveri uxlashi uchun)."""
        if self._pg is not None and not self._pg.closed and time.monotonic() - self._pg_used > seconds:
            try:
                self._pg.close()
            except Exception:
                pass
            self._pg = None

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.is_pg else sql

    def _run(self, sql: str, params=()):
        """Bitta so'rov; Postgres ulanishi uzilgan bo'lsa bir marta qayta ulanadi."""
        if not self.is_pg:
            return self.conn.execute(sql, params)
        for attempt in (1, 2):
            try:
                return self._pg_conn().execute(self._sql(sql), params)
            except self._psycopg.OperationalError:
                if attempt == 2:
                    raise
                log.warning("Postgres ulanishi uzildi — qayta ulanilmoqda")
                self._pg = None

    # ---------- past darajadagi yordamchilar ----------
    def _q(self, sql: str, params=()) -> list:
        return self._run(sql, params).fetchall()

    def _one(self, sql: str, params=()):
        return self._run(sql, params).fetchone()

    def _exec(self, sql: str, params=()):
        cur = self._run(sql, params)
        if not self.is_pg:
            self.conn.commit()
        return cur

    def _insert(self, sql: str, params=()) -> int:
        """INSERT qilib, yangi qatorning id sini qaytaradi."""
        if self.is_pg:
            return self._one(sql + " RETURNING id", params)[0]
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    @contextmanager
    def _tx(self):
        """Bir nechta so'rovni bitta tranzaksiyada bajarish. cur.execute(sql, params)."""
        if self.is_pg:
            conn = self._pg_conn()
            with conn.transaction():
                yield _PgTxCursor(conn, self._sql)
        else:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    # ---------- adminlar ----------
    def is_admin(self, tg_id: int) -> bool:
        return self._one("SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,)) is not None

    def admin_count(self) -> int:
        return self._one("SELECT COUNT(*) FROM admins")[0]

    def add_admin(self, tg_id: int, name: str | None = None) -> None:
        self._exec(
            "INSERT INTO admins(tg_id, name, added_at) VALUES (?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET name = COALESCE(excluded.name, admins.name)",
            (tg_id, name, now_str()),
        )

    def remove_admin(self, tg_id: int) -> None:
        self._exec("DELETE FROM admins WHERE tg_id = ?", (tg_id,))

    def list_admins(self) -> list:
        return self._q("SELECT * FROM admins ORDER BY added_at")

    # ---------- sozlamalar ----------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._one("SELECT value FROM settings WHERE key = ?", (key,))
        return row[0] if row else default

    def set_setting(self, key: str, value) -> None:
        self._exec(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def opening_cash(self) -> int:
        return int(self.get_setting("opening_cash", "0") or 0)

    # ---------- haftalik to'lov summasi ----------
    def fee_getter(self):
        rows = self._q("SELECT week_start, amount FROM fee_history ORDER BY week_start")
        keys = [date.fromisoformat(r[0]) for r in rows]
        vals = [r[1] for r in rows]

        def get(w: date) -> int:
            i = bisect_right(keys, w) - 1
            return vals[i] if i >= 0 else self.default_fee

        return get

    def fee_for(self, w: date) -> int:
        return self.fee_getter()(w)

    def current_fee(self) -> int:
        return self.fee_for(week_start())

    def next_fee(self) -> int:
        return self.fee_for(week_start() + WEEK)

    def set_fee(self, amount: int, from_week: date) -> None:
        with self._tx() as cur:
            cur.execute("DELETE FROM fee_history WHERE week_start >= ?", (from_week.isoformat(),))
            cur.execute("INSERT INTO fee_history(week_start, amount) VALUES (?, ?)",
                        (from_week.isoformat(), amount))

    # ---------- etajlar ----------
    def add_floor(self, name: str) -> int | None:
        try:
            return self._insert("INSERT INTO floors(name, sort) VALUES (?, ?)", (name, floor_sort_key(name)))
        except self.IntegrityError:
            return None

    def list_floors(self) -> list:
        return self._q(
            "SELECT f.id, f.name, "
            "(SELECT COUNT(*) FROM students s WHERE s.floor_id = f.id AND s.active = 1) AS cnt, "
            "(SELECT COUNT(*) FROM students s WHERE s.floor_id = f.id) AS total "
            "FROM floors f ORDER BY f.sort, f.name"
        )

    def get_floor(self, floor_id: int):
        return self._one("SELECT * FROM floors WHERE id = ?", (floor_id,))

    def rename_floor(self, floor_id: int, name: str) -> bool:
        try:
            self._exec("UPDATE floors SET name = ?, sort = ? WHERE id = ?",
                       (name, floor_sort_key(name), floor_id))
            return True
        except self.IntegrityError:
            return False

    def floor_student_total(self, floor_id: int) -> int:
        return self._one("SELECT COUNT(*) FROM students WHERE floor_id = ?", (floor_id,))[0]

    def delete_floor(self, floor_id: int) -> bool:
        if self.floor_student_total(floor_id):
            return False
        self._exec("DELETE FROM floors WHERE id = ?", (floor_id,))
        return True

    # ---------- bolalar ----------
    def add_student(self, full_name: str, floor_id: int, room: str | None = None,
                    phone: str | None = None) -> int:
        return self._insert(
            "INSERT INTO students(full_name, floor_id, room, phone, joined_week, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (full_name, floor_id, room, phone, week_start().isoformat(), now_str()),
        )

    def get_student(self, sid: int):
        return self._one(_STUDENT_SELECT + " WHERE s.id = ?", (sid,))

    def list_students(self, floor_id: int | None = None, active: bool | None = True) -> list:
        sql, params = _STUDENT_SELECT + " WHERE 1=1", []
        if active is not None:
            sql += " AND s.active = ?"
            params.append(1 if active else 0)
        if floor_id is not None:
            sql += " AND s.floor_id = ?"
            params.append(floor_id)
        return self._q(sql + _STUDENT_ORDER, params)

    def count_inactive(self) -> int:
        return self._one("SELECT COUNT(*) FROM students WHERE active = 0")[0]

    def search_students(self, query: str, limit: int = 30) -> list:
        q = query.casefold().strip()
        if not q:
            return []
        rows = self._q(_STUDENT_SELECT + " ORDER BY s.active DESC, lower(s.full_name)")
        found = [
            r for r in rows
            if q in r["full_name"].casefold() or (r["room"] and q == str(r["room"]).casefold())
        ]
        return found[:limit]

    def same_name_exists(self, floor_id: int, name: str) -> bool:
        return any(
            r["full_name"].casefold() == name.casefold()
            for r in self.list_students(floor_id=floor_id)
        )

    _EDITABLE = {"full_name", "floor_id", "room", "phone", "opening_debt"}

    def update_student(self, sid: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in self._EDITABLE}
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE students SET {cols} WHERE id = ?", (*fields.values(), sid))

    def deactivate_student(self, sid: int) -> None:
        """Chiqib ketdi: joriy haftagacha hisoblanadi, keyingisidan to'xtaydi."""
        self._exec("UPDATE students SET active = 0, left_week = ? WHERE id = ?",
                   (week_start().isoformat(), sid))

    def reactivate_student(self, sid: int) -> None:
        """Qaytib keldi: yo'q bo'lgan haftalar ozod hisoblanadi."""
        s = self.get_student(sid)
        if not s:
            return
        cur_week = week_start()
        with self._tx() as cur:
            if s["left_week"]:
                w = date.fromisoformat(s["left_week"]) + WEEK
                while w < cur_week:
                    cur.execute(
                        "INSERT INTO exemptions(student_id, week_start) VALUES (?, ?) ON CONFLICT DO NOTHING",
                        (sid, w.isoformat()),
                    )
                    w += WEEK
            cur.execute("UPDATE students SET active = 1, left_week = NULL WHERE id = ?", (sid,))

    def student_payment_count(self, sid: int) -> int:
        return self._one("SELECT COUNT(*) FROM payments WHERE student_id = ?", (sid,))[0]

    def delete_student(self, sid: int) -> bool:
        """Faqat to'lovi yo'q (xato kiritilgan) bolani butunlay o'chirish."""
        if self.student_payment_count(sid):
            return False
        with self._tx() as cur:
            cur.execute("DELETE FROM exemptions WHERE student_id = ?", (sid,))
            cur.execute("DELETE FROM students WHERE id = ?", (sid,))
        return True

    # ---------- ozod haftalar ----------
    def toggle_exemption(self, sid: int, w: date) -> bool:
        """True — endi ozod, False — ozodlik bekor qilindi."""
        key = (sid, w.isoformat())
        if self._one("SELECT 1 FROM exemptions WHERE student_id = ? AND week_start = ?", key):
            self._exec("DELETE FROM exemptions WHERE student_id = ? AND week_start = ?", key)
            return False
        self._exec("INSERT INTO exemptions(student_id, week_start) VALUES (?, ?) ON CONFLICT DO NOTHING", key)
        return True

    def student_exemptions(self, sid: int) -> list[date]:
        return [
            date.fromisoformat(r[0])
            for r in self._q("SELECT week_start FROM exemptions WHERE student_id = ? ORDER BY week_start", (sid,))
        ]

    def all_exemptions(self) -> dict[int, set[date]]:
        ex: dict[int, set[date]] = defaultdict(set)
        for r in self._q("SELECT student_id, week_start FROM exemptions"):
            ex[r[0]].add(date.fromisoformat(r[1]))
        return ex

    # ---------- to'lovlar ----------
    def add_payment(self, sid: int, amount: int, added_by: int | None = None, note: str | None = None) -> int:
        return self._insert(
            "INSERT INTO payments(student_id, amount, paid_at, added_by, note) VALUES (?, ?, ?, ?, ?)",
            (sid, amount, now_str(), added_by, note),
        )

    def recent_duplicate(self, sid: int, amount: int, seconds: int = 8) -> bool:
        """Tugmani tasodifan ikki marta bosishdan himoya."""
        since = (now() - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")
        return self._one(
            "SELECT 1 FROM payments WHERE student_id = ? AND amount = ? AND paid_at >= ?",
            (sid, amount, since),
        ) is not None

    def get_payment(self, pid: int):
        return self._one(
            "SELECT p.*, s.full_name, s.floor_id, s.active, f.name AS floor_name "
            "FROM payments p JOIN students s ON s.id = p.student_id "
            "JOIN floors f ON f.id = s.floor_id WHERE p.id = ?",
            (pid,),
        )

    def delete_payment(self, pid: int):
        row = self.get_payment(pid)
        if row:
            self._exec("DELETE FROM payments WHERE id = ?", (pid,))
        return row

    def student_payments(self, sid: int, limit: int = 15) -> list:
        return self._q(
            "SELECT * FROM payments WHERE student_id = ? ORDER BY paid_at DESC, id DESC LIMIT ?",
            (sid, limit),
        )

    def income_between(self, d1: date, d2: date) -> tuple[int, int]:
        """[d1, d2) oralig'idagi kirim: (summa, to'lovlar soni)."""
        r = self._one(
            "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM payments WHERE paid_at >= ? AND paid_at < ?",
            (d1.isoformat(), d2.isoformat()),
        )
        return int(r[0]), int(r[1])

    def income_by_floor(self, d1: date, d2: date) -> list:
        return self._q(
            "SELECT f.name, SUM(p.amount) AS total FROM payments p "
            "JOIN students s ON s.id = p.student_id JOIN floors f ON f.id = s.floor_id "
            "WHERE p.paid_at >= ? AND p.paid_at < ? GROUP BY f.id, f.name, f.sort ORDER BY f.sort, f.name",
            (d1.isoformat(), d2.isoformat()),
        )

    def all_payments(self) -> list:
        return self._q(
            "SELECT p.*, s.full_name, f.name AS floor_name FROM payments p "
            "JOIN students s ON s.id = p.student_id JOIN floors f ON f.id = s.floor_id "
            "ORDER BY p.paid_at DESC, p.id DESC"
        )

    def total_income(self) -> int:
        return int(self._one("SELECT COALESCE(SUM(amount), 0) FROM payments")[0])

    # ---------- xarajatlar ----------
    def add_expense(self, category: str, amount: int, description: str | None = None,
                    added_by: int | None = None, spent_at: date | None = None) -> int:
        return self._insert(
            "INSERT INTO expenses(category, description, amount, spent_at, added_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (category, description, amount, (spent_at or today()).isoformat(), added_by, now_str()),
        )

    def get_expense(self, eid: int):
        return self._one("SELECT * FROM expenses WHERE id = ?", (eid,))

    def delete_expense(self, eid: int):
        row = self.get_expense(eid)
        if row:
            self._exec("DELETE FROM expenses WHERE id = ?", (eid,))
        return row

    def recent_expenses(self, limit: int = 10) -> list:
        return self._q("SELECT * FROM expenses ORDER BY spent_at DESC, id DESC LIMIT ?", (limit,))

    def expense_between(self, d1: date, d2: date) -> tuple[int, int]:
        r = self._one(
            "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM expenses WHERE spent_at >= ? AND spent_at < ?",
            (d1.isoformat(), d2.isoformat()),
        )
        return int(r[0]), int(r[1])

    def expense_by_category(self, d1: date, d2: date) -> list:
        return self._q(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE spent_at >= ? AND spent_at < ? GROUP BY category ORDER BY total DESC",
            (d1.isoformat(), d2.isoformat()),
        )

    def all_expenses(self) -> list:
        return self._q("SELECT * FROM expenses ORDER BY spent_at DESC, id DESC")

    def total_expense(self) -> int:
        return int(self._one("SELECT COALESCE(SUM(amount), 0) FROM expenses")[0])

    def cash_balance(self) -> int:
        """Kassada bo'lishi kerak bo'lgan pul."""
        return self.opening_cash() + self.total_income() - self.total_expense()

    # ---------- qarz / balans ----------
    def balances(self, ids: list[int] | None = None) -> dict[int, Balance]:
        cur = week_start()
        fee = self.fee_getter()
        if ids is None:
            rows = self._q("SELECT id, joined_week, left_week, opening_debt FROM students")
        elif not ids:
            return {}
        else:
            marks = ",".join("?" * len(ids))
            rows = self._q(
                f"SELECT id, joined_week, left_week, opening_debt FROM students WHERE id IN ({marks})",
                list(ids),
            )
        paid = {r[0]: int(r[1]) for r in self._q(
            "SELECT student_id, SUM(amount) FROM payments GROUP BY student_id")}
        paid_week = {r[0]: int(r[1]) for r in self._q(
            "SELECT student_id, SUM(amount) FROM payments WHERE paid_at >= ? GROUP BY student_id",
            (cur.isoformat(),))}
        ex = self.all_exemptions()
        memo: dict[date, int] = {}
        out: dict[int, Balance] = {}
        for r in rows:
            sid = r["id"]
            w = date.fromisoformat(r["joined_week"])
            end = cur
            if r["left_week"]:
                end = min(end, date.fromisoformat(r["left_week"]))
            expected = r["opening_debt"] or 0
            skip = ex.get(sid, set())
            while w <= end:
                if w not in skip:
                    if w not in memo:
                        memo[w] = fee(w)
                    expected += memo[w]
                w += WEEK
            out[sid] = Balance(expected, paid.get(sid, 0), paid_week.get(sid, 0), cur in skip)
        return out

    # ---------- zaxira ----------
    @property
    def backup_ext(self) -> str:
        return "json" if self.is_pg else "db"

    def dump(self) -> dict:
        """Barcha jadvallar — JSON zaxira uchun."""
        out = {"format": "ttj-oshxona-backup", "version": 1, "created": now_str(), "tables": {}}
        for t in TABLES:
            rows = self._q(f"SELECT * FROM {t}")
            out["tables"][t] = [{k: r[k] for k in r.keys()} for r in rows]
        return out

    def backup_bytes(self) -> bytes:
        """Bazaning to'liq nusxasi: SQLite — .db fayl, Postgres — .json fayl."""
        if self.is_pg:
            return json.dumps(self.dump(), ensure_ascii=False, indent=1).encode("utf-8")
        if hasattr(self.conn, "serialize"):
            return self.conn.serialize()
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            dst = sqlite3.connect(tmp)
            with dst:
                self.conn.backup(dst)
            dst.close()
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            os.remove(tmp)


class _PgTxCursor:
    """Tranzaksiya ichida `?` li SQL ni Postgres'da bajarish."""

    def __init__(self, conn, translate):
        self._conn = conn
        self._t = translate

    def execute(self, sql: str, params=()):
        return self._conn.execute(self._t(sql), params)
