"""Existing histories receive stable, collision-checked URL slugs."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_store import ChatStore, new_thread


class SlugTests(unittest.TestCase):
    def test_legacy_database_migration_preserves_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            messages = [{'role': 'user', 'content': 'Existing history'}]
            with sqlite3.connect(Path(directory) / 'chats.sqlite3') as db:
                db.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL, updated_at INTEGER NOT NULL)')
                db.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', ('old-id', 'Old chat', json.dumps(messages), 1))
            store = ChatStore(directory)
            migrated = store.load('old-id')
            self.assertEqual(migrated['messages'], messages)
            self.assertEqual(store.load_slug(migrated['slug']), migrated)
            self.assertEqual(ChatStore(directory).load('old-id')['slug'], migrated['slug'])

    def test_slug_collision_and_duplicate_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(directory)
            first = new_thread()
            first['messages'] = [{'role': 'user', 'content': 'First'}]
            store.save(first)
            second = {**new_thread(), 'slug': first['slug'], 'messages': [{'role': 'user', 'content': 'Second'}]}
            store.save(second)
            self.assertNotEqual(first['slug'], second['slug'])
            copy = store.duplicate(first['id'])
            self.assertNotIn(copy['slug'], {first['slug'], second['slug']})
