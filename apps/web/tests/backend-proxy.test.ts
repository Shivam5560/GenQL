import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST } from '@/app/api/backend/[...path]/route';

/**
 * The proxy that makes the backend same-origin.
 *
 * Two properties matter more than the rest and are easy to break silently: a
 * response body must pass through unbuffered, or a streamed turn arrives all at
 * once when the pipeline finishes rather than stage by stage; and `gotrue/*`
 * must reach GoTrue rather than the API, or OAuth and the API disagree about
 * which service owns `/authorize`.
 */
const params = (...path: string[]) => ({ params: Promise.resolve({ path }) });

function req(url: string, init?: RequestInit): NextRequest {
  return new NextRequest(new Request(url, init));
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  process.env.GENQL_API_ORIGIN = 'https://api.example';
  process.env.GOTRUE_URL = 'https://auth.example';
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.GENQL_API_ORIGIN;
  delete process.env.GOTRUE_URL;
});

describe('backend proxy', () => {
  it('sends API paths to the API, preserving the query string', async () => {
    fetchMock.mockResolvedValue(new Response('[]', { status: 200 }));

    await GET(req('http://app.test/api/backend/v1/threads?limit=5'), params('v1', 'threads'));

    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example/v1/threads?limit=5');
  });

  it('sends gotrue paths to GoTrue, with the prefix consumed', async () => {
    // The prefix is this app's routing, not part of GoTrue's own API — it must
    // not survive into the upstream path or every auth call 404s.
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));

    await GET(req('http://app.test/api/backend/gotrue/health'), params('gotrue', 'health'));

    expect(fetchMock.mock.calls[0][0]).toBe('https://auth.example/health');
  });

  it('forwards the bearer token and drops the host header', async () => {
    // `host` would name this deployment rather than the backend, breaking TLS
    // SNI at the far end.
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));

    await GET(
      req('http://app.test/api/backend/v1/profile', {
        headers: { authorization: 'Bearer t-1', host: 'app.test' },
      }),
      params('v1', 'profile'),
    );

    const sent = fetchMock.mock.calls[0][1].headers as Headers;
    expect(sent.get('authorization')).toBe('Bearer t-1');
    expect(sent.get('host')).toBeNull();
  });

  it('passes a body through on a write', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));

    await POST(
      req('http://app.test/api/backend/v1/queries', {
        method: 'POST',
        body: JSON.stringify({ question: 'how many stores?' }),
        headers: { 'content-type': 'application/json' },
      }),
      params('v1', 'queries'),
    );

    expect(fetchMock.mock.calls[0][1].body).toBe('{"question":"how many stores?"}');
  });

  it('streams an event stream instead of buffering it', async () => {
    // The property that makes a live turn feel live. If this handler ever
    // awaits the body into a string, every stage lands at once at the end.
    const encoder = new TextEncoder();
    let push!: (chunk: string) => void;
    let close!: () => void;
    const upstream = new ReadableStream<Uint8Array>({
      start(controller) {
        push = (chunk) => controller.enqueue(encoder.encode(chunk));
        close = () => controller.close();
      },
    });
    fetchMock.mockResolvedValue(
      new Response(upstream, { status: 200, headers: { 'content-type': 'text/event-stream' } }),
    );

    const response = await GET(
      req('http://app.test/api/backend/v1/queries/stream?question=hi'),
      params('v1', 'queries', 'stream'),
    );
    const reader = response.body!.getReader();

    // The first frame must be readable while the stream is still open — that is
    // what "not buffered" means, and it cannot be asserted after the fact.
    push('event: stage\ndata: {"stage":"planning"}\n\n');
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toContain('"stage":"planning"');

    close();
    expect(response.headers.get('cache-control')).toContain('no-transform');
  });

  it('passes a redirect back so OAuth can complete', async () => {
    fetchMock.mockResolvedValue(
      new Response(null, { status: 302, headers: { location: 'https://accounts.google.com/o' } }),
    );

    const response = await GET(
      req('http://app.test/api/backend/gotrue/authorize?provider=google'),
      params('gotrue', 'authorize'),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe('https://accounts.google.com/o');
  });

  it('reports an unreachable backend as a gateway error, not a crash', async () => {
    // The likeliest failure of this deployment: a rotated tunnel URL that
    // nothing has repointed yet. It should read as "the backend is not there",
    // not as an opaque 500 from the frontend.
    fetchMock.mockRejectedValue(new TypeError('fetch failed'));

    const response = await GET(req('http://app.test/api/backend/v1/threads'), params('v1', 'threads'));

    expect(response.status).toBe(502);
    expect((await response.json()).error).toBe('BackendUnreachable');
  });
});
