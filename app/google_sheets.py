import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_name: str):
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.client = None
        self.sheet = None
        self._init_client()

    def _init_client(self):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, scope)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open(self.spreadsheet_name).sheet1
            logger.info(f"✅ Google Sheets подключен: {self.spreadsheet_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.client = None
            self.sheet = None

    async def add_comment_record(self, comment_data: Dict) -> bool:
        if not self.sheet:
            logger.error("❌ Google Sheets не инициализирован")
            return False
        try:
            row = [
                comment_data.get('datetime', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                comment_data.get('channel', ''),
                comment_data.get('user_id', ''),
                comment_data.get('username', ''),
                comment_data.get('display_name', ''),
                comment_data.get('mention', ''),
                comment_data.get('text', ''),
                '✅' if comment_data.get('replied', False) else '❌'
            ]
            self.sheet.append_row(row)
            logger.info(f"✅ Запись добавлена в Google Sheets: {row}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка записи в Google Sheets: {e}")
            return False