import type { StageEvent } from '@/lib/types';

/**
 * The two or three things about a turn that someone could actually dispute.
 *
 * The trail below answers "what did it do"; this answers "why does the SQL look
 * like this", which is the question people open the rail for. Twelve equal rows
 * cannot answer it, because the stage that settled the meaning of the question
 * looks exactly like the stage that counted the rows.
 *
 * Everything here is read out of `StageEvent.facts` — nothing is inferred, and
 * a card whose facts are absent is not rendered at all. That matters more than
 * it sounds: a turn nobody had to ask about has no answered question and no
 * contest, so on a straightforward turn this section is empty and the rail is
 * the trail alone. An empty card would be a claim that something was decided.
 */
export interface DecisionRow {
  label: string;
  value: string;
}

export interface Decision {
  key: string;
  eyebrow: string;
  /** Small mono value at the right of the eyebrow — a count, a dimension. */
  aside: string | null;
  /** The one line set larger than the rest, when the card has a single answer. */
  lead: string | null;
  rows: DecisionRow[];
  note: string | null;
  /** True for the card carrying something the user themselves said. */
  accent: boolean;
}

/**
 * Every fact a stage reported this turn, later reports winning per label.
 *
 * The gate reports twice on a turn it paused — once with the question it is
 * asking, once with what it finally settled — and both are true of the gate.
 */
function factsByStage(stages: StageEvent[]): Map<string, Map<string, string>> {
  const merged = new Map<string, Map<string, string>>();
  for (const event of stages) {
    const target = merged.get(event.stage) ?? new Map<string, string>();
    for (const [label, value] of event.facts ?? []) target.set(label, value);
    merged.set(event.stage, target);
  }
  return merged;
}

/** `"time_range=all history · grain=one row"` -> `[[time_range, all history], …]` */
function split(value: string | undefined, separator: string): [string, string][] {
  if (!value) return [];
  return value.split(' · ').flatMap((entry): [string, string][] => {
    const at = entry.indexOf(separator);
    if (at === -1) return [];
    return [[entry.slice(0, at).trim(), entry.slice(at + separator.length).trim()]];
  });
}

function answered(facts: Map<string, string> | undefined): Decision | null {
  const answer = facts?.get('your answer');
  if (!answer) return null;
  const rounds = Number(facts?.get('rounds') ?? '1');
  return {
    key: 'answered',
    eyebrow: 'You answered',
    aside: facts?.get('dimension') ?? null,
    lead: answer,
    rows: [],
    note: rounds > 1 ? `${rounds} questions were asked on this turn.` : null,
    accent: true,
  };
}

function assumed(facts: Map<string, string> | undefined): Decision | null {
  const pairs = split(facts?.get('assumed'), '=');
  if (pairs.length === 0) return null;
  const defaults = new Map(split(facts?.get('rule defaults'), ' via '));
  return {
    key: 'assumed',
    eyebrow: 'Assumed for you',
    aside: String(pairs.length),
    lead: null,
    rows: pairs.map(([dimension, value]) => ({
      label: dimension,
      value: defaults.has(dimension) ? `${value} · rule ${defaults.get(dimension)}` : value,
    })),
    note: 'Wrong? Say so in a follow-up and the gate re-asks.',
    accent: false,
  };
}

function chosen(byStage: Map<string, Map<string, string>>): Decision | null {
  const selection = byStage.get('candidate_selection');
  const why = selection?.get('why');
  const drafted = byStage.get('candidate_generation')?.get('candidates');
  // One candidate is not a contest. The rationale would read "only one
  // candidate survived validation", which explains nothing anyone asked.
  if (!why || !drafted || Number(drafted) <= 1) return null;

  const scores = split(byStage.get('critique')?.get('scores'), ' ');
  const cleared = byStage.get('static_validation')?.get('cleared');
  const resolved = byStage.get('ambiguity_probing')?.get('resolved to');
  return {
    key: 'chosen',
    eyebrow: 'Why this SQL won',
    aside: `${drafted} → 1`,
    lead: why,
    rows: scores.map(([candidate, score]) => ({
      label: candidate,
      value: resolved?.includes(candidate) ? `${score} · probe agreed` : score,
    })),
    note: cleared ? `${cleared} of ${drafted} cleared validation.` : null,
    accent: false,
  };
}

export function buildDecisions(stages: StageEvent[]): Decision[] {
  const byStage = factsByStage(stages);
  return [
    answered(byStage.get('ambiguity_interrupt')),
    assumed(byStage.get('ambiguity_gate')),
    chosen(byStage),
  ].filter((decision): decision is Decision => decision !== null);
}
