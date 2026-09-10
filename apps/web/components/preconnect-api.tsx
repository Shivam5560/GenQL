/**
 * Nothing to preconnect to any more.
 *
 * This used to open a connection to the API's own origin before anything
 * needed it, because the deployment fronted the API with a Tailscale Funnel
 * whose first TLS handshake cost 1.2s at best and 12-19s at worst — so the
 * first call after sign-in paid for an ingress negotiation rather than for
 * anything GenQL computed.
 *
 * `lib/api-client.ts` now calls `/api/backend/*` on this app's own origin,
 * which the browser is by definition already connected to: it just downloaded
 * the page over it. A preconnect to the same origin is a no-op, and one to the
 * backend would warm a connection nothing opens.
 *
 * Kept as an empty component rather than deleted so the layout keeps its shape
 * and the reasoning above stays somewhere a reader will find it — the latency
 * it was fighting was real, and worth not rediscovering.
 */
export function PreconnectApi() {
  return null;
}
