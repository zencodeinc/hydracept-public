/** Panel definition and session response shapes (additive /v1 contracts). */

export interface SurfaceActionInputField {
  readonly key: string;
  readonly label: string;
  readonly valueType?: 'string' | 'number' | 'boolean' | 'string[]';
}

export interface PanelDefinitionVersionView {
  readonly id: string;
  readonly definitionId: string;
  readonly version: number;
  readonly capabilityKey?: string | null;
  readonly capabilityVersion?: string | null;
  readonly allowedOrigins: readonly string[];
  readonly actions?: readonly unknown[];
}

export interface PanelDefinitionView {
  readonly id: string;
  readonly organizationId: string;
  readonly key: string;
  readonly displayName: string;
  readonly status: string;
  readonly origin?: 'hydracept' | 'project';
  readonly projectId?: string | null;
  readonly currentVersion?: PanelDefinitionVersionView;
}

/** GET /v1/panel-definitions list envelope. */
export interface PanelDefinitionListResponse {
  readonly definitions: readonly PanelDefinitionView[];
}

export interface PanelSessionCreated {
  readonly sessionId: string;
  readonly accessToken: string;
  readonly expiresAt?: string;
}
