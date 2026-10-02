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
        db.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                user_id INTEGER PRIMARY KEY,
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
        db.commit()

def get_character(user_id: int):
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM characters WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def save_character(user_id: int, data: dict):
    fields = ("name","age","pronouns","appearance","personality","backstory","occupation","faction","avatar_url")
    values = [data.get(f, "") for f in fields]
    with closing(connect()) as db:
        db.execute("""
            INSERT INTO characters
            (user_id,name,age,pronouns,appearance,personality,backstory,occupation,faction,avatar_url)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name, age=excluded.age, pronouns=excluded.pronouns,
                appearance=excluded.appearance, personality=excluded.personality,
                backstory=excluded.backstory, occupation=excluded.occupation,
                faction=excluded.faction, avatar_url=excluded.avatar_url,
                updated_at=CURRENT_TIMESTAMP
        """, (user_id, *values))
        db.commit()

def update_character(user_id: int, **changes):
    current = get_character(user_id) or {"name": "Unnamed"}
    current.update({k:v for k,v in changes.items() if k in {
        "name","age","pronouns","appearance","personality","backstory","occupation","faction","avatar_url"
    }})
    save_character(user_id, current)
    return get_character(user_id)

def delete_character(user_id: int):
    with closing(connect()) as db:
        db.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
        db.commit()
