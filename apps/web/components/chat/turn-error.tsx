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
  SchemaLinkingError:
    'Nothing in this datasource matched the question. Try naming a table or column directly.',
  StaticValidationError:
    'Every candidate GenQL wrote was rejected before it could run. Rephrasing usually helps.',
  CostEstimationError: 'The query could not be costed, so it was not run.',
  OptimizationError:
    'The query was over budget. Narrow it — a shorter date range, fewer columns.',
  AmbiguityGateError:
    'The question could not be disambiguated. Say which table or measure you mean.',
  ThreadLockError: 'Another question is still running on this thread. Wait for it to finish.',
  ConnectionError: 'Check that the GenQL API is running, then try again.',
  Stopped: '',
};

/**
 * An ExecutionError is whatever the warehouse said, which is a wide range of
 * unrelated problems. The old blanket line — "it may be a permissions problem
 * rather than the SQL" — was wrong for most of them and actively misleading
 * for the one that prompted this: a date/time overflow from casting a
 * surrogate key, where the SQL was exactly the problem and permissions had
 * nothing to do with it.
 *
 * Matched against the driver's own words rather than a parsed error code:
 * `psycopg` puts its SQLSTATE class name in the exception type it renders into
 * `detail` (`DatetimeFieldOverflow`, `UndefinedColumn`), and that string is the
 * most specific thing the stream carries.
 */
const EXECUTION_GUIDANCE: { match: RegExp; guidance: string }[] = [
  {
    match: /DatetimeFieldOverflow|date\/time field value out of range/i,
    guidance:
      'A value was read as a date that is not one — most often a surrogate key like ' +
      '`ss_sold_date_sk`, which is a row id in a date dimension rather than a date. ' +
      'Ask again mentioning the date column you mean, or the dimension table to join.',
  },
  {
    match: /UndefinedColumn|column .* does not exist/i,
    guidance:
      'The statement named a column this warehouse does not have. If it is a real column, ' +
      'the catalog may be stale — re-run ingestion from the datasources page.',
  },
  {
    match: /UndefinedTable|relation .* does not exist/i,
    guidance:
      'The statement named a table this warehouse does not have, or one outside the schemas ' +
      'this datasource was allowed to survey.',
  },
  {
    match: /InsufficientPrivilege|permission denied/i,
    guidance:
      'The read-only role GenQL connects as cannot read that object. Grant it SELECT, or ' +
      'exclude the schema from this datasource.',
  },
  {
    match: /QueryCanceled|statement timeout|canceling statement/i,
    guidance:
      'The warehouse cut the query off at the statement timeout. Narrow it — a shorter date ' +
      'range, fewer joins — and ask again.',
  },
  {
    match: /DivisionByZero|division by zero/i,
    guidance: 'A ratio was computed over a group with no denominator. Narrowing the question ' +
      'usually removes the empty group.',
  },
  {
    match: /OperationalError|could not connect|connection/i,
    guidance:
      'GenQL could not reach the warehouse. Check the host, port and network on the ' +
      'datasources page.',
  },
];

function guidanceFor(error: StreamError): string | undefined {
  if (error.error === 'ExecutionError') {
    return (
      EXECUTION_GUIDANCE.find(({ match }) => match.test(error.detail))?.guidance ??
      // Nothing recognised: say what is actually known, which is that the SQL
      // was valid enough to run and the warehouse refused it anyway.
      'The warehouse ran the statement and refused it. The message above is its own.'
    );
  }
  return GUIDANCE[error.error] || undefined;
}

export function TurnError({ error, onRetry }: { error: StreamError; onRetry?: () => void }) {
  const guidance = guidanceFor(error);

  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-md border border-[var(--bad)] bg-[var(--bad-soft)] px-4 py-3"
    >
      <p className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--bad)]">
        {error.error}
      </p>
      <p className="max-w-[64ch] break-words text-sm leading-relaxed text-[var(--ink)]">
        {error.detail}
      </p>
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
