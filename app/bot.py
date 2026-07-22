import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from .config import BOT_TOKEN, ADMIN_IDS
from .db import init_db
from .telethon_client import TelethonManager
from .account_manager import AccountManager
from .handlers import router, telethon_manager as tm, account_manager as am

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
    # Сохраняем в handlers
    import app.handlers as handlers
    handlers.account_manager = acc_manager
    handlers.telethon_manager = manager

    dp.include_router(router)
    await set_commands(bot)

    try:
        await dp.start_polling(bot)
    finally:
        await manager.stop_all()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())