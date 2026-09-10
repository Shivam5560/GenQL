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
  ExecutionError:
    'The warehouse ran the statement and refused it. The message above is its own.',
  CostEstimationError:
    'Postgres refused to plan the statement, so it was never run. The message above is its own.',
  OptimizationError:
    'The query was over budget. Narrow it — a shorter date range, fewer columns.',
  AmbiguityGateError:
    'The question could not be disambiguated. Say which table or measure you mean.',
  ThreadLockError: 'Another question is still running on this thread. Wait for it to finish.',
  ConnectionError: 'Check that the GenQL API is running, then try again.',
  Stopped: '',
};

/**
 * Two of the failure types are just "whatever Postgres said", which is a wide
 * range of unrelated problems: ExecutionError wraps the warehouse refusing the
 * statement, CostEstimationError wraps it refusing the EXPLAIN of the same
 * statement. Both carry a psycopg error inside `detail`, and the same table
 * reads both.
 *
 * The old blanket lines were "it may be a permissions problem rather than the
 * SQL" and "the query could not be costed, so it was not run" — the first
 * wrong for most cases and actively misleading for the date overflow that
 * prompted it, the second true but saying nothing a person can act on.
 *
 * Matched against the driver's own words rather than a parsed error code:
 * `psycopg` puts its SQLSTATE class name in the exception type it renders into
 * `detail` (`DatetimeFieldOverflow`, `UndefinedParameter`), and that string is
 * the most specific thing the stream carries.
 */
const DRIVER_GUIDANCE: { match: RegExp; guidance: string }[] = [
  {
    match: /UndefinedParameter|there is no parameter/i,
    guidance:
      'The statement was written with a placeholder for a value that was never ' +
      'decided. Ask again naming the value you want — the income bands, the ' +
      'category, the date range — so there is nothing left to fill in.',
  },
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

/** The two types whose detail is a driver message rather than GenQL's own. */
const DRIVER_ERRORS = new Set(['ExecutionError', 'CostEstimationError']);

function guidanceFor(error: StreamError): string | undefined {
  if (DRIVER_ERRORS.has(error.error)) {
    const matched = DRIVER_GUIDANCE.find(({ match }) => match.test(error.detail))?.guidance;
    if (matched) return matched;
  }
  return GUIDANCE[error.error] || undefined;
}

/**
 * Past this many characters, the driver's message is folded away.
 *
 * A psycopg error carries the SQLSTATE name, the offending line, a caret
 * pointing into it, the whole statement it was raised for, and a docs URL —
 * fifteen lines that dwarfed the answer above them and buried the one sentence
 * saying what to do about it. Short messages (`over budget`, `thread is
 * locked`) stay visible, because folding a sentence costs a click and saves
 * nothing.
 */
const FOLD_OVER = 180;

export function TurnError({ error, onRetry }: { error: StreamError; onRetry?: () => void }) {
  const guidance = guidanceFor(error);
  const fold = error.detail.length > FOLD_OVER;

  return (
    <div
      role="alert"
      className="flex max-w-[68ch] flex-col gap-2 rounded-md border border-[var(--bad)] bg-[var(--bad-soft)] px-4 py-3"
    >
      <p className="text-[0.78rem] font-semibold text-[var(--bad)]">
        {/* `StaticValidationError` reads as shouting in caps; the spaced-out
            words are the same information without the volume. */}
        {error.error.replace(/([a-z])([A-Z])/g, '$1 $2')}
      </p>
      {/* The actionable line leads. It used to sit underneath the wall of
          driver output, which is the wrong way round: what to do next is the
          part a person is looking for. */}
      {guidance && <p className="text-sm leading-relaxed text-[var(--ink)]">{guidance}</p>}
      {fold ? (
        <details className="group">
          <summary className="cursor-pointer list-none text-[0.74rem] text-[var(--mute)] marker:content-['']">
            <span className="group-open:hidden">Show technical detail ›</span>
            <span className="hidden group-open:inline">Hide technical detail ⌄</span>
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.7rem] leading-snug text-[var(--mute)]">
            {error.detail}
          </pre>
        </details>
      ) : (
        <p className="break-words text-sm leading-relaxed text-[var(--ink)]">{error.detail}</p>
      )}
      {onRetry && (
        <div className="flex gap-2 pt-0.5">
          <button
            type="button"
            onClick={onRetry}
            className="rounded border border-[var(--bad)] px-2.5 py-1 text-[0.74rem] font-medium text-[var(--bad)]"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
