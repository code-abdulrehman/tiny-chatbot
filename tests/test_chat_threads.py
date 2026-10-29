"""Persistence, privacy, and sidebar interaction checks."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_store import ChatStore, new_thread
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


class ThreadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'CHAT_DATA_DIR': self.temp.name})
        self.environment.start()
        self.store = ChatStore()
        self.engine_init = patch('chat_engine.ChatEngine.__init__', return_value=None)
        self.engine_init.start()
        self.title_generator = patch('chat_engine.ChatEngine.generate_title', return_value='Assistant introduction')
        self.mock_title = self.title_generator.start()

    def tearDown(self):
        self.title_generator.stop()
        self.engine_init.stop()
        self.environment.stop()
        self.temp.cleanup()

    def app(self):
        at = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(at.exception)
        return at

    def test_store_roundtrip_search_and_private_rejection(self):
        thread = new_thread()
        thread.update(title='Learning Python', messages=[{'role': 'user', 'content': 'Explain lists'}])
        self.store.save(thread)
        self.assertEqual(ChatStore().load(thread['id']), thread)
        self.assertEqual(len(self.store.list('LISTS')), 1)
        self.assertEqual(self.store.list('unmatched'), [])
        private = {**thread, 'id': 'private', 'private': True}
        with self.assertRaises(ValueError):
            self.store.save(private)
        self.assertEqual(len(self.store.list()), 1)

    def test_thread_switch_search_and_restart(self):
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        self.assertFalse(at.exception)
        first = at.session_state['active_chat']['id']
        at.button(key='new_chat').click().run()
        self.assertEqual(at.session_state['active_chat']['messages'], [])
        at.chat_input[0].set_value('Your name?').run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self.store.list()), 2)
        at.button(key=f'thread_{first}').click().run()
        self.assertEqual(at.session_state['active_chat']['messages'][0]['content'], 'Who are you?')
        self.assertEqual(self.store.load(first)['title'], 'Assistant introduction')
        self.assertEqual(self.mock_title.call_count, 2)
        at.text_input(key='search_chats').set_value('Who are').run()
        labels = [b.label for b in at.sidebar.button]
        self.assertIn('Assistant introduction', labels)
        self.assertEqual(len([b for b in at.sidebar.button if str(b.key).startswith('thread_')]), 1)
        restarted = self.app()
        restarted.button(key=f'thread_{first}').click().run()
        self.assertEqual(len(restarted.session_state['active_chat']['messages']), 2)
        self.assertFalse(restarted.exception)

    def test_private_chat_never_persists(self):
        at = self.app()
        at.toggle(key='private_mode').set_value(True).run()
        at.chat_input[0].set_value('Whats you name?').run()
        self.assertFalse(at.exception)
        self.assertTrue(at.session_state['active_chat']['private'])
        self.assertEqual(len(at.session_state['active_chat']['messages']), 2)
        self.assertEqual(self.store.list(), [])
        self.assertNotIn(b'Whats you name', self.store.path.read_bytes())
        self.mock_title.assert_not_called()
        at.button(key='new_chat').click().run()
        self.assertTrue(at.session_state['active_chat']['private'])
        self.assertEqual(at.session_state['active_chat']['messages'], [])
        at.toggle(key='private_mode').set_value(False).run()
        self.assertFalse(at.session_state['active_chat']['private'])
        self.assertEqual(at.session_state['active_chat']['messages'], [])
        self.assertEqual(self.app().session_state['active_chat']['messages'], [])

    def test_settings_modal_values_survive_close(self):
        at = self.app()
        at.button(key='settings_button').click().run()
        self.assertFalse(at.exception)
        at.select_slider[0].set_value(96)
        at.select_slider[1].set_value(2048)
        next(t for t in at.toggle if t.label == 'Experimental INT8 mode').set_value(True)
        next(t for t in at.toggle if t.label == 'Use downloaded model only').set_value(False)
        next(b for b in at.button if b.label == 'Save settings').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['settings'], {'tokens': 96, 'quantized': True, 'offline': False, 'context_tokens': 2048})
        at.button(key='new_chat').click().run()
        at.button(key='settings_button').click().run()
        self.assertEqual(at.select_slider[0].value, 96)
        self.assertEqual(at.select_slider[1].value, 2048)
        self.assertTrue(next(t for t in at.toggle if t.label == 'Experimental INT8 mode').value)
        self.assertFalse(next(t for t in at.toggle if t.label == 'Use downloaded model only').value)
        self.assertFalse(at.exception)
        restarted = self.app()
        self.assertEqual(restarted.session_state['settings'], {'tokens': 96, 'quantized': True, 'offline': False, 'context_tokens': 2048})
        restarted.button(key='settings_button').click().run()
        self.assertEqual(restarted.select_slider[0].value, 96)
        self.assertEqual(restarted.select_slider[1].value, 2048)

    def test_open_saved_chat_exits_private_mode(self):
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        saved_id = at.session_state['active_chat']['id']
        at.toggle(key='private_mode').set_value(True).run()
        at.chat_input[0].set_value('Your name?').run()
        at.button(key=f'thread_{saved_id}').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.toggle(key='private_mode').value)
        self.assertFalse(at.session_state['active_chat']['private'])
        self.assertEqual(len(self.store.list()), 1)

    def test_title_failure_preserves_reply(self):
        self.mock_title.side_effect = RuntimeError('Title model failed')
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        self.assertFalse(at.exception)
        thread = self.store.load(at.session_state['active_chat']['id'])
        self.assertEqual(thread['title'], 'New conversation')
        self.assertEqual(len(thread['messages']), 2)

    def test_thread_menu_rename_duplicate_and_delete(self):
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        first = at.session_state['active_chat']['id']
        at.menu_button(key=f'menu_{first}').click('Rename').run()
        self.assertFalse(at.exception)
        at.text_input(key='rename_title').set_value('My assistant')
        next(b for b in at.button if b.label == 'Save title').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self.store.load(first)['title'], 'My assistant')
        self.assertEqual(at.session_state['active_chat']['title'], 'My assistant')
        at.menu_button(key=f'menu_{first}').click('Duplicate').run()
        self.assertFalse(at.exception)
        copied = at.session_state['active_chat']
        self.assertNotEqual(copied['id'], first)
        self.assertEqual(copied['messages'], self.store.load(first)['messages'])
        self.assertEqual(copied['title'], 'My assistant (copy)')
        self.store.rename(copied['id'], 'Independent copy')
        self.assertEqual(self.store.load(first)['title'], 'My assistant')
        at.menu_button(key=f"menu_{copied['id']}").click('Delete').run()
        self.assertEqual(len(self.store.list()), 2)  # Requires confirmation.
        at.button(key='cancel_thread_action').click().run()
        self.assertEqual(len(self.store.list()), 2)
        at.menu_button(key=f"menu_{copied['id']}").click('Delete').run()
        at.button(key='confirm_delete').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(at.session_state['active_chat']['messages'], [])
        self.assertEqual(self.store.load(first)['title'], 'My assistant')

    def test_context_setting_reaches_generation(self):
        at = self.app()
        at.session_state['settings']['context_tokens'] = 512
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['A test response.'])) as stream:
            at.chat_input[0].set_value('Explain lists').run()
        self.assertFalse(at.exception)
        self.assertEqual(stream.call_args.kwargs['context_tokens'], 512)

    def test_private_toggle_is_in_header_and_single_menu_icon(self):
        at = self.app()
        self.assertEqual(len(at.sidebar.toggle), 0)
        self.assertEqual(at.container(key='private_header').toggle[0].key, 'private_mode')
        at.chat_input[0].set_value('Who are you?').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.menu_button[0].label, ':material/more_vert:')

    def test_both_messages_have_copy_controls(self):
        at = self.app()
        with patch('message_actions.copy_message') as copy:
            at.chat_input[0].set_value('Who are you?').run()
        self.assertFalse(at.exception)
        copied_text = [call.args[0] for call in copy.call_args_list]
        self.assertEqual(copied_text[-2:], [m['content'] for m in at.session_state['active_chat']['messages']])

    def test_retry_replaces_latest_answer_preserves_user_and_title(self):
        at = self.app()
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['Original answer.'])):
            at.chat_input[0].set_value('Explain lists').run()
        original = self.store.load(at.session_state['active_chat']['id'])
        self.assertEqual(len(original['messages']), 2)
        for message in original['messages']:
            self.assertIn('timestamp', message)
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['Replacement answer.'])) as stream:
            at.button(key=f"retry_{original['id']}").click().run()
        self.assertFalse(at.exception)
        updated = self.store.load(original['id'])
        self.assertEqual(updated['messages'][0], original['messages'][0])
        self.assertEqual(len(updated['messages']), 2)
        self.assertEqual(updated['messages'][-1]['content'], 'Replacement answer.')
        self.assertEqual(updated['title'], original['title'])
        self.assertTrue(stream.call_args.kwargs['sample'])
        self.assertEqual(len(stream.call_args.args[0]), 1)
        self.assertEqual(self.mock_title.call_count, 1)
        at.chat_input[0].set_value('Who are you?').run()
        retry_buttons = [b for b in at.button if str(b.key).startswith('retry_')]
        self.assertEqual(len(retry_buttons), 1)

    def test_failed_retry_keeps_previous_saved_answer(self):
        at = self.app()
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['Original answer.'])):
            at.chat_input[0].set_value('Explain lists').run()
        original = self.store.load(at.session_state['active_chat']['id'])
        with patch('chat_engine.ChatEngine.stream', side_effect=RuntimeError('CPU error')):
            at.button(key=f"retry_{original['id']}").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(self.store.load(original['id']), original)
        self.assertEqual(at.session_state['active_chat'], original)

    def test_private_retry_stays_unsaved(self):
        at = self.app()
        at.toggle(key='private_mode').set_value(True).run()
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['Private answer.'])):
            at.chat_input[0].set_value('Explain lists').run()
        thread_id = at.session_state['active_chat']['id']
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['Private retry.'])):
            at.button(key=f'retry_{thread_id}').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['active_chat']['messages'][-1]['content'], 'Private retry.')
        self.assertEqual(self.store.list(), [])

    def test_continue_appends_to_same_reply_without_repeating_user(self):
        at = self.app()
        def limited_reply(*args, **kwargs):
            kwargs['generation_status']['truncated'] = True
            yield 'First part'
        with patch('chat_engine.ChatEngine.stream', side_effect=limited_reply):
            at.chat_input[0].set_value('Explain lists').run()
        original = self.store.load(at.session_state['active_chat']['id'])
        self.assertTrue(original['messages'][-1]['truncated'])
        with patch('chat_engine.ChatEngine.stream', return_value=iter([' and the rest.'])) as stream:
            at.button(key=f"continue_{original['id']}").click().run()
        self.assertFalse(at.exception)
        updated = self.store.load(original['id'])
        self.assertEqual(len(updated['messages']), 2)
        self.assertEqual(updated['messages'][0], original['messages'][0])
        self.assertEqual(updated['messages'][-1]['content'], 'First part and the rest.')
        self.assertFalse(updated['messages'][-1]['truncated'])
        self.assertTrue(stream.call_args.kwargs['continue_reply'])
        self.assertEqual(stream.call_args.args[0][-1]['content'], 'First part')
        self.assertEqual(self.mock_title.call_count, 1)
        self.assertEqual(len(at.chat_message), 2)
        self.assertFalse(any(b.label == 'Continue' for b in at.chat_message[-1].button))
        self.assertEqual(at.button(key=f"continue_{original['id']}").label, 'Continue')

    def test_failed_continue_keeps_previous_answer(self):
        at = self.app()
        with patch('chat_engine.ChatEngine.stream', return_value=iter(['First part'])):
            at.chat_input[0].set_value('Explain lists').run()
        original = self.store.load(at.session_state['active_chat']['id'])
        with patch('chat_engine.ChatEngine.stream', side_effect=RuntimeError('Context full')):
            at.button(key=f"continue_{original['id']}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self.store.load(original['id']), original)

    def test_long_reply_setting_is_saved(self):
        at = self.app()
        at.button(key='settings_button').click().run()
        at.select_slider[0].set_value(1024)
        at.select_slider[1].set_value(4096)
        next(b for b in at.button if b.label == 'Save settings').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self.store.load_settings()['tokens'], 1024)
        self.assertEqual(self.app().session_state['settings']['context_tokens'], 4096)

    def test_slug_restores_chat_after_refresh_and_private_clears_url(self):
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        saved = at.session_state['active_chat']
        self.assertEqual(len(saved['slug']), 10)
        self.assertEqual(at.query_params['chat'], saved['slug'])
        refreshed = AppTest.from_file(str(APP), default_timeout=20)
        refreshed.query_params['chat'] = saved['slug']
        refreshed.run()
        self.assertFalse(refreshed.exception)
        self.assertEqual(refreshed.session_state['active_chat'], saved)
        refreshed.toggle(key='private_mode').set_value(True).run()
        self.assertNotIn('chat', refreshed.query_params)
        refreshed.chat_input[0].set_value('Your name?').run()
        self.assertNotIn('chat', refreshed.query_params)
        refreshed.button(key=f"thread_{saved['id']}").click().run()
        self.assertEqual(refreshed.query_params['chat'], saved['slug'])
        refreshed.button(key='new_chat').click().run()
        self.assertNotIn('chat', refreshed.query_params)

    def test_slug_navigation_and_deleted_link(self):
        at = self.app()
        at.chat_input[0].set_value('Who are you?').run()
        first = at.session_state['active_chat']
        at.menu_button(key=f"menu_{first['id']}").click('Duplicate').run()
        copied = at.session_state['active_chat']
        self.assertNotEqual(copied['slug'], first['slug'])
        at.query_params['chat'] = first['slug']
        at.run()
        self.assertEqual(at.session_state['active_chat']['id'], first['id'])
        self.store.rename(first['id'], 'Renamed')
        self.assertEqual(self.store.load(first['id'])['slug'], first['slug'])
        self.store.delete(first['id'])
        fresh = AppTest.from_file(str(APP), default_timeout=20)
        fresh.query_params['chat'] = first['slug']
        fresh.run()
        self.assertFalse(fresh.exception)
        self.assertEqual(fresh.session_state['active_chat']['messages'], [])
        self.assertNotIn('chat', fresh.query_params)


if __name__ == '__main__':
    unittest.main()
