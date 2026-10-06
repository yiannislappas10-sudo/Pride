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

        server_config_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(server_config)"
            ).fetchall()
        }
        if "archive_channel_id" not in server_config_columns:
            db.execute(
                "ALTER TABLE server_config ADD COLUMN archive_channel_id INTEGER"
            )
        if "archive_enabled" not in server_config_columns:
            db.execute(
                "ALTER TABLE server_config ADD COLUMN archive_enabled INTEGER NOT NULL DEFAULT 0"
            )

        db.execute("""
            CREATE TABLE IF NOT EXISTS player_config (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                active_character_id INTEGER,
                roleplay_active INTEGER NOT NULL DEFAULT 1,
                auto_rp_format INTEGER NOT NULL DEFAULT 0,
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

        if "auto_rp_format" not in player_config_columns:
            db.execute(
                "ALTER TABLE player_config ADD COLUMN "
                "auto_rp_format INTEGER NOT NULL DEFAULT 0"
            )

        db.execute("""
            CREATE TABLE IF NOT EXISTS rp_learning_examples (
                example_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_rp_learning_lookup
            ON rp_learning_examples(guild_id, user_id, character_id, example_id DESC)
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                premise TEXT DEFAULT '',
                location TEXT DEFAULT '',
                tone TEXT DEFAULT '',
                ending TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planning',
                channel_id INTEGER,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_guild_status
            ON episodes(guild_id, status, episode_id DESC)
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS episode_cast (
                episode_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (episode_id, user_id),
                FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
            )
        """)

        episode_cast_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(episode_cast)"
            ).fetchall()
        }
        for column_sql in (
            "auto_rp_format INTEGER NOT NULL DEFAULT 0",
            "roleplay_active INTEGER NOT NULL DEFAULT 1",
        ):
            column_name = column_sql.split()[0]
            if column_name not in episode_cast_columns:
                db.execute(
                    f"ALTER TABLE episode_cast ADD COLUMN {column_sql}"
                )

        episode_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(episodes)").fetchall()
        }
        if "prep_started_at" not in episode_columns:
            db.execute(
                "ALTER TABLE episodes ADD COLUMN prep_started_at TEXT"
            )
        for column_sql in (
            "details TEXT DEFAULT ''",
            "max_players INTEGER NOT NULL DEFAULT 2",
            "prep_channel_id INTEGER",
            "narrator_id INTEGER",
        ):
            column_name = column_sql.split()[0]
            if column_name not in episode_columns:
                db.execute(
                    f"ALTER TABLE episodes ADD COLUMN {column_sql}"
                )


        for column_sql in (
            "lobby_channel_id INTEGER",
            "lobby_message_id INTEGER",
            "prep_message_id INTEGER",
            "archive_published INTEGER NOT NULL DEFAULT 0",
            "archive_published_at TEXT",
            "last_activity_at TEXT",
            "inactivity_warning_sent INTEGER NOT NULL DEFAULT 0",
            "inactivity_warning_message_id INTEGER",
        ):
            column_name = column_sql.split()[0]
            if column_name not in episode_columns:
                db.execute(
                    f"ALTER TABLE episodes ADD COLUMN {column_sql}"
                )

        db.execute("""
            CREATE TABLE IF NOT EXISTS episode_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL DEFAULT 0,
                character_name TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                discord_message_id INTEGER,
                content TEXT NOT NULL,
                message_type TEXT NOT NULL DEFAULT 'character',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
            )
        """)

        episode_message_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(episode_messages)"
            ).fetchall()
        }
        if "message_type" not in episode_message_columns:
            db.execute(
                "ALTER TABLE episode_messages ADD COLUMN "
                "message_type TEXT NOT NULL DEFAULT 'character'"
            )

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_episode_messages_episode
            ON episode_messages(episode_id, message_id ASC)
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS episode_narrator_requests (
                episode_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (episode_id, user_id),
                FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_episode_narrator_requests_episode
            ON episode_narrator_requests(episode_id, requested_at ASC)
        """)

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


