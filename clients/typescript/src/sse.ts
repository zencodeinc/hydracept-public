import type { HydraceptRuntimeEvent } from './types.js';

/**
 * Maintained SSE helper for Hydracept invocation events.
 * Ordinary REST clients should prefer createHydraceptHttp / OpenAPI-generated types.
 */
export async function* iterInvocationEvents(
  baseUrl: string,
  token: string,
  executionId: string,
  options: {
    lastEventId?: string;
    signal?: AbortSignal;
    /** When true, baseUrl already points at /v1 (or a proxy that strips it). */
    pathsAreV1Relative?: boolean;
    fetchImpl?: typeof fetch;
    credentials?: RequestCredentials;
  } = {},
): AsyncGenerator<HydraceptRuntimeEvent, void, unknown> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    Accept: 'text/event-stream',
  };
  if (options.lastEventId) {
    headers['Last-Event-ID'] = options.lastEventId;
  }

  const root = baseUrl.replace(/\/$/, '');
  const path = options.pathsAreV1Relative
    ? `/invocations/${encodeURIComponent(executionId)}/events`
    : `/v1/invocations/${encodeURIComponent(executionId)}/events`;
  const fetchImpl = options.fetchImpl ?? fetch;
  const response = await fetchImpl(`${root}${path}`, {
    headers,
    credentials: options.credentials ?? 'omit',
    ...(options.signal ? { signal: options.signal } : {}),
  });
  if (!response.ok || !response.body) {
    throw new Error(`SSE failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventName = 'message';
  let dataLines: string[] = [];
  let eventId: string | undefined;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n');
    buffer = parts.pop() ?? '';
    for (const line of parts) {
      if (line === '') {
        if (dataLines.length) {
          const payload: HydraceptRuntimeEvent = {
            event: eventName,
            data: JSON.parse(dataLines.join('\n')),
          };
          if (eventId !== undefined) payload.id = eventId;
          yield payload;
        }
        eventName = 'message';
        dataLines = [];
        eventId = undefined;
        continue;
      }
      if (line.startsWith(':')) continue;
      if (line.startsWith('id:')) eventId = line.slice(3).trim();
      else if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
  }
}
