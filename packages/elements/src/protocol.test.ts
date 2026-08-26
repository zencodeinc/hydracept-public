import { describe, expect, it } from 'vitest';
import {
  PANEL_PROTOCOL_VERSION,
  createPanelMessage,
  isKnownPanelIframeMessage,
  isPanelMessage,
} from '../src/protocol.js';

describe('hydracept.panel.v1 protocol', () => {
  it('validates known panel envelopes', () => {
    const hello = createPanelMessage('hydracept.embed.hello', 'ps_test', {
      protocolVersion: PANEL_PROTOCOL_VERSION,
    });
    expect(isPanelMessage(hello)).toBe(true);
    expect(isKnownPanelIframeMessage(hello)).toBe(true);
  });

  it('rejects malformed envelopes', () => {
    expect(isPanelMessage(null)).toBe(false);
    expect(isPanelMessage({ protocol: 'other', type: 'x', panelSessionId: 'ps', payload: {} })).toBe(
      false,
    );
  });

  it('ignores unknown iframe message types', () => {
    const future = createPanelMessage('hydracept.future.event' as never, 'ps_test', {});
    expect(isPanelMessage(future)).toBe(true);
    expect(isKnownPanelIframeMessage(future)).toBe(false);
  });

  it('includes job events in known iframe types', () => {
    const completed = createPanelMessage('hydracept.job.completed', 'ps_test', {
      jobId: 'job_1',
      artifacts: [{ artifactId: 'art_1' }],
    });
    expect(isKnownPanelIframeMessage(completed)).toBe(true);
  });
});
