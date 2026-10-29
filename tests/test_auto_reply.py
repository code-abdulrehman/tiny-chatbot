"""Automatic continuation appends to one answer and has explicit stop conditions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_reply import complete_reply


class FakeEngine:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.calls = []

    def stream(self, history, **kwargs):
        self.calls.append((history, kwargs))
        step = next(self.steps)
        if isinstance(step, Exception):
            raise step
        text, truncated = step
        yield text
        kwargs['generation_status']['truncated'] = truncated


class AutoReplyTests(unittest.TestCase):
    def test_continues_until_eos_without_repeating_user(self):
        engine = FakeEngine([('One', True), (' two', True), (' three.', False)])
        status = {}
        text = ''.join(complete_reply(engine, [{'role': 'user', 'content': 'Question'}],
                                     max_new_tokens=24, context_tokens=1024, status=status))
        self.assertEqual(text, 'One two three.')
        self.assertFalse(status['truncated'])
        self.assertEqual(len(engine.calls), 3)
        self.assertEqual(engine.calls[1][0][-1], {'role': 'assistant', 'content': 'One'})
        self.assertEqual(engine.calls[2][0][-1]['content'], 'One two')
        self.assertFalse(engine.calls[0][1]['continue_reply'])
        self.assertTrue(engine.calls[1][1]['continue_reply'])

    def test_context_full_keeps_partial_answer(self):
        engine = FakeEngine([('Partial', True), ValueError('Context is full')])
        status = {}
        text = ''.join(complete_reply(engine, [{'role': 'user', 'content': 'Question'}],
                                     max_new_tokens=24, context_tokens=256, status=status))
        self.assertEqual(text, 'Partial')
        self.assertTrue(status['truncated'])
        self.assertIn('Context', status['pause_reason'])

    def test_no_progress_does_not_loop_forever(self):
        engine = FakeEngine([('', True)])
        status = {}
        self.assertEqual(''.join(complete_reply(engine, [{'role': 'user', 'content': 'Question'}],
                                               max_new_tokens=24, context_tokens=256, status=status)), '')
        self.assertEqual(len(engine.calls), 1)
        self.assertIn('no progress', status['pause_reason'])

    def test_manual_continue_also_continues_automatically(self):
        engine = FakeEngine([(' more', True), (' done.', False)])
        history = [{'role': 'user', 'content': 'Question'}, {'role': 'assistant', 'content': 'Existing'}]
        text = ''.join(complete_reply(engine, history, max_new_tokens=24, context_tokens=1024, continuing=True))
        self.assertEqual(text, ' more done.')
        self.assertEqual(engine.calls[1][0][-1]['content'], 'Existing more')
