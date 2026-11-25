"""Excel hisobot (daftar o'rniga): xulosa, bolalar, haftalik jadval, to'lovlar, xarajatlar."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from db import Database
from utils import fmt_date, fmt_dt, now, week_start

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
DEBT_FILL = PatternFill("solid", fgColor="F8D7DA")
OK_FILL = PatternFill("solid", fgColor="D4EDDA")
EXEMPT_FILL = PatternFill("solid", fgColor="E2E3E5")
MONEY_FMT = "#,##0"
WEEKS_IN_GRID = 12


def _header(ws, headers: list[str], widths: list[int]) -> None:
    ws.append(headers)
    for i, w in enumerate(widths, start=1):
        c = ws.cell(row=1, column=i)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _money_cols(ws, cols: list[int]) -> None:
    for row in ws.iter_rows(min_row=2):
        for c in cols:
            row[c - 1].number_format = MONEY_FMT


def build_excel(db: Database) -> bytes:
    wb = Workbook()
    students = db.list_students(active=None)
    bals = db.balances()
    payments = db.all_payments()
    expenses = db.all_expenses()
    cur_week = week_start()

    # ---------- 1. Xulosa ----------
    ws = wb.active
    ws.title = "Xulosa"
    active = [s for s in students if s["active"]]
    debt = sum(max(bals[s["id"]].debt, 0) for s in students)
    inc, exp, opening = db.total_income(), db.total_expense(), db.opening_cash()
    rows = [
        ("Hisobot sanasi", now().strftime("%d.%m.%Y %H:%M")),
        ("Haftalik to'lov", db.current_fee()),
        ("Faol bolalar", len(active)),
        ("Boshlang'ich kassa", opening),
        ("Jami kirim", inc),
        ("Jami chiqim", exp),
        ("Kassada bo'lishi kerak", opening + inc - exp),
        ("Qarzdorlar soni", sum(1 for s in students if bals[s["id"]].debt > 0)),
        ("Jami qarz", debt),
    ]
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 20
    for k, v in rows:
        ws.append([k, v])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        if isinstance(v, int) and k not in ("Faol bolalar", "Qarzdorlar soni"):
            ws.cell(row=ws.max_row, column=2).number_format = MONEY_FMT

    # ---------- 2. Bolalar ----------
    ws = wb.create_sheet("Bolalar")
    _header(ws, ["Etaj", "F.I.Sh", "Xona", "Telefon", "Holat", "Ro'yxatga olingan",
                 "Eski qarz", "Jami to'lagan", "Qarz (+) / Oldindan (−)"],
            [12, 30, 8, 16, 14, 16, 12, 14, 18])
    for s in students:
        b = bals[s["id"]]
        ws.append([
            s["floor_name"], s["full_name"], s["room"] or "", s["phone"] or "",
            "Faol" if s["active"] else "Chiqib ketgan",
            fmt_date(s["joined_week"]), s["opening_debt"], b.paid, b.debt,
        ])
        ws.cell(row=ws.max_row, column=9).fill = DEBT_FILL if b.debt > 0 else OK_FILL
    _money_cols(ws, [7, 8, 9])

    # ---------- 3. Haftalik jadval (daftar ko'rinishi) ----------
    ws = wb.create_sheet("Haftalik jadval")
    weeks = [cur_week - timedelta(weeks=i) for i in range(WEEKS_IN_GRID - 1, -1, -1)]
    labels = [f"{w.strftime('%d.%m')}–{(w + timedelta(days=6)).strftime('%d.%m')}" for w in weeks]
    _header(ws, ["Etaj", "F.I.Sh", *labels, "Qarz"], [12, 30, *([12] * len(weeks)), 12])
    per_week: dict[tuple[int, date], int] = defaultdict(int)
    for p in payments:
        per_week[(p["student_id"], week_start(date.fromisoformat(p["paid_at"][:10])))] += p["amount"]
    exemptions = db.all_exemptions()
    for s in active:
        joined = date.fromisoformat(s["joined_week"])
        row = [s["floor_name"], s["full_name"]]
        for w in weeks:
            if w in exemptions.get(s["id"], set()):
                row.append("ozod")
            else:
                row.append(per_week.get((s["id"], w)) or None)
        row.append(bals[s["id"]].debt)
        ws.append(row)
        r = ws.max_row
        for i, w in enumerate(weeks, start=3):
            c = ws.cell(row=r, column=i)
            c.number_format = MONEY_FMT
            c.alignment = Alignment(horizontal="center")
            if c.value == "ozod":
                c.fill = EXEMPT_FILL
            elif c.value is None and w >= joined:
                c.fill = DEBT_FILL
        last = ws.cell(row=r, column=len(weeks) + 3)
        last.number_format = MONEY_FMT
        last.fill = DEBT_FILL if bals[s["id"]].debt > 0 else OK_FILL
    ws.append([])
    ws.append(["", "Izoh: raqam — shu haftada to'langan summa; qizil — to'lov yo'q; kulrang — ozod."])

    # ---------- 4. To'lovlar ----------
    ws = wb.create_sheet("To'lovlar")
    _header(ws, ["Sana va vaqt", "Etaj", "F.I.Sh", "Summa", "Izoh"], [18, 12, 30, 14, 24])
    for p in payments:
        ws.append([fmt_dt(p["paid_at"]), p["floor_name"], p["full_name"], p["amount"], p["note"] or ""])
    _money_cols(ws, [4])

    # ---------- 5. Xarajatlar ----------
    ws = wb.create_sheet("Xarajatlar")
    _header(ws, ["Sana", "Toifa", "Nima olindi", "Summa"], [12, 24, 40, 14])
    for e in expenses:
        ws.append([fmt_date(e["spent_at"]), e["category"], e["description"] or "", e["amount"]])
    _money_cols(ws, [4])

    # ---------- 6. Haftalar bo'yicha kirim-chiqim ----------
    ws = wb.create_sheet("Haftalar")
    _header(ws, ["Hafta", "Kirim", "Chiqim", "Farq"], [24, 14, 14, 14])
    inc_w: dict[date, int] = defaultdict(int)
    exp_w: dict[date, int] = defaultdict(int)
    for p in payments:
        inc_w[week_start(date.fromisoformat(p["paid_at"][:10]))] += p["amount"]
    for e in expenses:
        exp_w[week_start(date.fromisoformat(e["spent_at"]))] += e["amount"]
    all_weeks = sorted(set(inc_w) | set(exp_w), reverse=True)
    for w in all_weeks:
        i, x = inc_w.get(w, 0), exp_w.get(w, 0)
        ws.append([f"{w.strftime('%d.%m.%Y')} – {(w + timedelta(days=6)).strftime('%d.%m.%Y')}", i, x, i - x])
    _money_cols(ws, [2, 3, 4])

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
