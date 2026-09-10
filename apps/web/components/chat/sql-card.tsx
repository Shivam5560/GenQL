'use client';

import { useEffect, useState } from 'react';
import type { TurnRecord } from '@/lib/types';
import { DialectSelect } from './dialect-select';
import { ExecuteButton } from './execute-button';
import { ReferencedObjects } from './referenced-objects';
import { ResultTable } from './result-table';

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
      className={`font-eyebrow rounded border px-2 py-1 text-[0.68rem] uppercase ${
        copied
          ? 'border-[var(--ok)] text-[var(--ok)]'
          : 'border-[var(--line)] text-[var(--mute)]'
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
}: {
  turn: TurnRecord;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
}) {
  const [dialect, setDialect] = useState('Postgres');

  if (!turn.validated_sql) return null;

  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)]">
      <div className="flex items-center justify-between gap-2.5 border-b border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2">
        <span className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">SQL</span>
        <div className="flex items-center gap-2">
          <DialectSelect value={dialect} onChange={setDialect} />
          <CopyButton text={turn.validated_sql} />
        </div>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap px-4 py-3.5 font-mono text-[0.8rem] leading-relaxed">
        {turn.validated_sql}
      </pre>
      {turn.referenced_objects && turn.referenced_objects.length > 0 && (
        <ReferencedObjects objects={turn.referenced_objects} />
      )}
      {revealed ? (
        <ResultTable turn={turn} accessToken={accessToken} threadId={threadId} />
      ) : (
        onReveal && (
          <div className="flex items-center justify-end border-t border-[var(--line)] px-3.5 py-2.5">
            <ExecuteButton onReveal={onReveal} />
          </div>
        )
      )}
    </div>
  );
}
