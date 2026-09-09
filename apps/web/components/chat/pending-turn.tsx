'use client';

import { TurnError } from './turn-error';
import type { PendingTurn as PendingTurnState } from '@/lib/types';

/**
 * The question, on screen at 0ms.
 *
 * The old composer blocked on `POST /v1/queries` and only rendered the
 * question once the whole answer came back — four to five seconds during
 * which the screen was unchanged and the typed text still sat in the input.
 * The bubble now appears the instant Send is pressed, and this is what sits
 * under it while the pipeline runs.
 *
 * The last stage's own summary is the status line, so the wait reads as work
 * being done rather than as a spinner: "4 candidates generated", "2 probes
 * executed". A failure replaces it in place — the question stays where it is,
 * because the thing a person wants after a failure is their question back.
 */
export function PendingTurn({ turn, onRetry }: { turn: PendingTurnState; onRetry: () => void }) {
  const latest = turn.stages[turn.stages.length - 1];

  return (
    <div className="flex flex-col gap-2.5">
      <div className="max-w-[70%] self-end rounded-lg rounded-br-sm bg-[var(--ink)] px-4 py-2.5 text-sm text-[var(--bg)]">
        {turn.question}
      </div>
      {turn.error ? (
        <TurnError error={turn.error} onRetry={onRetry} />
      ) : (
        <div className="flex items-center gap-2.5" aria-live="polite">
          <span aria-hidden className="gq-pulse size-[5px] shrink-0 rounded-full bg-[var(--brand)]" />
          <p className="font-mono text-[0.78rem] text-[var(--mute)]">
            {latest?.detail ?? latest?.stage.replace(/_/g, ' ') ?? 'Working…'}
          </p>
        </div>
      )}
    </div>
  );
}
