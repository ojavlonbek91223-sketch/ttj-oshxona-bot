"""Inline tugmalar uchun callback ma'lumotlari (64 baytdan oshmasligi kerak)."""
from aiogram.filters.callback_data import CallbackData


class Menu(CallbackData, prefix="m"):
    # pay | students | add | search | floors | inactive | exp | noop
    a: str


class FloorCB(CallbackData, prefix="f"):
    """Etajdagi bolalar ro'yxati."""
    id: int
    p: int = 0  # sahifa


class CardCB(CallbackData, prefix="c"):
    """Bola kartochkasi."""
    id: int


class PayCB(CallbackData, prefix="p"):
    """To'lovni yozish."""
    id: int
    amt: int


class PayDelCB(CallbackData, prefix="pd"):
    """To'lovni o'chirish. ok=0 — tasdiq so'rash; back=1 — etaj ro'yxatiga qaytish."""
    id: int
    ok: int = 0
    back: int = 0


class StuCB(CallbackData, prefix="s"):
    # custom | exempt | hist | edit | name | room | phone | debt | floor |
    # leave | leave_ok | return | del | del_ok
    a: str
    id: int


class MoveCB(CallbackData, prefix="mv"):
    id: int
    f: int


class AddToCB(CallbackData, prefix="at"):
    f: int


class FloorAdmCB(CallbackData, prefix="fa"):
    # add | ren | del | del_ok
    a: str
    id: int = 0


class ExpCatCB(CallbackData, prefix="ec"):
    i: int


class ExpCB(CallbackData, prefix="ex"):
    # skip | recent | del | del_ok
    a: str
    id: int = 0


class RepCB(CallbackData, prefix="r"):
    # w (hafta) | m (oy) | kassa | debt | xls
    k: str
    o: int = 0


class SetCB(CallbackData, prefix="st"):
    # main | fee | fee_now | fee_next | cash | admins | aadd | adel | adel_ok | backup
    a: str
    id: int = 0
