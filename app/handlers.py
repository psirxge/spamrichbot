import asyncio
import logging
import os
import json
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .db import (
    get_global_api_id, get_global_api_hash, set_global_api,
    get_all_accounts_from_db, toggle_account_role,
    get_monitoring_setting, set_monitoring_setting, get_setting, set_setting
)

from .config import ADMIN_IDS
from .keyboards import (
    get_main_menu,
    get_back_button,
    get_channels_menu,
    get_accounts_menu,
    get_settings_menu,
    get_cancel_kb,
    get_channels_management_kb,
    get_account_delete_buttons,
    get_channel_delete_buttons,
    get_resend_code_kb,
)
from .db import *
from .telethon_client import TelethonManager
from .account_manager import AccountManager
from .states import (
    AddAccountState,
    SetSettingState,
    AddChannelState,
    LoadJsonState,
    GetDiscussionIdState,
    SetGsheetsState,
)
from .gemini_utils import generate_rich_html
from .google_sheets import GoogleSheetsManager
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import SessionPasswordNeededError

router = Router()
telethon_manager: TelethonManager = None
account_manager: AccountManager = None
google_sheets_manager: GoogleSheetsManager = None
logger = logging.getLogger(__name__)

async def is_admin(message: Message) -> bool:
    return message.from_user.id in ADMIN_IDS

# ---------- Команды ----------
@router.message(Command("start"))
async def cmd_start(message: Message):
    if not await is_admin(message):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "👋 Привет! Я бот для автоматического парсинга комментариев и новостей.\n"
        "Используй меню для управления.",
        reply_markup=get_main_menu()
    )

# ---------- Главное меню ----------
@router.message(F.text == "📊 Управление аккаунтами")
async def manage_accounts(message: Message):
    if not await is_admin(message):
        return
    await message.answer("Управление аккаунтами:", reply_markup=get_accounts_menu())

@router.message(F.text == "📢 Управление каналами")
async def manage_channels_reply(message: Message):
    if not await is_admin(message):
        return
    await message.answer("Управление каналами (источники и типы):", reply_markup=get_channels_management_kb())

@router.message(F.text == "📰 Парсер новостей")
async def parse_news_now(message: Message):
    if not await is_admin(message):
        return
    if telethon_manager is None:
        await message.answer("❌ TelethonManager не инициализирован.")
        return

    target = await get_target_channel()
    if not target:
        await message.answer("⚠️ Целевой канал не задан. Сначала установите его в настройках.\nПоказываю сырые новости в чате:")
        await show_news_in_chat(message)
        return

    await message.answer("⏳ Парсинг новостей и публикация в целевой канал...")

    try:
        channels = await get_channels_by_type('news')
        if not channels:
            await message.answer("Нет каналов для парсинга.")
            return

        authorized = await account_manager.get_authorized_accounts(role='parser')
        if not authorized:
            await message.answer("❌ Нет авторизованных parser-аккаунтов.")
            return

        phone = authorized[0]['phone']
        client = await telethon_manager.get_client(phone)
        if not client:
            await message.answer(f"❌ Не удалось подключиться к {phone}.")
            return

        all_texts = []
        for ch in channels:
            async for msg in client.iter_messages(ch, limit=5):
                if msg.text:
                    all_texts.append(msg.text)

        if not all_texts:
            await message.answer("Нет новых текстовых сообщений.")
            return

        combined = "\n\n---\n\n".join(all_texts)
        try:
            html = await generate_rich_html(combined)
        except Exception as e:
            logger.error(f"Ошибка генерации HTML: {e}")
            html = f"<b>Ошибка генерации HTML</b>\n{combined}"

        try:
            await client.send_message(target, html, parse_mode='html')
            await message.answer(f"✅ Новости опубликованы в {target}.")
        except Exception as e:
            logger.error(f"Ошибка публикации: {e}")
            await message.answer(f"❌ Ошибка публикации: {e}")

    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        await message.answer(f"❌ Ошибка: {e}")

async def show_news_in_chat(message: Message):
    try:
        result = await telethon_manager.fetch_messages('news', limit=5)
        if not result:
            await message.answer("Нет каналов для парсинга или нет сообщений.")
            return
        output = "📰 Последние новости:\n\n"
        for ch, msgs in result.items():
            output += f"📌 Канал: {ch}\n"
            for i, msg in enumerate(msgs, 1):
                short = msg[:100] + "..." if len(msg) > 100 else msg
                output += f"{i}. {short}\n"
            output += "\n"
            if len(output) > 3000:
                await message.answer(output)
                output = ""
        if output:
            await message.answer(output)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@router.message(F.text == "💬 Парсер комментариев")
