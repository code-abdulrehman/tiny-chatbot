export const THREADS_KEY = 'tiny-chat-browser-threads-v1';
export const SETTINGS_KEY = 'tiny-chat-browser-settings-v1';
export const DEFAULT_SETTINGS = Object.freeze({ replyTokens: 128, contextMessages: 10 });

export function loadJson(storage, key, fallback) {
  try {
    const value = storage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

export function loadThreads(storage) {
  const threads = loadJson(storage, THREADS_KEY, []);
  return Array.isArray(threads) ? threads.filter((thread) =>
    thread && typeof thread.id === 'string' && Array.isArray(thread.messages)) : [];
}

export function saveThreads(storage, threads) {
  try {
    storage.setItem(THREADS_KEY, JSON.stringify(threads));
    return true;
  } catch {
    return false;
  }
}

export function loadSettings(storage) {
  const saved = loadJson(storage, SETTINGS_KEY, {});
  return {
    replyTokens: [64, 128, 256].includes(saved?.replyTokens) ? saved.replyTokens : DEFAULT_SETTINGS.replyTokens,
    contextMessages: [4, 10, 20].includes(saved?.contextMessages) ? saved.contextMessages : DEFAULT_SETTINGS.contextMessages,
  };
}

export function saveSettings(storage, settings) {
  try {
    storage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;
  }
}

export function newThread(privateChat = false) {
  return {
    id: crypto.randomUUID(),
    title: 'New conversation',
    messages: [],
    privateChat,
    updatedAt: new Date().toISOString(),
  };
}

export function routeFor(thread) {
  const url = new URL(window.location.href);
  if (thread && !thread.privateChat) url.searchParams.set('chat', thread.id);
  else url.searchParams.delete('chat');
  return url;
}
