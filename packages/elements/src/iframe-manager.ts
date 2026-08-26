import {
  createPanelMessage,
  isKnownPanelIframeMessage,
  isPanelMessage,
  PANEL_PROTOCOL_VERSION,
  type PanelErrorPayload,
  type PanelJobCompletedPayload,
  type PanelJobSubmittedPayload,
  type PanelMessageEnvelope,
  type PanelReadyPayload,
  type PanelResizePayload,
} from './protocol.js';
import { panelEmbedOrigin, panelEmbedUrl, type HydraceptPanelSession } from './panel-session.js';

export const PANEL_IFRAME_SANDBOX = 'allow-scripts allow-same-origin';

const MIN_RESIZE_HEIGHT_PX = 240;
const MAX_RESIZE_HEIGHT_PX = 2400;

export interface PanelIframeManagerOptions {
  session: HydraceptPanelSession;
  iframe: HTMLIFrameElement;
  onReady?: (payload: PanelReadyPayload) => void;
  onError?: (payload: PanelErrorPayload) => void;
  onResize?: (payload: PanelResizePayload) => void;
  onJobSubmitted?: (payload: PanelJobSubmittedPayload) => void;
  onJobCompleted?: (payload: PanelJobCompletedPayload) => void;
}

/** Host-side iframe lifecycle: hello/session handshake and event fan-out. */
export class PanelIframeManager {
  private readonly session: HydraceptPanelSession;
  private readonly iframe: HTMLIFrameElement;
  private readonly embedOrigin: string;
  private readonly onReady?: (payload: PanelReadyPayload) => void;
  private readonly onError?: (payload: PanelErrorPayload) => void;
  private readonly onResize?: (payload: PanelResizePayload) => void;
  private readonly onJobSubmitted?: (payload: PanelJobSubmittedPayload) => void;
  private readonly onJobCompleted?: (payload: PanelJobCompletedPayload) => void;
  private readonly handleMessage: (event: MessageEvent) => void;
  private disposed = false;

  constructor(options: PanelIframeManagerOptions) {
    this.session = options.session;
    this.iframe = options.iframe;
    this.embedOrigin = panelEmbedOrigin(this.session);
    this.onReady = options.onReady;
    this.onError = options.onError;
    this.onResize = options.onResize;
    this.onJobSubmitted = options.onJobSubmitted;
    this.onJobCompleted = options.onJobCompleted;

    this.handleMessage = (event: MessageEvent) => {
      if (this.disposed || event.origin !== this.embedOrigin) {
        return;
      }
      if (event.source !== this.iframe.contentWindow) {
        return;
      }
      if (!isPanelMessage(event.data)) {
        return;
      }
      if (event.data.panelSessionId !== this.session.sessionId) {
        return;
      }
      if (!isKnownPanelIframeMessage(event.data)) {
        return;
      }
      this.dispatchIframeMessage(event.data);
    };

    this.configureIframe();
    window.addEventListener('message', this.handleMessage);
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    window.removeEventListener('message', this.handleMessage);
  }

  sendPrefill(payload: Record<string, unknown>): void {
    this.postToIframe('hydracept.prefill', payload);
  }

  sendTheme(payload: Record<string, unknown>): void {
    this.postToIframe('hydracept.theme', payload);
  }

  private configureIframe(): void {
    this.iframe.src = panelEmbedUrl(this.session);
    this.iframe.setAttribute('sandbox', PANEL_IFRAME_SANDBOX);
    this.iframe.setAttribute('title', 'Hydracept generation panel');
    this.iframe.setAttribute('loading', 'lazy');
    this.iframe.style.border = '0';
    this.iframe.style.width = '100%';
    this.iframe.style.display = 'block';
    this.iframe.style.minHeight = `${MIN_RESIZE_HEIGHT_PX}px`;
  }

  private respondWithSession(): void {
    this.postToIframe('hydracept.session', {
      accessToken: this.session.accessToken,
    });
  }

  private postToIframe(type: PanelMessageEnvelope['type'], payload: Record<string, unknown>): void {
    const target = this.iframe.contentWindow;
    if (!target) {
      return;
    }
    target.postMessage(
      createPanelMessage(type, this.session.sessionId, payload),
      this.embedOrigin,
    );
  }

  private dispatchIframeMessage(message: PanelMessageEnvelope): void {
    switch (message.type) {
      case 'hydracept.embed.hello':
        this.respondWithSession();
        break;
      case 'hydracept.ready':
        this.onReady?.(message.payload as PanelReadyPayload);
        break;
      case 'hydracept.error':
        this.onError?.(message.payload as PanelErrorPayload);
        break;
      case 'hydracept.resize': {
        const resize = message.payload as unknown as PanelResizePayload;
        const height = Math.max(
          MIN_RESIZE_HEIGHT_PX,
          Math.min(MAX_RESIZE_HEIGHT_PX, Math.round(resize.height)),
        );
        this.iframe.style.height = `${height}px`;
        this.onResize?.({ ...resize, height });
        break;
      }
      case 'hydracept.job.submitted':
        this.onJobSubmitted?.(message.payload as PanelJobSubmittedPayload);
        break;
      case 'hydracept.job.completed':
        this.onJobCompleted?.(message.payload as PanelJobCompletedPayload);
        break;
      default:
        break;
    }
  }
}

export { PANEL_PROTOCOL_VERSION };
