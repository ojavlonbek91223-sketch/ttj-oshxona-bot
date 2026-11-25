"""TTJ oshxona hisobi — Telegram bot. Ishga tushirish: python bot.py"""
import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

import config
from db import Database
from handlers import setup_routers
from jobs import weekly_report_loop
from middlewares import AdminOnly, ClearStateOnButton
from webserver import WEBHOOK_PATH, start_webserver, webhook_secret


def build_dispatcher(db: Database) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), db=db)
    admin_only = AdminOnly(db)
    dp.message.outer_middleware(admin_only)
    dp.callback_query.outer_middleware(admin_only)
    dp.callback_query.outer_middleware(ClearStateOnButton())
    dp.include_router(setup_routers())
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        print("XATO: BOT_TOKEN topilmadi. '.env' faylini yarating va tokenni yozing (README.md ga qarang).")
        sys.exit(1)

    db = Database(config.DB_PATH, config.DEFAULT_WEEKLY_FEE, url=config.DATABASE_URL)
    for admin_id in config.ADMIN_IDS:
        db.add_admin(admin_id)

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(db)
    await bot.set_my_commands([
        BotCommand(command="start", description="Bosh menyu"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Amalni bekor qilish"),
    ])
    # Chat pastidagi chap tugma: ilova manzili bo'lsa — «Ochish», aks holda buyruqlar ro'yxati.
    if config.WEBAPP_URL.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📱 Ochish", web_app=WebAppInfo(url=config.WEBAPP_URL))
        )
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        if config.WEBAPP_URL:
            logging.warning("WEBAPP_URL https:// bilan boshlanishi kerak — ilova tugmasi qo'yilmadi.")
    me = await bot.get_me()
    logging.info("Bot ishga tushdi: @%s | baza: %s", me.username,
                 "Postgres" if db.is_pg else config.DB_PATH)
    updates = dp.resolve_used_update_types()

    if config.USE_WEBHOOK:
        # Server rejimi: Telegram xabarlarni o'zi /tg/webhook manziliga yuboradi.
        if not config.WEBAPP_URL.startswith("https://"):
            print("XATO: webhook uchun WEBAPP_URL (https://...) kerak.")
            sys.exit(1)
        runner = await start_webserver(db, bot, dp)
        await bot.set_webhook(f"{config.WEBAPP_URL}{WEBHOOK_PATH}", secret_token=webhook_secret(),
                              allowed_updates=updates)
        logging.info("Webhook o'rnatildi: %s%s", config.WEBAPP_URL, WEBHOOK_PATH)
        report_task = asyncio.create_task(weekly_report_loop(bot, db))
        try:
            await asyncio.Event().wait()
        finally:
            report_task.cancel()
            await runner.cleanup()
            await bot.session.close()
        return

    # Kompyuter rejimi (polling). Agar bot serverda ishlayotgan bo'lsa — to'xtaymiz,
    # aks holda serverdagi bot xabar olmay qoladi.
    hook = await bot.get_webhook_info()
    if hook.url:
        if os.getenv("FORCE_POLLING") != "1":
            print(f"XATO: bot serverda ishlayapti (webhook: {hook.url}).\n"
                  "Kompyuterda ishga tushirilsa, serverdagi bot ishlamay qoladi. To'xtatildi.\n"
                  "Baribir kompyuterda ishlatish kerak bo'lsa: FORCE_POLLING=1")
            await bot.session.close()
            sys.exit(1)
        await bot.delete_webhook()
    runner = await start_webserver(db, bot)
    report_task = asyncio.create_task(weekly_report_loop(bot, db))
    try:
        await dp.start_polling(bot, allowed_updates=updates)
    finally:
        report_task.cancel()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
