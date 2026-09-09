'use client';

import { useEffect, useState } from 'react';
import type { StageEvent } from '@/lib/types';

/**
 * The Instrument layout's right-hand rail: what the pipeline is doing, live.
 *
 * Eight stages run per turn and until now the UI showed none of them, so a
 * question looked like a four-second hang. This is that work, made visible.
 *
 * The known stages below are a *skeleton*, not a whitelist. `stage_events.py`
 * is deliberately open/closed — a node added by a later phase streams without
 * anyone editing a summariser — so a stage this file has never heard of is
 * appended with a humanised label rather than dropped. The rail must not be
 * the reason a new pipeline stage is invisible.
 */
const KNOWN_STAGES: { stage: string; label: string }[] = [
  { stage: 'schema_linking', label: 'Schema linking' },
  { stage: 'planning', label: 'Planning' },
  { stage: 'candidate_generation', label: 'Candidates' },
  { stage: 'static_validation', label: 'Validation' },
  { stage: 'ambiguity_probing', label: 'Probing' },
  { stage: 'candidate_selection', label: 'Selection' },
  { stage: 'rewrite_and_cost_gate', label: 'Cost gate' },
  { stage: 'guarded_execution', label: 'Execution' },
];

const KNOWN = new Set(KNOWN_STAGES.map((s) => s.stage));

function humanise(stage: string): string {
  return stage.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

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

function Dot({ state }: { state: 'done' | 'running' | 'waiting' | 'failed' | 'paused' }) {
  const colour =
    state === 'done'
      ? 'bg-[var(--ok)]'
      : state === 'failed'
        ? 'bg-[var(--bad)]'
        : state === 'running' || state === 'paused'
          ? 'bg-[var(--brand)]'
          : 'bg-[var(--line)]';
  return (
    <span
      aria-hidden
      className={`mt-[0.3rem] size-[5px] shrink-0 rounded-full ${colour} ${
        state === 'running' ? 'gq-pulse' : ''
      }`}
    />
  );
}

export function StageRail({
  stages,
  running,
  startedAt,
  failed,
}: {
  stages: StageEvent[];
  /** True while a turn is in flight — drives the pulse and the live timer. */
  running: boolean;
  startedAt: number | null;
  failed?: boolean;
}) {
  const elapsed = useElapsed(running ? startedAt : null);
  const byStage = new Map(stages.map((s) => [s.stage, s]));
  const extra = stages.filter((s) => !KNOWN.has(s.stage));
  // The first known stage with nothing reported yet is the one in progress.
  const nextPending = KNOWN_STAGES.find((s) => !byStage.has(s.stage))?.stage;

  const rows = [
    ...KNOWN_STAGES,
    ...extra.map((s) => ({ stage: s.stage, label: humanise(s.stage) })),
  ];

  const finished = !running && stages.length > 0;

  return (
    <aside
      aria-label="Pipeline stages for this turn"
      className="hidden w-[196px] shrink-0 flex-col gap-2.5 border-l border-[var(--line)] bg-[var(--panel-2)] px-4 py-4 lg:flex"
    >
      <p className="font-eyebrow text-[0.6rem] uppercase tracking-wide text-[var(--mute)]">
        This turn
      </p>
      <ol className="flex flex-col gap-1.5">
        {rows.map(({ stage, label }) => {
          const event = byStage.get(stage);
          const state = event
            ? event.status === 'failed'
              ? 'failed'
              : event.status === 'paused'
                ? 'paused'
                : 'done'
            : running && stage === nextPending
              ? 'running'
              : 'waiting';
          return (
            <li key={stage} className="flex gap-2">
              <Dot state={state} />
              <div className="min-w-0 flex-1">
                <p
                  className={`font-mono text-[0.68rem] leading-tight ${
                    state === 'waiting' ? 'text-[var(--mute)] opacity-55' : 'text-[var(--ink)]'
                  }`}
                >
                  {label}
                </p>
                {event?.detail && (
                  <p className="mt-0.5 break-words font-mono text-[0.62rem] leading-tight text-[var(--mute)]">
                    {event.detail}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="font-eyebrow mt-auto pt-2 text-[0.6rem] uppercase tracking-wide text-[var(--mute)]">
        {failed
          ? 'Stopped'
          : running
            ? `Elapsed ${(elapsed / 1000).toFixed(1)}s`
            : finished
              ? `${stages.length} stages completed`
              : 'Idle'}
      </p>
    </aside>
  );
}
