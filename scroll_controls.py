"""Conversation jump controls that scroll in the browser without rerunning Python."""
import streamlit.components.v2 as components

SCROLL_JS = """
export default function ({ parentElement }) {
  const root = parentElement.getRootNode?.();
  const host = parentElement.host ?? root?.host ?? parentElement;
  const main = host.closest?.('[data-testid="stMain"]');
  if (!main) return;
  const up = parentElement.querySelector('[data-scroll="up"]');
  const down = parentElement.querySelector('[data-scroll="down"]');
  let scroller = host.parentElement;
  while (scroller && !/auto|scroll/.test(getComputedStyle(scroller).overflowY)) {
    scroller = scroller.parentElement;
  }
  scroller ??= main;
  const messages = () => Array.from(main.querySelectorAll('[data-testid="stChatMessage"]'));
  function update() {
    const items = messages();
    const overflow = scroller.scrollHeight > scroller.clientHeight + 24;
    const bounds = scroller.getBoundingClientRect();
    up.hidden = !overflow || !items.length || items[0].getBoundingClientRect().top >= bounds.top - 16;
    down.hidden = !overflow || !items.length || items.at(-1).getBoundingClientRect().bottom <= bounds.bottom - 72;
  }
  function jump(direction) {
    const items = messages();
    if (!items.length) return;
    const bounds = scroller.getBoundingClientRect();
    const target = direction === 'up' ? items[0] : items.at(-1);
    const rectangle = target.getBoundingClientRect();
    const offset = direction === 'up' ? rectangle.top - bounds.top - 16
      : rectangle.bottom - bounds.top - scroller.clientHeight + 96;
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    scroller.scrollTo({ top: Math.max(0, scroller.scrollTop + offset), behavior });
  }
  up.onclick = () => jump('up');
  down.onclick = () => jump('down');
  scroller.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  const resize = new ResizeObserver(update);
  resize.observe(main.querySelector('[data-testid="stMainBlockContainer"]') ?? main);
  const mutation = new MutationObserver(update);
  mutation.observe(main, { childList: true, subtree: true, characterData: true });
  update();
  return () => {
    up.onclick = null;
    down.onclick = null;
    scroller.removeEventListener('scroll', update);
    window.removeEventListener('resize', update);
    resize.disconnect();
    mutation.disconnect();
  };
}
"""

_SCROLL_CONTROLS = components.component(
    'chat_scroll_controls',
    html='''
<nav aria-label="Conversation navigation">
  <button type="button" data-scroll="up" title="Go to first message" aria-label="Go to first message" hidden>
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 12 6-6 6 6M12 6v14"/></svg>
  </button>
  <button type="button" data-scroll="down" title="Go to latest message" aria-label="Go to latest message" hidden>
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 12 6 6 6-6M12 4v14"/></svg>
  </button>
</nav>
''',
    css='''
nav { display: flex; flex-direction: column; gap: 0.4rem; }
button {
  display: flex; align-items: center; justify-content: center;
  width: 2.3rem; height: 2.3rem; padding: 0; border-radius: 50%;
  border: 1px solid var(--st-border-color, #8888);
  color: var(--st-text-color, inherit);
  background: var(--st-secondary-background-color, #80808020);
  box-shadow: 0 2px 6px #0002; cursor: pointer;
}
button[hidden] { display: none; }
button:hover { background: color-mix(in srgb, var(--st-text-color, #888) 15%, var(--st-secondary-background-color, #fff)); }
button:focus-visible { outline: 2px solid var(--st-primary-color, #ff4b4b); outline-offset: 2px; }
''',
    js=SCROLL_JS,
)


def conversation_scroll_controls():
    _SCROLL_CONTROLS(key='conversation_scroll', width='content', height='content')
