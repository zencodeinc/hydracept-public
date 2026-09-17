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

    resolveCapability<T = unknown>(body: unknown): Promise<T> {
      return http.fetchJson<T>('/capabilities/resolve', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    estimateCapability<T = unknown>(key: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/quote`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    quoteCapability<T = unknown>(key: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/quote`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    createCapabilityRequest<T = unknown>(body: unknown): Promise<T> {
      return http.fetchJson<T>('/capability-requests', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    reviseCapabilityRequest<T = unknown>(requestId: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/capability-requests/${encodeURIComponent(requestId)}/revisions`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    submitCapabilityRequest<T = unknown>(requestId: string): Promise<T> {
      return http.fetchJson<T>(`/capability-requests/${encodeURIComponent(requestId)}/submit`, {
        method: 'POST',
      });
    },

    getCapabilityRequest<T = unknown>(requestId: string): Promise<T> {
      return http.fetchJson<T>(`/capability-requests/${encodeURIComponent(requestId)}`);
    },

    getCapabilityRequestQuote<T = unknown>(requestId: string): Promise<T> {
      return http.fetchJson<T>(`/capability-requests/${encodeURIComponent(requestId)}/quote`);
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

    createComparison<T = unknown>(key: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/comparisons`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    estimateComparison<T = unknown>(key: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/capabilities/${encodeURIComponent(key)}/comparisons/estimate`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    getComparison<T = unknown>(comparisonId: string): Promise<T> {
      return http.fetchJson<T>(`/comparisons/${encodeURIComponent(comparisonId)}`);
    },

    submitComparisonJudgement<T = unknown>(comparisonId: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/comparisons/${encodeURIComponent(comparisonId)}/judgements`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    getJobReceipt<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJson<T>(`/jobs/${encodeURIComponent(jobId)}/receipt`);
    },

    listProjectJobs<T = unknown>(
      projectId: string,
      options: {
        limit?: number;
        cursor?: string;
        status?: string;
        capabilityKey?: string;
        outcome?: 'failed' | 'reusable';
        selected?: boolean;
      } = {},
    ): Promise<T> {
      const params = new URLSearchParams();
      if (options.limit !== undefined) params.set('limit', String(options.limit));
      if (options.cursor) params.set('cursor', options.cursor);
      if (options.status) params.set('status', options.status);
      if (options.capabilityKey) params.set('capabilityKey', options.capabilityKey);
      if (options.outcome) params.set('outcome', options.outcome);
      if (options.selected !== undefined) params.set('selected', String(options.selected));
      const query = params.toString();
      return http.fetchJson<T>(
        `/projects/${encodeURIComponent(projectId)}/jobs${query ? `?${query}` : ''}`,
      );
    },

    cancelJob<T = unknown>(jobId: string): Promise<T> {
      return http.fetchJson<T>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
    },

    createPinnedInference<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/inference/pinned', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    createPinnedInferenceBulk<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/inference/pinned/bulk', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getPinnedBulk<T = unknown>(bulkId: string): Promise<T> {
      return http.fetchJson<T>(`/inference/pinned/bulk/${encodeURIComponent(bulkId)}`);
    },

    getPinnedReceipt<T = unknown>(receiptId: string): Promise<T> {
      return http.fetchJson<T>(`/inference/pinned/${encodeURIComponent(receiptId)}`);
    },

    listPinnedReceipts<T = unknown>(): Promise<T> {
      return http.fetchJson<T>('/inference/pinned');
    },

    createRunManifest<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/provenance/manifests', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getRunManifest<T = unknown>(manifestId: string): Promise<T> {
      return http.fetchJson<T>(`/provenance/manifests/${encodeURIComponent(manifestId)}`);
    },

    verifyRunManifest<T = unknown>(manifestId: string, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(`/provenance/manifests/${encodeURIComponent(manifestId)}/verify`, {
        method: 'POST',
        ...init,
      });
    },

    getLockfile<T = unknown>(receiptId: string): Promise<T> {
      return http.fetchJson<T>(
        `/provenance/lockfile?receipt_id=${encodeURIComponent(receiptId)}`,
      );
    },

    verifyLockfile<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/provenance/lockfile/verify', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    downloadJobArtifact(jobId: string, artifactId: string): Promise<Blob> {
      return http.fetchBlob(
        `/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`,
      );
    },

    async pollJobUntilTerminal<T extends { status?: string } = { status?: string }>(
      jobId: string,
      options: { intervalMs?: number; signal?: AbortSignal; terminal?: string[] } = {},
    ): Promise<T> {
      const intervalMs = options.intervalMs ?? 2000;
      const terminal = new Set(
        (options.terminal ?? ['succeeded', 'failed', 'canceled', 'cancelled']).map((s) =>
          s.toLowerCase(),
        ),
      );
      for (;;) {
        if (options.signal?.aborted) {
          throw new DOMException('Aborted', 'AbortError');
        }
        const job = await http.fetchJsonWithRetry<T>(`/jobs/${encodeURIComponent(jobId)}`);
        const status = String(job.status ?? '').toLowerCase();
        if (terminal.has(status)) {
          return job;
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
      }
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
