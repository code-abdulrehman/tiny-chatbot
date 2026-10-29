import './styles.css';
import { DEFAULT_SYSTEM_PROMPT, loadThreads, saveThreads, loadSettings, saveSettings, newThread, routeFor } from './storage.js';
import { DEFAULT_GATEWAY_API_KEY, DEFAULT_GATEWAY_BASE_URL, DEFAULT_GATEWAY_MODEL, createGatewayChat, loadGatewaySettings, saveGatewaySettings } from './gateway.js';
import { createElement, ArrowUp, Bot, Check, Clock, Copy, EllipsisVertical, Lock, Menu, MessageSquare, Pencil, Play, Plus, RotateCcw, Search, Settings, Square, Trash2, User } from 'lucide';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const root = document.querySelector('#app');
root.innerHTML = `
  <aside class="sidebar">
    <header class="brand"><img class="brand-icon" src="./favicon.svg" alt="" width="30" height="30"><strong>Tiny Chat</strong><span class="brand-tag">Browser</span></header>
    <button id="new-chat" class="primary">New chat</button>
    <label class="private-row"><span id="private-label">Private chat</span><input id="private-toggle" type="checkbox" role="switch"></label>
    <div class="search-wrap"><input id="search" class="search" type="search" placeholder="Search chats" aria-label="Search chats"></div>
    <nav id="threads" aria-label="Saved chats"></nav>
    <button id="settings-button" class="settings-button">Settings</button>
  </aside>
  <main class="main">
    <header class="topbar"><button id="mobile-menu" aria-label="Toggle sidebar"></button><span id="model-status">Model loads on first message</span></header>
    <section id="messages" class="messages" aria-live="polite"></section>
    <div class="composer-wrap">
      <button id="continue-button" class="continue-button" hidden>Continue reply</button>
      <form id="composer"><textarea id="prompt" rows="1" placeholder="Message Tiny Chat" aria-label="Message Tiny Chat"></textarea><button id="send" type="submit" aria-label="Send message"></button><button id="stop" type="button" aria-label="Stop generating" hidden>Stop</button></form>
      <p class="hint">Runs on your device · Chats stay in this browser · AI can make mistakes</p>
    </div>
  </main>
  <dialog id="settings-dialog"><form method="dialog"><h2>Chat settings</h2><p class="model-name">onnx-community/Qwen2.5-0.5B-Instruct</p><label>Reply length (tokens)<select id="reply-tokens"><option>64</option><option>128</option><option>256</option></select></label><label>Recent context messages<select id="context-messages"><option>4</option><option>10</option><option>20</option></select></label><label>System prompt<textarea id="system-prompt" rows="6" maxlength="1200" spellcheck="true"></textarea></label><div class="prompt-help"><span>Applies to future replies in all chats.</span><button id="reset-system-prompt" type="button">Reset to default</button></div><p class="note">First load downloads model weights to your browser. WebGPU uses q4f16; CPU fallback uses q8. Chats are saved only in browser storage.</p>
  <label>Gateway base URL<input id="gateway-base-url" type="text" placeholder="http://127.0.0.1:8080" /></label>
  <label>Gateway API key<input id="gateway-api-key" type="password" placeholder="Optional · Bearer key" /></label>
  <label>Gateway model<input id="gateway-model" type="text" placeholder="org-model" /></label>
  <menu><button value="cancel">Cancel</button><button id="save-settings" value="save" class="primary">Save</button></menu></form></dialog>
`;

const $ = (selector) => root.querySelector(selector);
const icon = (definition, className = 'ui-icon') => {
  const svg = createElement(definition);
  svg.classList.add(className);
  svg.setAttribute('aria-hidden', 'true');
  return svg;
};
function renderMarkdown(element, source) {
  try {
    const html = marked.parse(source || '', { gfm: true, breaks: true });
    element.innerHTML = DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ['img', 'iframe', 'video', 'audio', 'source'],
    });
    for (const link of element.querySelectorAll('a')) {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
  } catch {
    element.textContent = source || '';
  }
}
$('#new-chat').prepend(icon(Plus));
$('#private-label').prepend(icon(Lock));
$('.search-wrap').prepend(icon(Search));
$('#settings-button').prepend(icon(Settings));
$('#mobile-menu').append(icon(Menu));
$('#continue-button').prepend(icon(Play));
$('#send').append(icon(ArrowUp));
$('#stop').prepend(icon(Square));
const store = window.localStorage;
const state = {
  threads: loadThreads(store),
  settings: loadSettings(store),
  current: null,
  busy: false,
  task: null,
  worker: null,
  queuedTitle: false,
  status: 'Model loads on first message',
  gateway: loadGatewaySettings(store),
};

