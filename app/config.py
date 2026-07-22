import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Администраторы (Telegram ID, через запятую)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Путь к БД
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/data.db")
DATABASE_PATH = DATABASE_URL.replace("sqlite:///", "")

# Путь к файлу credentials Google Sheets
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "")