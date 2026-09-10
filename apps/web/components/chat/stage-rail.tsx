'use client';

import { useEffect, useState } from 'react';
import type { StageEvent } from '@/lib/types';

/**
 * The Instrument layout's right-hand rail: what the pipeline is doing, live.
 *
 * This is the ONLY place stage detail appears. The transcript used to print
 * the newest stage's summary under the question — so "4 candidates generated"
 * and "2 probes executed" flickered through the conversation and then
 * vanished, mixing the machine's working notes into the thread you came back
 * to read. The rail keeps them; the transcript keeps the answer.
 *
 * Stages are listed in the order they actually happened. The previous version
 * rendered a fixed skeleton and appended anything unrecognised at the bottom,
 * which put a stage that ran third at the end of the list and made the rail
 * read as though it had run last. The skeleton is now only a source of *names
 * not yet reached* — every stage that has reported sits in arrival order,
 * ahead of whatever is still pending.
 */
const KNOWN_STAGES: { stage: string; label: string }[] = [
  { stage: 'intent_classification', label: 'Intent' },
  { stage: 'domain_scoping', label: 'Domain scoping' },
  { stage: 'schema_linking', label: 'Schema linking' },
  { stage: 'ambiguity_gate', label: 'Ambiguity gate' },
  { stage: 'planning', label: 'Planning' },
  { stage: 'candidate_generation', label: 'Candidates' },
  { stage: 'static_validation', label: 'Validation' },
  { stage: 'critique', label: 'Critique' },
  { stage: 'ambiguity_probing', label: 'Probing' },
  { stage: 'candidate_selection', label: 'Selection' },
  { stage: 'rewrite_and_cost_gate', label: 'Cost gate' },
  { stage: 'guarded_execution', label: 'Execution' },
];

const LABELS = new Map(KNOWN_STAGES.map((s) => [s.stage, s.label]));

function humanise(stage: string): string {
  return LABELS.get(stage) ?? stage.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

/**
 * Keep serialized structures out of a reading surface.
 *
 * Most stages report a short phrase — "10 objects linked", "4 candidates".
 * The ambiguity gate reports its whole payload, which reaches the browser as
 * a Python dict repr: `{'question': '…', 'suggested_answer': '…', 'options':
 * (…)}`. Six lines of quoted keys in a 212px rail, restating a question that
 * is already on screen in full. The stage still lists — that it ran is the
 * useful part — it just does so without the blob.
 */
function isProse(detail: string): boolean {
  const trimmed = detail.trim();
  return !/^[[{(]/.test(trimmed) && !/'\s*:\s*/.test(trimmed);
}

type RowState = 'done' | 'running' | 'waiting' | 'failed' | 'paused';

interface Row {
  key: string;
  label: string;
  state: RowState;
  detail: string | null;
}

/**
 * What happened, in the order it happened, then what has not happened yet.
 *
 * Reported stages come first and keep their arrival order — that is the whole
 * point. The remaining skeleton names follow as `waiting`, minus any already
 * reported, so the rail still shows where the turn is going without claiming
 * a stage ran at a position it did not.
 */
export function buildRows(stages: StageEvent[], running: boolean): Row[] {
  const seen = new Set<string>();
  const rows: Row[] = [];

  for (const event of stages) {
    // A stage can report twice — the gate runs once per clarification round.
    // The later report wins its original position rather than adding a row.
    const existing = rows.find((row) => row.key === event.stage);
    const state: RowState =
      event.status === 'failed' ? 'failed' : event.status === 'paused' ? 'paused' : 'done';
    const detail = event.detail && isProse(event.detail) ? event.detail : null;
    if (existing) {
      existing.state = state;
      existing.detail = detail;
      continue;
    }
    seen.add(event.stage);
    rows.push({ key: event.stage, label: humanise(event.stage), state, detail });
  }

  const pending = KNOWN_STAGES.filter((s) => !seen.has(s.stage));
  // Only the first unreported stage is "running", and only while the turn is
  // in flight — the rest are genuinely waiting. This is a guess about order
  // (the pipeline branches), which is why it is never applied to a stage that
  // has already reported something real.
  pending.forEach(({ stage, label }, index) => {
    rows.push({
      key: stage,
      label,
      state: running && index === 0 ? 'running' : 'waiting',
      detail: null,
    });
  });

  return rows;
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

function Dot({ state }: { state: RowState }) {
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
  const rows = buildRows(stages, running);
  const finished = !running && stages.length > 0;

  return (
    <aside
      aria-label="Pipeline stages for this turn"
      className="hidden w-[212px] shrink-0 flex-col gap-3 border-l border-[var(--line)] bg-[var(--panel-2)] px-4 py-5 lg:flex"
    >
      <p className="text-[0.78rem] font-semibold">How this was answered</p>
      <ol className="flex flex-col gap-2 overflow-y-auto">
        {rows.map((row) => (
          <li key={row.key} className="flex gap-2">
            <Dot state={row.state} />
            <div className="min-w-0 flex-1">
              <p
                className={`text-[0.76rem] leading-tight ${
                  row.state === 'waiting' ? 'text-[var(--mute)] opacity-55' : 'text-[var(--ink)]'
                }`}
              >
                {row.label}
              </p>
              {row.detail && (
                <p className="mt-0.5 break-words font-mono text-[0.68rem] leading-tight text-[var(--mute)]">
                  {row.detail}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-auto pt-2 text-[0.72rem] text-[var(--mute)]">
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
