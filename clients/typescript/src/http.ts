import type { HydraceptClientOptions, HydraceptHttpError } from './types.js';

function resolveToken(options: HydraceptClientOptions): string {
  if (options.getToken) return options.getToken();
  return options.token ?? '';
}

function joinUrl(baseUrl: string, path: string): string {
  const base = baseUrl.replace(/\/$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${base}${suffix}`;
}

function toV1Path(path: string, pathsAreV1Relative: boolean | undefined): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  if (pathsAreV1Relative) {
    // Caller already speaks /assets, /workflows, etc. (Vite proxy to /v1).
    return normalized;
  }
  if (normalized.startsWith('/v1/') || normalized === '/v1' || normalized === '/healthz') {
    return normalized;
  }
  return `/v1${normalized}`;
}

export function createHydraceptHttp(options: HydraceptClientOptions) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const credentials = options.credentials ?? 'omit';

  function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    const token = resolveToken(options);
    const headers: Record<string, string> = { ...extra };
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  function urlFor(path: string): string {
    return joinUrl(options.baseUrl, toV1Path(path, options.pathsAreV1Relative));
  }

  async function fetchResponse(path: string, init: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
      ...authHeaders(),
      ...(init.headers as Record<string, string> | undefined),
    };
    if (init.body && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetchImpl(urlFor(path), {
      ...init,
      headers,
      credentials,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      const error = new Error(`Hydracept ${path} failed (${res.status}): ${text}`) as HydraceptHttpError;
      error.status = res.status;
      error.body = text;
      throw error;
    }
    return res;
  }

  async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetchResponse(path, init);
    return res.json() as Promise<T>;
  }

  async function fetchBlob(path: string, init: RequestInit = {}): Promise<Blob> {
    const res = await fetchResponse(path, init);
    return res.blob();
  }

  async function fetchBytes(path: string, init: RequestInit = {}): Promise<ArrayBuffer> {
    const res = await fetchResponse(path, init);
    return res.arrayBuffer();
  }

  function isRetryableStatus(status: number): boolean {
    return status === 408 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
  }

  async function fetchJsonWithRetry<T>(
    path: string,
    init: RequestInit = {},
    retry: { maxAttempts?: number; baseDelayMs?: number } = {},
  ): Promise<T> {
    const maxAttempts = retry.maxAttempts ?? 8;
    const baseDelayMs = retry.baseDelayMs ?? 750;
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        return await fetchJson<T>(path, init);
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        lastError = error;
        const status = (error as HydraceptHttpError).status;
        const retryable = status !== undefined && isRetryableStatus(status);
        if (!retryable || attempt === maxAttempts) throw error;
        const delayMs = baseDelayMs * attempt;
        await new Promise<void>((resolve, reject) => {
          const timer = setTimeout(resolve, delayMs);
          init.signal?.addEventListener(
            'abort',
            () => {
              clearTimeout(timer);
              reject(init.signal?.reason ?? new DOMException('Aborted', 'AbortError'));
            },
            { once: true },
          );
        });
      }
    }

    throw lastError ?? new Error(`Hydracept ${path} failed after retries`);
  }

  return {
    options,
    authHeaders,
    urlFor,
    fetchResponse,
    fetchJson,
    fetchBlob,
    fetchBytes,
    fetchJsonWithRetry,
  };
}

export type HydraceptHttp = ReturnType<typeof createHydraceptHttp>;