async def parse_comments_now(message: Message):
    if not await is_admin(message):
        return
    if telethon_manager is None:
        await message.answer("❌ TelethonManager не инициализирован.")
        return

    await message.answer("⏳ Получаю последние комментарии...")
    try:
        channels = await get_channels_by_type('comment')
        if not channels:
            await message.answer("Нет каналов для парсинга комментариев.")
            return
        result = await telethon_manager.fetch_messages('comments', limit=5)
        if not result:
            await message.answer("Нет сообщений в каналах комментариев.")
            return
        output = "💬 Последние сообщения в каналах комментариев:\n\n"
        for ch, msgs in result.items():
            output += f"📌 Канал: {ch}\n"
            for i, msg in enumerate(msgs, 1):
                short = msg[:100] + "..." if len(msg) > 100 else msg
                output += f"{i}. {short}\n"
            output += "\n"
            if len(output) > 3000:
                await message.answer(output)
                output = ""
        if output:
            await message.answer(output)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {e}")

# ---------- Настройки ----------
@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    if not await is_admin(message):
        return
    running = telethon_manager.running if telethon_manager else False
    answer_enabled = await get_monitoring_setting("answer_enabled")
    collect_enabled = await get_monitoring_setting("collect_enabled")
    await message.answer("⚙️ Настройки:", reply_markup=get_settings_menu(running, answer_enabled, collect_enabled))

