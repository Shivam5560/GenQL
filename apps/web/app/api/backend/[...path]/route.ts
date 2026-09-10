import { NextRequest } from 'next/server';

/**
 * A same-origin door to the API, so the browser never talks to the backend host.
 *
 * The backend lives behind a tunnel on a machine with no domain, and its
 * hostname is both rotating and — on at least one real network — unresolvable:
 * an ISP resolver returned NXDOMAIN for `*.trycloudflare.com` subdomains while
 * resolving the apex fine, so the browser could not reach the API at all even
 * though Vercel's servers could. Login kept working (it is proxied here) and
 * every direct call failed, which is a confusing way to find out your DNS is
 * filtered.
 *
 * Routing every call through this handler makes the browser's view of the
 * backend a path on the site it already loaded. That kills three problems at
 * once: the browser no longer resolves the tunnel host, CORS stops applying
 * because it is all one origin, and the tunnel's URL becomes a server-side
 * secret that can rotate without rebuilding the client bundle.
 *
 * The cost is one extra hop through a Vercel function. That is a few tens of
 * milliseconds against a backend that is already ~1s away through the tunnel.
 */

/**
 * Which backend a path belongs to, and where that backend lives.
 *
 * Two services sit behind this door — the API and GoTrue — and the split is
 * decided here rather than inherited from whatever the deployment happens to
 * put in front of them. The tunnelled deployment does have an edge proxy that
 * serves both under one hostname, but a local frontend points straight at two
 * separate ports, and a handler that assumed the edge's layout would work in
 * one of those and not the other.
 *
 * Read per-request rather than at module scope so a rotated tunnel URL takes
 * effect on the next deploy without this file caring how it got here.
 */
function route(path: string[]): { target: string; rest: string[] } {
  if (path[0] === 'gotrue') {
    return {
      target: process.env.GOTRUE_URL ?? 'http://localhost:9999',
      rest: path.slice(1),
    };
  }
  return {
    target:
      process.env.GENQL_API_ORIGIN ??
      process.env.NEXT_PUBLIC_GENQL_API_ORIGIN ??
      'http://localhost:8000',
    rest: path,
  };
}

// Never cache: every route behind this is either authenticated, a mutation, or
// an open event stream, and Next will happily cache a GET that looks static.
export const dynamic = 'force-dynamic';
// Long enough for a pipeline turn to finish streaming. A turn that runs the
// full twelve stages against a cold warehouse has been measured near a minute;
// the stream must not be cut while stages are still arriving.
export const maxDuration = 300;

/**
 * Headers worth passing upstream.
 *
 * An allowlist rather than a copy of everything: `host` would name the Vercel
 * deployment rather than the tunnel and break TLS SNI at the far end, and
 * `accept-encoding` would invite a compressed body that this handler would then
 * have to decode before it could stream it. Everything the API actually reads —
 * the bearer token, the content type, the SSE `Accept` — is here.
 */
const FORWARDED = ['authorization', 'content-type', 'accept', 'accept-language'];

/**
 * Headers worth passing back.
 *
 * `content-length` is deliberately absent: a streamed response has none, and a
 * stale one copied from upstream would truncate the body.
 *
 * `location` is here for one route in particular. GoTrue's `/authorize` answers
 * an OAuth sign-in with a 302 to Google or GitHub, and the browser follows it
 * as a top-level navigation. Dropping the header would turn "Continue with
 * Google" into a blank 302 with nowhere to go.
 */
const RETURNED = ['content-type', 'cache-control', 'x-request-id', 'location'];

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const { target: base, rest } = route(path);
  const target = `${base}/${rest.join('/')}${request.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARDED) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  // Read the body rather than streaming it: every request this app makes is a
  // small JSON document, and a streamed request body would need `duplex: 'half'`
  // plus a runtime that supports it. Responses are the half that must stream.
  const body =
    request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.text();

  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body,
      // The client hanging up must reach the backend: an abandoned turn should
      // stop the pipeline, not leave it running with nobody listening.
      signal: request.signal,
      redirect: 'manual',
    });
  } catch (reason) {
    // The upstream being unreachable is this deployment's most likely failure —
    // a rotated tunnel that nothing has repointed yet. Say so as a gateway
    // error rather than letting it surface as an opaque 500.
    if (request.signal.aborted) return new Response(null, { status: 499 });
    const detail = reason instanceof Error ? reason.message : 'unknown error';
    return Response.json(
      { error: 'BackendUnreachable', detail: `could not reach the API: ${detail}` },
      { status: 502 },
    );
  }

  const out = new Headers();
  for (const name of RETURNED) {
    const value = response.headers.get(name);
    if (value) out.set(name, value);
  }
  // Two hints that keep an event stream flowing rather than sitting in a buffer
  // somewhere between here and the browser. Harmless on a plain JSON response.
  if (out.get('content-type')?.includes('text/event-stream')) {
    out.set('cache-control', 'no-cache, no-transform');
    out.set('x-accel-buffering', 'no');
  }

  // `response.body` passed straight through, never awaited into a string: that
  // is what makes an SSE turn arrive stage by stage instead of all at once when
  // the pipeline finishes.
  return new Response(response.body, { status: response.status, headers: out });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: Context): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function POST(request: NextRequest, { params }: Context): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function PATCH(request: NextRequest, { params }: Context): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function PUT(request: NextRequest, { params }: Context): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function DELETE(request: NextRequest, { params }: Context): Promise<Response> {
  return proxy(request, (await params).path);
}
