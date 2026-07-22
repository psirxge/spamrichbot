import os
from dotenv import load_dotenv
import pathlib

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Администраторы (Telegram ID, через запятую)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Путь к БД: используем переменную окружения или по умолчанию
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/data.db")
# Извлекаем путь без "sqlite:///"
DATABASE_PATH = DATABASE_URL.replace("sqlite:///", "")

# Создаём папку для БД, если её нет
db_dir = os.path.dirname(DATABASE_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# Для совместимости с другими частями кода
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "data/accounts.json")  # не используется