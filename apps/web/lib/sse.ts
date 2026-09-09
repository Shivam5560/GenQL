/**
 * A Server-Sent Events reader built on `fetch`, not `EventSource`.
 *
 * `EventSource` cannot send an `Authorization` header, and every GenQL stream
 * is behind a Bearer token. The alternatives were putting an access token in a
 * query string — where it lands in server logs and browser history — or
 * reading the stream ourselves. This is the second one, and it costs about
 * forty lines.
 *
 * The wire format is deliberately handled in full rather than assumed: events
 * are separated by a blank line, `data:` may repeat within one event and joins
 * with newlines, and a frame with no `event:` field is an unnamed `message`.
 */

export interface SseEvent {
  event: string;
  data: string;
}

/** Thrown before the stream opens — a 401, a 404, a dead server. */
export class SseHttpError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`stream failed with ${status}`);
  }
}

function parseFrame(frame: string): SseEvent | null {
  let event = 'message';
  const data: string[] = [];

  // Split on either line ending: a proxy may have rewritten LF to CRLF on
  // the way through, and a trailing \r left on a value corrupts it silently.
  for (const rawLine of frame.split(/\r?\n/)) {
    // Per the spec a leading colon is a comment — servers send them as
    // keep-alives, and treating one as data would corrupt the next JSON parse.
    if (rawLine.startsWith(':')) continue;
    const separator = rawLine.indexOf(':');
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator);
    // One optional space after the colon is part of the framing, not the value.
    const value = separator === -1 ? '' : rawLine.slice(separator + 1).replace(/^ /, '');
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
  }

  if (data.length === 0) return null;
  return { event, data: data.join('\n') };
}

/**
 * Open `url` and yield each event as it arrives.
 *
 * Aborting the signal ends the loop and releases the connection, which is what
 * a component unmounting mid-turn must do — otherwise the pipeline keeps
 * running server-side with nobody listening.
 */
export async function* readEventStream(
  url: string,
  accessToken: string,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${accessToken}`, Accept: 'text/event-stream' },
    signal,
  });

  if (!response.ok || !response.body) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Not JSON — the status is all we have, and it is enough to route on.
    }
    throw new SseHttpError(response.status, body);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;

      // A chunk can carry several events, or half of one. Split on the blank
      // line and keep the remainder — the tail is a partial frame until the
      // next chunk proves otherwise. \r\n\r\n is accepted too: some proxies
      // normalise line endings on the way through.
      let boundary = buffer.search(/\r?\n\r?\n/);
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + buffer.slice(boundary).match(/^\r?\n\r?\n/)![0].length);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
        boundary = buffer.search(/\r?\n\r?\n/);
      }
    }
  } finally {
    // Cancelling propagates upstream and closes the socket. Without it an
    // aborted turn leaves the server writing into a connection nobody reads.
    await reader.cancel().catch(() => {});
  }
}

/** True when a rejection is this stream being deliberately torn down. */
export function isAbort(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === 'AbortError';
}
