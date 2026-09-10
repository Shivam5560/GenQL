'use client';

import { useEffect, useState } from 'react';
import type { StageEvent } from '@/lib/types';
import { buildRows } from './stage-rows';
import { StageTimeline } from './stage-timeline';

export { buildRows };

/**
 * The Instrument layout's right-hand rail: how a turn was answered.
 *
 * This is the ONLY place stage detail appears. The transcript used to print
 * the newest stage's summary under the question — so "4 candidates generated"
 * and "2 probes executed" flickered through the conversation and then
 * vanished, mixing the machine's working notes into the thread you came back
 * to read. The rail keeps them; the transcript keeps the answer.
 *
 * It is no longer only a live readout. The backend records a turn's stage
 * trail with the turn, so this panel answers the question a reviewer actually
 * has — why does this SQL look like this — on a statement written last week as
 * readily as on one that arrived a second ago. `StageTimeline` draws it; this
 * file is the frame around it: whose discussion, and how the turn ended.
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
  const finished = !running && stages.length > 0;
  // Reported, not completed. Some of those stages short-circuited, and calling
  // twelve reports "twelve stages completed" claims work the pipeline
  // deliberately did not do.
  const ran = stages.filter((stage) => stage.status !== 'skipped').length;

  return (
    <aside
      aria-label="Pipeline stages for this turn"
      // `min-h-0` on both this element and the scrolling list below is what
      // lets the list actually scroll inside a fixed-height flex row — without
      // it a flex child ignores `overflow-y-auto` and just grows past the
      // viewport, taking the header and footer with it.
      className="hidden h-full min-h-0 w-[240px] shrink-0 flex-col gap-2.5 border-l border-[var(--line)] bg-[var(--panel-2)] px-4 py-5 lg:flex"
    >
      <div className="shrink-0">
        <p className="font-eyebrow text-[0.66rem] uppercase tracking-[0.14em] text-[var(--mute)]">
          How this was answered
        </p>
        {viewingQuestion && (
          <p
            className="mt-1 truncate text-[0.68rem] italic text-[var(--mute)]"
            title={viewingQuestion}
          >
            {viewingQuestion}
          </p>
        )}
      </div>
      <StageTimeline rows={rows} trailKey={viewingQuestion ?? (running ? 'live' : 'latest')} />
      <p className="mt-auto shrink-0 pt-2 text-[0.72rem] text-[var(--mute)]">
        {failed
          ? 'Stopped'
          : running
            ? `Elapsed ${(elapsed / 1000).toFixed(1)}s`
            : finished
              ? `${ran} of ${stages.length} stages ran`
              : 'Idle'}
      </p>
    </aside>
  );
}
