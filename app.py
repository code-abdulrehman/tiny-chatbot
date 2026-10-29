"""Local chat with saved threads and session-only private conversations."""
from time import perf_counter
from hashlib import sha256
import importlib
import sqlite3
from pathlib import Path
from contextlib import nullcontext
import streamlit as st
import chat_engine

# Streamlit can rerun app.py while imported modules and cached model objects
# still reference old method signatures. Refresh both when engine code changes.
engine_revision = sha256(Path(chat_engine.__file__).read_bytes()).hexdigest()
if getattr(chat_engine, 'ENGINE_REVISION', None) != engine_revision:
    importlib.reload(chat_engine)
from chat_engine import ChatEngine, DEFAULT_MODEL, identity_reply
import chat_store
if getattr(chat_store, 'STORE_REVISION', None) != sha256(Path(chat_store.__file__).read_bytes()).hexdigest():
    importlib.reload(chat_store)
from chat_store import ChatStore, new_thread, REPLY_LENGTHS
from message_actions import copy_message
from message_time import timestamp_now, display_time
from scroll_controls import conversation_scroll_controls

st.set_page_config(page_title='Tiny Chat', page_icon='💬', layout='centered')
logo = (Path(__file__).resolve().parent / 'assets' / 'logo.svg').read_text()
st.logo(logo, size='large', icon_image=':material/forum:')
st.html(Path(__file__).resolve().parent / 'assets' / 'chat.css')
store = ChatStore()
# Thread navigation uses trigger buttons, which cannot bind to query params.
# Keep the route explicitly in sync with saved-chat selection instead.
url_slug = st.query_params.get('chat')
if 'active_chat' not in st.session_state or url_slug != st.session_state.get('route_slug'):
    try:
        restored = store.load_slug(url_slug) if url_slug else new_thread()
    except KeyError:
        restored = new_thread()
        st.query_params.pop('chat', None)
        url_slug = None
        st.session_state.route_notice = 'That chat is unavailable. Start a new conversation.'
    st.session_state.active_chat = restored
    st.session_state.private_mode = restored['private']
    st.session_state.route_slug = url_slug
if 'settings' not in st.session_state:
    st.session_state.settings = store.load_settings()
st.session_state.settings.setdefault('context_tokens', 1024)
st.session_state.setdefault('private_mode', st.session_state.active_chat['private'])


def update_chat_url(thread):
    slug = thread.get('slug') if thread['messages'] and not thread['private'] else None
    if slug:
        st.query_params['chat'] = slug
    else:
        st.query_params.pop('chat', None)
    st.session_state.route_slug = slug


@st.cache_resource(show_spinner=False, max_entries=1)
def load_engine(quantized, offline, engine_revision):
    # The revision participates in the cache key, invalidating old instances.
    return ChatEngine(quantized=quantized, offline=offline)


def start_chat(private=None):
    # Replacing a private conversation discards it rather than archiving it.
    private = st.session_state.private_mode if private is None else private
    st.session_state.private_mode = private
    st.session_state.active_chat = new_thread(private)
    st.session_state.search_chats = ''
    update_chat_url(st.session_state.active_chat)


def open_chat(thread_id):
    st.session_state.active_chat = store.load(thread_id)
    st.session_state.private_mode = False
    update_chat_url(st.session_state.active_chat)


def change_private_mode():
    start_chat(st.session_state.private_mode)


def retry_reply(thread_id):
    st.session_state.retry_chat_id = thread_id


def continue_last_reply(thread_id):
    st.session_state.continue_chat_id = thread_id


def message_footer(message, thread_id, index, allow_retry=False):
    with st.container(horizontal=True, horizontal_alignment='right', vertical_alignment='center'):
        with st.container(key=f'message_actions_{thread_id}_{index}', horizontal=True, width='content', vertical_alignment='center', gap=None):
            copy_message(message['content'], key=f'copy_{thread_id}_{index}')
            if allow_retry:
                st.button('Retry', icon=':material/refresh:', type='tertiary',
                          key=f'retry_{thread_id}', on_click=retry_reply, args=(thread_id,))
        with st.container(key=f'message_time_{thread_id}_{index}', width='content'):
            label, full_time = display_time(message.get('timestamp'), st.context.timezone)
            st.caption(label, help=full_time)


def dismiss_settings():
    st.session_state.settings_open = False


def dismiss_thread_action():
    st.session_state.pop('thread_action', None)


def thread_menu(thread_id):
    action = st.session_state.get(f'menu_{thread_id}')
    dismiss_settings()
    if action == 'Duplicate':
        copied = store.duplicate(thread_id)
        st.session_state.active_chat = copied
        st.session_state.private_mode = False
        st.session_state.search_chats = ''
        update_chat_url(copied)
        dismiss_thread_action()
    elif action in {'Rename', 'Delete'}:
        st.session_state.thread_action = (action, thread_id)


