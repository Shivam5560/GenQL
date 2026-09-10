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
  divided = true,
  resumes = false,
}: {
  turn: PendingTurnState;
  onRetry: () => void;
  /** Abandon a turn that is taking too long. */
  onStop?: () => void;
  /** False for the opening turn, which needs no rule above it. */
  divided?: boolean;
  /** True when this turn answers the previous turn's clarifying question. */
  resumes?: boolean;
}) {
  return (
    <article
      className={`flex flex-col gap-4 ${
        divided && !resumes ? 'border-t border-[var(--line)] pt-8' : ''
      }`}
    >
      {/* Set exactly as the finished turn will be, so nothing moves when the
          answer lands underneath. */}
      {resumes ? (
        <p className="max-w-[62ch] text-[0.95rem]">
          <span className="text-[var(--mute)]">Answered</span> {turn.question}
        </p>
      ) : (
        <h2 className="max-w-[34ch] font-serif text-[1.55rem] font-normal leading-[1.25] tracking-[-0.01em]">
          {turn.question}
        </h2>
      )}
      {turn.error ? (
        <TurnError error={turn.error} onRetry={onRetry} />
      ) : (
        <div className="flex items-center gap-2.5" aria-live="polite">
          <span aria-hidden className="gq-pulse size-[5px] shrink-0 rounded-full bg-[var(--brand)]" />
          {/* A count, not a fraction: the pipeline branches — an unclear
              question pauses early, a decisive critique skips probing — so
              there is no honest denominator to put after it. */}
          <p className="text-[0.86rem] text-[var(--mute)]">
            {turn.stages.length === 0
              ? 'Working…'
              : `Working: ${turn.stages.length} ${
                  turn.stages.length === 1 ? 'stage' : 'stages'
                } done`}
          </p>
          {onStop && (
            <button
              type="button"
              onClick={onStop}
              className="rounded border border-[var(--line)] px-2.5 py-1 text-[0.72rem] font-medium text-[var(--mute)]"
            >
              Stop
            </button>
          )}
        </div>
      )}
    </article>
  );
}
