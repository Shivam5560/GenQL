'use client';

import type { StreamError } from '@/lib/types';

/**
 * A failed turn, rendered in the thread where the answer would have been.
 *
 * Failures used to collapse into one toast reading "Something went wrong" —
 * which vanished after four seconds, named nothing, and left the transcript
 * looking as though the question had never been asked. The pipeline already
 * reports typed failures (`StaticValidationError`, `CostEstimationError`,
 * `SchemaLinkingError`), so the type is shown as the heading and the server's
 * own message as the body. A person can act on that, or paste it into a bug.
 */

/** What a person can actually do about each kind of failure. */
const GUIDANCE: Record<string, string> = {
  SchemaLinkingError: 'Nothing in this datasource matched the question. Try naming a table or column directly.',
  StaticValidationError: 'Every candidate GenQL wrote was rejected before it could run. Rephrasing usually helps.',
  CostEstimationError: 'The query could not be costed, so it was not run.',
  OptimizationError: 'The query was over budget. Narrow it — a shorter date range, fewer columns.',
  ExecutionError: 'The warehouse refused the query. It may be a permissions problem rather than the SQL.',
  AmbiguityGateError: 'The question could not be disambiguated. Say which table or measure you mean.',
  ThreadLockError: 'Another question is still running on this thread. Wait for it to finish.',
  ConnectionError: 'Check that the GenQL API is running, then try again.',
};

export function TurnError({ error, onRetry }: { error: StreamError; onRetry?: () => void }) {
  const guidance = GUIDANCE[error.error];

  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-md border border-[var(--bad)] bg-[var(--bad-soft)] px-4 py-3"
    >
      <p className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--bad)]">
        {error.error}
      </p>
      <p className="max-w-[64ch] text-sm leading-relaxed text-[var(--ink)]">{error.detail}</p>
      {guidance && <p className="max-w-[64ch] text-sm text-[var(--mute)]">{guidance}</p>}
      {onRetry && (
        <div className="flex gap-2 pt-0.5">
          <button
            type="button"
            onClick={onRetry}
            className="font-eyebrow rounded border border-[var(--bad)] px-2.5 py-1 text-[0.68rem] uppercase tracking-wide text-[var(--bad)]"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
