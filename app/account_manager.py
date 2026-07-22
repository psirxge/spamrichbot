from .db import (
    add_or_update_account, get_all_accounts_from_db, get_active_accounts_from_db,
    get_authorized_accounts, update_account_session, toggle_account_active_db,
    delete_account_from_db, toggle_account_role
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

    async def get_active_accounts(self, role: str = None) -> List[Dict]:
        return await get_active_accounts_from_db(role)

    async def get_authorized_accounts(self, role: str = None) -> List[Dict]:
        return await get_authorized_accounts(role)

    async def add_account(self, api_id: int, api_hash: str, phone: str, is_sender: bool = False, is_parser: bool = False):
        await add_or_update_account(api_id, api_hash, phone, is_sender, is_parser)
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

    async def toggle_role(self, phone: str, role: str, enabled: bool):
        await toggle_account_role(phone, role, enabled)
        await self.load()

    async def remove_account(self, phone: str):
        await delete_account_from_db(phone)
        await self.load()

    async def get_next_account(self, role: str = None) -> Optional[Dict]:
        active = await self.get_active_accounts(role)
        if not active:
            return None
        for i in range(len(active)):
            idx = (self.current_index + i) % len(active)
            acc = active[idx]
            if acc.get("is_active", True):
                self.current_index = (idx + 1) % len(active)
                return acc
        return None