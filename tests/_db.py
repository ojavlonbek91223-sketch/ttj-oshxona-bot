"""Testlar uchun toza baza: oddiy holda SQLite (xotirada),
TEST_DATABASE_URL berilsa — Postgres (jadvallar har safar tozalanadi)."""
import os

from db import TABLES, Database


def fresh_db(default_fee: int = 90000) -> Database:
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not url:
        return Database(":memory:", default_fee)
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        for t in reversed(TABLES):
            conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    return Database(default_fee=default_fee, url=url)
