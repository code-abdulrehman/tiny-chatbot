import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_SETTINGS, DEFAULT_SYSTEM_PROMPT, MAX_SYSTEM_PROMPT_LENGTH, loadThreads, saveThreads, loadSettings, saveSettings, newThread, routeFor } from '../src/storage.js';

function memoryStore() {
  const items = new Map();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
  };
}

test('saved threads and settings survive a new load', () => {
  const storage = memoryStore();
  const thread = newThread();
  thread.messages.push({ role: 'user', content: 'Hello' });
  assert.equal(saveThreads(storage, [thread]), true);
  assert.equal(loadThreads(storage)[0].messages[0].content, 'Hello');
  assert.equal(saveSettings(storage, { replyTokens: 256, contextMessages: 20, systemPrompt: 'Answer in Roman Urdu.' }), true);
  assert.deepEqual(loadSettings(storage), { replyTokens: 256, contextMessages: 20, systemPrompt: 'Answer in Roman Urdu.' });
});

test('older settings gain the default system prompt without losing preferences', () => {
  const storage = memoryStore();
  saveSettings(storage, { replyTokens: 64, contextMessages: 4 });
  assert.deepEqual(loadSettings(storage), { replyTokens: 64, contextMessages: 4, systemPrompt: DEFAULT_SYSTEM_PROMPT });
  saveSettings(storage, { replyTokens: 64, contextMessages: 4, systemPrompt: 'x'.repeat(MAX_SYSTEM_PROMPT_LENGTH + 1) });
  assert.equal(loadSettings(storage).systemPrompt, DEFAULT_SYSTEM_PROMPT);
});

test('invalid storage data falls back safely', () => {
  const storage = { getItem: () => '{broken', setItem: () => { throw Error('blocked'); } };
  assert.deepEqual(loadThreads(storage), []);
  assert.deepEqual(loadSettings(storage), DEFAULT_SETTINGS);
  assert.equal(saveThreads(storage, []), false);
});

test('private chats are excluded from shareable URLs', () => {
  globalThis.window = { location: { href: 'https://example.com/chat/?chat=old' } };
  assert.equal(routeFor(newThread(true)).searchParams.has('chat'), false);
  const saved = newThread();
  assert.equal(routeFor(saved).searchParams.get('chat'), saved.id);
  delete globalThis.window;
});
