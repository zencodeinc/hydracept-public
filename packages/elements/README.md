# @hydracept/elements

Public embed host SDK for Hydracept panel iframes.

Mount a Hydracept-owned generation surface in your app without copying protocol code or Hydracept UI internals.

```bash
npm install @hydracept/elements
```

## Quick start

```ts
import {
  DEFAULT_PANEL_EMBED_BASE_URL,
  PanelIframeManager,
  type HydraceptPanelSession,
} from '@hydracept/elements';

const session: HydraceptPanelSession = {
  sessionId: 'ps_…',
  accessToken: 'hpt_…', // memory only — never URL, storage, or DOM
  embedBaseUrl: DEFAULT_PANEL_EMBED_BASE_URL, // https://api.hydracept.com
};

const iframe = document.createElement('iframe');
document.getElementById('panel')!.appendChild(iframe);

const manager = new PanelIframeManager({
  session,
  iframe,
  onReady: () => console.log('panel ready'),
  onJobCompleted: ({ jobId, artifacts }) => {
    console.log('job done', jobId, artifacts.map((a) => a.artifactId));
  },
});

manager.sendPrefill({ inputs: { prompt: 'cute slime icon' } });
```

## Web component

```html
<script type="module">
  import '@hydracept/elements/register';
</script>

<hydracept-panel id="panel"></hydracept-panel>
<script type="module">
  const el = document.getElementById('panel');
  el.session = {
    sessionId: 'ps_…',
    accessToken: 'hpt_…',
    embedBaseUrl: 'https://api.hydracept.com',
  };
  el.addEventListener('jobCompleted', (e) => console.log(e.detail));
</script>
```

`<hydracept-generate>` remains registered as a deprecated alias.

## Protocol (`hydracept.panel.v1`)

| Direction | Message | Purpose |
|---|---|---|
| iframe → host | `hydracept.embed.hello` | Start handshake |
| host → iframe | `hydracept.session` | Deliver `hpt_*` token |
| iframe → host | `hydracept.ready` | Generation UI mounted |
| iframe → host | `hydracept.resize` | Host adjusts iframe height |
| iframe → host | `hydracept.job.submitted` | Job started (`jobId`) |
| iframe → host | `hydracept.job.completed` | Job finished (`artifactId` authoritative) |
| iframe → host | `hydracept.error` | e.g. `session_expired` |
| host → iframe | `hydracept.prefill` / `hydracept.theme` | Seed panel inputs |

Hosts **ignore unknown message types** for forward-compatible evolution.

Create panel sessions with [`@hydracept/sdk`](../clients/typescript) — never ship API keys in production client bundles.

Docs: https://docs.hydracept.com · Activate: https://hydracept.com/start

A Zencode company · © Zencode Consulting Inc.
