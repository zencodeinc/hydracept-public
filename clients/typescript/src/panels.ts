import type { HydraceptHttp } from './http.js';
import type {
  PanelDefinitionListResponse,
  PanelDefinitionView,
  PanelSessionCreated,
} from './panel-types.js';

/** Panel definition and session helpers for hosted panels and embed integrations. */
export function createHydraceptPanelsApi(http: HydraceptHttp) {
  return {
    createPanelDefinition<T = PanelDefinitionView>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/panel-definitions', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    listPanelDefinitions(projectId?: string): Promise<PanelDefinitionListResponse> {
      const suffix = projectId ? `?projectId=${encodeURIComponent(projectId)}` : '';
      return http.fetchJson<PanelDefinitionListResponse>(`/panel-definitions${suffix}`);
    },

    getPanelDefinition<T = unknown>(definitionId: string): Promise<T> {
      return http.fetchJson<T>(`/panel-definitions/${encodeURIComponent(definitionId)}`);
    },

    patchPanelDefinition<T = unknown>(
      definitionId: string,
      body: unknown,
      init: RequestInit = {},
    ): Promise<T> {
      return http.fetchJson<T>(`/panel-definitions/${encodeURIComponent(definitionId)}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
        ...init,
      });
    },

    createPanelSession(body: unknown, init: RequestInit = {}): Promise<PanelSessionCreated> {
      return http.fetchJson<PanelSessionCreated>('/panel-sessions', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },

    getPanelSession<T = unknown>(sessionId: string): Promise<T> {
      return http.fetchJson<T>(`/panel-sessions/${encodeURIComponent(sessionId)}`);
    },

    revokePanelSession<T = unknown>(sessionId: string, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(`/panel-sessions/${encodeURIComponent(sessionId)}/revoke`, {
        method: 'POST',
        ...init,
      });
    },

    createPanelLaunchCode<T = unknown>(sessionId: string, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>(
        `/panel-sessions/${encodeURIComponent(sessionId)}/launch-codes`,
        {
          method: 'POST',
          ...init,
        },
      );
    },

    getPanelBootstrap<T = unknown>(init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/panel/bootstrap', init);
    },

    exchangePanelLaunchCode<T = unknown>(body: unknown, init: RequestInit = {}): Promise<T> {
      return http.fetchJson<T>('/panel/launch-codes/exchange', {
        method: 'POST',
        body: JSON.stringify(body),
        ...init,
      });
    },
  };
}

export type HydraceptPanelsApi = ReturnType<typeof createHydraceptPanelsApi>;
