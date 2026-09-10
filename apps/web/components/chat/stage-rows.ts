import type { StageEvent } from '@/lib/types';

/**
 * The row model behind the discussion timeline: what happened, in order.
 *
 * Kept apart from the components that draw it because it is the part with
 * rules — arrival order, one row per stage, only ever one `running` — and
 * those rules are worth testing without a DOM.
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
 * (…)}`. Six lines of quoted keys in a 240px rail, restating a question that
 * is already on screen in full. The stage still lists — that it ran is the
 * useful part — it just does so without the blob.
 */
function isProse(detail: string): boolean {
  const trimmed = detail.trim();
  return !/^[[{(]/.test(trimmed) && !/'\s*:\s*/.test(trimmed);
}

export type RowState = 'done' | 'running' | 'waiting' | 'failed' | 'paused';

export interface Row {
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

/**
 * Which stage is expanded when the rail first draws a trail.
 *
 * The last stage that actually said something. Live, that is the newest thing
 * the pipeline has reported, and it moves down the line as the turn runs — the
 * stage marked `running` is by construction one that has not reported yet, so
 * opening *it* would open an empty panel. On a finished or reloaded trail it
 * is the stage that produced the SQL on screen, which is the reason anyone
 * opens this panel at all.
 *
 * Null when no stage has reported prose: nothing is expanded, and the rail is
 * a list of labels rather than a list of labels with a gap under one of them.
 */
export function defaultOpenKey(rows: Row[]): string | null {
  return rows.filter((row) => row.detail !== null).at(-1)?.key ?? null;
}
