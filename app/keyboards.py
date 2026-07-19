from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton(text="👥 Управление аккаунтами", callback_data="manage_accounts")],
        [InlineKeyboardButton(text="🔄 Парсер комментариев", callback_data="parser_comments")],
        [InlineKeyboardButton(text="📰 Парсер новостей", callback_data="parser_news")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ])

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def get_channels_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="list_channels")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def get_accounts_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account")],
        [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="list_accounts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def get_parser_comments_menu(running: bool):
    status = "⏹ Остановить" if running else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_comment_parser")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def get_parser_news_menu(running: bool):
    status = "⏹ Остановить" if running else "▶️ Запустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="toggle_news_parser")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def get_settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Ключевые слова", callback_data="set_keywords")],
        [InlineKeyboardButton(text="📝 Текст предложения", callback_data="set_offer")],
        [InlineKeyboardButton(text="🎯 Целевой канал", callback_data="set_target")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])