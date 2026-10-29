"""Context selection trims complete old turns and reserves response tokens."""
from pathlib import Path
import sys
import unittest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_engine import ChatEngine


class CountingTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        return ' '.join(m['content'] for m in messages)

    def __call__(self, prompt, **kwargs):
        return {'input_ids': torch.zeros((1, len(prompt.split())), dtype=torch.long)}


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.engine = ChatEngine.__new__(ChatEngine)
        self.engine.context_limit = 8192
        self.engine.tokenizer = CountingTokenizer()
        self.history = []
        for i in range(8):
            self.history += [{'role': 'user', 'content': f'Question{i} ' * 30},
                             {'role': 'assistant', 'content': f'Answer{i} ' * 30}]
        self.history.append({'role': 'user', 'content': 'Latest question'})

    def test_larger_context_keeps_more_than_three_turns(self):
        self.engine.prepare_inputs(self.history, 48, 1024)
        self.assertEqual(len(self.engine.tokenizer.messages), len(self.history) + 1)

    def test_small_context_drops_complete_turns_and_reserves_reply(self):
        inputs = self.engine.prepare_inputs(self.history, 48, 256)
        retained = self.engine.tokenizer.messages
        self.assertLess(len(retained), len(self.history) + 1)
        self.assertEqual(retained[-1]['content'], 'Latest question')
        self.assertEqual(retained[1]['role'], 'user')
        self.assertLessEqual(inputs['input_ids'].shape[1] + 48, 256)

    def test_model_limit_and_oversized_message(self):
        self.engine.context_limit = 256
        with self.assertRaises(ValueError):
            self.engine.prepare_inputs([{'role': 'user', 'content': 'word ' * 300}], 48, 8192)
        with self.assertRaises(ValueError):
            self.engine.prepare_inputs(self.history, 48, -1)

    def test_continuation_preserves_latest_question_and_partial_reply(self):
        history = self.history + [{'role': 'assistant', 'content': 'Partial answer'}]
        self.engine.prepare_inputs(history, 48, 256, continue_reply=True)
        self.assertEqual(self.engine.tokenizer.messages[-2:], history[-2:])
        with self.assertRaises(ValueError):
            self.engine.prepare_inputs([{'role': 'user', 'content': 'question ' * 160},
                                        {'role': 'assistant', 'content': 'answer ' * 160}],
                                       48, 256, continue_reply=True)
