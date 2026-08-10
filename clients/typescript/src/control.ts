import type { HydraceptHttp } from './http.js';
import type { HydraceptAssetOut, HydraceptAssetPage } from './types.js';

function normalizeAssetList(data: readonly HydraceptAssetOut[] | HydraceptAssetPage): HydraceptAssetOut[] {
  if (Array.isArray(data)) return [...data];
  const page = data as HydraceptAssetPage;
  return [...(page.items ?? [])];
}

/** Control-plane helpers used by product authoring UIs (KOL, Workbench). */
export function createHydraceptControlApi(http: HydraceptHttp) {
  return {
    healthz(path = '/healthz'): Promise<Response> {
      // healthz is outside /v1 — call absolute-ish via fetchResponse with special path handling
      return http.fetchResponse(path.startsWith('/healthz') ? path : '/healthz');
    },

    listProviders<T = unknown>(): Promise<T> {
      return http.fetchJson<T>('/providers');
    },

    syncProject<T = unknown>(projectId: string, body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(`/projects/${encodeURIComponent(projectId)}/syncs`, {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    listAssets(projectId: string, limit = 500): Promise<HydraceptAssetOut[]> {
      return http
        .fetchJson<readonly HydraceptAssetOut[] | HydraceptAssetPage>(
          `/assets?projectId=${encodeURIComponent(projectId)}&limit=${limit}`,
        )
        .then(normalizeAssetList);
    },

    generateAsset<T = unknown>(assetId: string, body: unknown = {}, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(`/assets/${encodeURIComponent(assetId)}/generate`, {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getWorkflow<T = unknown>(workflowId: string): Promise<T> {
      return http.fetchJsonWithRetry<T>(`/workflows/${encodeURIComponent(workflowId)}`);
    },

    getArtifact<T = unknown>(artifactId: string): Promise<T> {
      return http.fetchJson<T>(`/artifacts/${encodeURIComponent(artifactId)}`);
    },

    getArtifactContent(artifactId: string): Promise<Blob> {
      return http.fetchBlob(`/artifacts/${encodeURIComponent(artifactId)}/content`);
    },

    createReview<T = unknown>(body: unknown): Promise<T> {
      return http.fetchJson<T>('/reviews', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    createPromotion<T = unknown>(body: unknown): Promise<T> {
      return http.fetchJson<T>('/promotions', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },

    reportPromotion<T = unknown>(promotionId: string, body: unknown): Promise<T> {
      return http.fetchJson<T>(`/promotions/${encodeURIComponent(promotionId)}/report`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
  };
}

export type HydraceptControlApi = ReturnType<typeof createHydraceptControlApi>;