# ---------- Добавление аккаунта ----------
@router.message(F.text == "➕ Добавить аккаунт")
async def add_account_start(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    api_id = await get_global_api_id()
    api_hash = await get_global_api_hash()
    if not api_id or not api_hash:
        await message.answer(
            "⚠️ Глобальные API ID и API Hash не заданы.\n"
            "Пожалуйста, сначала загрузите .json файл через кнопку «📁 Загрузить .json»"
        )
        return
    await state.update_data(api_id=api_id, api_hash=api_hash, is_sender=True, is_parser=True)
    await message.answer("Введите номер телефона в формате +71234567890:", reply_markup=get_cancel_kb())
    await state.set_state(AddAccountState.waiting_phone)

# ---------- Загрузка .json ----------
@router.message(F.text == "📁 Загрузить .json")
async def load_json_start(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await state.set_state(LoadJsonState.waiting_file)
    await message.answer(
        "📁 **Загрузка .json файла (TData)**\n\n"
        "Отправьте .json файл, который содержит API ID и API Hash.\n"
        "После загрузки бот сразу запросит номер телефона для добавления аккаунта.\n\n"
        "Файл обычно имеет структуру: {\"app_id\": 12345, \"app_hash\": \"abc...\"}\n"
        "Вы можете скачать такой файл из Telegram Desktop (TData)."
    )

@router.message(LoadJsonState.waiting_file, F.document)
async def load_json_file(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    document = message.document
    if not document.file_name.endswith('.json'):
        await message.answer("❌ Пожалуйста, отправьте файл с расширением .json")
        return

    file_path = f"/tmp/{document.file_name}"
    await message.bot.download(document, file_path)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        api_id = data.get('app_id')
        api_hash = data.get('app_hash')

        if not api_id or not api_hash:
            await message.answer(
                "❌ Не удалось найти app_id и app_hash в файле.\n"
                "Убедитесь, что файл содержит поля 'app_id' и 'app_hash'."
            )
            os.remove(file_path)
            await state.clear()
            return

        await set_global_api(api_id, api_hash)
        await state.update_data(api_id=api_id, api_hash=api_hash, is_sender=True, is_parser=True)
        await message.answer(
            f"✅ API данные успешно загружены:\n"
            f"📌 API ID: {api_id}\n"
            f"📌 API Hash: {api_hash}\n\n"
            "Теперь введите номер телефона в формате +71234567890:",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(AddAccountState.waiting_phone)
        os.remove(file_path)
    except json.JSONDecodeError:
        await message.answer("❌ Ошибка: файл не является корректным JSON.")
        os.remove(file_path)
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки .json файла: {e}")
        await message.answer(f"❌ Ошибка: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        await state.clear()

# ---------- Проверка авторизации ----------
@router.message(F.text == "🔍 Проверить авторизацию")
async def check_auth(message: Message):
    if not await is_admin(message):
        return
    accounts = await get_all_accounts_from_db()
    if not accounts:
        await message.answer("📭 Нет добавленных аккаунтов.")
        return

    text = "🔍 **Результаты проверки авторизации:**\n\n"
    for acc in accounts:
        phone = acc['phone']
        roles = []
        if acc.get('is_sender'):
            roles.append("Sender")
        if acc.get('is_parser'):
            roles.append("Parser")
        role_str = ", ".join(roles) if roles else "Нет ролей"

        if acc.get('session_string') and acc.get('is_authorized'):
            client = await telethon_manager.get_client(phone)
            if client:
                status = "✅ **Авторизован**"
            else:
                status = "❌ **Сессия недействительна** (требуется переавторизация)"
        else:
            status = "⏳ **Ожидает авторизации** (нет сессии)"
        text += f"• {phone} ({role_str}) – {status}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "back_to_main")
async def back_to_main_from_check(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    await callback.answer()

# ---------- Каналы ----------
@router.message(F.text == "➕ Добавить канал")
async def add_channel_reply_start(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await message.answer("Введите ID или username канала (например, @channel или -1001234567890):")
    await state.set_state(AddChannelState.waiting_chat_id)

@router.message(F.text == "📋 Список каналов")
async def list_channels_reply(message: Message):
    if not await is_admin(message):
        return
    channels = await get_all_channels()
    if not channels:
        await message.answer("Нет добавленных каналов.", reply_markup=get_channels_management_kb())
        return

    enriched_channels = []
    client = None
    if telethon_manager:
        authorized = await account_manager.get_authorized_accounts(role='parser')
        if authorized:
            phone = authorized[0]['phone']
            client = await telethon_manager.get_client(phone)

    for ch in channels:
        chat_id = ch['chat_id']
        ch_type = ch['type']
        is_active = "🟢 Активен" if ch['active'] else "🔴 Неактивен"
        linked_id = ""
        if client:
            try:
                entity = await client.get_entity(int(chat_id))
                full = await client(GetFullChannelRequest(entity))
                linked = getattr(full, 'linked_chat_id', None)
                if linked:
                    linked_id = f" ↔ {linked}"
            except:
                pass
        enriched_channels.append(f"• {chat_id} ({ch_type}) – {is_active}{linked_id}")

    text = "📋 Список каналов:\n\n" + "\n".join(enriched_channels)
    kb = get_channel_delete_buttons(channels)
    await message.answer(text, reply_markup=kb)

# ---------- Получить ID обсуждений ----------
@router.message(F.text == "🔍 Получить ID обсуждений")
async def get_discussion_id_start(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await state.set_state(GetDiscussionIdState.waiting_chat_id)
    await message.answer(
        "Введите ID или username канала (например, @channel или -1001234567890):\n"
        "Бот покажет ID группы обсуждений, если она есть."
    )

@router.message(GetDiscussionIdState.waiting_chat_id)
async def get_discussion_id_chat_id(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    chat_input = message.text.strip()
    try:
        authorized = await account_manager.get_authorized_accounts(role='parser')
        if not authorized:
            await message.answer("❌ Нет авторизованных parser-аккаунтов для выполнения запроса.")
            await state.clear()
            return
        phone = authorized[0]['phone']
        client = await telethon_manager.get_client(phone)
        if not client:
            await message.answer("❌ Не удалось получить клиент.")
            await state.clear()
            return

        try:
            entity = await client.get_entity(int(chat_input))
        except:
            try:
                entity = await client.get_entity(chat_input)
            except Exception as e:
                await message.answer(f"❌ Не удалось найти канал по указанному ID/username: {e}")
                await state.clear()
                return

        full_channel = await client(GetFullChannelRequest(entity))
        logger.info(f"GetFullChannelRequest response: {full_channel}")
        linked_id = getattr(full_channel, 'linked_chat_id', None)
        if linked_id:
            await message.answer(
                f"✅ ID чата обсуждений для {chat_input}:\n"
                f"`{linked_id}`\n\n"
                f"Вы можете добавить этот ID как канал типа 'comment' в разделе управления каналами."
            )
        else:
            found_chats = []
            if hasattr(full_channel, 'chats') and full_channel.chats:
                for chat in full_channel.chats:
                    if hasattr(chat, 'id') and chat.id != entity.id:
                        found_chats.append(f"ID: {chat.id}, Название: {chat.title}")
                if found_chats:
                    await message.answer(
                        f"🔍 Найдены связанные чаты:\n" + "\n".join(found_chats) + "\n\n"
                        f"Возможно, это группа обсуждений. Попробуйте добавить её ID как канал типа 'comment'."
                    )
                else:
                    await message.answer(f"❌ У канала {chat_input} нет чата обсуждений (или он недоступен).")
            else:
                await message.answer(f"❌ У канала {chat_input} нет чата обсуждений (или он недоступен).")
    except Exception as e:
        logger.error(f"Ошибка получения ID обсуждений: {e}")
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

# ---------- Настройка Google Sheets ----------
@router.message(Command("set_gsheets"))
async def set_gsheets(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await state.set_state(SetGsheetsState.waiting_credentials)
    await message.answer("Отправьте файл credentials.json (ключ сервисного аккаунта Google Sheets).")

@router.message(SetGsheetsState.waiting_credentials, F.document)
async def set_gsheets_credentials(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    document = message.document
    if not document.file_name.endswith('.json'):
        await message.answer("❌ Пожалуйста, отправьте файл .json")
        return
    file_path = f"/tmp/{document.file_name}"
    await message.bot.download(document, file_path)
    os.makedirs("data", exist_ok=True)
    dest_path = "data/credentials.json"
    os.rename(file_path, dest_path)
    await state.set_state(SetGsheetsState.waiting_spreadsheet)
    await message.answer("✅ Файл сохранён. Теперь введите название таблицы Google Sheets (например, 'Comments'):")

@router.message(SetGsheetsState.waiting_spreadsheet)
async def set_gsheets_spreadsheet(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    spreadsheet_name = message.text.strip()
    await set_setting("gsheets_spreadsheet", spreadsheet_name)
    await message.answer(f"✅ Таблица '{spreadsheet_name}' сохранена. Теперь настройка завершена.\n"
                         "Перезапустите бота или используйте кнопку «⚙️ Настройки» для активации.")
    await state.clear()

# ---------- Отмена ----------
@router.message(F.text == "❌ Отмена")
@router.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu())

# ---------- Общий обработчик номера ----------
@router.message(AddAccountState.waiting_phone)
async def add_account_phone(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    phone = message.text.strip()
    data = await state.get_data()
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    is_sender = data.get('is_sender', True)
    is_parser = data.get('is_parser', True)

    if not api_id or not api_hash:
        await message.answer("❌ Ошибка: API данные не найдены. Загрузите .json файл.")
        await state.clear()
        return

    await account_manager.add_account(api_id, api_hash, phone, is_sender=is_sender, is_parser=is_parser)
    await state.update_data(phone=phone)

    if await telethon_manager.is_account_authorized(phone):
        await message.answer(
            f"✅ Аккаунт {phone} уже авторизован (найдена валидная сессия).\n"
            "Используйте его для работы."
        )
        await state.clear()
        return

    client = await telethon_manager.create_client_and_send_code(phone)
    if not client:
        flood_time = telethon_manager.last_flood_time.get(phone, 0)
        if flood_time:
            hours = flood_time // 3600
            minutes = (flood_time % 3600) // 60
            seconds = flood_time % 60
            await message.answer(
                f"❌ Telegram заблокировал отправку кодов для этого номера.\n"
                f"Пожалуйста, подождите: {hours}ч {minutes}м {seconds}с\n"
                f"или удалите аккаунт и попробуйте позже."
            )
        else:
            await message.answer(
                "❌ Не удалось отправить код. Проверьте API ID, API Hash и номер телефона.\n"
                "Возможно, аккаунт уже авторизован, но сессия невалидна.\n"
                "Попробуйте заново добавить аккаунт."
            )
        await state.clear()
        return

    await state.update_data(client=client)
    await message.answer(
        f"✅ Аккаунт {phone} добавлен. Код подтверждения отправлен в Telegram.\n"
        "Теперь введите код, который пришёл в Telegram.\n\n"
        "⚠️ Если код не приходит:\n"
        "1️⃣ Проверьте, что номер введён правильно\n"
        "2️⃣ Откройте Telegram на устройстве с этим номером\n"
        "3️⃣ Код придёт в чат 'Telegram' (системное сообщение)\n"
        "4️⃣ Если кода нет, нажмите кнопку 'Запросить новый код' ниже",
        reply_markup=get_resend_code_kb()
    )
    await state.set_state(AddAccountState.waiting_code)

@router.message(AddAccountState.waiting_code)
async def process_code(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    code = message.text.strip()
    data = await state.get_data()
    phone = data.get('phone')
    client = data.get('client')

    if not phone:
        await message.answer("❌ Ошибка: телефон не найден. Попробуйте заново.")
        await state.clear()
        return

    if not client:
        if await telethon_manager.is_account_authorized(phone):
            await message.answer("✅ Аккаунт уже авторизован!", reply_markup=get_accounts_menu())
            await state.clear()
            return
        client = await telethon_manager.create_client_and_send_code(phone)
        if not client:
            await message.answer("❌ Не удалось отправить код. Попробуйте заново добавить аккаунт.")
            await state.clear()
            return
        await state.update_data(client=client)

    try:
        success, error_type = await telethon_manager.complete_authorization_with_code(client, phone, code)
        if success:
            await message.answer("✅ Аккаунт успешно авторизован!", reply_markup=get_accounts_menu())
            await state.clear()
        else:
            if error_type == "expired":
                await message.answer(
                    "⏰ Код истёк. Нажмите кнопку, чтобы запросить новый код.",
                    reply_markup=get_resend_code_kb()
                )
            elif error_type == "invalid":
                await message.answer("❌ Неверный код. Попробуйте ещё раз:")
            else:
                await message.answer(f"❌ Ошибка: {error_type}. Попробуйте заново.")
                await state.clear()
    except SessionPasswordNeededError:
        await message.answer("🔐 Включена двухфакторная аутентификация. Введите пароль:")
        await state.set_state(AddAccountState.waiting_password)
        await state.update_data(client=client)

@router.message(AddAccountState.waiting_password)
async def process_password(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    password = message.text.strip()
    data = await state.get_data()
    phone = data.get('phone')
    client = data.get('client')
    if not phone or not client:
        await message.answer("❌ Ошибка: данные потеряны. Попробуйте заново.")
        await state.clear()
        return

    success = await telethon_manager.complete_authorization_with_password(client, phone, password)
    if success:
        await message.answer("✅ Аккаунт успешно авторизован!", reply_markup=get_accounts_menu())
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова или /cancel.")

# ---------- Обработчик кнопки "Запросить новый код" ----------
@router.callback_query(F.data == "resend_code")
async def resend_code_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != AddAccountState.waiting_code.state:
        await callback.answer("Вы не в процессе ввода кода.", show_alert=True)
        return

    data = await state.get_data()
    phone = data.get('phone')
    if not phone:
        await callback.answer("❌ Телефон не найден. Начните заново.", show_alert=True)
        await state.clear()
        return

    if await telethon_manager.is_account_authorized(phone):
        await callback.message.edit_text("✅ Аккаунт уже авторизован!")
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Отправляю новый код в Telegram...")
    new_client = await telethon_manager.refresh_client_and_send_code(phone)
    if new_client:
        await state.update_data(client=new_client)
        await callback.message.edit_text(
            "✅ Новый код отправлен в Telegram. Введите его:",
            reply_markup=get_resend_code_kb()
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось отправить новый код. Проверьте данные аккаунта и попробуйте позже."
        )
    await callback.answer()

# ---------- Обработчик продолжения незавершённой авторизации ----------
@router.callback_query(F.data.startswith("continue_acc_"))
async def continue_account_authorization(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split("_", 3)
    if len(parts) < 3:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
        return
    phone = parts[2]

    acc = await get_account(phone)
    if not acc:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    if acc.get('session_string') and acc.get('is_authorized'):
        await callback.answer("✅ Аккаунт уже авторизован", show_alert=True)
        return

    api_id = await get_global_api_id()
    api_hash = await get_global_api_hash()
    if not api_id or not api_hash:
        await callback.message.edit_text("❌ Глобальные API данные не заданы. Загрузите .json файл.")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(phone=phone, api_id=api_id, api_hash=api_hash)
    await state.set_state(AddAccountState.waiting_code)
    client = await telethon_manager.create_client_and_send_code(phone)
    if not client:
        await callback.message.edit_text("❌ Не удалось отправить код. Попробуйте позже.")
        await state.clear()
        await callback.answer()
        return
    await state.update_data(client=client)
    await callback.message.edit_text(
        f"🔄 Продолжаем авторизацию для {phone}.\n"
        "Код подтверждения отправлен в Telegram.\n"
        "Введите код:",
        reply_markup=get_resend_code_kb()
    )
    await callback.answer()

# ---------- Списки аккаунтов ----------
@router.message(F.text == "📋 Список аккаунтов")
async def list_accounts(message: Message):
    if not await is_admin(message):
        return
    accounts = await get_all_accounts_from_db()
    if not accounts:
        await message.answer("Нет добавленных аккаунтов.", reply_markup=get_accounts_menu())
        return
    kb = get_account_delete_buttons(accounts)
    await message.answer("👥 Список аккаунтов:", reply_markup=kb)

@router.message(F.text == "🔙 Назад")
async def back_to_main(message: Message):
    if not await is_admin(message):
        return
    await message.answer("Главное меню:", reply_markup=get_main_menu())

# ---------- Управление ролями (callback) ----------
@router.callback_query(F.data.startswith("toggle_role_"))
async def toggle_role_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    parts = callback.data.split("_", 3)
    if len(parts) < 4:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
        return
    phone = parts[2]
    role = parts[3]

    acc = await get_account(phone)
    if not acc:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return

    current_value = acc.get(f'is_{role}', 0)
    new_value = not current_value
    await toggle_account_role(phone, role, new_value)

    accounts = await get_all_accounts_from_db()
    kb = get_account_delete_buttons(accounts)
    await callback.message.edit_text("👥 Список аккаунтов:", reply_markup=kb)
    await callback.answer(f"✅ Роль {role} {'включена' if new_value else 'выключена'} для {phone}")

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()

# ---------- Удаление аккаунтов (callback) ----------
@router.callback_query(F.data.startswith("delete_acc_"))
async def delete_account_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    parts = callback.data.split("_", 3)
    if len(parts) < 3:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
        return
    phone = parts[2]
    await delete_account_from_db(phone)
    await callback.answer(f"✅ Аккаунт {phone} удалён.")
    accounts = await get_all_accounts_from_db()
    if not accounts:
        await callback.message.edit_text("Нет добавленных аккаунтов.", reply_markup=get_accounts_menu())
        return
    kb = get_account_delete_buttons(accounts)
    await callback.message.edit_text("👥 Список аккаунтов:", reply_markup=kb)

# ---------- Удаление каналов (callback) ----------
@router.callback_query(F.data.startswith("delete_channel_"))
async def delete_channel_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
        return
    chat_id = parts[2]
    await remove_channel(chat_id)
    await callback.answer(f"✅ Канал {chat_id} удалён.")
    channels = await get_all_channels()
    if not channels:
        await callback.message.edit_text("Нет добавленных каналов.", reply_markup=get_back_button())
        return
    text = "📋 Список каналов:\n\n"
    for ch in channels:
        status = "🟢 Активен" if ch['active'] else "🔴 Неактивен"
        text += f"• {ch['chat_id']} ({ch['type']}) – {status}\n"
    kb = get_channel_delete_buttons(channels)
    await callback.message.edit_text(text, reply_markup=kb)

# ---------- Настройки (callback) ----------
@router.callback_query(F.data == "set_keywords")
async def set_keywords(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    current = await get_setting("keywords")
    await callback.message.edit_text(
        f"Текущие ключевые слова (через запятую):\n{current or 'не заданы'}\n\nВведите новые:"
    )
    await state.set_state(SetSettingState.waiting_value)
    await state.update_data(setting_key="keywords")
    await callback.answer()

@router.callback_query(F.data == "set_offer")
async def set_offer(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    current = await get_setting("offer_text")
    await callback.message.edit_text(
        f"Текущий текст предложения:\n{current or 'не задан'}\n\nВведите новый:"
    )
    await state.set_state(SetSettingState.waiting_value)
    await state.update_data(setting_key="offer_text")
    await callback.answer()

@router.callback_query(F.data == "set_target")
async def set_target(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    current = await get_setting("target_channel")
    await callback.message.edit_text(
        f"Текущий целевой канал:\n{current or 'не задан'}\n\nВведите новый username или ID:"
    )
    await state.set_state(SetSettingState.waiting_value)
    await state.update_data(setting_key="target_channel")
    await callback.answer()

@router.message(SetSettingState.waiting_value)
async def set_setting_value(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    data = await state.get_data()
    key = data["setting_key"]
    value = message.text.strip()
    await set_setting(key, value)
    await message.answer(f"✅ Настройка '{key}' обновлена.")
    await state.clear()

# ---------- Переключатели ответов/сбора ----------
@router.callback_query(F.data == "toggle_answer")
async def toggle_answer(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    current = await get_monitoring_setting("answer_enabled")
    new_value = not current
    await set_monitoring_setting("answer_enabled", new_value)
    await callback.answer(f"📝 Ответы {'включены' if new_value else 'выключены'}")
    running = telethon_manager.running if telethon_manager else False
    answer_enabled = await get_monitoring_setting("answer_enabled")
    collect_enabled = await get_monitoring_setting("collect_enabled")
    await callback.message.edit_reply_markup(reply_markup=get_settings_menu(running, answer_enabled, collect_enabled))

@router.callback_query(F.data == "toggle_collect")
async def toggle_collect(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    current = await get_monitoring_setting("collect_enabled")
    new_value = not current
    await set_monitoring_setting("collect_enabled", new_value)
    await callback.answer(f"📊 Сбор данных {'включён' if new_value else 'выключен'}")
    running = telethon_manager.running if telethon_manager else False
    answer_enabled = await get_monitoring_setting("answer_enabled")
    collect_enabled = await get_monitoring_setting("collect_enabled")
    await callback.message.edit_reply_markup(reply_markup=get_settings_menu(running, answer_enabled, collect_enabled))

# ---------- Управление мониторингом комментариев (inline) ----------
@router.callback_query(F.data == "toggle_comment_parser")
async def toggle_comment_parser(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if telethon_manager.running:
        await telethon_manager.stop_all()
        await callback.answer("⏹ Мониторинг комментариев остановлен")
    else:
        authorized = await account_manager.get_authorized_accounts(role='parser')
        if not authorized:
            await callback.answer("❌ Нет авторизованных parser-аккаунтов. Добавьте аккаунт с ролью parser.", show_alert=True)
            return
        await telethon_manager.start_comment_monitoring()
        await callback.answer("▶️ Мониторинг комментариев запущен")
    running = telethon_manager.running
    answer_enabled = await get_monitoring_setting("answer_enabled")
    collect_enabled = await get_monitoring_setting("collect_enabled")
    await callback.message.edit_reply_markup(reply_markup=get_settings_menu(running, answer_enabled, collect_enabled))

@router.callback_query(F.data == "toggle_news_parser")
async def toggle_news_parser(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if telethon_manager.running:
        await telethon_manager.stop_all()
        await callback.answer("⏹ Мониторинг новостей остановлен")
    else:
        authorized = await account_manager.get_authorized_accounts(role='parser')
        if not authorized:
            await callback.answer("❌ Нет авторизованных parser-аккаунтов. Добавьте аккаунт с ролью parser.", show_alert=True)
            return
        await telethon_manager.start_news_monitoring()
        await callback.answer("▶️ Мониторинг новостей запущен")
    running = telethon_manager.running
    answer_enabled = await get_monitoring_setting("answer_enabled")
    collect_enabled = await get_monitoring_setting("collect_enabled")
    await callback.message.edit_reply_markup(reply_markup=get_settings_menu(running, answer_enabled, collect_enabled))

# ---------- Добавление канала ----------
@router.message(AddChannelState.waiting_chat_id)
async def add_channel_chat_id(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    chat_id = message.text.strip()
    await state.update_data(chat_id=chat_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Комментарии", callback_data="type_comment")],
        [InlineKeyboardButton(text="📰 Новости", callback_data="type_news")],
    ])
    await message.answer("Выберите тип канала:", reply_markup=kb)
    await state.set_state(AddChannelState.waiting_type)

@router.callback_query(F.data.startswith("type_"))
async def add_channel_type(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    typ = callback.data.split("_")[1]
    data = await state.get_data()
    chat_id = data["chat_id"]
    await add_channel(chat_id, typ)
    await callback.message.edit_text(f"✅ Канал {chat_id} добавлен как {typ}.")
    await state.clear()
    await callback.answer()