# @hydracept/sdk

TypeScript client for the Hydracept public API — **one API for AI workloads in games**.

Free for individual developers. BYOK. No inference markup.

```bash
npm install @hydracept/sdk
```

## Copy-paste job

```ts
import { createHydraceptClient } from '@hydracept/sdk';

const client = createHydraceptClient({
  baseUrl: 'https://api.hydracept.com',
  getToken: () => process.env.HYDRACEPT_API_KEY ?? '',
});

const job = await client.runtime.submitCapabilityJob('image.generate.v1', {
  context: {
    productId: 'my-game',
    projectId: process.env.HYDRACEPT_PROJECT,
    environment: 'development',
  },
  input: { prompt: 'cute slime icon, flat game art' },
  execution: { executionPreference: 'automatic' },
  idempotencyKey: 'demo-1',
});

const status = await client.runtime.getJob(job.jobId);
const receipt = await client.runtime.getJobReceipt(job.jobId);
```

### Pinned Execution (RIP)

```ts
const result = await client.runtime.createPinnedInference({
  pin: { provider: 'openai', model: 'gpt-5.6-sol', api: 'responses' },
  isolation: 'stateless',
  input: 'ping',
});
const pinned = await client.runtime.getPinnedReceipt(result.receipt.receipt_id);
const lock = await client.runtime.getLockfile(pinned.receiptId);
await client.runtime.verifyLockfile(lock);
```

### Panel sessions (embed host)

```ts
import { createHydraceptClient } from '@hydracept/sdk';

const client = createHydraceptClient({
  baseUrl: 'https://api.hydracept.com',
  getToken: () => process.env.HYDRACEPT_API_KEY ?? '',
});

const { definitions } = await client.panels.listPanelDefinitions();
const created = await client.panels.createPanelSession({
  panelDefinitionId: definitions[0]!.id,
  projectId: process.env.HYDRACEPT_PROJECT,
  environment: 'development',
  allowedOrigins: ['http://localhost:5173'],
});

// Pass sessionId + accessToken to @hydracept/elements PanelIframeManager
console.log(created.sessionId, created.accessToken);
```

Pair with [`@hydracept/elements`](https://www.npmjs.com/package/@hydracept/elements) to mount the hosted iframe — do not copy protocol code.

Activate at https://hydracept.com/start · Docs: https://docs.hydracept.com

A Zencode company · © Zencode Consulting Inc.
