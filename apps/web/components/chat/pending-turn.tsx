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
 * What sits under it is deliberately almost nothing. This used to print the
 * newest stage's own summary — "4 candidates generated", "2 probes executed" —
 * which put the machine's working notes in the middle of the conversation,
 * changing every second and leaving nothing behind. Those belong in the rail,
 * which keeps them and orders them; the transcript keeps the question and the
 * answer. A failure still replaces this in place, because the thing a person
 * wants after a failure is their question back.
 */
export function PendingTurn({
  turn,
  onRetry,
  onStop,
}: {
  turn: PendingTurnState;
  onRetry: () => void;
  /** Abandon a turn that is taking too long. */
  onStop?: () => void;
}) {
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
          {/* A count, not a fraction: the pipeline branches — an unclear
              question pauses early, a decisive critique skips probing — so
              there is no honest denominator to put after it. */}
          <p className="text-[0.82rem] text-[var(--mute)]">
            {turn.stages.length === 0
              ? 'Working…'
              : `Working — ${turn.stages.length} ${
                  turn.stages.length === 1 ? 'stage' : 'stages'
                } done`}
          </p>
          {onStop && (
            <button
              type="button"
              onClick={onStop}
              className="font-eyebrow rounded border border-[var(--line)] px-2 py-0.5 text-[0.62rem] uppercase tracking-wide text-[var(--mute)]"
            >
              Stop
            </button>
          )}
        </div>
      )}
    </div>
  );
}
