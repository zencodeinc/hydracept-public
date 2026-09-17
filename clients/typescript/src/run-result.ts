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
  /** What this customer was charged. 0 when Hydracept covers the execution. */
  customerChargeUsd: number | null;
  /** `covered` | `charged` | `byok` | `unsettled`. */
  chargeState: string | null;
  /** `managed` | `byok` | `platform`. */
  billingMode: string | null;
  /** Upstream provider price basis the charge was computed from — not a retail price. */
  providerCostUsd: number | null;
  providerCostBasis: 'upstream-price-basis';
  /** Pre-execution upstream provider price basis. */
  estimatedProviderCostUsd: number | null;
  /** Pre-execution managed customer charge (provider basis + Hydracept fee). */
  estimatedCustomerChargeUsd: number | null;
  /** Kept only when a receipt-less job reported a bare actual cost. */
  legacyActualCostUsd?: number | null;
  summary?: string | null;
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

function microsUsd(value: unknown): number | null {
  const micros = asNumber(value);
  return micros == null ? null : micros / 1_000_000;
}

export function pricingFromJob(
  job: Record<string, unknown>,
  receipt: Record<string, unknown> | null | undefined,
): HydraceptRunPricing {
  const source = (receipt || job) as Record<string, unknown>;
  const pricing = (source.pricing as Record<string, unknown> | undefined) || {};
  const charge = (pricing.charge as Record<string, unknown> | undefined) || {};
  const customerCharge = (charge.customerCharge as Record<string, unknown> | undefined) || {};
  const basisActual = (pricing.basisActual as Record<string, unknown> | undefined) || {};
  const basisEstimated = (pricing.basisEstimated as Record<string, unknown> | undefined) || {};
  const estimatedCharge = (pricing.estimatedCharge as Record<string, unknown> | undefined) || {};
  const quote = ((pricing.quote as Record<string, unknown> | undefined)?.customerTotal ||
    {}) as Record<string, unknown>;
  const providerUsage = (pricing.providerUsage as Record<string, unknown> | undefined) || {};
  const reportedCost = (providerUsage.reportedCost as Record<string, unknown> | undefined) || {};

  const owed =
    microsUsd(customerCharge.amountMicros) ?? microsUsd(customerCharge.customerTotalMicros);
  const basis =
    microsUsd(basisActual.amountMicros) ??
    microsUsd((pricing.actualCharge as Record<string, unknown> | undefined)?.amountMicros) ??
    microsUsd(reportedCost.amountMicros);
  const estimatedBasis = microsUsd(basisEstimated.amountMicros);
  const estimated =
    microsUsd(estimatedCharge.amountMicros) ??
    microsUsd(quote.amountMicros) ??
    asNumber(job.estimatedCost);

  const payload: HydraceptRunPricing = {
    customerChargeUsd: owed,
    chargeState: owed == null ? null : owed > 0 ? 'charged' : 'covered',
    billingMode: (pricing.mode as string | undefined) ?? null,
    providerCostUsd: basis,
    providerCostBasis: 'upstream-price-basis',
    estimatedProviderCostUsd: estimatedBasis,
    estimatedCustomerChargeUsd: estimated,
    currency: 'USD',
  };
  if (owed == null && basis == null) {
    const legacy = asNumber(job.actualCost);
    if (legacy != null) payload.legacyActualCostUsd = legacy;
  }
  return payload;
}
