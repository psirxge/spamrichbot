import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Администраторы (Telegram ID, через запятую)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/data.db")
DATABASE_PATH = DATABASE_URL.replace("sqlite:///", "")
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "data/accounts.json")  # не используется, но оставлено