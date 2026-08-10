import type { HydraceptHttp } from './http.js';
import { iterInvocationEvents } from './sse.js';
import type { HydraceptRuntimeEvent } from './types.js';

/** Runtime helpers used by trusted product backends (product-backend). */
export function createHydraceptRuntimeApi(http: HydraceptHttp) {
  return {
    invoke<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/invocations', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getInvocation<T = unknown>(executionId: string): Promise<T> {
      return http.fetchJson<T>(`/invocations/${encodeURIComponent(executionId)}`);
    },

    getReceipt<T = unknown>(executionId: string): Promise<T> {
      return http.fetchJson<T>(`/invocations/${encodeURIComponent(executionId)}/receipt`);
    },

    cancelInvocation<T = unknown>(executionId: string): Promise<T> {
      return http.fetchJson<T>(`/invocations/${encodeURIComponent(executionId)}/cancel`, {
        method: 'POST',
      });
    },

    submitJob<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/jobs', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getJob<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJsonWithRetry<T>(`/jobs/${encodeURIComponent(jobId)}`);
    },

    getJobResult<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJson<T>(`/jobs/${encodeURIComponent(jobId)}/result`);
    },

    getCapabilities<T = unknown>(): Promise<T> {
      return http.fetchJson<T>('/capabilities');
    },

    describeCapability<T = unknown>(key: string): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}`);
    },

    invokeCapability<T = unknown>(key: string, body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/invoke`, {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    submitCapabilityJob<T = unknown>(
      key: string,
      body: unknown,
      init: RequestInit = {},
    ): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/jobs`, {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getJobReceipt<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJson<T>(`/jobs/${encodeURIComponent(jobId)}/receipt`);
    },

    cancelJob<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJson<T>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
    },

    streamInvocationEvents(
      executionId: string,
      options: { lastEventId?: string; signal?: AbortSignal } = {},
    ): AsyncGenerator<HydraceptRuntimeEvent, void, unknown> {
      const token = http.options.getToken?.() ?? http.options.token ?? '';
      const sseOptions: {
        lastEventId?: string;
        signal?: AbortSignal;
        pathsAreV1Relative?: boolean;
        credentials?: RequestCredentials;
        fetchImpl?: typeof fetch;
      } = {};
      if (options.lastEventId !== undefined) sseOptions.lastEventId = options.lastEventId;
      if (options.signal !== undefined) sseOptions.signal = options.signal;
      if (http.options.pathsAreV1Relative !== undefined) {
        sseOptions.pathsAreV1Relative = http.options.pathsAreV1Relative;
      }
      if (http.options.credentials !== undefined) sseOptions.credentials = http.options.credentials;
      if (http.options.fetchImpl !== undefined) sseOptions.fetchImpl = http.options.fetchImpl;
      return iterInvocationEvents(http.options.baseUrl, token, executionId, sseOptions);
    },
  };
}

export type HydraceptRuntimeApi = ReturnType<typeof createHydraceptRuntimeApi>;
