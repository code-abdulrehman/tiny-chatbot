export const DEFAULT_GATEWAY_BASE_URL = 'http://127.0.0.1:8080';
export const DEFAULT_GATEWAY_API_KEY = '';
export const DEFAULT_GATEWAY_MODEL = '';

export function loadGatewaySettings(storage, sessionStorage = storage) {
  const baseUrl = typeof storage?.getItem === 'function' ? (storage.getItem('gatewayBaseUrl') || DEFAULT_GATEWAY_BASE_URL) : DEFAULT_GATEWAY_BASE_URL;
  const apiKey = typeof sessionStorage?.getItem === 'function' ? (sessionStorage.getItem('gatewayApiKey') || DEFAULT_GATEWAY_API_KEY) : DEFAULT_GATEWAY_API_KEY;
  const model = typeof storage?.getItem === 'function' ? (storage.getItem('gatewayModel') || DEFAULT_GATEWAY_MODEL) : DEFAULT_GATEWAY_MODEL;
  return { baseUrl: String(baseUrl).replace(/\/+$/, ''), apiKey: String(apiKey), model: String(model) };
}

export function saveGatewaySettings(storage, settings, sessionStorage = storage) {
  try {
    storage.setItem('gatewayBaseUrl', settings?.baseUrl || DEFAULT_GATEWAY_BASE_URL);
    sessionStorage.setItem('gatewayApiKey', settings?.apiKey || DEFAULT_GATEWAY_API_KEY);
    storage.setItem('gatewayModel', settings?.model || DEFAULT_GATEWAY_MODEL);
    return true;
  } catch {
    return false;
  }
}

export function gatewayHeaders(apiKey) {
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;
  return headers;
}

export async function checkGatewayHealth(baseUrl) {
  const response = await fetch(`${baseUrl}/health`);
  if (!response.ok) throw new Error(`Gateway health check failed with status ${response.status}`);
  return response.json();
}

export async function listGatewayModels(baseUrl, apiKey) {
  const response = await fetch(`${baseUrl}/v1/models`, { headers: gatewayHeaders(apiKey) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `Gateway model list failed with status ${response.status}`);
  return data;
}

export async function createGatewayChat({ baseUrl, apiKey, messages, model, maxOutputTokens, stream = true, onToken, signal }) {
  const response = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: gatewayHeaders(apiKey),
    body: JSON.stringify({ model, messages, max_output_tokens: maxOutputTokens, stream }),
    signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error?.message || `Gateway chat failed with status ${response.status}`);
  }
  if (!stream) return response.json();
  if (!response.body) throw new Error('Gateway did not return a streaming response body.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let content = '';
  let settled = false;
  let finishReason = 'stop';
  while (!settled) {
    const { done: streamDone, value } = await reader.read();
    if (streamDone) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      const event = JSON.parse(payload);
      if (event.event === 'token') { content += event.text || ''; onToken?.(event.text || ''); }
      if (event.event === 'error') throw new Error(event.message || 'Gateway generation failed.');
      if (event.event === 'done') { content = event.content || content; finishReason = event.finish_reason || 'stop'; settled = true; break; }
    }
  }
  if (!settled) throw new Error('Gateway stream ended before completion.');
  return { choices: [{ message: { role: 'assistant', content }, finish_reason: finishReason }] };
}