@st.dialog('Manage chat', on_dismiss=dismiss_thread_action)
def thread_action_dialog(action, thread_id):
    thread = store.load(thread_id)
    if action == 'Rename':
        with st.form('rename_chat'):
            title = st.text_input('Chat title', value=thread['title'], max_chars=80, key='rename_title')
            if st.form_submit_button('Save title', type='primary'):
                try:
                    renamed = store.rename(thread_id, title)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    if st.session_state.active_chat['id'] == thread_id:
                        st.session_state.active_chat = renamed
                    dismiss_thread_action()
                    st.rerun()
    elif action == 'Delete':
        st.write(f'Delete “{thread["title"]}” and its messages? This cannot be undone.')
        if st.button('Delete chat', type='primary', key='confirm_delete'):
            store.delete(thread_id)
            if st.session_state.active_chat['id'] == thread_id:
                st.session_state.active_chat = new_thread(st.session_state.private_mode)
                update_chat_url(st.session_state.active_chat)
            dismiss_thread_action()
            st.rerun()
    if st.button('Cancel', key='cancel_thread_action'):
        dismiss_thread_action()
        st.rerun()


@st.dialog('Chat settings', on_dismiss=dismiss_settings)
def settings_dialog():
    settings = st.session_state.settings
    st.caption(DEFAULT_MODEL)
    with st.form('chat_settings'):
        tokens = st.select_slider('Reply length (tokens)', options=REPLY_LENGTHS, value=settings['tokens'],
                                  help='Maximum tokens per reply or continuation. A higher limit may take longer on CPU.')
        context_tokens = st.select_slider('Context length (tokens)', options=[256, 512, 1024, 2048, 4096, 8192], value=settings['context_tokens'],
                                         help='Budget for instructions, recent messages, and reply. Longer context uses more CPU and RAM.')
        quantized = st.toggle('Experimental INT8 mode', value=settings['quantized'])
        offline = st.toggle('Use downloaded model only', value=settings['offline'])
        if st.form_submit_button('Save settings', type='primary', width='stretch'):
            try:
                saved = store.save_settings({'tokens': tokens, 'quantized': quantized, 'offline': offline, 'context_tokens': context_tokens})
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f'Could not save settings: {exc}')
            else:
                st.session_state.settings = saved
                st.session_state.settings_open = False
                st.rerun()
    st.caption('Best for short English messages. Answers can be wrong; this model does not browse the web.')


with st.container(key='private_header', width='content'):
    st.toggle('Private chat', key='private_mode', on_change=change_private_mode,
              help='Switching modes starts a fresh chat. Private messages are never saved.')

with st.sidebar:
    st.button('New chat', icon=':material/add:', type='primary', width='stretch', key='new_chat', on_click=start_chat)
    search = st.text_input('Search chats', placeholder='Search chats', key='search_chats', label_visibility='collapsed')
    with st.container(height=420, border=False, key='thread_list'):
        threads = store.list(search)
        if not threads:
            st.caption('No matching chats.' if search else 'Your saved chats will appear here.')
        for thread in threads:
            title_column, menu_column = st.columns([0.82, 0.18], gap=None, wrap=False)
            with title_column:
                st.button(thread['title'], key=f"thread_{thread['id']}", width='stretch',
                          icon=':material/chat_bubble:',
                          type='primary' if thread['id'] == st.session_state.active_chat['id'] else 'tertiary',
                          on_click=open_chat, args=(thread['id'],))
            with menu_column:
                st.menu_button(':material/more_vert:', ['Rename', 'Duplicate', 'Delete'], key=f"menu_{thread['id']}",
                               type='tertiary', width='stretch', help='Chat actions',
                               on_click=thread_menu, args=(thread['id'],))
    with st.container(key='sidebar_footer'):
        if st.button('Settings', icon=':material/settings:', width='stretch', key='settings_button'):
            dismiss_thread_action()
            st.session_state.settings_open = True

if st.session_state.get('settings_open'):
    settings_dialog()
elif st.session_state.get('thread_action'):
    thread_action_dialog(*st.session_state.thread_action)

active = st.session_state.active_chat
if st.session_state.get('route_notice'):
    st.info(st.session_state.pop('route_notice'))
retrying = (st.session_state.pop('retry_chat_id', None) == active['id']
            and len(active['messages']) >= 2
            and active['messages'][-1]['role'] == 'assistant'
            and active['messages'][-2]['role'] == 'user')
