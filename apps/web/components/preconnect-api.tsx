'use client';

import ReactDOM from 'react-dom';

const API_ORIGIN = process.env.NEXT_PUBLIC_GENQL_API_ORIGIN ?? 'http://localhost:8000';

/**
 * Opens the connection to the API before anything needs it.
 *
 * The measured problem: the first request to the API origin paid a TLS
 * handshake of 1.2s at best and 12-17s at worst, because the deployment
 * fronts the API with a Tailscale Funnel and every fresh connection is
 * negotiated through its ingress. Steady-state requests over an established
 * connection came back in 0.44s, and the same API reached directly over the
 * tailnet answered in 0.13-0.36s — so essentially none of that first-call
 * latency was GenQL's code.
 *
 * This does not fix that; it only moves the handshake off the critical path,
 * so it overlaps rendering the login screen instead of blocking the first
 * fetch after sign-in. The actual fix is an ingress that terminates TLS at an
 * edge and keeps connections warm.
 *
 * `crossOrigin: 'anonymous'` deliberately matches how `lib/api-client.ts`
 * actually fetches — an `Authorization` header, no cookies, so anonymous CORS
 * mode. The browser keys its connection pool on credentials mode, so a
 * mismatch here would warm a connection that the real request cannot reuse,
 * which is worse than not preconnecting at all.
 */
export function PreconnectApi() {
  ReactDOM.preconnect(API_ORIGIN, { crossOrigin: 'anonymous' });
  return null;
}
