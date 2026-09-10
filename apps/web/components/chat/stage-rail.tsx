'use client';

import { useEffect, useState } from 'react';
import type { StageEvent } from '@/lib/types';
import { DecisionCards } from './stage-decision-cards';
import { formatDuration } from './stage-glance';
import { buildDecisions } from './stage-decisions';
import { buildRows } from './stage-rows';
import { StageTimeline } from './stage-timeline';

export { buildRows };

/**
 * The Instrument layout's right-hand rail: how a turn was answered.
 *
 * This is the ONLY place stage detail appears. The transcript used to print the
 * newest stage's summary under the question — so "4 candidates generated" and
 * "2 probes executed" flickered through the conversation and then vanished,
 * mixing the machine's working notes into the thread you came back to read. The
 * rail keeps them; the transcript keeps the answer.
 *
 * It is read in two tiers, because two different questions get asked of it. The
 * decisions on top answer "why does this SQL look like this" — the question you
 * answered, what was assumed on your behalf, which of several drafts won and
 * why. The trail underneath answers "what did it actually do". Twelve equal
 * rows could only ever answer the second, which is why the first used to
 * require opening rows one at a time and reading between them.
 *
 * Both tiers are built from what the backend reports and nothing else. A turn
 * that nobody had to ask about has no decisions section at all, rather than an
 * empty card implying something was decided.
 */

/** Ticks while a turn is in flight so the elapsed readout actually moves. */
function useElapsed(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, [startedAt]);

  return startedAt === null ? 0 : Math.max(now - startedAt, 0);
}

/** What became of the turn, in the fewest words that are still true. */
function verdict(
  stages: StageEvent[],
  running: boolean,
  failed: boolean,
): { text: string; tone: string; aside: string | null } | null {
  if (failed) return { text: 'Stopped', tone: 'bg-[var(--bad)]', aside: null };
  if (running) return { text: 'Working', tone: 'bg-[var(--brand)] gq-pulse', aside: null };
  if (stages.length === 0) return null;

  const facts = (stage: string, label: string) =>
    stages.find((event) => event.stage === stage)?.facts?.find(([key]) => key === label)?.[1];

  if (stages.at(-1)?.status === 'paused') {
    return { text: 'Waiting on your answer', tone: 'bg-[var(--brand)]', aside: null };
  }
  const rows = facts('guarded_execution', 'rows');
  if (rows !== undefined) {
    return {
      text: 'Validated, then run',
      tone: 'bg-[var(--ok)]',
      aside: `${rows} row${rows === '1' ? '' : 's'}`,
    };
  }
  if (facts('rewrite_and_cost_gate', 'verdict') === 'over budget') {
    return { text: 'Held at the cost gate', tone: 'bg-[var(--bad)]', aside: null };
  }
  return { text: 'Validated, not yet run', tone: 'bg-[var(--ok)]', aside: null };
}

export function StageRail({
  stages,
  running,
  startedAt,
  failed,
  /** Which turn's discussion is on screen, for the caption under the header.
      Omitted while the rail is following the in-flight turn. */
  viewingQuestion,
}: {
  stages: StageEvent[];
  /** True while a turn is in flight — drives the pulse and the live timer. */
  running: boolean;
  startedAt: number | null;
  failed?: boolean;
  viewingQuestion?: string | null;
}) {
  const elapsed = useElapsed(running ? startedAt : null);
  const rows = buildRows(stages, running);
  const decisions = buildDecisions(stages);
  const outcome = verdict(stages, running, failed ?? false);

  const ran = stages.filter((stage) => stage.status !== 'skipped').length;
  // Summed from what the stream measured, never from the wall clock: a trail
  // reloaded next week has real per-stage timings and no session to time.
  const measured = stages.reduce<number | null>(
    (total, stage) =>
      stage.duration_ms === null || stage.duration_ms === undefined
        ? total
        : (total ?? 0) + stage.duration_ms,
    null,
  );

  return (
    <aside
      aria-label="Pipeline stages for this turn"
      // `min-h-0` on both this element and the scrolling list below is what lets
      // the list actually scroll inside a fixed-height flex row — without it a
      // flex child ignores `overflow-y-auto` and just grows past the viewport,
      // taking the header and footer with it.
      className="hidden h-full min-h-0 w-[300px] shrink-0 flex-col border-l border-[var(--line)] bg-[var(--panel-2)] lg:flex"
    >
      <div className="shrink-0 border-b border-[var(--line)] px-4 py-4">
        <p className="font-eyebrow text-[0.62rem] uppercase tracking-[0.15em] text-[var(--mute)]">
          How this was answered
        </p>
        {outcome && (
          <p className="mt-2 flex items-center gap-2">
            <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${outcome.tone}`} />
            <span className="text-[0.9rem] font-medium leading-tight text-[var(--ink)]">
              {outcome.text}
            </span>
            {outcome.aside && (
              <span className="ml-auto shrink-0 font-mono text-[0.62rem] tabular-nums text-[var(--mute)]">
                {outcome.aside}
              </span>
            )}
          </p>
        )}
        {viewingQuestion && (
          <p
            className="mt-1.5 line-clamp-2 text-[0.72rem] italic leading-snug text-[var(--mute)]"
            title={viewingQuestion}
          >
            {viewingQuestion}
          </p>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3.5">
        <DecisionCards decisions={decisions} />
        <section aria-label="Full trail" className="flex flex-col">
          <p className="pb-1 font-eyebrow text-[0.58rem] uppercase tracking-[0.16em] text-[var(--mute)] opacity-70">
            Full trail
          </p>
          <StageTimeline
            rows={rows}
            trailKey={viewingQuestion ?? (running ? 'live' : 'latest')}
          />
        </section>
      </div>

      <p className="shrink-0 border-t border-[var(--line)] px-4 py-3 font-mono text-[0.62rem] tabular-nums text-[var(--mute)]">
        {failed
          ? 'Stopped'
          : running
            ? `Elapsed ${(elapsed / 1000).toFixed(1)}s`
            : stages.length > 0
              ? [`${ran} of ${stages.length} stages ran`, formatDuration(measured)]
                  .filter(Boolean)
                  .join(' · ')
              : 'Idle'}
      </p>
    </aside>
  );
}
