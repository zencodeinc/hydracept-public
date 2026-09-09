export type HydraceptRunArtifact = {
  artifactId: string;
  mediaType: string;
  sha256?: string | null;
  byteLength?: number | null;
  remoteRef?: string | null;
  localPath?: string | null;
  verified: boolean;
};

export type HydraceptRunPricing = {
  estimatedCost: number | null;
  actualCost: number | null;
  currency: string;
};

/** hydracept.run-result.v1 — semantic contract shared with Python/CLI/MCP. */
export type HydraceptRunResult = {
  schemaVersion: 'hydracept.run-result.v1';
  capability: string;
  jobId: string | null;
  executionId: string | null;
  status: string;
  output?: unknown;
  typedOutput?: unknown;
  artifacts: HydraceptRunArtifact[];
  pricing: HydraceptRunPricing;
  receipt: Record<string, unknown> | null;
  idempotencyKey: string | null;
  error?: Record<string, unknown> | null;
  diagnostics?: Record<string, unknown> | null;
};

export type HydraceptRunOptions = {
  wait?: boolean;
  timeoutMs?: number;
  maxCostUsd?: number;
  idempotencyKey?: string;
  out?: string;
};

function asNumber(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function pricingFromJob(
  job: Record<string, unknown>,
  receipt: Record<string, unknown> | null | undefined,
): HydraceptRunPricing {
  let estimated = asNumber(job.estimatedCost);
  let actual = asNumber(job.actualCost);
  const status = String(job.status || '').toLowerCase();
  if (receipt) {
    const pricing = (receipt.pricing as Record<string, unknown> | undefined) || {};
    const charge = ((pricing.charge as Record<string, unknown> | undefined)?.customerCharge ||
      {}) as Record<string, unknown>;
    const quote = ((pricing.quote as Record<string, unknown> | undefined)?.customerTotal ||
      {}) as Record<string, unknown>;
    if (estimated == null) {
      const micros = asNumber(quote.amountMicros);
      if (micros != null) estimated = micros / 1_000_000;
    }
    const sealed = asNumber(charge.amountMicros);
    if (sealed != null) actual = sealed / 1_000_000;
    else if (status !== 'succeeded') actual = null;
  } else if (status !== 'succeeded' && status !== 'failed') {
    actual = null;
  }
  return { estimatedCost: estimated, actualCost: actual, currency: 'USD' };
}
