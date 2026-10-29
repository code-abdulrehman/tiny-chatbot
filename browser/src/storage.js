export const THREADS_KEY = 'tiny-chat-browser-threads-v1';

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
