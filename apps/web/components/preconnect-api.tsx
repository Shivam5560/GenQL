const API_ORIGIN = process.env.NEXT_PUBLIC_GENQL_API_ORIGIN ?? 'http://localhost:8000';

/**
 * Opens the connection to the API before anything needs it.
 *
 * The measured problem: the first request to the API origin paid a TLS
 * handshake of 1.2s at best and 12-19s at worst, because the deployment
 * fronts the API with a Tailscale Funnel and every fresh connection is
 * negotiated through its ingress. Steady-state requests over an established
 * connection came back in 0.44s, and the same API reached directly over the
 * tailnet answered in 0.13-0.36s — so essentially none of that first-call
 * latency is GenQL's code.
 *
 * This does not fix that; it only moves the handshake off the critical path,
 * so it overlaps rendering the login screen instead of blocking the first
 * fetch after sign-in. The actual fix is an ingress that terminates TLS at an
 * edge and keeps connections warm.
 *
 * A plain `<link>`, which React hoists into <head>, rather than react-dom's
 * `preconnect()`. This Next version's docs
 * (03-api-reference/04-functions/generate-metadata.md) recommend
 * `import ReactDOM from 'react-dom'; ReactDOM.preconnect(...)` for exactly
 * this, and it type-checks — but on react-dom 19.2 the default export
 * carries no `preconnect`, so that form is a silent no-op, and the named
 * import emitted nothing either when served from a production build. Both
 * were checked by grepping the rendered HTML for `rel="preconnect"` and
 * finding none; this element is there.
 *
 * `crossOrigin="anonymous"` deliberately matches how `lib/api-client.ts`
 * actually fetches — an `Authorization` header, no cookies, so anonymous CORS
 * mode. The browser keys its connection pool on credentials mode, so a
 * mismatch here would warm a connection the real request cannot reuse, which
 * is worse than not preconnecting at all.
 */
export function PreconnectApi() {
  return <link rel="preconnect" href={API_ORIGIN} crossOrigin="anonymous" />;
}
