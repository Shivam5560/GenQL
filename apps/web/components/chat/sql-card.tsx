'use client';

import { useEffect, useMemo, useState } from 'react';
import type { TurnRecord } from '@/lib/types';
import { formatSql } from '@/lib/sql-format';
import { DialectSelect } from './dialect-select';
import { ExecuteButton } from './execute-button';
import { ReferencedObjects } from './referenced-objects';
import { ResultTable } from './result-table';
import { SqlHighlight } from './sql-highlight';

/**
 * Copy, and say so.
 *
 * A copy button that does nothing visible is a button people press twice, then
 * paste to check. Two seconds of "Copied" is the whole feature.
 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(id);
  }, [copied]);

  return (
    <button
      type="button"
      className={`rounded border px-2.5 py-1 font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] ${
        copied ? 'border-[var(--ok)] text-[var(--ok)]' : 'border-[var(--line)] text-[var(--mute)]'
      }`}
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => setCopied(true));
      }}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export function SqlCard({
  turn,
  revealed,
  onReveal,
  accessToken,
  threadId,
  hasDiscussion = false,
  discussionActive = false,
  onOpenDiscussion,
}: {
  turn: TurnRecord;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
  /** True when this turn's pipeline trail was captured this session. */
  hasDiscussion?: boolean;
  /** True when the right rail is already showing this turn's trail. */
  discussionActive?: boolean;
  onOpenDiscussion?: () => void;
}) {
  const [dialect, setDialect] = useState('Postgres');
  const sql = turn.validated_sql;
  // The pipeline emits one long line. Formatting only moves whitespace — see
  // `lib/sql-format` — so what is displayed is still exactly what ran, and
  // what Copy hands over is the readable version rather than the wire one.
  const formatted = useMemo(() => (sql ? formatSql(sql) : ''), [sql]);

  if (!sql) return null;

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--panel)]">
      <div className="flex items-center justify-between gap-2.5 border-b border-[var(--line)] bg-[var(--panel-2)] px-4 py-2">
        <div className="flex items-baseline gap-2.5">
          <span className="font-eyebrow text-[0.68rem] uppercase tracking-[0.14em] text-[var(--mute)]">
            Generated SQL
          </span>
          {/* The pipeline parsed and cost-checked this statement before it
              reached the browser. Saying so here is the difference between
              reading a suggestion and reading a query. */}
          <span className="font-eyebrow text-[0.68rem] uppercase tracking-[0.1em] text-[var(--ok)]">
            ● Validated
          </span>
        </div>
        <div className="flex items-center gap-2">
          {hasDiscussion && onOpenDiscussion && (
            <button
              type="button"
              onClick={onOpenDiscussion}
              aria-pressed={discussionActive}
              // The right rail already carries the discussion — this is a
              // pointer to it, not a second copy of it, so pressing it never
              // does more than change which turn the rail is following.
              className={`rounded border px-2.5 py-1 font-eyebrow text-[0.62rem] uppercase tracking-[0.1em] ${
                discussionActive
                  ? 'border-[var(--brand)] text-[var(--brand)]'
                  : 'border-[var(--line)] text-[var(--mute)]'
              }`}
            >
              Discussion
            </button>
          )}
          <DialectSelect value={dialect} onChange={setDialect} />
          <CopyButton text={formatted} />
        </div>
      </div>
      <pre className="overflow-x-auto px-4 py-3.5 text-[0.8rem] leading-[1.65]">
        <SqlHighlight sql={formatted} />
      </pre>
      {turn.referenced_objects && turn.referenced_objects.length > 0 && (
        <ReferencedObjects objects={turn.referenced_objects} />
      )}
      {revealed ? (
        <ResultTable turn={turn} accessToken={accessToken} threadId={threadId} />
      ) : (
        onReveal && (
          <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] px-4 py-2.5">
            <span className="text-[0.72rem] text-[var(--mute)]">
              Nothing has run yet. This reads your warehouse when you run it.
            </span>
            <ExecuteButton onReveal={onReveal} />
          </div>
        )
      )}
    </div>
  );
}
