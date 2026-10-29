export const DEFAULT_GATEWAY_BASE_URL = 'http://127.0.0.1:8080';
export const DEFAULT_GATEWAY_API_KEY = '';
export const DEFAULT_GATEWAY_MODEL = '';

export function loadGatewaySettings(storage) {
  const baseUrl = typeof storage?.getItem === 'function' ? (storage.getItem('gatewayBaseUrl') || DEFAULT_GATEWAY_BASE_URL) : DEFAULT_GATEWAY_BASE_URL;
  const apiKey = typeof storage?.getItem === 'function' ? (storage.getItem('gatewayApiKey') || DEFAULT_GATEWAY_API_KEY) : DEFAULT_GATEWAY_API_KEY;
  const model = typeof storage?.getItem === 'function' ? (storage.getItem('gatewayModel') || DEFAULT_GATEWAY_MODEL) : DEFAULT_GATEWAY_MODEL;
  return { baseUrl: String(baseUrl).replace(/\/+$/, ''), apiKey: String(apiKey), model: String(model) };
}

export function saveGatewaySettings(storage, settings) {
  try {
    storage.setItem('gatewayBaseUrl', settings?.baseUrl || DEFAULT_GATEWAY_BASE_URL);
    storage.setItem('gatewayApiKey', settings?.apiKey || DEFAULT_GATEWAY_API_KEY);
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

export async function createGatewayChat({ baseUrl, apiKey, messages, model, maxOutputTokens, stream = true, onToken }) {
  const response = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: gatewayHeaders(apiKey),
    body: JSON.stringify({ model, messages, max_output_tokens: maxOutputTokens, stream }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `Gateway chat failed with status ${response.status}`);
  if (!stream) return data;
  if (!response.body) throw new Error('Gateway did not return a streaming response body.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let content = '';
  let settled = false;
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
      if (event.event === 'done') { settled = true; break; }
    }
  }
  const finalContent = content || data?.choices?.[0]?.message?.content || '';
  return { ...data, choices: [{ ...(data?.choices?.[0] || {}), message: { ...(data?.choices?.[0]?.message || {}), content: finalContent }, finish_reason: (data?.choices?.[0]?.finish_reason) || 'stop' }] };
}
