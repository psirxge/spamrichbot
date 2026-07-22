import asyncio
import logging
import random
from telethon import TelegramClient, events
from telethon.errors import (
    RPCError, FloodWaitError, SessionPasswordNeededError,
    PhoneCodeExpiredError, PhoneCodeInvalidError, AuthKeyError,
    PhoneNumberInvalidError, PhoneNumberBannedError, PhoneCodeHashEmptyError
)
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.sessions import StringSession, SQLiteSession
from typing import Optional, Dict, Callable, Awaitable
from datetime import datetime

from .db import (
    get_channels_by_type, get_keywords, get_offer_text, get_target_channel,
    get_account, update_account_session, toggle_account_active_db,
    add_channel, get_all_channels, get_monitoring_setting
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

    async def get_entity(self, identifier):
        for phone, client in self.clients.items():
            try:
                entity = await client.get_entity(identifier)
                return entity
            except:
                continue
        return None

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

    # ---------- Отправка сообщений ----------
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
        active = await self.account_manager.get_active_accounts(role='sender')
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

    # ---------- Парсинг по запросу ----------
    async def fetch_messages(self, parse_type: str = 'news', limit: int = 5) -> dict:
        channels = await get_channels_by_type(parse_type)
        if not channels:
            return {}

        authorized = await self.account_manager.get_authorized_accounts(role='parser')
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

    # ---------- Мониторинг комментариев (поллинг) ----------
    async def start_comment_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts(role='parser')
        if not authorized:
            logger.warning("Нет авторизованных parser-аккаунтов для мониторинга")
            return
        for acc in authorized:
            phone = acc['phone']
            task = asyncio.create_task(self._poll_comments(phone))
            self.monitoring_tasks[phone] = task

    async def _poll_comments(self, phone: str):
        client = await self.get_client(phone)
        if not client:
            logger.error(f"Не удалось получить клиента для {phone}")
            return

        channels_str = await get_channels_by_type("comment")
        if not channels_str:
            logger.info(f"Нет каналов для мониторинга комментариев у {phone}")
            return

        try:
            await client.get_dialogs()
            logger.info(f"Диалоги для {phone} загружены")
        except Exception as e:
            logger.error(f"Ошибка загрузки диалогов для {phone}: {e}")

        channel_entities = []
        for ch_str in channels_str:
            try:
                entity = None
                try:
                    entity = await client.get_entity(int(ch_str))
                except:
                    try:
                        entity = await client.get_entity(ch_str)
                    except:
                        pass

                if entity:
                    try:
                        full_channel = await client(GetFullChannelRequest(entity))
                        logger.info(f"Full channel info: {full_channel}")
                        linked_id = getattr(full_channel, 'linked_chat_id', None)
                        if linked_id:
                            logger.info(f"🔗 Канал {ch_str} имеет чат обсуждений с ID: {linked_id}")
                            all_channels = await get_all_channels()
                            exists = any(ch['chat_id'] == str(linked_id) and ch['type'] == 'comment' for ch in all_channels)
                            if not exists:
                                await add_channel(str(linked_id), 'comment')
                                logger.info(f"✅ Автоматически добавлен чат обсуждений {linked_id} как тип 'comment'")
                                try:
                                    linked_entity = await client.get_entity(linked_id)
                                    channel_entities.append(linked_entity)
                                    logger.info(f"Сущность чата обсуждений {linked_id} добавлена в мониторинг")
                                except Exception as e:
                                    logger.error(f"Не удалось получить сущность чата обсуждений {linked_id}: {e}")
                            else:
                                logger.info(f"Чат обсуждений {linked_id} уже добавлен в БД")
                        else:
                            if hasattr(full_channel, 'chats') and full_channel.chats:
                                for chat in full_channel.chats:
                                    if hasattr(chat, 'id') and chat.id != entity.id:
                                        logger.info(f"Найден связанный чат: ID={chat.id}, название={chat.title}")
                                        linked_id = chat.id
                                        all_channels = await get_all_channels()
                                        exists = any(ch['chat_id'] == str(linked_id) and ch['type'] == 'comment' for ch in all_channels)
                                        if not exists:
                                            await add_channel(str(linked_id), 'comment')
                                            logger.info(f"✅ Автоматически добавлен чат обсуждений {linked_id} как тип 'comment'")
                                            try:
                                                linked_entity = await client.get_entity(linked_id)
                                                channel_entities.append(linked_entity)
                                                logger.info(f"Сущность чата обсуждений {linked_id} добавлена в мониторинг")
                                            except Exception as e:
                                                logger.error(f"Не удалось получить сущность чата обсуждений {linked_id}: {e}")
                                        else:
                                            logger.info(f"Чат обсуждений {linked_id} уже добавлен в БД")
                    except Exception as e:
                        logger.warning(f"Не удалось получить linked_chat_id для {ch_str}: {e}")

                    channel_entities.append(entity)
                    logger.info(f"Канал {ch_str} найден")
                    continue

                dialogs = await client.get_dialogs()
                found = False
                for d in dialogs:
                    clean_id = ch_str.lstrip('-')
                    if str(d.id) == clean_id or d.id == int(clean_id):
                        channel_entities.append(d.entity)
                        logger.info(f"Канал {ch_str} найден среди диалогов")
                        found = True
                        break
                if not found:
                    logger.warning(f"Канал {ch_str} не найден ни одним способом")
            except Exception as e:
                logger.warning(f"Канал {ch_str} недоступен: {e}")

        if not channel_entities:
            logger.info(f"Нет доступных каналов для мониторинга комментариев у {phone}")
            return

        processed_replies = set()
        logger.info(f"Мониторинг комментариев (polling) запущен для {phone}, каналов: {len(channel_entities)}")

        google_sheets_manager = getattr(self, 'google_sheets_manager', None)
        if google_sheets_manager:
            logger.info("✅ Google Sheets менеджер доступен в TelethonManager")
        else:
            logger.warning("⚠️ Google Sheets менеджер НЕ доступен в TelethonManager")

        while self.running:
            try:
                for entity in channel_entities:
                    try:
                        messages = await client.get_messages(entity, limit=30)
                        if messages:
                            logger.info(f"Получено {len(messages)} сообщений из чата {entity}")
                        channel_id = entity.id if hasattr(entity, 'id') else entity.channel_id

                        for msg in reversed(messages):
                            if not msg.text:
                                continue

                            # Игнорируем сообщения от самого канала (посты)
                            if msg.sender_id == channel_id:
                                continue

                            reply_key = f"{channel_id}_{msg.id}"
                            if reply_key in processed_replies:
                                continue

                            try:
                                me = await client.get_me()
                                if msg.sender_id == me.id:
                                    processed_replies.add(reply_key)
                                    continue
                            except:
                                pass

                            text = msg.text or ""
                            keywords = await get_keywords()
                            if any(kw.lower() in text.lower() for kw in keywords):
                                answer_enabled = await get_monitoring_setting("answer_enabled")
                                collect_enabled = await get_monitoring_setting("collect_enabled")
                                offer = await get_offer_text()
                                replied = False

                                if answer_enabled:
                                    try:
                                        await client.send_message(entity, offer, reply_to=msg.id)
                                        logger.info(f"✅ Ответ отправлен в чате {entity} на сообщение {msg.id}")
                                        replied = True
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка отправки ответа: {e}")
                                        try:
                                            await client.send_message(msg.sender_id, offer)
                                            logger.info(f"✅ Ответ отправлен в личку пользователю {msg.sender_id}")
                                            replied = True
                                        except Exception as e2:
                                            logger.error(f"❌ Ошибка отправки в личку: {e2}")

                                if collect_enabled and google_sheets_manager:
                                    try:
                                        user = await client.get_entity(msg.sender_id)
                                        username = user.username
                                        first_name = user.first_name or ''
                                        last_name = user.last_name or ''
                                        full_name = f"{first_name} {last_name}".strip()
                                        display_name = username or full_name or str(msg.sender_id)
                                        mention = f"@{username}" if username else f"[{full_name}](tg://user?id={msg.sender_id})"
                                    except:
                                        username = None
                                        full_name = str(msg.sender_id)
                                        display_name = str(msg.sender_id)
                                        mention = f"tg://user?id={msg.sender_id}"

                                    comment_data = {
                                        'datetime': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        'channel': str(entity),
                                        'user_id': msg.sender_id,
                                        'username': username or '',
                                        'display_name': display_name,
                                        'mention': mention,
                                        'text': text,
                                        'replied': replied
                                    }
                                    success = await google_sheets_manager.add_comment_record(comment_data)
                                    if success:
                                        logger.info("✅ Запись добавлена в Google Sheets")
                                    else:
                                        logger.error("❌ Не удалось добавить запись в Google Sheets")

                                processed_replies.add(reply_key)
                    except Exception as e:
                        logger.error(f"Ошибка при опросе чата {entity}: {e}")

                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(10)

        await client.disconnect()

    # ---------- Мониторинг новостей ----------
    async def start_news_monitoring(self):
        if self.running:
            return
        self.running = True
        authorized = await self.account_manager.get_authorized_accounts(role='parser')
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

        try:
            await client.get_dialogs()
        except Exception as e:
            logger.error(f"Ошибка загрузки диалогов для новостей: {e}")

        sources = await get_channels_by_type("news")
        if not sources:
            logger.info(f"Нет источников новостей для {phone}")
            return

        available_entities = []
        for ch in sources:
            try:
                entity = await client.get_input_entity(ch)
                available_entities.append(entity)
                logger.info(f"Источник {ch} доступен для новостей")
            except Exception as e:
                logger.warning(f"Источник {ch} недоступен: {e}")

        if not available_entities:
            logger.info(f"Нет доступных источников новостей для {phone}")
            return

        target = await get_target_channel()

        @client.on(events.NewMessage(chats=available_entities))
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
                    logger.error(f"Ошибка публикации в {target}: {e}")

        logger.info(f"Мониторинг новостей запущен для {phone} (доступно источников: {len(available_entities)})")
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