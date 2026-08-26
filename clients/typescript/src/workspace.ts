import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createHydraceptHttp } from './http.js';
import { createHydraceptControlApi } from './control.js';
import { createHydraceptPanelsApi } from './panels.js';
import { createHydraceptRuntimeApi } from './runtime.js';
import { createHydraceptJobRunner, type HydraceptJobRunner } from './jobs.js';
import type { HydraceptClient } from './index.js';

export type HydraceptWorkspaceBinding = {
  schemaVersion?: string;
  projectId: string;
  environment?: string;
  apiOrigin?: string;
};

export class HydraceptWorkspace {
  readonly client: HydraceptClient;
  readonly jobs: HydraceptJobRunner;
  readonly root: string;
  readonly binding: HydraceptWorkspaceBinding;

  private constructor(
    root: string,
    binding: HydraceptWorkspaceBinding,
    client: HydraceptClient,
    jobs: HydraceptJobRunner,
  ) {
    this.root = root;
    this.binding = binding;
    this.client = client;
    this.jobs = jobs;
  }

  static open(root?: string): HydraceptWorkspace {
    const projectRoot = resolve(root ?? process.cwd());
    const bindingPath = join(projectRoot, '.hydracept', 'project.json');
    if (!existsSync(bindingPath)) {
      throw new Error('Missing .hydracept/project.json — run python -m hydracept init');
    }
    const binding = JSON.parse(readFileSync(bindingPath, 'utf8')) as HydraceptWorkspaceBinding;
    if (!binding.projectId) {
      throw new Error('project.json is missing projectId');
    }
    const envProject = process.env.HYDRACEPT_PROJECT || process.env.HYDRACEPT_PROJECT_ID;
    if (envProject && envProject !== binding.projectId) {
      throw new Error(
        `HYDRACEPT_PROJECT=${envProject} disagrees with project.json projectId=${binding.projectId}`,
      );
    }
    const secretsPath = join(projectRoot, '.hydracept', 'secrets.json');
    const secrets = existsSync(secretsPath)
      ? (JSON.parse(readFileSync(secretsPath, 'utf8')) as { apiKey?: string; token?: string })
      : {};
    const token = process.env.HYDRACEPT_API_KEY || secrets.apiKey || secrets.token;
    if (!token) {
      throw new Error('No workspace API key in secrets.json');
    }
    const http = createHydraceptHttp({
      baseUrl: binding.apiOrigin || 'https://api.hydracept.com',
      token,
    });
    const client: HydraceptClient = {
      http,
      control: createHydraceptControlApi(http),
      runtime: createHydraceptRuntimeApi(http),
      panels: createHydraceptPanelsApi(http),
    };
    const jobs = createHydraceptJobRunner(client, binding);
    return new HydraceptWorkspace(projectRoot, binding, client, jobs);
  }
}
