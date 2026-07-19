import aiosqlite
from typing import List, Dict, Any, Optional
from .config import DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица каналов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                type TEXT NOT NULL,
                active BOOLEAN DEFAULT 1
            )
        """)
        # Таблица аккаунтов (с сессиями)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                session_string TEXT,          -- сериализованная сессия
                is_active BOOLEAN DEFAULT 1,
                is_authorized BOOLEAN DEFAULT 0
            )
        """)
        # Таблица настроек
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("keywords", ",".join(["впн лагает", "подскажите впн", "какой впн", "впн не работает"]))
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("target_channel", "@your_channel")
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("offer_text", "Мы предлагаем отличный VPN с персональной скидкой. Промокод: SKIDKA2026. Первые 3 дня – бесплатно! Подробнее в нашем канале @vpn_chanel")
        )
        await db.commit()

# ---------- Channels ----------
async def add_channel(chat_id: str, type: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels (chat_id, type, active) VALUES (?, ?, 1)",
            (chat_id, type)
        )
        await db.commit()

async def remove_channel(chat_id: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_channels_by_type(type: str) -> List[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT chat_id FROM channels WHERE type = ? AND active = 1", (type,)
        )
        rows = await cursor.fetchall()
    return [row[0] for row in rows]

async def get_all_channels() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM channels")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def toggle_channel_active(chat_id: str, active: bool) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE channels SET active = ? WHERE chat_id = ?",
            (1 if active else 0, chat_id)
        )
        await db.commit()

# ---------- Accounts (новые методы) ----------
async def add_account_to_db(api_id: int, api_hash: str, phone: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO accounts (api_id, api_hash, phone, is_active, is_authorized) VALUES (?, ?, ?, 1, 0)",
            (api_id, api_hash, phone)
        )
        await db.commit()

async def get_all_accounts_from_db() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def get_active_accounts_from_db() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE is_active = 1")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def get_authorized_accounts() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE is_active = 1 AND is_authorized = 1")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]

async def update_account_session(phone: str, session_string: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE accounts SET session_string = ?, is_authorized = 1 WHERE phone = ?",
            (session_string, phone)
        )
        await db.commit()

async def toggle_account_active_db(phone: str, active: bool) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE accounts SET is_active = ? WHERE phone = ?",
            (1 if active else 0, phone)
        )
        await db.commit()

async def delete_account_from_db(phone: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
        await db.commit()

# ---------- Settings ----------
async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
    return row[0] if row else None

async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()

async def get_keywords() -> List[str]:
    val = await get_setting("keywords")
    if not val:
        return ["впн лагает", "подскажите впн", "какой впн", "впн не работает"]
    return [kw.strip() for kw in val.split(",") if kw.strip()]

async def get_offer_text() -> str:
    val = await get_setting("offer_text")
    if not val:
        return "Мы предлагаем отличный VPN с персональной скидкой. Промокод: SKIDKA2026. Первые 3 дня – бесплатно! Подробнее в нашем канале @vpn_chanel"
    return val

async def get_target_channel() -> str:
    val = await get_setting("target_channel")
    return val or "@your_channel"