import { PanelIframeManager } from './iframe-manager.js';
import type {
  PanelErrorPayload,
  PanelJobCompletedPayload,
  PanelJobSubmittedPayload,
  PanelReadyPayload,
  PanelResizePayload,
} from './protocol.js';
import type { HydraceptPanelSession } from './panel-session.js';

/** Canonical custom element tag for embed host. */
export const HYDRACEPT_PANEL_TAG = 'hydracept-panel';

/** @deprecated Use HYDRACEPT_PANEL_TAG */
export const HYDRACEPT_GENERATE_TAG = 'hydracept-generate';

export class HydraceptPanelElement extends HTMLElement {
  static get observedAttributes(): string[] {
    return [];
  }

  private manager: PanelIframeManager | null = null;
  private iframe: HTMLIFrameElement | null = null;
  private _session: HydraceptPanelSession | null = null;

  connectedCallback(): void {
    if (!this.iframe) {
      this.iframe = document.createElement('iframe');
      this.appendChild(this.iframe);
    }
    this.mount();
  }

  disconnectedCallback(): void {
    this.unmount();
  }

  get session(): HydraceptPanelSession | null {
    return this._session;
  }

  set session(value: HydraceptPanelSession | null) {
    this._session = value;
    this.mount();
  }

  sendPrefill(payload: Record<string, unknown>): void {
    this.manager?.sendPrefill(payload);
  }

  sendTheme(payload: Record<string, unknown>): void {
    this.manager?.sendTheme(payload);
  }

  private mount(): void {
    this.unmount();
    if (!this._session || !this.iframe) {
      return;
    }

    this.manager = new PanelIframeManager({
      session: this._session,
      iframe: this.iframe,
      onReady: (payload) => this.emit('ready', payload),
      onError: (payload) => this.emit('error', payload),
      onResize: (payload) => this.emit('resize', payload),
      onJobSubmitted: (payload) => this.emit('jobSubmitted', payload),
      onJobCompleted: (payload) => this.emit('jobCompleted', payload),
    });
  }

  private unmount(): void {
    this.manager?.dispose();
    this.manager = null;
  }

  private emit(
    name: 'ready' | 'error' | 'resize' | 'jobSubmitted' | 'jobCompleted',
    detail:
      | PanelReadyPayload
      | PanelErrorPayload
      | PanelResizePayload
      | PanelJobSubmittedPayload
      | PanelJobCompletedPayload,
  ): void {
    this.dispatchEvent(
      new CustomEvent(name, {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }
}

/** @deprecated Use HydraceptPanelElement */
export const HydraceptGenerateElement = HydraceptPanelElement;
export type HydraceptGenerateElement = HydraceptPanelElement;

export function registerHydraceptPanel(tagName = HYDRACEPT_PANEL_TAG): void {
  if (typeof customElements === 'undefined') {
    return;
  }
  if (!customElements.get(tagName)) {
    customElements.define(tagName, HydraceptPanelElement);
  }
}

/** @deprecated Use registerHydraceptPanel */
export function registerHydraceptGenerate(tagName = HYDRACEPT_GENERATE_TAG): void {
  if (typeof customElements === 'undefined') {
    return;
  }
  if (!customElements.get(tagName)) {
    customElements.define(tagName, HydraceptPanelElement);
  }
}

export function registerHydraceptPanelElements(): void {
  registerHydraceptPanel();
  registerHydraceptGenerate();
}

if (typeof HTMLElement !== 'undefined' && typeof customElements !== 'undefined') {
  registerHydraceptPanelElements();
}