function persist() {
  if (state.current?.privateChat) return;
  const index = state.threads.findIndex((t) => t.id === state.current.id);
  if (index >= 0) state.threads[index] = state.current;
  else if (state.current.messages.length) state.threads.unshift(state.current);
  state.threads.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  if (!saveThreads(store, state.threads)) setStatus('Browser storage is full or unavailable; this chat may not survive refresh.');
  renderThreads();
}

function setStatus(message) {
  state.status = message;
  $('#model-status').textContent = message;
}

function navigate(thread) {
  history.replaceState(null, '', routeFor(thread));
}

function setCurrent(thread) {
  if (state.busy) return;
  state.current = thread;
  $('#private-toggle').checked = !!thread.privateChat;
  navigate(thread);
  renderThreads();
  renderMessages();
  document.body.classList.remove('sidebar-open');
}

function renderThreads() {
  const container = $('#threads');
  container.replaceChildren();
  const query = $('#search').value.trim().toLowerCase();
  for (const thread of state.threads) {
    if (query && !`${thread.title} ${thread.messages.map((m) => m.content).join(' ')}`.toLowerCase().includes(query)) continue;
    const row = document.createElement('div');
    row.className = 'thread-row';
    const open = document.createElement('button');
    open.className = 'thread-open' + (thread.id === state.current?.id ? ' active' : '');
    const title = document.createElement('span');
    title.className = 'thread-title';
    title.textContent = thread.title;
    open.append(icon(MessageSquare), title);
    open.title = thread.title;
    open.addEventListener('click', () => setCurrent(thread));
    const menu = document.createElement('details');
    menu.className = 'thread-menu';
    const summary = document.createElement('summary');
    summary.append(icon(EllipsisVertical));
    summary.setAttribute('aria-label', `Actions for ${thread.title}`);
    menu.append(summary);
    for (const [label, actionIcon, action] of [
      ['Rename', Pencil, () => {
        const title = prompt('Chat title', thread.title)?.trim();
        if (title) { thread.title = title.slice(0, 48); thread.customTitle = true; persistThread(thread); }
      }],
      ['Duplicate', Copy, () => {
        const copy = { ...structuredClone(thread), id: crypto.randomUUID(), title: `${thread.title} (copy)`, updatedAt: new Date().toISOString() };
        state.threads.unshift(copy); saveThreads(store, state.threads); setCurrent(copy);
      }],
      ['Delete', Trash2, () => {
        if (!confirm(`Delete “${thread.title}”?`)) return;
        state.threads = state.threads.filter((t) => t.id !== thread.id);
        saveThreads(store, state.threads);
        if (state.current?.id === thread.id) setCurrent(newThread());
        else renderThreads();
      }],
    ]) {
      const button = document.createElement('button');
      button.append(icon(actionIcon), document.createTextNode(label));
      button.addEventListener('click', (event) => { event.stopPropagation(); menu.open = false; action(); });
      menu.append(button);
    }
    row.append(open, menu);
    container.append(row);
  }
}

function persistThread(thread) {
  thread.updatedAt = new Date().toISOString();
  if (!saveThreads(store, state.threads)) setStatus('Browser storage is full or unavailable.');
  renderThreads();
}

function messageElement(message, lastAssistant) {
  const article = document.createElement('article');
  article.className = `message ${message.role}`;
  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  avatar.append(icon(message.role === 'user' ? User : Bot));
  const body = document.createElement('div');
  body.className = 'message-body';
  const content = document.createElement('div');
  content.className = 'content';
  renderMarkdown(content, message.content);
  const footer = document.createElement('div');
  footer.className = 'message-footer';
  const actions = document.createElement('span');
  actions.className = 'message-actions';
  const copy = document.createElement('button');
  copy.append(icon(Copy), document.createTextNode('Copy'));
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(message.content); copy.replaceChildren(icon(Check), document.createTextNode('Copied')); }
    catch { copy.replaceChildren(icon(Copy), document.createTextNode('Copy failed')); }
  });
  actions.append(copy);
  if (message.role === 'assistant') {
    if (lastAssistant && !state.busy) {
      const retry = document.createElement('button');
      retry.append(icon(RotateCcw), document.createTextNode('Retry'));
      retry.addEventListener('click', retryLast);
      actions.append(retry);
    }
  }
  const time = document.createElement('time');
  time.dateTime = message.timestamp;
  time.append(icon(Clock), document.createTextNode(new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })));
  footer.append(actions, time);
  body.append(content, footer);
  article.append(avatar, body);
  return article;
}

