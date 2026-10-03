import json
import os
import sqlite3
from contextlib import closing

DB_PATH = os.getenv("DATABASE_PATH", "/data/rp.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "rp.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with closing(connect()) as db:
        table_info = db.execute("PRAGMA table_info(characters)").fetchall()

        if table_info:
            old_primary_key = next(
                (
                    row for row in table_info
                    if row["name"] == "user_id" and row["pk"] == 1
                ),
                None,
            )

            if old_primary_key:
                db.execute("""
                    CREATE TABLE characters_new (
                        character_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        age TEXT DEFAULT '',
                        pronouns TEXT DEFAULT '',
                        appearance TEXT DEFAULT '',
                        personality TEXT DEFAULT '',
                        backstory TEXT DEFAULT '',
                        occupation TEXT DEFAULT '',
                        faction TEXT DEFAULT '',
                        avatar_url TEXT DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                db.execute("""
                    INSERT INTO characters_new
                    (
                        user_id, name, age, pronouns, appearance,
                        personality, backstory, occupation, faction,
                        avatar_url, created_at, updated_at
                    )
                    SELECT
                        user_id, name, age, pronouns, appearance,
                        personality, backstory, occupation, faction,
                        avatar_url, created_at, updated_at
                    FROM characters
                """)

                db.execute("DROP TABLE characters")
                db.execute(
                    "ALTER TABLE characters_new RENAME TO characters"
                )

        db.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                character_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                age TEXT DEFAULT '',
                pronouns TEXT DEFAULT '',
                appearance TEXT DEFAULT '',
                personality TEXT DEFAULT '',
                backstory TEXT DEFAULT '',
                occupation TEXT DEFAULT '',
                faction TEXT DEFAULT '',
                avatar_url TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_characters_user_id
            ON characters(user_id)
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS server_config (
                guild_id INTEGER PRIMARY KEY,
                rp_enabled INTEGER NOT NULL DEFAULT 0,
                rp_channel_ids TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS player_config (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                active_character_id INTEGER,
                roleplay_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        player_config_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(player_config)"
            ).fetchall()
        }
        if "roleplay_active" not in player_config_columns:
            db.execute(
                "ALTER TABLE player_config ADD COLUMN "
                "roleplay_active INTEGER NOT NULL DEFAULT 1"
            )

        
        db.commit()


def get_active_character_id(guild_id: int, user_id: int):
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT active_character_id
            FROM player_config
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    return int(row["active_character_id"]) if row and row["active_character_id"] else None


def save_active_character_id(
    guild_id: int,
    user_id: int,
    character_id: int | None,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO player_config (
                guild_id, user_id, active_character_id, updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                active_character_id = excluded.active_character_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, user_id, character_id),
        )
        db.commit()


def get_player_roleplay_active(guild_id: int, user_id: int) -> bool:
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT roleplay_active
            FROM player_config
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    if not row:
        return True

    return bool(row["roleplay_active"])


def save_player_roleplay_active(
    guild_id: int,
    user_id: int,
    active: bool,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO player_config (
                guild_id, user_id, active_character_id,
                roleplay_active, updated_at
            )
            VALUES (?, ?, NULL, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                roleplay_active = excluded.roleplay_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, user_id, 1 if active else 0),
        )
        db.commit()


def get_roleplay_settings(guild_id: int):
    with closing(connect()) as db:
        row = db.execute(
            "SELECT guild_id, rp_enabled, rp_channel_ids "
            "FROM server_config WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()

    if not row:
        return {
            "guild_id": guild_id,
            "enabled": False,
            "channel_ids": [],
        }

    try:
        channel_ids = [
            int(channel_id)
            for channel_id in json.loads(row["rp_channel_ids"] or "[]")
        ]
    except (TypeError, ValueError, json.JSONDecodeError):
        channel_ids = []

    return {
        "guild_id": guild_id,
        "enabled": bool(row["rp_enabled"]),
        "channel_ids": channel_ids,
    }


def save_roleplay_settings(
    guild_id: int,
    enabled: bool,
    channel_ids: list[int],
):
    unique_channels = list(dict.fromkeys(int(channel_id) for channel_id in channel_ids))

    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO server_config (
                guild_id, rp_enabled, rp_channel_ids, updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                rp_enabled = excluded.rp_enabled,
                rp_channel_ids = excluded.rp_channel_ids,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                guild_id,
                1 if enabled else 0,
                json.dumps(unique_channels),
            ),
        )
        db.commit()


def get_characters(user_id: int):
    with closing(connect()) as db:
        rows = db.execute(
            """
            SELECT *
            FROM characters
            WHERE user_id = ?
            ORDER BY character_id ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_character(character_id: int):
    with closing(connect()) as db:
        row = db.execute(
            "SELECT * FROM characters WHERE character_id = ?",
            (character_id,),
        ).fetchone()
        return dict(row) if row else None


def save_character(
    user_id: int,
    data: dict,
    character_id: int | None = None,
):
    fields = (
        "name",
        "age",
        "pronouns",
        "appearance",
        "personality",
        "backstory",
        "occupation",
        "faction",
        "avatar_url",
    )
    values = [data.get(field, "") for field in fields]

    with closing(connect()) as db:
        if character_id is None:
            cursor = db.execute(
                """
                INSERT INTO characters
                (
                    user_id, name, age, pronouns, appearance,
                    personality, backstory, occupation, faction, avatar_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, *values),
            )
            db.commit()
            return int(cursor.lastrowid)

        db.execute(
            """
            UPDATE characters
            SET
                name = ?,
                age = ?,
                pronouns = ?,
                appearance = ?,
                personality = ?,
                backstory = ?,
                occupation = ?,
                faction = ?,
                avatar_url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE character_id = ? AND user_id = ?
            """,
            (*values, character_id, user_id),
        )
        db.commit()
        return character_id


def update_character(character_id: int, **changes):
    allowed = {
        "name",
        "age",
        "pronouns",
        "appearance",
        "personality",
        "backstory",
        "occupation",
        "faction",
        "avatar_url",
    }

    with closing(connect()) as db:
        current = db.execute(
            "SELECT * FROM characters WHERE character_id = ?",
            (character_id,),
        ).fetchone()

        if not current:
            return None

        current = dict(current)
        current.update(
            {
                key: value
                for key, value in changes.items()
                if key in allowed
            }
        )

        fields = (
            "name",
            "age",
            "pronouns",
            "appearance",
            "personality",
            "backstory",
            "occupation",
            "faction",
            "avatar_url",
        )

        db.execute(
            f"""
            UPDATE characters
            SET
                {", ".join(f"{field} = ?" for field in fields)},
                updated_at = CURRENT_TIMESTAMP
            WHERE character_id = ?
            """,
            tuple(current.get(field, "") for field in fields)
            + (character_id,),
        )
        db.commit()

    return get_character(character_id)


def delete_character(character_id: int):
    with closing(connect()) as db:
        db.execute(
            "DELETE FROM characters WHERE character_id = ?",
            (character_id,),
        )
        db.commit()
