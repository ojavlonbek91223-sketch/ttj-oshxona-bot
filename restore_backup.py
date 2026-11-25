"""JSON zaxirani bazaga tiklash.

    python restore_backup.py oshxona_backup_2026-11-30.json

Baza .env dagi DATABASE_URL (Postgres) yoki data/oshxona.db (SQLite).
Faqat BO'SH bazaga tiklaydi (bolalar va to'lovlar yo'q bo'lsa). Majburan: --force
(bunda bazadagi barcha ma'lumot o'chiriladi va zaxiradagisi yoziladi).
"""
import json
import sys

import config
from db import TABLES, Database

SERIAL_TABLES = ["floors", "students", "payments", "expenses"]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    with open(args[0], encoding="utf-8") as f:
        dump = json.load(f)
    if dump.get("format") != "ttj-oshxona-backup":
        sys.exit("XATO: bu fayl oshxona zaxirasi emas.")

    db = Database(config.DB_PATH, config.DEFAULT_WEEKLY_FEE, url=config.DATABASE_URL)
    has_data = db._one("SELECT COUNT(*) FROM students")[0] or db._one("SELECT COUNT(*) FROM payments")[0]
    if has_data and not force:
        sys.exit("XATO: bazada ma'lumot bor. Ustidan yozish uchun --force qo'shing.")

    with db._tx() as cur:
        for t in reversed(TABLES):
            cur.execute(f"DELETE FROM {t}")
        for t in TABLES:
            for row in dump["tables"].get(t, []):
                cols = list(row)
                marks = ", ".join("?" * len(cols))
                cur.execute(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({marks})", [row[c] for c in cols])
        if db.is_pg:  # id hisoblagichlarini to'g'rilash
            for t in SERIAL_TABLES:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1)) FROM {t}")
    counts = {t: len(dump["tables"].get(t, [])) for t in TABLES}
    print("Tiklandi:", ", ".join(f"{t}={n}" for t, n in counts.items()))


if __name__ == "__main__":
    main()
