import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createHydraceptHttp } from './http.js';
import { createHydraceptControlApi } from './control.js';
import { createHydraceptPanelsApi } from './panels.js';
import { createHydraceptRuntimeApi } from './runtime.js';
import { createHydraceptJobRunner, type HydraceptJobRunner } from './jobs.js';
import type { HydraceptClient } from './index.js';
import { pricingFromJob } from './run-result.js';

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

  async run(
    capabilityKey: string,
    body: Record<string, unknown>,
    options: {
      wait?: boolean;
      timeoutMs?: number;
      maxCostUsd?: number;
      idempotencyKey?: string;
      out?: string;
    } = {},
  ): Promise<import('./run-result.js').HydraceptRunResult> {
    await this.ensureExecutionProject();
    const { randomUUID } = await import('node:crypto');
    const key = options.idempotencyKey || `run-${randomUUID().replace(/-/g, '')}`;
    let payload: Record<string, unknown> = { ...body };
    if (
      !('input' in payload)
      && !('context' in payload)
      && !('execution' in payload)
      && !('idempotencyKey' in payload)
    ) {
      payload = { input: payload };
    }
    payload.idempotencyKey = key;
    if (options.maxCostUsd != null) {
      const existing = (payload.execution as Record<string, unknown> | undefined) || {};
      const constraints = {
        ...((existing.executionConstraints as Record<string, unknown> | undefined) || {}),
        maxCostUsd: options.maxCostUsd,
      };
      payload.execution = { ...existing, executionConstraints: constraints };
    }
    if (options.wait === false) {
      const submitted = (await this.client.runtime.submitCapabilityJob(
        capabilityKey,
        payload,
      )) as Record<string, unknown>;
      const jobId = String(submitted.jobId || submitted.id || '');
      if (!jobId) throw new Error('No jobId in submit response');
      return {
        schemaVersion: 'hydracept.run-result.v1',
        capability: capabilityKey,
        jobId,
        executionId: jobId,
        status: 'running',
        artifacts: [],
        pricing: pricingFromJob(submitted, null),
        receipt: null,
        idempotencyKey: key,
      };
    }
    const result = await this.jobs.run(capabilityKey, payload, {
      downloadDir: options.out,
      outputRoot: options.out ? undefined : this.root,
      pollMs: options.timeoutMs ?? Number.POSITIVE_INFINITY,
    });
    return {
      schemaVersion: 'hydracept.run-result.v1',
      capability: capabilityKey,
      jobId: result.jobId,
      executionId: result.jobId,
      status: result.status,
      artifacts: result.downloads.map((localPath) => ({
        artifactId: '',
        mediaType: 'application/octet-stream',
        localPath,
        verified: true,
      })),
      pricing: pricingFromJob(result.job, result.receipt),
      receipt: result.receipt,
      idempotencyKey: key,
    };
  }

  private async ensureExecutionProject(): Promise<void> {
    let token = '';
    try {
      const diag = (await this.client.http.fetchJson('/diagnostics/session')) as {
        projectId?: string;
        tokenProjectId?: string;
        principalProjectId?: string;
      };
      token = String(diag.tokenProjectId || diag.principalProjectId || diag.projectId || '').trim();
    } catch {
      throw new Error(
        'Cannot resolve an execution project — checkout and credential must match. Run python -m hydracept doctor --fix',
      );
    }
    let home = '';
    try {
      const session = (await this.client.http.fetchJson('/session/context')) as {
        project?: { id?: string };
      };
      home = String(session.project?.id || '').trim();
    } catch {
      home = '';
    }
    const checkout = this.binding.projectId;
    if (token && home && token === home && token !== checkout) {
      token = '';
    }
    if (!token) {
      throw new Error(
        'Cannot resolve an execution project — checkout and credential must match. Run python -m hydracept doctor --fix',
      );
    }
    if (token !== checkout) {
      throw new Error(
        `Checkout project ${checkout} disagrees with credential project ${token}. Hydracept will not manufacture an execution project.`,
      );
    }
  }
}
