import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_GATEWAY_API_KEY, DEFAULT_GATEWAY_BASE_URL, DEFAULT_GATEWAY_MODEL, gatewayHeaders, loadGatewaySettings, saveGatewaySettings } from '../src/gateway.js';

function memoryStore() {
  const items = new Map();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
  };
}

test('gateway settings load defaults and persist overrides', () => {
  const storage = memoryStore();
  assert.deepEqual(loadGatewaySettings(storage), { baseUrl: DEFAULT_GATEWAY_BASE_URL, apiKey: DEFAULT_GATEWAY_API_KEY, model: DEFAULT_GATEWAY_MODEL });
  assert.equal(saveGatewaySettings(storage, { baseUrl: 'http://localhost:9000', apiKey: 'gk_test' }), true);
  assert.deepEqual(loadGatewaySettings(storage), { baseUrl: 'http://localhost:9000', apiKey: 'gk_test', model: DEFAULT_GATEWAY_MODEL });
  assert.equal(saveGatewaySettings(storage, { baseUrl: 'http://127.0.0.1:8080/' }), true);
  assert.equal(loadGatewaySettings(storage).baseUrl, 'http://127.0.0.1:8080');
});

test('gateway headers include bearer auth only when a key is present', () => {
  assert.deepEqual(gatewayHeaders('gk_test'), { 'Content-Type': 'application/json', Authorization: 'Bearer gk_test' });
  assert.deepEqual(gatewayHeaders(''), { 'Content-Type': 'application/json' });
});
