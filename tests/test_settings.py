"""Local settings persist and invalid writes don't overwrite valid preferences."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_store import ChatStore, DEFAULT_SETTINGS


class SettingsTests(unittest.TestCase):
    def test_settings_survive_new_store_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(directory)
            self.assertEqual(store.load_settings(), DEFAULT_SETTINGS)
            changed = {'tokens': 96, 'context_tokens': 2048, 'quantized': True, 'offline': False}
            store.save_settings(changed)
            self.assertEqual(ChatStore(directory).load_settings(), changed)
            with self.assertRaises(ValueError):
                store.save_settings({**changed, 'tokens': -1})
            self.assertEqual(store.load_settings(), changed)

    def test_invalid_stored_data_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(directory)
            with store.connect() as db:
                db.execute('INSERT INTO app_settings VALUES (1, ?)', ('bad json',))
            self.assertEqual(store.load_settings(), DEFAULT_SETTINGS)
