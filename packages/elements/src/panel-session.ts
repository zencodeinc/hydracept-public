/** Session credentials supplied by the host backend to mount an embed iframe. */

/** Default public API origin that serves `/embed/panels/{sessionId}`. */
export const DEFAULT_PANEL_EMBED_BASE_URL = 'https://api.hydracept.com';

export interface HydraceptPanelSession {
  /** Panel session id (`ps_*`). */
  sessionId: string;
  /** Short-lived panel bearer token (`hpt_*`). Never put in the iframe URL. */
  accessToken: string;
  /**
   * Origin serving `/embed/panels/{sessionId}` (public API, not Studio app).
   * Example: `https://api.hydracept.com`
   */
  embedBaseUrl: string;
}

export function panelEmbedUrl(session: HydraceptPanelSession): string {
  const base = session.embedBaseUrl.replace(/\/+$/, '');
  return `${base}/embed/panels/${encodeURIComponent(session.sessionId)}`;
}

export function panelEmbedOrigin(session: HydraceptPanelSession): string {
  return new URL(session.embedBaseUrl).origin;
}
