from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

# ---------- Reply-клавиатуры ----------
def get_main_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📊 Управление аккаунтами")],
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

def get_channels_management_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="➕ Добавить канал")],
        [KeyboardButton(text="📋 Список каналов")],
        [KeyboardButton(text="🔍 Получить ID обсуждений")],
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

def get_settings_menu(running: bool, answer_enabled: bool, collect_enabled: bool) -> InlineKeyboardMarkup:
    comment_status = "⏹ Остановить" if running else "▶️ Запустить"
    answer_status = "✅ Вкл" if answer_enabled else "❌ Выкл"
    collect_status = "✅ Вкл" if collect_enabled else "❌ Выкл"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Ключевые слова", callback_data="set_keywords")],
        [InlineKeyboardButton(text="💬 Текст предложения", callback_data="set_offer")],
        [InlineKeyboardButton(text="📢 Целевой канал", callback_data="set_target")],
        [InlineKeyboardButton(text=f"💬 {comment_status} мониторинг", callback_data="toggle_comment_parser")],
        [InlineKeyboardButton(text=f"📝 Ответы: {answer_status}", callback_data="toggle_answer")],
        [InlineKeyboardButton(text=f"📊 Сбор данных: {collect_status}", callback_data="toggle_collect")],
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

def get_account_delete_buttons(accounts: List[Dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for acc in accounts:
        phone = acc['phone']
        is_sender = acc.get('is_sender', 0)
        is_parser = acc.get('is_parser', 0)
        is_authorized = acc.get('is_authorized', 0)
        has_session = bool(acc.get('session_string'))

        if is_authorized and has_session:
            auth_status = "✅ Авторизован"
        elif has_session and not is_authorized:
            auth_status = "⚠️ Сессия есть, но не подтверждена"
        else:
            auth_status = "❌ Не авторизован"

        roles = []
        if is_sender:
            roles.append("📤Sender")
        if is_parser:
            roles.append("📡Parser")
        role_str = ", ".join(roles) if roles else "❌ Нет ролей"

        btn_sender = InlineKeyboardButton(
            text=f"{'✅' if is_sender else '⬜'} Sender",
            callback_data=f"toggle_role_{phone}_sender"
        )
        btn_parser = InlineKeyboardButton(
            text=f"{'✅' if is_parser else '⬜'} Parser",
            callback_data=f"toggle_role_{phone}_parser"
        )
        btn_delete = InlineKeyboardButton(
            text="❌ Удалить",
            callback_data=f"delete_acc_{phone}"
        )

        keyboard.append([InlineKeyboardButton(
            text=f"📱 {phone} | {auth_status} | {role_str}",
            callback_data="ignore"
        )])
        keyboard.append([btn_sender, btn_parser, btn_delete])
        keyboard.append([InlineKeyboardButton(text="─" * 20, callback_data="ignore")])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_channel_delete_buttons(channels: List[Dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in channels:
        chat_id = ch['chat_id']
        chat_type = ch.get('type', 'unknown')
        linked_id = ch.get('linked_chat_id', '')
        label = f"{chat_id} ({chat_type})"
        if linked_id:
            label += f" ↔ {linked_id}"
        btn_text = f"❌ Удалить {label}"
        callback_data = f"delete_channel_{chat_id}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_resend_code_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Запросить новый код", callback_data="resend_code")]
    ])