import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from .config import BOT_TOKEN, ADMIN_IDS, GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_NAME
from .db import init_db
from .telethon_client import TelethonManager
from .account_manager import AccountManager
from .google_sheets import GoogleSheetsManager
from .handlers import router, telethon_manager as tm, account_manager as am, google_sheets_manager as gsm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def set_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ])

async def main():
    await init_db()
    logger.info("База данных инициализирована")

    acc_manager = AccountManager()
    await acc_manager.load()

    manager = TelethonManager(acc_manager, bot)
    
    # Инициализация Google Sheets из переменных окружения
    gs_manager = None
    if GOOGLE_CREDENTIALS_FILE and GOOGLE_SHEET_NAME and os.path.exists(GOOGLE_CREDENTIALS_FILE):
        try:
            gs_manager = GoogleSheetsManager(GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_NAME)
            logger.info(f"✅ Google Sheets подключен: {GOOGLE_SHEET_NAME}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения Google Sheets: {e}")
    else:
        if not GOOGLE_CREDENTIALS_FILE:
            logger.warning("GOOGLE_CREDENTIALS_FILE не задан. Google Sheets отключён.")
        elif not GOOGLE_SHEET_NAME:
            logger.warning("GOOGLE_SHEET_NAME не задан. Google Sheets отключён.")
        elif not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            logger.warning(f"Файл {GOOGLE_CREDENTIALS_FILE} не найден. Google Sheets отключён.")

    # Сохраняем в handlers
    import app.handlers as handlers
    handlers.account_manager = acc_manager
    handlers.telethon_manager = manager
    handlers.google_sheets_manager = gs_manager
    
    # Сохраняем в telethon_manager для доступа к Google Sheets
    manager.google_sheets_manager = gs_manager

    dp.include_router(router)
    await set_commands(bot)

    try:
        await dp.start_polling(bot)
    finally:
        await manager.stop_all()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())