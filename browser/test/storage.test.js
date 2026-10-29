import test from 'node:test';
import assert from 'node:assert/strict';
import { loadThreads, saveThreads, newThread, routeFor } from '../src/storage.js';

function memoryStore() {
  const items = new Map();
  return { getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value) };
}

test('saved threads survive a new load', () => {
  const storage = memoryStore();
  const thread = newThread();
  thread.messages.push({ role: 'user', content: 'Hello' });
  assert.equal(saveThreads(storage, [thread]), true);
  assert.equal(loadThreads(storage)[0].messages[0].content, 'Hello');
});

test('invalid storage data falls back safely', () => {
  const storage = { getItem: () => '{broken', setItem: () => { throw Error('blocked'); } };
  assert.deepEqual(loadThreads(storage), []);
  assert.equal(saveThreads(storage, []), false);
});

test('private chats are excluded from shareable URLs', () => {
  globalThis.window = { location: { href: 'https://example.com/chat/?chat=old' } };
  assert.equal(routeFor(newThread(true)).searchParams.has('chat'), false);
  const saved = newThread();
  assert.equal(routeFor(saved).searchParams.get('chat'), saved.id);
  delete globalThis.window;
});
