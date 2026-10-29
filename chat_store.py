"""Local storage for saved chat threads. Private chats never enter this store."""
import json
import os
import sqlite3
from hashlib import sha256
from pathlib import Path
from time import time_ns
from uuid import uuid4

STORE_REVISION = sha256(Path(__file__).read_bytes()).hexdigest()
REPLY_LENGTHS = [24, 48, 96, 128, 256, 512, 1024]
DEFAULT_SETTINGS = {'tokens': 256, 'context_tokens': 1024, 'quantized': False, 'offline': True}


def validate_settings(settings):
    result = {**DEFAULT_SETTINGS, **settings}
    if type(result['tokens']) is not int or result['tokens'] not in REPLY_LENGTHS:
        raise ValueError('Unsupported reply length.')
    if type(result['context_tokens']) is not int or result['context_tokens'] not in {256, 512, 1024, 2048, 4096, 8192}:
        raise ValueError('Unsupported context length.')
    if any(type(result[key]) is not bool for key in ('quantized', 'offline')):
        raise ValueError('INT8 and offline settings must be true or false.')
    if result['context_tokens'] <= result['tokens']:
        raise ValueError('Context length must be larger than reply length. Increase context length to leave space for your question.')
    return {key: result[key] for key in DEFAULT_SETTINGS}


def new_thread(private=False):
    thread_id = uuid4().hex
    return {'id': thread_id, 'slug': thread_id[:10], 'title': 'New chat', 'messages': [], 'private': private}


class ChatStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get('CHAT_DATA_DIR') or Path(__file__).resolve().parent / 'data')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'chats.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL, updated_at INTEGER NOT NULL)')
            if 'slug' not in {row[1] for row in db.execute('PRAGMA table_info(chats)')}:
                db.execute('ALTER TABLE chats ADD COLUMN slug TEXT')
            for (thread_id,) in db.execute('SELECT id FROM chats WHERE slug IS NULL').fetchall():
                db.execute('UPDATE chats SET slug=? WHERE id=?', (self.allocate_slug(db), thread_id))
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS chats_slug ON chats(slug)')
            db.execute('CREATE TABLE IF NOT EXISTS app_settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def load_settings(self):
        with self.connect() as db:
            row = db.execute('SELECT value FROM app_settings WHERE id=1').fetchone()
        if row is None:
            return dict(DEFAULT_SETTINGS)
        try:
            return validate_settings(json.loads(row[0]))
        except (ValueError, TypeError):
            return dict(DEFAULT_SETTINGS)

    def save_settings(self, settings):
        validated = validate_settings(settings)
        with self.connect() as db:
            db.execute('INSERT INTO app_settings (id, value) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (json.dumps(validated),))
        return validated

    @staticmethod
    def allocate_slug(db, preferred=None):
        candidate = preferred or uuid4().hex[:10]
        while db.execute('SELECT 1 FROM chats WHERE slug=?', (candidate,)).fetchone():
            candidate = uuid4().hex[:10]
        return candidate

    def save(self, thread):
        if thread['private']:
            raise ValueError('Private chats cannot be saved.')
        if not thread['messages']:
            return
        with self.connect() as db:
            existing = db.execute('SELECT slug FROM chats WHERE id=?', (thread['id'],)).fetchone()
            thread['slug'] = existing[0] if existing else self.allocate_slug(db, thread.get('slug'))
            db.execute('INSERT INTO chats (id, title, messages, updated_at, slug) VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, messages=excluded.messages, updated_at=excluded.updated_at',
                       (thread['id'], thread['title'], json.dumps(thread['messages'], ensure_ascii=False), time_ns(), thread['slug']))

    def list(self, search=''):
        with self.connect() as db:
            rows = db.execute('SELECT id, title, messages FROM chats ORDER BY updated_at DESC').fetchall()
        needle = search.casefold().strip()
        return [{'id': row[0], 'title': row[1]} for row in rows
                if not needle or needle in row[1].casefold() or any(needle in m['content'].casefold() for m in json.loads(row[2]))]

    def load(self, thread_id):
        with self.connect() as db:
            row = db.execute('SELECT id, title, messages, slug FROM chats WHERE id=?', (thread_id,)).fetchone()
        if row is None:
            raise KeyError('This chat no longer exists.')
        return {'id': row[0], 'slug': row[3], 'title': row[1], 'messages': json.loads(row[2]), 'private': False}

    def load_slug(self, slug):
        with self.connect() as db:
            row = db.execute('SELECT id FROM chats WHERE slug=?', (slug,)).fetchone()
        if row is None:
            raise KeyError('This chat no longer exists.')
        return self.load(row[0])

    def rename(self, thread_id, title):
        title = ' '.join(title.split()).strip()
        if not title or len(title) > 80:
            raise ValueError('Enter a title between 1 and 80 characters.')
        with self.connect() as db:
            db.execute('UPDATE chats SET title=? WHERE id=?', (title, thread_id))
        return self.load(thread_id)

    def duplicate(self, thread_id):
        original = self.load(thread_id)
        copied = {**original, **new_thread(), 'title': original['title'][:73] + ' (copy)', 'messages': original['messages']}
        self.save(copied)
        return copied

    def delete(self, thread_id):
        with self.connect() as db:
            db.execute('DELETE FROM chats WHERE id=?', (thread_id,))
