"""Small local Streamlit chat application."""
from time import perf_counter
import streamlit as st
from chat_engine import ChatEngine, DEFAULT_MODEL, identity_reply

st.set_page_config(page_title='Tiny Chat', page_icon='💬', layout='centered')


@st.cache_resource(show_spinner=False, max_entries=1)
def load_engine(quantized, offline):
    return ChatEngine(quantized=quantized, offline=offline)


st.title('Tiny Chat')
st.caption('A small assistant running on your CPU.')
with st.sidebar:
    st.subheader('Chat settings')
    st.caption(DEFAULT_MODEL)
    tokens = st.select_slider('Reply length (tokens)', options=[24, 48, 96, 128], value=48)
    quantized = st.toggle('Experimental INT8 mode', value=False)
    offline = st.toggle('Use downloaded model only', value=True)
    if st.button('New chat', use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption('Best for short English messages. Answers can be wrong; this model does not browse the web.')

if 'messages' not in st.session_state:
    st.session_state.messages = []
for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.markdown(message['content'])
if not st.session_state.messages:
    st.info('Ask a short question, or try: “Explain a Python list in one sentence.”')

if prompt := st.chat_input('Message Tiny Chat', max_chars=2000):
    history = st.session_state.messages + [{'role': 'user', 'content': prompt}]
    with st.chat_message('user'):
        st.markdown(prompt)
    with st.chat_message('assistant'):
        started = perf_counter()
        try:
            fixed = identity_reply(prompt)
            if fixed:
                answer = fixed
                st.markdown(answer)
            else:
                with st.spinner('Loading model…'):
                    engine = load_engine(quantized, offline)
                answer = st.write_stream(engine.stream(history, tokens))
            if not answer.strip():
                answer = "I couldn't produce a reply. Please rephrase your question."
                st.markdown(answer)
            st.session_state.messages = history + [{'role': 'assistant', 'content': answer}]
            st.caption(f'{perf_counter() - started:.1f}s · generated locally')
        except Exception as exc:
            st.error(f"Couldn't generate a reply: {exc}")
            st.caption('If model files are missing, turn off “Use downloaded model only” while connected to the internet.')