def get_player_auto_rp_format(guild_id: int, user_id: int) -> bool:
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT auto_rp_format
            FROM player_config
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ).fetchone()

    return bool(row["auto_rp_format"]) if row else False


def save_player_auto_rp_format(
    guild_id: int,
    user_id: int,
    enabled: bool,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO player_config (
                guild_id, user_id, active_character_id,
                roleplay_active, auto_rp_format, updated_at
            )
            VALUES (?, ?, NULL, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                auto_rp_format = excluded.auto_rp_format,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, user_id, 1 if enabled else 0),
        )
        db.commit()


def get_rp_learning_examples(
    guild_id: int,
    user_id: int,
    character_id: int,
    limit: int = 8,
):
    safe_limit = max(1, min(int(limit), 20))
    with closing(connect()) as db:
        rows = db.execute(
            f"""
            SELECT input_text, output_text
            FROM rp_learning_examples
            WHERE guild_id = ? AND user_id = ? AND character_id = ?
            ORDER BY example_id DESC
            LIMIT {safe_limit}
            """,
            (guild_id, user_id, character_id),
        ).fetchall()

    return [dict(row) for row in rows]


def save_rp_learning_example(
    guild_id: int,
    user_id: int,
    character_id: int,
    input_text: str,
    output_text: str,
):
    input_text = (input_text or "").strip()[:2000]
    output_text = (output_text or "").strip()[:2000]
    if not input_text or not output_text:
        return

    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO rp_learning_examples (
                guild_id, user_id, character_id, input_text, output_text
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, character_id, input_text, output_text),
        )

        db.execute(
            """
            DELETE FROM rp_learning_examples
            WHERE guild_id = ? AND user_id = ? AND character_id = ?
              AND example_id NOT IN (
                  SELECT example_id
                  FROM rp_learning_examples
                  WHERE guild_id = ? AND user_id = ? AND character_id = ?
                  ORDER BY example_id DESC
                  LIMIT 200
              )
            """,
            (
                guild_id, user_id, character_id,
                guild_id, user_id, character_id,
            ),
        )
        db.commit()

