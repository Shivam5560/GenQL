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

// Labelled but deliberately absent from the skeleton above. The interrupt node
// only runs on a turn the gate actually paused, so listing it as `waiting`
// would promise a question to every turn that never gets asked one.
const EXTRA_LABELS: [string, string][] = [['ambiguity_interrupt', 'Your answer']];

const LABELS = new Map([
  ...KNOWN_STAGES.map((s): [string, string] => [s.stage, s.label]),
  ...EXTRA_LABELS,
]);

function humanise(stage: string): string {
  return LABELS.get(stage) ?? stage.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

/**
 * The five things a turn does, in the order it does them.
 *
 * A phase is a reading aid, not a reordering: rows stay in arrival order and a
 * heading is drawn wherever the phase changes. That keeps the guarantee the
 * flat list was built for — a stage that ran second is never drawn last — while
 * giving twelve rows a shape. A pipeline that loops back to the gate genuinely
 * re-enters `settle`, and drawing that heading twice is the truth about it.
 */
export type PhaseKey = 'read' | 'settle' | 'draft' | 'prove' | 'run' | 'other';

const PHASE_LABELS: Record<PhaseKey, string> = {
  read: 'Read the question',
  settle: 'Settle the ambiguity',
  draft: 'Draft the SQL',
  prove: 'Prove it',
  run: 'Run it',
  other: 'Also reported',
};

const STAGE_PHASES = new Map<string, PhaseKey>([
  ['intent_classification', 'read'],
  ['domain_scoping', 'read'],
  ['schema_linking', 'read'],
  ['ambiguity_gate', 'settle'],
  ['ambiguity_interrupt', 'settle'],
  ['planning', 'draft'],
  ['candidate_generation', 'draft'],
  ['static_validation', 'prove'],
  ['critique', 'prove'],
  ['ambiguity_probing', 'prove'],
  ['candidate_selection', 'prove'],
  ['rewrite_and_cost_gate', 'prove'],
  ['guarded_execution', 'run'],
]);

export function phaseLabel(phase: PhaseKey): string {
  return PHASE_LABELS[phase];
}

/**
 * Keep serialized structures out of a reading surface.
 *
 * The ambiguity gate used to report its whole payload, which reached the
 * browser as a Python dict repr: `{'question': '…', 'suggested_answer': '…',
 * 'options': (…)}`. Six lines of quoted keys in a 240px rail, restating a
 * question already on screen in full.
 *
 * The backend now reads that mapping by key and sends prose plus facts, so
 * nothing new arrives in this shape. This stays as a guard over history: rows
 * written before that fix are still in the store and still say `{'question':
 * …}`, and they should read as a stage that listed rather than as a blob.
 */
function isProse(detail: string): boolean {
  const trimmed = detail.trim();
  return !/^[[{(]/.test(trimmed) && !/'\s*:\s*/.test(trimmed);
}

export type RowState = 'done' | 'running' | 'waiting' | 'failed' | 'paused' | 'skipped';

export interface Row {
  key: string;
  label: string;
  state: RowState;
  detail: string | null;
  phase: PhaseKey;
  /** The stage's decision as label/value pairs. Empty for a waiting stage, and
      for any turn recorded before the backend sent them. */
  facts: [string, string][];
  /** Measured by the stream that drained the graph. Null for the same two
      reasons, and never invented here — an unmeasured stage shows no time
      rather than a plausible one. */
  durationMs: number | null;
  /** Above 1 only after the escalated regeneration re-ran a stage. */
  attempt: number;
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
    // `skipped` is mapped rather than folded into `done`: a stage that
    // short-circuited did not do the work, and marking it complete is the
    // reason three stages that had genuinely run used to sort below stages
    // that had not.
    const state: RowState =
      event.status === 'failed'
        ? 'failed'
        : event.status === 'paused'
          ? 'paused'
          : event.status === 'skipped'
            ? 'skipped'
            : 'done';
    const detail = event.detail && isProse(event.detail) ? event.detail : null;
    const facts = event.facts ?? [];
    const durationMs = event.duration_ms ?? null;
    const attempt = event.attempt ?? 1;
    if (existing) {
      existing.state = state;
      existing.detail = detail;
      existing.facts = facts;
      // Summed, not replaced: a gate that ran three rounds occupies one row,
      // and the time that row stands for is all three.
      existing.durationMs = (existing.durationMs ?? 0) + (durationMs ?? 0);
      existing.attempt = Math.max(existing.attempt, attempt);
      continue;
    }
    seen.add(event.stage);
    rows.push({
      key: event.stage,
      label: humanise(event.stage),
      state,
      detail,
      phase: STAGE_PHASES.get(event.stage) ?? 'other',
      facts,
      durationMs,
      attempt,
    });
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
      phase: STAGE_PHASES.get(stage) ?? 'other',
      facts: [],
      durationMs: null,
      attempt: 1,
    });
  });

  return rows;
}

/**
 * A row is worth opening when it has anything to show — prose, facts, or both.
 *
 * Facts alone are enough: `candidate_selection` can arrive with a rationale in
 * `why` and a detail line that only repeats the method.
 */
export function isExpandable(row: Row): boolean {
  return row.detail !== null || row.facts.length > 0;
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
  return rows.filter(isExpandable).at(-1)?.key ?? null;
}
