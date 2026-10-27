import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY, due TEXT NOT NULL, text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, amount REAL NOT NULL,
    category TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL,
    value REAL, note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY, created TEXT NOT NULL, text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
"""


def db_path() -> Path:
    return Path(os.environ.get("JARVIS_DB", ROOT / "data" / "jarvis.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
