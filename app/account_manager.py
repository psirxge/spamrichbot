from .db import (
    add_account_to_db, get_all_accounts_from_db, get_active_accounts_from_db,
    get_authorized_accounts, update_account_session, toggle_account_active_db,
    delete_account_from_db
)
from typing import Dict, List, Optional

class AccountManager:
    def __init__(self):
        self.accounts = []
        self.current_index = 0

    async def load(self):
        self.accounts = await get_all_accounts_from_db()

    async def save(self):
        pass

    # Для sender-аккаунтов
    async def get_active_accounts(self, purpose: str = 'sender') -> List[Dict]:
        return await get_active_accounts_from_db(purpose)

    async def get_authorized_accounts(self, purpose: str = 'sender') -> List[Dict]:
        return await get_authorized_accounts(purpose)

    async def add_account(self, api_id: int, api_hash: str, phone: str, purpose: str = 'sender'):
        await add_account_to_db(api_id, api_hash, phone, purpose)
        await self.load()

    async def mark_authorized(self, phone: str, session_string: str):
        await update_account_session(phone, session_string)
        await self.load()

    async def mark_blocked(self, phone: str):
        await toggle_account_active_db(phone, False)
        await self.load()

    async def toggle_active(self, phone: str, active: bool):
        await toggle_account_active_db(phone, active)
        await self.load()

    async def remove_account(self, phone: str):
        await delete_account_from_db(phone)
        await self.load()

    async def get_next_account(self, purpose: str = 'sender') -> Optional[Dict]:
        active = await self.get_active_accounts(purpose)
        if not active:
            return None
        for i in range(len(active)):
            idx = (self.current_index + i) % len(active)
            acc = active[idx]
            if acc.get("is_active", True):
                self.current_index = (idx + 1) % len(active)
                return acc
        return None