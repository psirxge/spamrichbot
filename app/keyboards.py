from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

# ---------- Reply-клавиатуры ----------
def get_main_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📊 Управление аккаунтами")],
        [KeyboardButton(text="📡 Парсерные аккаунты")],
        [KeyboardButton(text="📢 Управление каналами")],
        [KeyboardButton(text="📰 Парсер новостей")],
        [KeyboardButton(text="💬 Парсер комментариев")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_accounts_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="➕ Добавить аккаунт")],
        [KeyboardButton(text="📁 Загрузить .json")],
        [KeyboardButton(text="📋 Список аккаунтов")],
        [KeyboardButton(text="🔍 Проверить авторизацию")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_parser_accounts_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="➕ Добавить парсер-аккаунт")],
        [KeyboardButton(text="📁 Загрузить .json")],
        [KeyboardButton(text="📋 Список парсер-аккаунтов")],
        [KeyboardButton(text="🔍 Проверить авторизацию")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_channels_management_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="➕ Добавить канал")],
        [KeyboardButton(text="📋 Список каналов")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

# ---------- Inline-клавиатуры ----------
def get_back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_channels_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="list_channels")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_accounts_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")],
        [InlineKeyboardButton(text="📁 Загрузить .json", callback_data="load_json")],
        [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="list_accounts")],
        [InlineKeyboardButton(text="🔍 Проверить авторизацию", callback_data="check_auth")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_parser_accounts_inline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить парсер-аккаунт", callback_data="add_parser_account")],
        [InlineKeyboardButton(text="📁 Загрузить .json", callback_data="load_parser_json")],
        [InlineKeyboardButton(text="📋 Список парсер-аккаунтов", callback_data="list_parser_accounts")],
        [InlineKeyboardButton(text="🔍 Проверить авторизацию", callback_data="check_parser_auth")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Ключевые слова", callback_data="set_keywords")],
        [InlineKeyboardButton(text="💬 Текст предложения", callback_data="set_offer")],
        [InlineKeyboardButton(text="📢 Целевой канал", callback_data="set_target")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_parser_comments_menu(running: bool) -> InlineKeyboardMarkup:
    status = "⏹ Остановить" if running else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_comment_parser")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_parser_news_menu(running: bool) -> InlineKeyboardMarkup:
    status = "⏹ Остановить" if running else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_news_parser")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def get_account_delete_buttons(accounts: List[Dict], purpose: str) -> InlineKeyboardMarkup:
    keyboard = []
    for acc in accounts:
        phone = acc['phone']
        is_authorized = acc.get('is_authorized', 0)
        if not is_authorized and not acc.get('session_string'):
            btn_text = f"▶️ Продолжить {phone}"
            callback_data = f"continue_acc_{purpose}_{phone}"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
        btn_delete = f"❌ Удалить {phone}"
        callback_delete = f"delete_acc_{purpose}_{phone}"
        keyboard.append([InlineKeyboardButton(text=btn_delete, callback_data=callback_delete)])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_channel_delete_buttons(channels: List[Dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in channels:
        chat_id = ch['chat_id']
        btn_text = f"❌ Удалить {chat_id}"
        callback_data = f"delete_channel_{chat_id}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_resend_code_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Запросить новый код", callback_data="resend_code")]
    ])