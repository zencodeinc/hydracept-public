export type HydraceptRuntimeEvent = {
  id?: string;
  event: string;
  data: unknown;
};

export type HydraceptClientOptions = {
  /** Hydracept API origin (https://api.hydracept.com or http://localhost:8080). */
  baseUrl: string;
  /** Static bearer token, or omit and supply getToken. */
  token?: string;
  getToken?: () => string;
  /** fetch credentials mode. Prefer 'omit' for browser API calls. */
  credentials?: RequestCredentials;
  /** When true, paths already include /v1 (or proxy strips it). */
  pathsAreV1Relative?: boolean;
  fetchImpl?: typeof fetch;
};

export type HydraceptHttpError = Error & {
  status?: number;
  body?: string;
};

export type HydraceptAssetOut = {
  readonly id: string;
  readonly logicalKey: string;
  readonly [key: string]: unknown;
};

export type HydraceptAssetPage = {
  readonly items?: readonly HydraceptAssetOut[];
};

