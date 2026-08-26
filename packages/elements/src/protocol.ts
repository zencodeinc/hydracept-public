/** hydracept.panel.v1 postMessage envelope shared by host and embed shell. */

export const PANEL_PROTOCOL_VERSION = 'hydracept.panel.v1' as const;

export type PanelProtocolVersion = typeof PANEL_PROTOCOL_VERSION;

/** Iframe → host (handshake initiator) */
export type PanelEmbedHelloMessageType = 'hydracept.embed.hello';

/** Host → iframe */
export type PanelHostMessageType =
  | 'hydracept.session'
  | 'hydracept.prefill'
  | 'hydracept.theme';

/** Iframe → host */
export type PanelIframeMessageType =
  | PanelEmbedHelloMessageType
  | 'hydracept.ready'
  | 'hydracept.error'
  | 'hydracept.resize'
  | 'hydracept.job.submitted'
  | 'hydracept.job.completed';

export type PanelMessageType = PanelHostMessageType | PanelIframeMessageType;

export interface PanelMessageEnvelope<TPayload extends Record<string, unknown> = Record<string, unknown>> {
  protocol: PanelProtocolVersion;
  type: PanelMessageType;
  panelSessionId: string;
  payload: TPayload;
}

export interface PanelEmbedHelloPayload {
  protocolVersion: PanelProtocolVersion;
  [key: string]: unknown;
}

export interface PanelSessionPayload {
  accessToken: string;
  [key: string]: unknown;
}

export interface PanelReadyPayload {
  capability?: string;
  [key: string]: unknown;
}

export type PanelErrorCategory =
  | 'session_expired'
  | 'budget_exceeded'
  | 'provider_unavailable'
  | 'generation_failed'
  | 'network_error'
  | 'panel_policy_violation'
  | string;

export interface PanelErrorPayload {
  category?: PanelErrorCategory;
  message?: string;
  [key: string]: unknown;
}

export interface PanelResizePayload {
  height: number;
  width?: number;
}

export interface PanelPrefillPayload {
  inputs?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PanelThemePayload {
  theme?: 'light' | 'dark' | 'system';
  [key: string]: unknown;
}

export interface PanelJobArtifactPayload {
  artifactId: string;
  previewUrl?: string;
}

export interface PanelJobSubmittedPayload {
  jobId: string;
  [key: string]: unknown;
}

export interface PanelJobCompletedPayload {
  jobId: string;
  artifacts: PanelJobArtifactPayload[];
  [key: string]: unknown;
}

export function isPanelMessage(data: unknown): data is PanelMessageEnvelope {
  if (!data || typeof data !== 'object') {
    return false;
  }
  const candidate = data as Partial<PanelMessageEnvelope>;
  return (
    candidate.protocol === PANEL_PROTOCOL_VERSION &&
    typeof candidate.type === 'string' &&
    typeof candidate.panelSessionId === 'string' &&
    typeof candidate.payload === 'object' &&
    candidate.payload !== null
  );
}

export function isKnownPanelIframeMessage(message: PanelMessageEnvelope): boolean {
  switch (message.type) {
    case 'hydracept.embed.hello':
    case 'hydracept.ready':
    case 'hydracept.error':
    case 'hydracept.resize':
    case 'hydracept.job.submitted':
    case 'hydracept.job.completed':
      return true;
    default:
      return false;
  }
}

export function createPanelMessage<TPayload extends Record<string, unknown>>(
  type: PanelMessageType,
  panelSessionId: string,
  payload: TPayload,
): PanelMessageEnvelope<TPayload> {
  return {
    protocol: PANEL_PROTOCOL_VERSION,
    type,
    panelSessionId,
    payload,
  };
}