continuing = (st.session_state.pop('continue_chat_id', None) == active['id']
              and len(active['messages']) >= 2
              and active['messages'][-1]['role'] == 'assistant'
              and active['messages'][-2]['role'] == 'user')
st.title('Private chat' if active['private'] else 'Tiny Chat')
if active['private']:
    st.caption('This conversation is not saved. Switching chats or ending the session discards it.')
else:
    st.caption(active['title'] if active['messages'] else 'A small assistant running on your CPU.')
visible_messages = active['messages'][:-1] if retrying else active['messages']
continuation_placeholder = None
for index, message in enumerate(visible_messages):
    with st.chat_message(message['role']):
        if continuing and index == len(active['messages']) - 1:
            continuation_placeholder = st.empty()
            continuation_placeholder.markdown(message['content'])
        else:
            st.markdown(message['content'])
        message_footer(message, active['id'], index,
                       allow_retry=not (retrying or continuing) and index == len(active['messages']) - 1 and message['role'] == 'assistant')
        if message.get('truncated') and index == len(active['messages']) - 1:
            st.caption('Reply reached its length limit. Use Continue to finish it.')
if active['messages'] and active['messages'][-1]['role'] == 'assistant' and not (retrying or continuing):
    with st.container(horizontal=True, horizontal_alignment='right'):
        st.button('Continue', icon=':material/last_page:', key=f"continue_{active['id']}",
                  on_click=continue_last_reply, args=(active['id'],))
if not active['messages']:
    st.info('Ask a short question, or try: “Explain a Python list in one sentence.”')
if st.session_state.get('last_reply'):
    st.caption(st.session_state.pop('last_reply'))

with st.container(key='chat_scroll_controls', width='content'):
    conversation_scroll_controls()

prompt = st.chat_input('Message Tiny Chat', max_chars=2000, submit_mode='disable')
if prompt or retrying or continuing:
    history = (active['messages'] if continuing else active['messages'][:-1] if retrying else
               active['messages'] + [{'role': 'user', 'content': prompt, 'timestamp': timestamp_now()}])
    prompt = history[-2]['content'] if continuing else history[-1]['content']
    if not retrying and not continuing:
        with st.chat_message('user'):
            st.markdown(prompt)
            message_footer(history[-1], active['id'], len(history) - 1)
    with (nullcontext() if continuing else st.chat_message('assistant')):
        started = perf_counter()
        generation_status = {}
        try:
            fixed = None if continuing else identity_reply(prompt)
            if fixed:
                answer = fixed
                st.markdown(answer)
            else:
                settings = st.session_state.settings
                with st.spinner('Continuing reply…' if continuing else 'Loading model…'):
                    engine = load_engine(settings['quantized'], settings['offline'], engine_revision)
                stream = engine.stream(history, max_new_tokens=settings['tokens'], context_tokens=settings['context_tokens'],
                                       sample=retrying, continue_reply=continuing, generation_status=generation_status)
                if continuing:
                    answer = history[-1]['content']
                    for chunk in stream:
                        if chunk:
                            answer += chunk
                            continuation_placeholder.markdown(answer)
                else:
                    answer = st.write_stream(stream)
            if not answer.strip():
                answer = "I couldn't produce a reply. Please rephrase your question."
                st.markdown(answer)
            updated = {**active, 'messages': (history[:-1] if continuing else history) + [
                {'role': 'assistant', 'content': answer, 'timestamp': timestamp_now(), 'truncated': generation_status.get('truncated', False)}]}
            if not active['messages'] and not updated['private']:
                try:
                    settings = st.session_state.settings
                    with st.spinner('Naming chat…'):
                        engine = load_engine(settings['quantized'], settings['offline'], engine_revision)
                        updated['title'] = engine.generate_title(updated['messages'])
                except Exception:
                    # Title failure must not lose a successfully generated reply.
                    updated['title'] = 'New conversation'
            if not updated['private']:
                store.save(updated)
            st.session_state.active_chat = updated
            update_chat_url(updated)
            st.session_state.last_reply = f'{perf_counter() - started:.1f}s · generated locally'
        except Exception as exc:
            st.error(f"Couldn't complete the reply: {exc}")
            st.caption('For missing model files, disable “Use downloaded model only” in Settings while online.')
            if retrying or continuing:
                st.caption('Previous reply kept:')
                if continuing:
                    continuation_placeholder.markdown(active['messages'][-1]['content'])
                    st.button('Continue', icon=':material/last_page:', key=f"continue_{active['id']}",
                              on_click=continue_last_reply, args=(active['id'],))
                else:
                    st.markdown(active['messages'][-1]['content'])
                    message_footer(active['messages'][-1], active['id'], len(active['messages']) - 1, allow_retry=True)
        else:
            st.rerun()
