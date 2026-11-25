from aiogram import Router

from handlers import common, expenses, fallback, payments, reports, settings, students


def setup_routers() -> Router:
    root = Router(name="root")
    # Tartib muhim: menyu tugmalari birinchi, "tushunilmadi" javobi oxirida.
    root.include_routers(
        common.router,
        payments.router,
        students.router,
        expenses.router,
        reports.router,
        settings.router,
        fallback.router,
    )
    return root
