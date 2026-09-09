'use client';

import { useState } from 'react';
import type { TurnRecord } from '@/lib/types';
import { DialectSelect } from './dialect-select';
import { ExecuteButton } from './execute-button';
import { ResultTable } from './result-table';

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
          <button
            className="font-eyebrow rounded border border-[var(--line)] px-2 py-1 text-[0.68rem] uppercase text-[var(--mute)]"
            onClick={() => navigator.clipboard.writeText(turn.validated_sql ?? '')}
          >
            Copy
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap px-4 py-3.5 font-mono text-[0.8rem] leading-relaxed">
        {turn.validated_sql}
      </pre>
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
