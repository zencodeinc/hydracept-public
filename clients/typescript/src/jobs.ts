import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { HydraceptClient } from './index.js';

export type HydraceptJobBinding = {
  projectId: string;
  environment?: string;
};

export type HydraceptJobRunResult = {
  jobId: string;
  status: string;
  job: Record<string, unknown>;
  receipt: Record<string, unknown> | null;
  downloads: string[];
  nextAction: string;
};

function nextActionForJob(job: Record<string, unknown>): string {
  const status = String(job.status || '').toLowerCase();
  const artifacts = job.artifacts;
  const hasArtifacts = Array.isArray(artifacts) && artifacts.length > 0;
  if (['queued', 'running', 'awaiting_approval', 'canceling'].includes(status)) return 'poll';
  if (status === 'succeeded') return hasArtifacts ? 'download' : 'receipt';
  return 'done';
}

export type HydraceptJobRunner = {
  run(
    capabilityKey: string,
    body: Record<string, unknown>,
    options?: { downloadDir?: string; outputRoot?: string; pollMs?: number },
  ): Promise<HydraceptJobRunResult>;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const MEDIA_EXTENSIONS: Record<string, string> = {
  'audio/ogg': '.ogg',
  'application/ogg': '.ogg',
  'audio/wav': '.wav',
  'audio/mpeg': '.mp3',
  'image/png': '.png',
  'image/jpeg': '.jpg',
  'image/webp': '.webp',
  'model/gltf-binary': '.glb',
  'video/mp4': '.mp4',
  'application/json': '.json',
};

export function normalizeSha256Digest(value: string | undefined | null): string {
  let raw = String(value || '').trim().toLowerCase();
  if (raw.startsWith('sha256:')) raw = raw.slice(7);
  return raw;
}

function filenameForDownload(item: Record<string, unknown>, artifactId: string): string {
  const media = String(item.mediaType || item.mimeType || '')
    .split(';')[0]
    .trim()
    .toLowerCase();
  let name = String(item.filename || item.label || artifactId || 'artifact')
    .replace(/\\/g, '/')
    .split('/')
    .pop() || 'artifact';
  const ext = MEDIA_EXTENSIONS[media];
  if (ext && !name.toLowerCase().endsWith(ext)) name = `${name}${ext}`;
  return name;
}

function omitStaleQuoteIds(body: Record<string, unknown>): Record<string, unknown> {
  const execution = body.execution;
  if (!execution || typeof execution !== 'object') return body;
  const cleaned = { ...(execution as Record<string, unknown>) };
  delete cleaned.quoteId;
  delete cleaned.estimateId;
  return { ...body, execution: cleaned };
}

export function createHydraceptJobRunner(
  client: HydraceptClient,
  binding: HydraceptJobBinding,
): HydraceptJobRunner {
  return {
    async run(capabilityKey, body, options = {}) {
      const payload = omitStaleQuoteIds({
        ...body,
        context: {
          productId: binding.projectId,
          projectId: binding.projectId,
          environment: binding.environment || 'development',
          ...((body.context as Record<string, unknown> | undefined) ?? {}),
        },
      });
      const submitted = (await client.runtime.submitCapabilityJob(capabilityKey, payload)) as {
        jobId?: string;
        id?: string;
        status?: string;
      };
      const jobId = String(submitted.jobId || submitted.id || '');
      if (!jobId) throw new Error('No jobId in submit response');
      const dest =
        options.downloadDir ||
        (options.outputRoot ? join(options.outputRoot, '.hydracept', 'output', jobId) : undefined);
      const pollMs = options.pollMs ?? 120_000;
      const deadline = Number.isFinite(pollMs) ? Date.now() + pollMs : Number.POSITIVE_INFINITY;
      let job: Record<string, unknown> = submitted as Record<string, unknown>;
      let status = String(submitted.status || 'queued');
      while (true) {
        job = (await client.runtime.getJob(jobId)) as Record<string, unknown>;
        status = String(job.status || 'unknown');
        if (['succeeded', 'failed', 'canceled', 'cancelled'].includes(status)) break;
        if (Date.now() >= deadline) break;
        await sleep(2000);
      }
      let receipt: Record<string, unknown> | null = null;
      if (status === 'succeeded') {
        receipt = (await client.runtime.getJobReceipt(jobId)) as Record<string, unknown>;
      }
      const downloads: string[] = [];
      if (dest && status === 'succeeded' && receipt) {
        const artifacts = (receipt.artifacts as Array<Record<string, unknown>>) || [];
        for (const item of artifacts) {
          const artifactId = String(item.artifactId || item.id || '');
          if (!artifactId) continue;
          const buffer = await client.http.fetchBytes(
            `/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}`,
          );
          const bytes = new Uint8Array(buffer);
          const nested =
            item.digest && typeof item.digest === 'object'
              ? (item.digest as Record<string, unknown>)
              : {};
          const expected = normalizeSha256Digest(
            String(item.sha256 || nested.sha256 || ''),
          );
          const actual = createHash('sha256').update(bytes).digest('hex');
          if (expected && expected !== actual) {
            throw new Error(`SHA-256 mismatch for ${artifactId}`);
          }
          const filename = filenameForDownload(item, artifactId);
          const target = join(dest, filename);
          mkdirSync(dirname(target), { recursive: true });
          writeFileSync(target, bytes);
          downloads.push(target);
        }
      }
      return { jobId, status, job, receipt, downloads, nextAction: nextActionForJob(job) };
    },
  };
}
