import asyncio
import logging
import random
from telethon import TelegramClient, events
from telethon.errors import RPCError, FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.types import InputPeerUser
from telethon.sessions import StringSession
from typing import Optional, Dict, Callable, Awaitable

# Вместо этого просто убираем прокси, поэтому импорты не нужны.
from .db import get_channels_by_type, get_keywords, get_offer_text, get_target_channel
from .gemini_utils import generate_rich_html
from .account_manager import AccountManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelethonManager:
    def __init__(self, account_manager: AccountManager, bot):
        self.account_manager = account_manager
        self.bot = bot
        self.clients: Dict[str, TelegramClient] = {}
        self.running = False
        self.monitoring_tasks = {}  # phone -> task
        self.lock = asyncio.Lock()

    # Удалён метод _get_proxy_dict — прокси не используется

    async def get_client(self, phone: str, force_new: bool = False) -> Optional[TelegramClient]:
        if phone in self.clients and not force_new:
            return self.clients[phone]

        accounts = await self.account_manager.get_active_accounts()
        acc = next((a for a in accounts if a['phone'] == phone), None)
        if not acc:
            logger.error(f"Аккаунт {phone} не найден или неактивен")
            return None

        session_string = acc.get('session_string')
        if session_string:
            client = TelegramClient(
                StringSession(session_string),
                acc['api_id'],
                acc['api_hash']
                # прокси не передаём
            )
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(f"Сессия для {phone} недействительна, требуется повторная авторизация")
                    await self.account_manager.mark_blocked(phone)
                    return None
                await client(UpdateStatusRequest(offline=False))
                self.clients[phone] = client
                logger.info(f"Клиент для {phone} восстановлен из сессии")
                return client
            except Exception as e:
                logger.error(f"Ошибка восстановления сессии для {phone}: {e}")
                await self.account_manager.mark_blocked(phone)
                return None
        else:
            logger.info(f"Для аккаунта {phone} нет сессии, нужно авторизовать")
            return None

    async def authorize_account(self, phone: str, code_callback: Callable[[], Awaitable[str]], 
                                password_callback: Callable[[], Awaitable[str]] = None) -> bool:
        accounts = await self.account_manager.get_active_accounts()
        acc = next((a for a in accounts if a['phone'] == phone), None)
        if not acc:
            return False

        client = TelegramClient(
            StringSession(),
            acc['api_id'],
            acc['api_hash']
            # без прокси
        )
        try:
            await client.connect()
            await client.send_code_request(phone)
            code = await code_callback()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                if password_callback:
                    password = await password_callback()
                    await client.sign_in(password=password)
                else:
                    logger.error(f"Для {phone} требуется пароль, но callback не предоставлен")
                    return False
            session_string = client.session.save()
            await self.account_manager.mark_authorized(phone, session_string)
            self.clients[phone] = client
            logger.info(f"Аккаунт {phone} успешно авторизован")
            return True
        except Exception as e:
            logger.error(f"Ошибка авторизации {phone}: {e}")
            return False

    async def send_pm_from_account(self, from_phone: str, user_id: int, text: str) -> bool:
        client = await self.get_client(from_phone)
        if not client:
            logger.warning(f"Клиент для {from_phone} не готов")
            return False
        try:
            await client.send_message(user_id, text)
            logger.info(f"✅ Отправлено от {from_phone} пользователю {user_id}")
            return True
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds} секунд для {from_phone}")
            await self.account_manager.mark_blocked(from_phone)
            return False
        except RPCError as e:
            logger.warning(f"Ошибка отправки с {from_phone}: {e}")
            if "BANNED" in str(e) or "CHAT_SEND" in str(e):
                await self.account_manager.mark_blocked(from_phone)
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка с {from_phone}: {e}")
            return False

    async def send_pm_with_fallback(self, user_id: int, text: str) -> bool:
        active = await self.account_manager.get_active_accounts()
        if not active:
            logger.error("Нет активных аккаунтов для отправки")
            return False

        random.shuffle(active)
        for acc in active:
            phone = acc['phone']
            success = await self.send_pm_from_account(phone, user_id, text)
            if success:
                return True
        logger.error("Все аккаунты не смогли отправить сообщение")
        return False

    # ---------- Мониторинг комментариев ----------
    async def start_comment_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts()
        if not authorized:
            logger.warning("Нет авторизованных аккаунтов для мониторинга")
            return
        for acc in authorized:
            phone = acc['phone']
            task = asyncio.create_task(self._monitor_comments(phone))
            self.monitoring_tasks[phone] = task

    async def _monitor_comments(self, phone: str):
        client = await self.get_client(phone)
        if not client:
            logger.error(f"Не удалось получить клиента для {phone}")
            return

        channels = await get_channels_by_type("comment")
        if not channels:
            logger.info(f"Нет каналов для мониторинга комментариев у {phone}")
            return

        @client.on(events.NewMessage(chats=channels))
        async def handler(event):
            if not event.message.reply_to:
                return
            text = event.message.text or ""
            keywords = await get_keywords()
            if any(kw.lower() in text.lower() for kw in keywords):
                sender_id = event.message.sender_id
                if not sender_id:
                    return
                offer = await get_offer_text()
                success = await self.send_pm_from_account(phone, sender_id, offer)
                if success:
                    logger.info(f"Предложение отправлено пользователю {sender_id} от {phone}")
                else:
                    logger.warning(f"Не удалось отправить от {phone} пользователю {sender_id}")

        logger.info(f"Мониторинг комментариев запущен для {phone}")
        while self.running:
            await asyncio.sleep(1)
        await client.disconnect()

    # ---------- Мониторинг новостей ----------
    async def start_news_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts()
        if not authorized:
            logger.warning("Нет авторизованных аккаунтов для мониторинга новостей")
            return
        acc = authorized[0]
        task = asyncio.create_task(self._monitor_news(acc['phone']))
        self.monitoring_tasks[acc['phone']] = task

    async def _monitor_news(self, phone: str):
        client = await self.get_client(phone)
        if not client:
            logger.error(f"Не удалось получить клиента для новостей ({phone})")
            return

        sources = await get_channels_by_type("news")
        if not sources:
            logger.info(f"Нет источников новостей для {phone}")
            return

        target = await get_target_channel()

        @client.on(events.NewMessage(chats=sources))
        async def handler(event):
            if not event.message.text:
                return
            raw = event.message.text
            try:
                html = await generate_rich_html(raw)
            except Exception as e:
                logger.error(f"Ошибка генерации HTML: {e}")
                return
            if target:
                try:
                    await client.send_message(target, html, parse_mode='html')
                    logger.info(f"Опубликована новость в {target} от {phone}")
                except Exception as e:
                    logger.error(f"Ошибка публикации: {e}")

        logger.info(f"Мониторинг новостей запущен для {phone}")
        while self.running:
            await asyncio.sleep(1)
        await client.disconnect()

    async def stop_all(self):
        self.running = False
        for task in self.monitoring_tasks.values():
            task.cancel()
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()
        logger.info("Все клиенты и мониторинги остановлены")