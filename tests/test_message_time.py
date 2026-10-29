"""New timestamps are timezone-aware; legacy messages don't get invented times."""
from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from message_time import timestamp_now, display_time


class MessageTimeTests(unittest.TestCase):
    def test_timestamp_has_timezone(self):
        self.assertIsNotNone(datetime.fromisoformat(timestamp_now()).tzinfo)

    def test_browser_timezone_display(self):
        label, tooltip = display_time('2026-10-29T07:00:00+00:00', 'Asia/Karachi')
        self.assertEqual(label, '12:00 PM')
        self.assertIn('2026-10-29 12:00:00', tooltip)

    def test_missing_or_invalid_legacy_time(self):
        self.assertEqual(display_time(None)[0], '—')
        self.assertEqual(display_time('not a timestamp')[0], '—')
