import json
import sqlite3
from contextlib import contextmanager
from .config import settings


@contextmanager
def connection():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.data_dir / 'assistant.db', timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        yield db


def initialize():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
            chunks INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY, title TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')


def rows(query, params=()):
    with connection() as db:
        return [dict(row) for row in db.execute(query, params).fetchall()]


def execute(query, params=()):
    with connection() as db:
        db.execute(query, params)


def messages(chat_id):
    result = rows('SELECT * FROM messages WHERE chat_id=? ORDER BY id', (chat_id,))
    for item in result:
        item['sources'] = json.loads(item['sources'])
    return result
