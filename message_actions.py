"""Browser-local message clipboard controls, without a Python rerun."""
import streamlit.components.v2 as components

COPY_JS = """
export default function ({ data, parentElement }) {
  const button = parentElement.querySelector('button');
  const label = parentElement.querySelector('[data-copy-label]');
  const status = parentElement.querySelector('[role="status"]');
  let timer;
  button.onclick = async () => {
    try {
      const text = data.text;
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(text);
      } catch {
        const doc = parentElement.ownerDocument;
        const field = doc.createElement('textarea');
        field.value = text;
        field.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
        parentElement.appendChild(field);
        try {
          field.focus();
          field.select();
          if (!doc.execCommand('copy')) throw new Error('Copy denied');
        } finally {
          field.remove();
          button.focus();
        }
      }
      label.textContent = 'Copied';
      status.textContent = 'Message copied to clipboard';
    } catch {
      label.textContent = 'Try selecting text';
      status.textContent = 'Clipboard blocked. Select the message text to copy it.';
    }
    clearTimeout(timer);
    timer = setTimeout(() => { label.textContent = 'Copy'; status.textContent = ''; }, 2500);
  };
  return () => { clearTimeout(timer); button.onclick = null; };
}
"""

_COPY_MESSAGE = components.component(
    'copy_message',
    html='''
<button type="button" aria-label="Copy message" title="Copy message">
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
    <rect x="8" y="8" width="12" height="13" rx="2"></rect>
    <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path>
  </svg>
  <span data-copy-label>Copy</span>
</button>
<span class="sr-only" role="status" aria-live="polite"></span>
''',
    css='''
button {
  display: inline-flex; align-items: center; gap: 0.35rem;
  border: 0; border-radius: 0.3rem; padding: 0.3rem 0.4rem;
  background: transparent; color: var(--st-text-color, inherit);
  font: inherit; font-size: 0.75rem; cursor: pointer; opacity: 0.7;
}
button:hover, button:focus-visible { opacity: 1; background: var(--st-secondary-background-color, #80808020); }
button:focus-visible { outline: 2px solid var(--st-primary-color, #ff4b4b); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
''',
    js=COPY_JS,
)


def copy_message(text, *, key):
    _COPY_MESSAGE(data={'text': text}, key=key, width='content', height='content')
