import { describe, expect, it } from 'vitest';
import { readEventStream } from '@/lib/sse';

/** Serves `chunks` as a streaming response body, one chunk per read. */
function stubFetch(chunks: string[], init: { ok?: boolean; status?: number } = {}) {
  const encoder = new TextEncoder();
  return (): Promise<Response> => {
    if (init.ok === false) {
      return Promise.resolve({
        ok: false,
        status: init.status ?? 500,
        body: null,
        json: () => Promise.reject(new Error('not json')),
      } as unknown as Response);
    }
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
    return Promise.resolve({ ok: true, status: 200, body: stream } as unknown as Response);
  };
}

async function collect(chunks: string[]) {
  const original = globalThis.fetch;
  globalThis.fetch = stubFetch(chunks) as typeof fetch;
  try {
    const events = [];
    for await (const event of readEventStream('/stream', 'token')) events.push(event);
    return events;
  } finally {
    globalThis.fetch = original;
  }
}

describe('readEventStream', () => {
  it('parses named events and their data', async () => {
    const events = await collect(['event: stage\ndata: {"stage":"planning"}\n\n']);

    expect(events).toEqual([{ event: 'stage', data: '{"stage":"planning"}' }]);
  });

  it('reassembles an event split across two network chunks', async () => {
    // The realistic failure this guards: a chunk boundary lands mid-JSON, and
    // a naive parser hands half a document to JSON.parse.
    const events = await collect(['event: stage\ndata: {"sta', 'ge":"planning"}\n\n']);

    expect(events).toEqual([{ event: 'stage', data: '{"stage":"planning"}' }]);
  });

  it('delivers several events arriving in one chunk', async () => {
    const events = await collect([
      'event: stage\ndata: 1\n\nevent: stage\ndata: 2\n\nevent: result\ndata: 3\n\n',
    ]);

    expect(events.map((e) => e.event)).toEqual(['stage', 'stage', 'result']);
    expect(events.map((e) => e.data)).toEqual(['1', '2', '3']);
  });

  it('joins repeated data fields with newlines, per the SSE spec', async () => {
    const events = await collect(['event: log\ndata: first\ndata: second\n\n']);

    expect(events[0].data).toBe('first\nsecond');
  });

  it('ignores keep-alive comments rather than treating them as data', async () => {
    const events = await collect([': ping\n\n', 'event: result\ndata: done\n\n']);

    expect(events).toEqual([{ event: 'result', data: 'done' }]);
  });

  it('accepts CRLF framing from a proxy that rewrote the line endings', async () => {
    const events = await collect(['event: stage\r\ndata: ok\r\n\r\n']);

    expect(events).toEqual([{ event: 'stage', data: 'ok' }]);
  });

  it('names an unnamed event "message", as the spec requires', async () => {
    const events = await collect(['data: bare\n\n']);

    expect(events[0].event).toBe('message');
  });

  it('throws with the status when the stream is refused before it opens', async () => {
    const original = globalThis.fetch;
    globalThis.fetch = stubFetch([], { ok: false, status: 401 }) as typeof fetch;
    try {
      const iterate = async () => {
        for await (const _ of readEventStream('/stream', 'token')) void _;
      };
      await expect(iterate()).rejects.toMatchObject({ status: 401 });
    } finally {
      globalThis.fetch = original;
    }
  });
});
