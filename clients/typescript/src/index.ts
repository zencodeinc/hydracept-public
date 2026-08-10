import { createHydraceptControlApi } from './control.js';
import { createHydraceptHttp, type HydraceptHttp } from './http.js';
import { createHydraceptRuntimeApi } from './runtime.js';
import type { HydraceptClientOptions } from './types.js';

export type { HydraceptHttpError, HydraceptClientOptions, HydraceptRuntimeEvent } from './types.js';
export { createHydraceptHttp } from './http.js';
export type { HydraceptHttp } from './http.js';
export { createHydraceptControlApi } from './control.js';
export type { HydraceptControlApi } from './control.js';
export { createHydraceptRuntimeApi } from './runtime.js';
export type { HydraceptRuntimeApi } from './runtime.js';
export { iterInvocationEvents } from './sse.js';
export type {
  HydraceptAssetOut,
  HydraceptAssetPage,
} from './types.js';

export type HydraceptClient = {
  http: HydraceptHttp;
  control: ReturnType<typeof createHydraceptControlApi>;
  runtime: ReturnType<typeof createHydraceptRuntimeApi>;
};

export function createHydraceptClient(options: HydraceptClientOptions): HydraceptClient {
  const http = createHydraceptHttp(options);
  return {
    http,
    control: createHydraceptControlApi(http),
    runtime: createHydraceptRuntimeApi(http),
  };
}