def get_roleplay_settings(guild_id: int):
    with closing(connect()) as db:
        row = db.execute(
            "SELECT guild_id, rp_enabled, rp_channel_ids, "
            "archive_channel_id, archive_enabled "
            "FROM server_config WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()

    if not row:
        return {
            "guild_id": guild_id,
            "enabled": False,
            "channel_ids": [],
            "archive_channel_id": None,
            "archive_enabled": False,
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
        "archive_channel_id": (
            int(row["archive_channel_id"])
            if row["archive_channel_id"]
            else None
        ),
        "archive_enabled": bool(row["archive_enabled"]),
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


def save_archive_settings(
    guild_id: int,
    archive_channel_id: int | None,
    archive_enabled: bool,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO server_config (
                guild_id, rp_enabled, rp_channel_ids,
                archive_channel_id, archive_enabled, updated_at
            )
            VALUES (
                ?, 0, '[]', ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT(guild_id) DO UPDATE SET
                archive_channel_id = excluded.archive_channel_id,
                archive_enabled = excluded.archive_enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                guild_id,
                archive_channel_id,
                1 if archive_enabled else 0,
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


def create_episode(
    guild_id: int,
    creator_id: int,
    title: str,
    premise: str = "",
    location: str = "",
    tone: str = "",
    ending: str = "",
    details: str = "",
    max_players: int = 2,
):
    title = (title or "").strip()[:100]
    premise = (premise or "").strip()[:2000]
    location = (location or "").strip()[:300]
    tone = (tone or "").strip()[:300]
    ending = (ending or "").strip()[:1000]
    details = (details or "").strip()[:3000]
    try:
        max_players = max(1, min(int(max_players), 25))
    except (TypeError, ValueError):
        max_players = 2

    if not title:
        return None

    with closing(connect()) as db:
        cursor = db.execute(
            """
            INSERT INTO episodes (
                guild_id, creator_id, title, premise, location,
                tone, ending, details, max_players
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id, creator_id, title, premise, location,
                tone, ending, details, max_players,
            ),
        )
        db.commit()
        episode_id = int(cursor.lastrowid)

    return get_episode(episode_id)


def get_episode(episode_id: int):
    with closing(connect()) as db:
        row = db.execute(
            "SELECT * FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
    return dict(row) if row else None


def get_episodes(guild_id: int, limit: int = 25):
    safe_limit = max(1, min(int(limit), 25))
    with closing(connect()) as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM episodes
            WHERE guild_id = ?
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'preparing' THEN 2
                    WHEN 'planning' THEN 3
                    WHEN 'completed' THEN 4
                    WHEN 'paused' THEN 1
                    ELSE 4
                END,
                episode_id DESC
            LIMIT {safe_limit}
            """,
            (guild_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_episode(
    episode_id: int,
    *,
    status: str | None = None,
    channel_id: int | None = None,
    prep_channel_id: int | None = None,
    title: str | None = None,
    premise: str | None = None,
    location: str | None = None,
    tone: str | None = None,
    ending: str | None = None,
    details: str | None = None,
    max_players: int | None = None,
    lobby_channel_id: int | None = None,
    lobby_message_id: int | None = None,
    prep_message_id: int | None = None,
    narrator_id: int | None = None,
    archive_published: bool | None = None,
):
    allowed_statuses = {"planning", "preparing", "active", "paused", "completed"}

    with closing(connect()) as db:
        current = db.execute(
            "SELECT * FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if not current:
            return None

        values = dict(current)
        if status in allowed_statuses:
            values["status"] = status
        if channel_id is not None:
            values["channel_id"] = int(channel_id)
        if prep_channel_id is not None:
            values["prep_channel_id"] = int(prep_channel_id)
        for key, value, limit in (
            ("title", title, 100),
            ("premise", premise, 2000),
            ("location", location, 300),
            ("tone", tone, 300),
            ("ending", ending, 1000),
            ("details", details, 3000),
        ):
            if value is not None:
                values[key] = str(value).strip()[:limit]
        if max_players is not None:
            try:
                values["max_players"] = max(1, min(int(max_players), 25))
            except (TypeError, ValueError):
                pass
        if lobby_channel_id is not None:
            values["lobby_channel_id"] = int(lobby_channel_id)
        if lobby_message_id is not None:
            values["lobby_message_id"] = int(lobby_message_id)
        if prep_message_id is not None:
            values["prep_message_id"] = int(prep_message_id)
        if narrator_id is not None:
            values["narrator_id"] = int(narrator_id)
        if archive_published is not None:
            values["archive_published"] = 1 if archive_published else 0

        db.execute(
            """
            UPDATE episodes
            SET
                status = ?,
                channel_id = ?,
                prep_channel_id = ?,
                title = ?,
                premise = ?,
                location = ?,
                tone = ?,
                ending = ?,
                details = ?,
                max_players = ?,
                lobby_channel_id = ?,
                lobby_message_id = ?,
                prep_message_id = ?,
                narrator_id = ?,
                archive_published = ?,
                archive_published_at = CASE
                    WHEN ? = 1 AND COALESCE(archive_published, 0) = 0
                    THEN CURRENT_TIMESTAMP
                    WHEN ? = 0 THEN NULL
                    ELSE archive_published_at
                END,
                prep_started_at = CASE
                    WHEN ? = 'preparing' AND prep_started_at IS NULL
                    THEN CURRENT_TIMESTAMP
                    ELSE prep_started_at
                END,
                started_at =
                    CASE
                        WHEN ? = 'active' AND started_at IS NULL
                        THEN CURRENT_TIMESTAMP
                        ELSE started_at
                    END,
                ended_at =
                    CASE
                        WHEN ? = 'completed'
                        THEN CURRENT_TIMESTAMP
                        ELSE ended_at
                    END,
                updated_at = CURRENT_TIMESTAMP
            WHERE episode_id = ?
            """,
            (
                values["status"],
                values["channel_id"],
                values.get("prep_channel_id"),
                values["title"],
                values["premise"],
                values["location"],
                values["tone"],
                values["ending"],
                values.get("details", ""),
                values.get("max_players", 2),
                values.get("lobby_channel_id"),
                values.get("lobby_message_id"),
                values.get("prep_message_id"),
                values.get("narrator_id"),
                values.get("archive_published", 0),
                values.get("archive_published", 0),
                values.get("archive_published", 0),
                values["status"],
                values["status"],
                values["status"],
                episode_id,
            ),
        )
        db.commit()

    return get_episode(episode_id)


def touch_episode_activity(episode_id: int):
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT inactivity_warning_message_id
            FROM episodes
            WHERE episode_id = ? AND status = 'active'
            """,
            (episode_id,),
        ).fetchone()
        warning_message_id = (
            int(row["inactivity_warning_message_id"])
            if row and row["inactivity_warning_message_id"]
            else None
        )
        db.execute(
            """
            UPDATE episodes
            SET last_activity_at = CURRENT_TIMESTAMP,
                inactivity_warning_sent = 0,
                inactivity_warning_message_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE episode_id = ? AND status = 'active'
            """,
            (episode_id,),
        )
        db.commit()
    return warning_message_id


def mark_episode_inactivity_warning(
    episode_id: int,
    message_id: int,
):
    with closing(connect()) as db:
        db.execute(
            """
            UPDATE episodes
            SET inactivity_warning_sent = 1,
                inactivity_warning_message_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE episode_id = ?
            """,
            (int(message_id), episode_id),
        )
        db.commit()


def mark_episode_archive_published(episode_id: int, published: bool = True):
    with closing(connect()) as db:
        db.execute(
            """
            UPDATE episodes
            SET archive_published = ?,
                archive_published_at = CASE
                    WHEN ? = 1 THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE episode_id = ?
            """,
            (1 if published else 0, 1 if published else 0, episode_id),
        )
        db.commit()


def get_unpublished_completed_episodes(guild_id: int):
    with closing(connect()) as db:
        rows = db.execute(
            """
            SELECT *
            FROM episodes
            WHERE guild_id = ?
              AND status = 'completed'
              AND COALESCE(archive_published, 0) = 0
            ORDER BY episode_id ASC
            """,
            (guild_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_episode(episode_id: int):
    with closing(connect()) as db:
        db.execute("DELETE FROM episode_messages WHERE episode_id = ?", (episode_id,))
        db.execute("DELETE FROM episode_cast WHERE episode_id = ?", (episode_id,))
        db.execute("DELETE FROM episodes WHERE episode_id = ?", (episode_id,))
        db.commit()


def get_episode_cast(episode_id: int):
    with closing(connect()) as db:
        rows = db.execute(
            """
            SELECT *
            FROM episode_cast
            WHERE episode_id = ?
            ORDER BY joined_at ASC
            """,
            (episode_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_episode_cast(
    episode_id: int,
    guild_id: int,
    user_id: int,
    character_id: int,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO episode_cast (
                episode_id, guild_id, user_id, character_id
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(episode_id, user_id) DO UPDATE SET
                character_id = excluded.character_id
            """,
            (episode_id, guild_id, user_id, character_id),
        )
        db.commit()


def add_episode_narrator_request(
    episode_id: int,
    guild_id: int,
    user_id: int,
):
    with closing(connect()) as db:
        db.execute(
            """
            INSERT OR IGNORE INTO episode_narrator_requests (
                episode_id, guild_id, user_id
            )
            VALUES (?, ?, ?)
            """,
            (episode_id, guild_id, user_id),
        )
        db.commit()


def get_episode_narrator_requests(episode_id: int):
    with closing(connect()) as db:
        rows = db.execute(
            """
            SELECT *
            FROM episode_narrator_requests
            WHERE episode_id = ?
            ORDER BY requested_at ASC
            """,
            (episode_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_episode_narrator_request(episode_id: int, user_id: int):
    with closing(connect()) as db:
        db.execute(
            """
            DELETE FROM episode_narrator_requests
            WHERE episode_id = ? AND user_id = ?
            """,
            (episode_id, user_id),
        )
        db.commit()


def clear_episode_narrator_requests(episode_id: int):
    with closing(connect()) as db:
        db.execute(
            "DELETE FROM episode_narrator_requests WHERE episode_id = ?",
            (episode_id,),
        )
        db.commit()


def set_episode_narrator(episode_id: int, narrator_id: int | None):
    with closing(connect()) as db:
        db.execute(
            """
            UPDATE episodes
            SET narrator_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE episode_id = ?
            """,
            (int(narrator_id) if narrator_id is not None else None, episode_id),
        )
        db.commit()


def get_active_episode(guild_id: int, channel_id: int):
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT *
            FROM episodes
            WHERE guild_id = ? AND channel_id = ? AND status = 'active'
            ORDER BY episode_id DESC
            LIMIT 1
            """,
            (guild_id, channel_id),
        ).fetchone()
    return dict(row) if row else None


def save_episode_message(
    episode_id: int,
    guild_id: int,
    user_id: int,
    character_id: int,
    character_name: str,
    channel_id: int,
    discord_message_id: int | None,
    content: str,
    message_type: str = "character",
):
    content = (content or "").strip()[:2000]
    character_name = (character_name or "Character").strip()[:100]
    message_type = (
        "narrator" if str(message_type).strip().lower() == "narrator"
        else "character"
    )
    if not content:
        return

    with closing(connect()) as db:
        db.execute(
            """
            INSERT INTO episode_messages (
                episode_id, guild_id, user_id, character_id,
                character_name, channel_id, discord_message_id, content,
                message_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id,
                guild_id,
                user_id,
                character_id,
                character_name,
                channel_id,
                discord_message_id,
                content,
                message_type,
            ),
        )
        db.commit()


def get_episode_message_count(episode_id: int):
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT COUNT(*) AS message_count
            FROM episode_messages
            WHERE episode_id = ?
            """,
            (episode_id,),
        ).fetchone()
    return int(row["message_count"]) if row else 0


def get_episode_messages(episode_id: int):
    with closing(connect()) as db:
        rows = db.execute(
            """
            SELECT *
            FROM episode_messages
            WHERE episode_id = ?
            ORDER BY message_id ASC
            """,
            (episode_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def remove_episode_cast(episode_id: int, user_id: int):
    with closing(connect()) as db:
        db.execute(
            "DELETE FROM episode_cast WHERE episode_id = ? AND user_id = ?",
            (episode_id, user_id),
        )
        db.commit()


def lock_episode_player_settings(episode_id: int):
    """Snapshot each cast member's OC/AI setting when the episode begins.

    Personal RP is activated automatically at episode start; AI RP Format keeps
    the player's last saved choice from before the prep timer ended.
    """
    with closing(connect()) as db:
        db.execute(
            """
            UPDATE episode_cast
            SET
                auto_rp_format = COALESCE(
                    (
                        SELECT auto_rp_format
                        FROM player_config
                        WHERE player_config.guild_id = episode_cast.guild_id
                          AND player_config.user_id = episode_cast.user_id
                    ),
                    0
                ),
                roleplay_active = 1
            WHERE episode_id = ?
            """,
            (episode_id,),
        )
        db.commit()



def get_episode_preparation_remaining(episode_id: int, prep_seconds: int = 600):
    episode = get_episode(episode_id)
    if not episode or not episode.get("prep_started_at"):
        return prep_seconds

    from datetime import datetime, timezone

    try:
        started = datetime.strptime(
            episode["prep_started_at"],
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return prep_seconds

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return max(0, int(prep_seconds - elapsed))
