import asyncio
import logging
import random
import os
from telethon import TelegramClient, events
from telethon.errors import (
    RPCError, FloodWaitError, SessionPasswordNeededError,
    PhoneCodeExpiredError, PhoneCodeInvalidError, AuthKeyError,
    PhoneNumberInvalidError, PhoneNumberBannedError, PhoneCodeHashEmptyError
)
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.sessions import StringSession, SQLiteSession
from typing import Optional, Dict, Callable, Awaitable

from .db import (
    get_channels_by_type, get_keywords, get_offer_text, get_target_channel,
    get_account, update_account_session, toggle_account_active_db
)
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
        self.last_request_time = {}  # phone -> timestamp
        self.last_flood_time = {}  # phone -> seconds

    async def get_client(self, phone: str, force_new: bool = False) -> Optional[TelegramClient]:
        if phone in self.clients and not force_new:
            return self.clients[phone]

        acc = await get_account(phone)
        if not acc:
            logger.error(f"Аккаунт {phone} не найден в БД")
            return None
        if not acc.get('is_active'):
            logger.error(f"Аккаунт {phone} неактивен")
            return None

        session_string = acc.get('session_string')
        if session_string:
            client = TelegramClient(
                StringSession(session_string),
                acc['api_id'],
                acc['api_hash']
            )
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning(f"Сессия для {phone} недействительна, требуется повторная авторизация")
                    await toggle_account_active_db(phone, False)
                    return None
                await client(UpdateStatusRequest(offline=False))
                self.clients[phone] = client
                logger.info(f"Клиент для {phone} восстановлен из сессии")
                return client
            except AuthKeyError:
                logger.warning(f"AuthKeyError для {phone}, сессия невалидна")
                await toggle_account_active_db(phone, False)
                return None
            except Exception as e:
                logger.error(f"Ошибка восстановления сессии для {phone}: {e}")
                await toggle_account_active_db(phone, False)
                return None
        else:
            logger.info(f"Для аккаунта {phone} нет сессии, нужно авторизовать")
            return None

    async def is_account_authorized(self, phone: str) -> bool:
        acc = await get_account(phone)
        if not acc:
            return False
        if not acc.get('session_string'):
            return False
        client = await self.get_client(phone)
        if client:
            return True
        return False

    async def load_session_from_file(self, file_path: str, api_id: int, api_hash: str) -> Optional[Dict]:

        try:
            session = SQLiteSession(file_path)
            client = TelegramClient(session, api_id, api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                logger.error(f"Сессия в файле {file_path} невалидна")
                await client.disconnect()
                return None
            me = await client.get_me()
            phone = me.phone
            if not phone:
                logger.error("Не удалось получить номер телефона из сессии")
                await client.disconnect()
                return None
            session_string = client.session.save()
            await client.disconnect()
            return {"phone": phone, "session_string": session_string}
        except Exception as e:
            logger.error(f"Ошибка загрузки .session файла: {e}")
            return None

    async def create_client_and_send_code(self, phone: str) -> Optional[TelegramClient]:
        if phone in self.last_request_time:
            elapsed = asyncio.get_event_loop().time() - self.last_request_time[phone]
            if elapsed < 5:
                logger.warning(f"Слишком частый запрос кода для {phone}, прошло {elapsed:.1f} секунд")
                return None

        if await self.is_account_authorized(phone):
            logger.info(f"Аккаунт {phone} уже авторизован, код не отправляем")
            return await self.get_client(phone)

        acc = await get_account(phone)
        if not acc or not acc.get('is_active'):
            logger.error(f"Аккаунт {phone} не найден или неактивен")
            return None

        client = TelegramClient(StringSession(), acc['api_id'], acc['api_hash'])
        try:
            await client.connect()
            logger.info(f"Клиент для {phone} подключён, отправляем код через Telegram...")
            result = await client.send_code_request(phone, force_sms=False)
            logger.info(f"Ответ Telegram: {result}")
            logger.info(f"Код отправлен на {phone}")
            self.last_request_time[phone] = asyncio.get_event_loop().time()
            return client
        except FloodWaitError as e:
            wait_seconds = e.seconds
            hours = wait_seconds // 3600
            minutes = (wait_seconds % 3600) // 60
            seconds = wait_seconds % 60
            logger.error(f"Flood wait {wait_seconds} секунд ({hours}ч {minutes}м {seconds}с) для {phone}")
            self.last_flood_time[phone] = wait_seconds
            return None
        except PhoneNumberInvalidError:
            logger.error(f"Неверный номер телефона: {phone}")
            return None
        except PhoneNumberBannedError:
            logger.error(f"Номер телефона забанен: {phone}")
            return None
        except PhoneCodeHashEmptyError as e:
            logger.error(f"Ошибка PhoneCodeHashEmpty: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка отправки кода для {phone}: {e}")
            return None

    async def refresh_client_and_send_code(self, phone: str) -> Optional[TelegramClient]:
        if phone in self.clients:
            try:
                await self.clients[phone].disconnect()
                logger.info(f"Старый клиент для {phone} отключён")
            except Exception as e:
                logger.error(f"Ошибка отключения клиента для {phone}: {e}")
            del self.clients[phone]

        logger.info(f"Ожидание 5 секунд перед повторной отправкой кода для {phone}")
        await asyncio.sleep(5)

        if await self.is_account_authorized(phone):
            logger.info(f"Аккаунт {phone} уже авторизован, код не нужен")
            return await self.get_client(phone)

        acc = await get_account(phone)
        if not acc or not acc.get('is_active'):
            logger.error(f"Аккаунт {phone} не найден или неактивен")
            return None

        client = TelegramClient(StringSession(), acc['api_id'], acc['api_hash'])
        try:
            await client.connect()
            logger.info(f"Новый клиент для {phone} подключён, отправляем код через Telegram...")
            result = await client.send_code_request(phone, force_sms=False)
            logger.info(f"Ответ Telegram: {result}")
            logger.info(f"Новый код отправлен на {phone}")
            return client
        except FloodWaitError as e:
            wait_seconds = e.seconds
            hours = wait_seconds // 3600
            minutes = (wait_seconds % 3600) // 60
            seconds = wait_seconds % 60
            logger.error(f"Flood wait {wait_seconds} секунд ({hours}ч {minutes}м {seconds}с) для {phone}")
            self.last_flood_time[phone] = wait_seconds
            return None
        except Exception as e:
            logger.error(f"Ошибка отправки нового кода для {phone}: {e}")
            return None

    async def complete_authorization_with_code(self, client: TelegramClient, phone: str, code: str) -> tuple[bool, str]:
        try:
            await client.sign_in(phone, code)
            session_string = client.session.save()
            await update_account_session(phone, session_string)
            self.clients[phone] = client
            logger.info(f"Аккаунт {phone} авторизован с кодом")
            return True, ""
        except SessionPasswordNeededError:
            raise
        except PhoneCodeExpiredError:
            return False, "expired"
        except PhoneCodeInvalidError:
            return False, "invalid"
        except Exception as e:
            logger.error(f"Ошибка входа с кодом для {phone}: {e}")
            return False, str(e)

    async def complete_authorization_with_password(self, client: TelegramClient, phone: str, password: str) -> bool:
        try:
            await client.sign_in(password=password)
            session_string = client.session.save()
            await update_account_session(phone, session_string)
            self.clients[phone] = client
            logger.info(f"Аккаунт {phone} авторизован с паролем")
            return True
        except Exception as e:
            logger.error(f"Ошибка входа с паролем для {phone}: {e}")
            return False

    # ---------- Остальные методы без изменений ----------
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
            await toggle_account_active_db(from_phone, False)
            return False
        except RPCError as e:
            logger.warning(f"Ошибка отправки с {from_phone}: {e}")
            if "BANNED" in str(e) or "CHAT_SEND" in str(e):
                await toggle_account_active_db(from_phone, False)
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка с {from_phone}: {e}")
            return False

    async def send_pm_with_fallback(self, user_id: int, text: str) -> bool:
        active = await self.account_manager.get_active_accounts(purpose='sender')
        if not active:
            logger.error("Нет активных sender-аккаунтов для отправки")
            return False

        random.shuffle(active)
        for acc in active:
            phone = acc['phone']
            success = await self.send_pm_from_account(phone, user_id, text)
            if success:
                return True
        logger.error("Все sender-аккаунты не смогли отправить сообщение")
        return False

    async def fetch_messages(self, parse_type: str = 'news', limit: int = 5) -> dict:
        channels = await get_channels_by_type(parse_type)
        if not channels:
            return {}

        authorized = await self.account_manager.get_authorized_accounts(purpose='parser')
        if not authorized:
            logger.error("Нет авторизованных parser-аккаунтов")
            return {}

        phone = authorized[0]['phone']
        client = await self.get_client(phone)
        if not client:
            logger.error(f"Не удалось получить клиент для {phone}")
            return {}

        result = {}
        for ch in channels:
            try:
                messages = []
                async for msg in client.iter_messages(ch, limit=limit):
                    if msg.text:
                        messages.append(msg.text)
                result[ch] = messages if messages else ["Нет текстовых сообщений"]
            except Exception as e:
                logger.error(f"Ошибка парсинга {ch}: {e}")
                result[ch] = [f"Ошибка: {e}"]
        return result

    async def start_comment_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts(purpose='parser')
        if not authorized:
            logger.warning("Нет авторизованных parser-аккаунтов для мониторинга")
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
                success = await self.send_pm_with_fallback(sender_id, offer)
                if success:
                    logger.info(f"Предложение отправлено пользователю {sender_id}")
                else:
                    logger.warning(f"Не удалось отправить предложение пользователю {sender_id}")

        logger.info(f"Мониторинг комментариев запущен для {phone}")
        while self.running:
            await asyncio.sleep(1)
        await client.disconnect()

    async def start_news_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts(purpose='parser')
        if not authorized:
            logger.warning("Нет авторизованных parser-аккаунтов для мониторинга новостей")
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