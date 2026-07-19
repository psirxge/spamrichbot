import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .config import ADMIN_IDS
from .keyboards import (
    get_main_menu,
    get_back_button,
    get_channels_menu,
    get_accounts_menu,
    get_parser_comments_menu,
    get_parser_news_menu,
    get_settings_menu,
)
from .db import *
from .telethon_client import TelethonManager
from .account_manager import AccountManager

router = Router()
telethon_manager: TelethonManager = None
account_manager: AccountManager = None

# Проверка администратора
async def is_admin(message: Message) -> bool:
    return message.from_user.id in ADMIN_IDS

# Состояния
class AddAccountState(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class AddChannelState(StatesGroup):
    waiting_chat_id = State()
    waiting_type = State()

class SetSettingState(StatesGroup):
    waiting_value = State()

# ---------- Команда /start ----------
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
@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    await callback.answer()

# ---------- Управление каналами ----------
@router.callback_query(F.data == "manage_channels")
async def manage_channels(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Управление каналами:", reply_markup=get_channels_menu())
    await callback.answer()

@router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Введите ID или username канала (например, @channel или -1001234567890):")
    await state.set_state(AddChannelState.waiting_chat_id)
    await callback.answer()

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

@router.callback_query(F.data == "list_channels")
async def list_channels(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    channels = await get_all_channels()
    if not channels:
        await callback.message.edit_text("Нет добавленных каналов.", reply_markup=get_back_button())
        await callback.answer()
        return
    text = "📋 Список каналов:\n\n"
    for ch in channels:
        status = "🟢 Активен" if ch['active'] else "🔴 Неактивен"
        text += f"• {ch['chat_id']} ({ch['type']}) – {status}\n"
    await callback.message.edit_text(text, reply_markup=get_back_button())
    await callback.answer()

# ---------- Управление аккаунтами ----------
@router.callback_query(F.data == "manage_accounts")
async def manage_accounts(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Управление аккаунтами фермы:", reply_markup=get_accounts_menu())
    await callback.answer()

@router.callback_query(F.data == "add_account")
async def add_account_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Введите API ID (число):")
    await state.set_state(AddAccountState.waiting_api_id)
    await callback.answer()

@router.message(AddAccountState.waiting_api_id)
async def add_account_api_id(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    try:
        api_id = int(message.text.strip())
        await state.update_data(api_id=api_id)
        await message.answer("Введите API Hash:")
        await state.set_state(AddAccountState.waiting_api_hash)
    except ValueError:
        await message.answer("❌ API ID должен быть числом. Попробуйте снова:")

@router.message(AddAccountState.waiting_api_hash)
async def add_account_api_hash(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    api_hash = message.text.strip()
    await state.update_data(api_hash=api_hash)
    await message.answer("Введите номер телефона в формате +71234567890:")
    await state.set_state(AddAccountState.waiting_phone)

@router.message(AddAccountState.waiting_phone)
async def add_account_phone(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    phone = message.text.strip()
    data = await state.get_data()
    await account_manager.add_account(data['api_id'], data['api_hash'], phone)
    await message.answer(f"✅ Аккаунт {phone} добавлен. Теперь введите код подтверждения, который пришёл в Telegram:")
    await state.update_data(phone=phone)
    await state.set_state(AddAccountState.waiting_code)

@router.message(AddAccountState.waiting_code)
async def process_code(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    code = message.text.strip()
    data = await state.get_data()
    phone = data.get('phone')
    if not phone:
        await message.answer("❌ Ошибка: телефон не найден. Попробуйте заново добавить аккаунт.")
        await state.clear()
        return
    # Пытаемся авторизовать
    success = await telethon_manager.authorize_account(
        phone,
        code_callback=lambda: asyncio.sleep(0) or code,
        password_callback=None
    )
    if success:
        await message.answer("✅ Аккаунт успешно авторизован!")
        await state.clear()
    else:
        await message.answer("❌ Неверный код или требуется пароль двухфакторной аутентификации. Введите пароль (если он есть) или отправьте /cancel для отмены.")
        await state.set_state(AddAccountState.waiting_password)

@router.message(AddAccountState.waiting_password)
async def process_password(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    password = message.text.strip()
    data = await state.get_data()
    phone = data.get('phone')
    if not phone:
        await message.answer("❌ Ошибка.")
        await state.clear()
        return
    # Повторно с паролем
    success = await telethon_manager.authorize_account(
        phone,
        code_callback=lambda: asyncio.sleep(0) or data.get('code'),
        password_callback=lambda: asyncio.sleep(0) or password
    )
    if success:
        await message.answer("✅ Аккаунт успешно авторизован!")
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова или /cancel.")

@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    if not await is_admin(message):
        return
    await state.clear()
    await message.answer("Действие отменено.")

# ---------- Список аккаунтов ----------
@router.callback_query(F.data == "list_accounts")
async def list_accounts(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    accounts = await get_all_accounts_from_db()
    if not accounts:
        await callback.message.edit_text("Нет добавленных аккаунтов.", reply_markup=get_back_button())
        await callback.answer()
        return
    text = "👥 Аккаунты фермы:\n\n"
    for acc in accounts:
        status = "🟢 Активен" if acc['is_active'] else "🔴 Неактивен"
        auth = "✅ Авторизован" if acc['is_authorized'] else "❌ Не авторизован"
        text += f"• {acc['phone']} – {status}, {auth}\n"
    await callback.message.edit_text(text, reply_markup=get_back_button())
    await callback.answer()

# ---------- Парсеры ----------
@router.callback_query(F.data == "parser_comments")
async def parser_comments_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    running = telethon_manager.running
    await callback.message.edit_text(
        "🔄 Управление парсером комментариев",
        reply_markup=get_parser_comments_menu(running)
    )
    await callback.answer()

@router.callback_query(F.data == "toggle_comment_parser")
async def toggle_comment_parser(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if telethon_manager.running:
        await telethon_manager.stop_all()
        await callback.answer("Парсеры остановлены")
    else:
        await telethon_manager.start_comment_monitoring()
        await callback.answer("Парсер комментариев запущен")
    running = telethon_manager.running
    await callback.message.edit_reply_markup(reply_markup=get_parser_comments_menu(running))

@router.callback_query(F.data == "parser_news")
async def parser_news_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    running = telethon_manager.running
    await callback.message.edit_text(
        "📰 Управление парсером новостей",
        reply_markup=get_parser_news_menu(running)
    )
    await callback.answer()

@router.callback_query(F.data == "toggle_news_parser")
async def toggle_news_parser(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    if telethon_manager.running:
        await telethon_manager.stop_all()
        await callback.answer("Парсеры остановлены")
    else:
        await telethon_manager.start_news_monitoring()
        await callback.answer("Парсер новостей запущен")
    running = telethon_manager.running
    await callback.message.edit_reply_markup(reply_markup=get_parser_news_menu(running))

# ---------- Настройки ----------
@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("⚙️ Настройки:", reply_markup=get_settings_menu())
    await callback.answer()

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

# ---------- Назад ----------
@router.callback_query(F.data == "back")
async def back_to_main(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    await callback.answer()