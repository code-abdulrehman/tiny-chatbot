"""Check scroll direction, visibility, reduced motion, and listener cleanup."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed to check scroll JavaScript')
class ScrollTests(unittest.TestCase):
    def test_scroll_controls(self):
        module = ast.parse((Path(__file__).resolve().parents[1] / 'scroll_controls.py').read_text())
        source = next(ast.literal_eval(n.value) for n in module.body
                      if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SCROLL_JS' for t in n.targets))
        script = '''
import assert from 'node:assert/strict';
const source = SOURCE;
const render = (await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))).default;
const up = {}, down = {}, listeners = new Map();
let firstTop = 100, lastBottom = 1500, reduced = false, disconnected = 0;
const first = { getBoundingClientRect: () => ({ top: firstTop }) };
const last = { getBoundingClientRect: () => ({ bottom: lastBottom }) };
let messages = [first, last];
const scroller = {
  scrollHeight: 1600, clientHeight: 600, scrollTop: 0,
  getBoundingClientRect: () => ({ top: 0, bottom: 600 }),
  addEventListener(name, fn) { listeners.set(name, fn); },
  removeEventListener(name) { listeners.delete(name); },
  scrollTo(options) { this.destination = options; }
};
const main = { querySelectorAll: () => messages, querySelector: () => ({}) };
const host = { closest: () => main, parentElement: scroller };
const parentElement = { getRootNode: () => ({ host }), querySelector: s => s.includes('up') ? up : down };
globalThis.getComputedStyle = () => ({ overflowY: 'auto' });
globalThis.window = {
  matchMedia: () => ({ matches: reduced }),
  addEventListener(name, fn) { listeners.set(name, fn); },
  removeEventListener(name) { listeners.delete(name); }
};
globalThis.ResizeObserver = class { observe() {} disconnect() { disconnected++; } };
globalThis.MutationObserver = class { observe() {} disconnect() { disconnected++; } };
const cleanup = render({ parentElement });
assert.equal(up.hidden, true);
assert.equal(down.hidden, false);
down.onclick();
assert.deepEqual(scroller.destination, { top: 996, behavior: 'smooth' });
scroller.scrollTop = 1000; firstTop = -900; lastBottom = 500;
listeners.get('scroll')();
assert.equal(up.hidden, false);
assert.equal(down.hidden, true);
reduced = true;
up.onclick();
assert.deepEqual(scroller.destination, { top: 84, behavior: 'auto' });
scroller.scrollHeight = 500;
listeners.get('resize')();
assert.equal(up.hidden, true);
assert.equal(down.hidden, true);
messages = [];
listeners.get('scroll')();
assert.equal(up.hidden, true);
assert.equal(down.hidden, true);
cleanup();
assert.equal(listeners.size, 0);
assert.equal(disconnected, 2);
assert.equal(up.onclick, null);
assert.equal(down.onclick, null);
'''.replace('SOURCE', json.dumps(source), 1)
        result = subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
