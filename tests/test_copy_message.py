"""Exercise the actual clipboard JavaScript without a browser dependency."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed to check clipboard JavaScript')
class ClipboardTests(unittest.TestCase):
    def test_clipboard_success_fallback_and_blocked_feedback(self):
        module = ast.parse((Path(__file__).resolve().parents[1] / 'message_actions.py').read_text())
        source = next(ast.literal_eval(n.value) for n in module.body
                      if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'COPY_JS' for t in n.targets))
        script = '''
import assert from 'node:assert/strict';
const source = SOURCE;
const render = (await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))).default;
for (const mode of ['clipboard', 'fallback', 'blocked']) {
  const button = { focus() {} }, label = {}, status = {};
  const text = 'Private message <script> and Unicode: سلام';
  let copied, removed = false;
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: mode === 'clipboard'
    ? { clipboard: { async writeText(value) { copied = value; } } } : {} });
  const parent = {
    querySelector(selector) { return selector === 'button' ? button : selector === '[data-copy-label]' ? label : status; },
    appendChild(field) { this.field = field; },
    ownerDocument: {
      createElement() { return { style: {}, focus() {}, select() {}, remove() { removed = true; } }; },
      execCommand(command) { assert.equal(command, 'copy'); copied = parent.field.value; return mode !== 'blocked'; }
    }
  };
  const cleanup = render({ data: { text }, parentElement: parent });
  await button.onclick();
  if (mode === 'blocked') {
    assert.equal(label.textContent, 'Try selecting text');
    assert.match(status.textContent, /blocked/);
  } else {
    assert.equal(copied, text);
    assert.equal(label.textContent, 'Copied');
  }
  if (mode !== 'clipboard') assert.equal(removed, true);
  cleanup();
}
console.log('Clipboard API, fallback, and denied-copy feedback passed.');
'''.replace('SOURCE', json.dumps(source), 1)
        result = subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
