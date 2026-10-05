import assert from 'node:assert/strict';
import test from 'node:test';

import { createHydraceptHttp } from '../dist/http.js';
import { createHydraceptRuntimeApi } from '../dist/runtime.js';

test('invokeCapability preserves caller idempotencyKey', async () => {
  const calls = [];
  const http = createHydraceptHttp({
    baseUrl: 'http://example.test',
    token: 't',
    fetchImpl: async (_url, init) => {
      calls.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const api = createHydraceptRuntimeApi(http);
  await api.invokeCapability('text.general.fast.v1', { idempotencyKey: 'keep-me', input: { prompt: 'hi' } });
  assert.equal(calls[0].idempotencyKey, 'keep-me');
});

test('invokeCapability retries transient failures with same body', async () => {
  const calls = [];
  const http = createHydraceptHttp({
    baseUrl: 'http://example.test',
    token: 't',
    fetchImpl: async (_url, init) => {
      calls.push(init.body);
      if (calls.length < 2) {
        return new Response('unavailable', { status: 503 });
      }
      return new Response(JSON.stringify({ status: 'Succeeded' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const api = createHydraceptRuntimeApi(http);
  const body = { idempotencyKey: 'retry-stable', input: { prompt: 'hi' } };
  const result = await api.invokeCapability('text.general.fast.v1', body);
  assert.equal(result.status, 'Succeeded');
  assert.equal(calls.length, 2);
  assert.equal(calls[0], calls[1]);
});

test('invokeCapability retries transport failures with stable idempotencyKey', async () => {
  const calls = [];
  let attempts = 0;
  const http = createHydraceptHttp({
    baseUrl: 'http://example.test',
    token: 't',
    fetchImpl: async (_url, init) => {
      attempts += 1;
      calls.push(JSON.parse(String(init.body)).idempotencyKey);
      if (attempts < 2) {
        throw new TypeError('fetch failed');
      }
      return new Response(JSON.stringify({ status: 'Succeeded' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const api = createHydraceptRuntimeApi(http);
  const result = await api.invokeCapability('text.general.fast.v1', {
    idempotencyKey: 'transport-stable',
    input: { prompt: 'hi' },
  });
  assert.equal(result.status, 'Succeeded');
  assert.equal(calls.length, 2);
  assert.equal(calls[0], calls[1]);
});

test('fetchJsonWithRetry does not retry after abort', async () => {
  let attempts = 0;
  const controller = new AbortController();
  const http = createHydraceptHttp({
    baseUrl: 'http://example.test',
    token: 't',
    fetchImpl: async () => {
      attempts += 1;
      controller.abort(new DOMException('user abort', 'AbortError'));
      return new Response('unavailable', { status: 503 });
    },
  });
  await assert.rejects(
    () =>
      http.fetchJsonWithRetry('/capabilities/k/invoke', {
        method: 'POST',
        body: JSON.stringify({ idempotencyKey: 'abort-once' }),
        signal: controller.signal,
      }),
    (err) => err instanceof DOMException && err.name === 'AbortError',
  );
  assert.equal(attempts, 1);
});

test('invokeCapability rejects non-object body', () => {
  const http = createHydraceptHttp({
    baseUrl: 'http://example.test',
    token: 't',
    fetchImpl: async () => new Response('{}', { status: 200 }),
  });
  const api = createHydraceptRuntimeApi(http);
  assert.throws(() => api.invokeCapability('k', 'nope'), TypeError);
});
