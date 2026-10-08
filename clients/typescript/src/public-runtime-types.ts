/** Narrow public runtime shapes used in README samples and strict type-checking. */

export type HydraceptCapabilityJobSubmitResponse = {
  jobId: string;
  id?: string;
};

export type HydraceptJobStatusResponse = Record<string, unknown>;

export type HydraceptJobReceiptResponse = Record<string, unknown>;

export type HydraceptPinnedInferenceResponse = {
  receipt: {
    receipt_id: string;
  };
};

export type HydraceptPinnedReceiptResponse = {
  receiptId: string;
};
