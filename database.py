from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

import aiosqlite

DB_PATH = os.getenv("DATABASE_PATH") or ("/data/pride.db" if os.path.isdir("/data") else "pride.db")
_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


async def db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.commit()
    return _db


async def init_db():
    conn = await db()
    async with _lock:
        await conn.executescript("""
        CREATE TABLE IF NOT EXISTS pride_users (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reputation INTEGER NOT NULL DEFAULT 0,
            event_count INTEGER NOT NULL DEFAULT 0,
            title TEXT,
            achievements TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS pride_events (
            event_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source_bot TEXT NOT NULL,
            event_name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 0,
            metadata TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pride_users_rep ON pride_users(guild_id, reputation DESC);
        CREATE INDEX IF NOT EXISTS idx_pride_events_user ON pride_events(guild_id, user_id, created_at);
        """)
        await conn.commit()


async def ensure_user(guild_id: int, user_id: int):
    conn = await db()
    async with _lock:
        await conn.execute(
            "INSERT OR IGNORE INTO pride_users (guild_id,user_id,updated_at) VALUES (?,?,?)",
            (guild_id, user_id, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()


async def get_user(guild_id: int, user_id: int) -> dict:
    await ensure_user(guild_id, user_id)
    conn = await db()
    async with _lock:
        cur = await conn.execute(
            "SELECT * FROM pride_users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
    result = dict(row)
    result["achievements"] = json.loads(result["achievements"] or "[]")
    return result


async def record_event(event_id, guild_id, user_id, source_bot, event_name, points, metadata=None):
    await ensure_user(guild_id, user_id)
    conn = await db()
    now = datetime.now(timezone.utc).isoformat()

    async with _lock:
        cur = await conn.execute("SELECT 1 FROM pride_events WHERE event_id=?", (event_id,))
        if await cur.fetchone():
            cur = await conn.execute(
                "SELECT * FROM pride_users WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )
            row = await cur.fetchone()
            result = dict(row)
            result["achievements"] = json.loads(result["achievements"] or "[]")
            result["newly_unlocked"] = []
            return result, False

        cur = await conn.execute(
            "SELECT * FROM pride_users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        reputation = max(0, int(row["reputation"]) + int(points))
        event_count = int(row["event_count"]) + 1
        achievements = json.loads(row["achievements"] or "[]")

        checks = [
            ("FIRST_STEP", event_count >= 1),
            ("RECOGNIZED", reputation >= 50),
            ("RENOWNED", reputation >= 100),
            ("PROUD", reputation >= 250),
            ("ICON", reputation >= 500),
            ("UNFORGETTABLE", reputation >= 1000),
            ("VETERAN", event_count >= 100),
            ("LEGACY", event_count >= 500),
        ]
        newly_unlocked = []
        for key, condition in checks:
            if condition and key not in achievements:
                achievements.append(key)
                newly_unlocked.append(key)

        await conn.execute(
            """INSERT INTO pride_events
               (event_id,guild_id,user_id,source_bot,event_name,points,metadata,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event_id, guild_id, user_id, source_bot, event_name, int(points),
             json.dumps(metadata or {}, separators=(",", ":")), now),
        )
        await conn.execute(
            """UPDATE pride_users
               SET reputation=?,event_count=?,achievements=?,updated_at=?
               WHERE guild_id=? AND user_id=?""",
            (reputation, event_count, json.dumps(achievements, separators=(",", ":")),
             now, guild_id, user_id),
        )
        await conn.commit()

    result = await get_user(guild_id, user_id)
    result["newly_unlocked"] = newly_unlocked
    return result, True


async def set_title(guild_id, user_id, title):
    await ensure_user(guild_id, user_id)
    conn = await db()
    async with _lock:
        await conn.execute(
            "UPDATE pride_users SET title=?,updated_at=? WHERE guild_id=? AND user_id=?",
            (title, datetime.now(timezone.utc).isoformat(), guild_id, user_id),
        )
        await conn.commit()


async def adjust_reputation(guild_id, user_id, delta, source_bot, reason):
    event_id = f"manual:{guild_id}:{user_id}:{source_bot}:{datetime.now(timezone.utc).timestamp()}:{delta}"
    return await record_event(
        event_id, guild_id, user_id, source_bot, "manual_adjustment", delta, {"reason": reason}
    )


async def leaderboard(guild_id, limit=10):
    conn = await db()
    async with _lock:
        cur = await conn.execute(
            """SELECT user_id,reputation,event_count,achievements,title
               FROM pride_users WHERE guild_id=?
               ORDER BY reputation DESC,event_count DESC LIMIT ?""",
            (guild_id, limit),
        )
        rows = await cur.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["achievements"] = json.loads(item["achievements"] or "[]")
        result.append(item)
    return result