function renderMessages() {
  const container = $('#messages');
  container.replaceChildren();
  if (!state.current.messages.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.innerHTML = '<div class="empty-title"><img src="./favicon.svg" alt=""><h1>Tiny Chat</h1></div><p>Private, on-device conversations with a small AI model.</p>';
    container.append(empty);
  } else {
    const last = state.current.messages.length - 1;
    state.current.messages.forEach((message, index) => container.append(messageElement(message, index === last && message.role === 'assistant')));
  }
  const last = state.current.messages.at(-1);
  $('#continue-button').hidden = state.busy || !(last?.role === 'assistant' && last.truncated);
  container.scrollTop = container.scrollHeight;
}

function setBusy(busy) {
  state.busy = busy;
  $('#send').hidden = busy;
  $('#stop').hidden = !busy;
  $('#prompt').disabled = busy;
  $('#new-chat').disabled = busy;
  $('#private-toggle').disabled = busy;
  renderMessages();
}

function getWorker() {
  if (state.worker) return state.worker;
  state.worker = new Worker(new URL('./model-worker.js', import.meta.url), { type: 'module' });
  state.worker.onmessage = onWorkerMessage;
  state.worker.onerror = (event) => finishError(event.message || 'Model worker failed to load.');
  return state.worker;
}

function startGeneration({ retry = false, continuation = false } = {}) {
  if (state.busy) return;
  const thread = state.current;
  const last = thread.messages.at(-1);
  if (retry && last?.role === 'assistant') thread.messages.pop();
  if (continuation && last?.role !== 'assistant') return;
  let message;
  if (continuation) {
    message = last;
    message.truncated = false;
  } else {
    message = { role: 'assistant', content: '', timestamp: new Date().toISOString(), truncated: false };
    thread.messages.push(message);
  }
  const id = crypto.randomUUID();
  const task = { id, thread, message, continuation, initialContent: message.content, stopped: false };
  state.task = task;
  setBusy(true);
  setStatus('Loading model / generating…');
  const messages = thread.messages.slice(0, -1).map(({ role, content }) => ({ role, content }));
  if (continuation) {
    messages.push({ role: 'assistant', content: message.content });
    messages.push({ role: 'user', content: 'Continue the previous answer from where it stopped. Do not repeat earlier text.' });
  }
  if (state.gateway.apiKey) { void runGatewayTask(task, messages, state.settings.replyTokens); return; }
  getWorker().postMessage({ type: 'generate', id, messages, maxNewTokens: state.settings.replyTokens, contextMessages: state.settings.contextMessages, systemPrompt: state.settings.systemPrompt });
}

async function runGatewayTask(task, messages, maxTokens) {
  try {
    setStatus('Waiting for gateway…');
    const response = await createGatewayChat({ baseUrl: state.gateway.baseUrl, apiKey: state.gateway.apiKey, messages, model: state.gateway.model || 'org-model', maxOutputTokens: maxTokens, stream: true, onToken: (token) => { if (token) task.message.content += token; } });
    const content = response?.choices?.[0]?.message?.content || task.initialContent || '';
    task.message.content = content;
    task.message.truncated = false;
    task.thread.updatedAt = new Date().toISOString();
    state.task = null;
    if (!task.thread.privateChat) persist();
    renderMessages();
    const last = state.current.messages.at(-1);
    const canTitle = !task.thread.privateChat && task.thread.title === 'New conversation' && !task.thread.customTitle && task.thread.messages.length === 2 && task.message.content;
    if (canTitle) {
      const id = crypto.randomUUID();
      state.queuedTitle = { id, thread: task.thread };
      if (state.worker) state.worker.postMessage({ type: 'generate', id, title: true, messages: task.thread.messages.map(({ role, content }) => ({ role, content })) });
    }
    setBusy(false);
    setStatus('Ready');
  } catch (error) {
    finishError(error?.message || 'Gateway request failed.');
  }
}

