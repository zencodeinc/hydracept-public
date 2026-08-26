import { createHydraceptControlApi } from './control.js';
import { createHydraceptHttp, type HydraceptHttp } from './http.js';
import { createHydraceptPanelsApi } from './panels.js';
import { createHydraceptRuntimeApi } from './runtime.js';
import type { HydraceptClientOptions } from './types.js';

export type { HydraceptHttpError, HydraceptClientOptions, HydraceptRuntimeEvent } from './types.js';
export { createHydraceptHttp } from './http.js';
export type { HydraceptHttp } from './http.js';
export { createHydraceptControlApi } from './control.js';
export type { HydraceptControlApi } from './control.js';
export { createHydraceptRuntimeApi } from './runtime.js';
export type { HydraceptRuntimeApi } from './runtime.js';
export { createHydraceptPanelsApi } from './panels.js';
export type { HydraceptPanelsApi } from './panels.js';
export type {
  PanelDefinitionListResponse,
  PanelDefinitionView,
  PanelDefinitionVersionView,
  PanelSessionCreated,
  SurfaceActionInputField,
} from './panel-types.js';
export { iterInvocationEvents } from './sse.js';
export type {
  HydraceptAssetOut,
  HydraceptAssetPage,
} from './types.js';

export type HydraceptClient = {
  http: HydraceptHttp;
  control: ReturnType<typeof createHydraceptControlApi>;
  runtime: ReturnType<typeof createHydraceptRuntimeApi>;
  panels: ReturnType<typeof createHydraceptPanelsApi>;
};

export function createHydraceptClient(options: HydraceptClientOptions): HydraceptClient {
  const http = createHydraceptHttp(options);
  return {
    http,
    control: createHydraceptControlApi(http),
    runtime: createHydraceptRuntimeApi(http),
    panels: createHydraceptPanelsApi(http),
  };
}

export { HydraceptWorkspace } from './workspace.js';
export { createHydraceptJobRunner } from './jobs.js';
export type { HydraceptJobRunner, HydraceptJobRunResult } from './jobs.js';
