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

Activate at https://hydracept.com/start · Docs: https://docs.hydracept.com

A Zencode product · © Zencode Consulting Inc.