function onWorkerMessage({ data }) {
  if (data.type === 'loading') { setStatus(`Loading ${data.device.toUpperCase()} model (${data.dtype})…`); return; }
  if (data.type === 'download') { setStatus(`Downloading model: ${data.percent}%`); return; }
  if (data.type === 'ready') { setStatus(`Ready · ${data.device.toUpperCase()} · ${data.dtype}`); return; }
  if (state.queuedTitle && data.id === state.queuedTitle.id) {
    if (data.type === 'done') {
      const title = data.text.replace(/["'\n\r]/g, ' ').trim().replace(/\s+/g, ' ').split(' ').slice(0, 5).join(' ');
      if (title && !state.queuedTitle.thread.customTitle) { state.queuedTitle.thread.title = title.slice(0, 48); persistThread(state.queuedTitle.thread); }
      state.queuedTitle = false;
      setBusy(false);
      setStatus('Ready');
    } else if (data.type === 'error') {
      state.queuedTitle = false;
      setBusy(false);
      setStatus('Ready');
    }
    return;
  }
  const task = state.task;
  if (!task || data.id !== task.id) return;
  if (data.type === 'token') {
    task.message.content += data.text;
    const content = $('#messages .message:last-child .content');
    if (content) renderMarkdown(content, task.message.content);
    $('#messages').scrollTop = $('#messages').scrollHeight;
    return;
  }
  if (data.type === 'error') { finishError(data.message); return; }
  if (data.type !== 'done') return;
  const fresh = data.text || '';
  if (fresh) task.message.content = task.initialContent + fresh;
  if (task.stopped && !task.message.content) {
    task.thread.messages.pop();
    state.task = null;
    if (!task.thread.privateChat) persist();
    setBusy(false);
    setStatus('Stopped');
    return;
  }
  task.message.truncated = !!data.truncated && !task.stopped;
  task.thread.updatedAt = new Date().toISOString();
  state.task = null;
  if (!task.thread.privateChat) persist();
  renderMessages();
  if (!task.thread.privateChat && task.thread.title === 'New conversation' && !task.thread.customTitle && task.thread.messages.length === 2 && task.message.content) {
    const id = crypto.randomUUID();
    state.queuedTitle = { id, thread: task.thread };
    getWorker().postMessage({ type: 'generate', id, title: true, messages: task.thread.messages.map(({ role, content }) => ({ role, content })) });
  } else {
    setBusy(false);
    setStatus('Ready');
  }
}

function finishError(message) {
  const task = state.task;
  if (task) {
    if (!task.message.content) task.message.content = `Could not generate a reply: ${message}`;
    task.message.truncated = false;
    state.task = null;
    if (!task.thread.privateChat) persist();
  }
  state.queuedTitle = false;
  setBusy(false);
  setStatus(`Model error: ${message}`);
}

function retryLast() {
  if (state.busy || state.current.messages.at(-1)?.role !== 'assistant') return;
  startGeneration({ retry: true });
}

$('#composer').addEventListener('submit', (event) => {
  event.preventDefault();
  const content = $('#prompt').value.trim();
  if (!content || state.busy) return;
  state.current.messages.push({ role: 'user', content, timestamp: new Date().toISOString() });
  state.current.updatedAt = new Date().toISOString();
  $('#prompt').value = '';
  if (!state.current.privateChat) { persist(); navigate(state.current); }
  renderMessages();
  startGeneration();
});
$('#prompt').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#composer').requestSubmit(); }
});
$('#new-chat').addEventListener('click', () => setCurrent(newThread($('#private-toggle').checked)));
$('#private-toggle').addEventListener('change', (event) => setCurrent(newThread(event.target.checked)));
$('#search').addEventListener('input', renderThreads);
$('#stop').addEventListener('click', () => {
  if (state.task) { state.task.stopped = true; getWorker().postMessage({ type: 'stop' }); setStatus('Stopping…'); }
});
$('#continue-button').addEventListener('click', () => startGeneration({ continuation: true }));
$('#mobile-menu').addEventListener('click', () => document.body.classList.toggle('sidebar-open'));
$('#settings-button').addEventListener('click', () => {
  $('#reply-tokens').value = String(state.settings.replyTokens);
  $('#context-messages').value = String(state.settings.contextMessages);
  $('#system-prompt').value = state.settings.systemPrompt;
  $('#settings-dialog').showModal();
});
$('#reset-system-prompt').addEventListener('click', () => { $('#system-prompt').value = DEFAULT_SYSTEM_PROMPT; });
$('#save-settings').addEventListener('click', () => {
  state.settings = {
    replyTokens: Number($('#reply-tokens').value),
    contextMessages: Number($('#context-messages').value),
    systemPrompt: $('#system-prompt').value.trim() || DEFAULT_SYSTEM_PROMPT,
  };
  if (!saveSettings(store, state.settings)) setStatus('Could not save settings in this browser.');
  state.gateway = {
    baseUrl: String($('#gateway-base-url').value || DEFAULT_GATEWAY_BASE_URL).replace(/\/+$/, ''),
    apiKey: String($('#gateway-api-key').value || DEFAULT_GATEWAY_API_KEY),
    model: String($('#gateway-model').value || DEFAULT_GATEWAY_MODEL),
  };
  if (!saveGatewaySettings(store, state.gateway)) setStatus('Could not save gateway settings in this browser.');
});
window.addEventListener('popstate', () => {
  if (state.busy) return;
  const id = new URL(location.href).searchParams.get('chat');
  setCurrent(state.threads.find((thread) => thread.id === id) || newThread());
});

const id = new URL(location.href).searchParams.get('chat');
setCurrent(state.threads.find((thread) => thread.id === id) || newThread());
