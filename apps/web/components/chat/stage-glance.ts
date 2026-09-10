import type { Row } from './stage-rows';

/**
 * The one value a trail row shows without being opened.
 *
 * `detail` is a sentence — "3 candidates cleared validation" — which is the
 * right thing to read once a row is open and the wrong thing to hang off the
 * right edge of a 300px rail. This is the same fact as a phrase: "3 cleared".
 *
 * Per-stage rather than generic, deliberately. A generic rule would have to
 * choose between "2 objects" and "domain 3" without knowing which noun belongs
 * in front of the number, and would get one of them wrong. Presentation is
 * exactly where per-stage knowledge belongs, and an unrecognised stage falls
 * back to its first fact — so a node added by a later phase still shows
 * something rather than nothing.
 */
type Lookup = (label: string) => string | undefined;

function count(value: string | undefined, noun: string): string | null {
  if (value === undefined) return null;
  return `${value} ${noun}${value === '1' ? '' : 's'}`;
}

function compact(parts: (string | null)[]): string | null {
  const kept = parts.filter((part): part is string => part !== null);
  return kept.length > 0 ? kept.join(' · ') : null;
}

/** "time_range=all history · grain=one row" -> 2. */
function pairCount(value: string | undefined): number {
  return value ? value.split(' · ').length : 0;
}

/** "#0 0.92 · #1 0.71" -> "top 0.92". */
function topScore(value: string | undefined): string | null {
  const best = value
    ?.split(' · ')
    .map((entry) => Number(entry.split(' ')[1]))
    .filter((score) => !Number.isNaN(score))
    .sort((a, b) => b - a)[0];
  return best === undefined ? null : `top ${best.toFixed(2)}`;
}

const GLANCE: Record<string, (fact: Lookup) => string | null> = {
  intent_classification: (fact) => fact('intent') ?? null,
  domain_scoping: (fact) => (fact('domain_id') ? `domain ${fact('domain_id')}` : null),
  schema_linking: (fact) =>
    compact([count(fact('objects'), 'object'), count(fact('join paths'), 'join')]),
  ambiguity_gate: (fact) =>
    compact([
      fact('asking about') ? `asking ${fact('asking about')}` : null,
      pairCount(fact('assumed')) > 0 ? `${pairCount(fact('assumed'))} assumed` : null,
    ]),
  ambiguity_interrupt: (fact) => fact('dimension') ?? null,
  planning: (fact) => {
    const grounded = fact('grounded in');
    return grounded ? count(String(grounded.split(', ').length), 'object') : null;
  },
  candidate_generation: (fact) => count(fact('candidates'), 'candidate'),
  static_validation: (fact) => (fact('cleared') ? `${fact('cleared')} cleared` : null),
  critique: (fact) => topScore(fact('scores')),
  ambiguity_probing: (fact) => count(fact('probes'), 'probe'),
  candidate_selection: (fact) => fact('method') ?? null,
  rewrite_and_cost_gate: (fact) => fact('verdict') ?? null,
  guarded_execution: (fact) => count(fact('rows'), 'row'),
};

export function glanceOf(row: Row): string | null {
  // A skipped stage's whole story is why it did not run, and that is in the
  // detail. Showing a count beside it would describe work that never happened.
  if (row.state === 'skipped') return 'skipped';
  if (row.facts.length === 0) return null;
  const map = new Map(row.facts);
  const format = GLANCE[row.key];
  return format ? format((label) => map.get(label)) : (row.facts[0][1] ?? null);
}

/** "1.2s", or "340ms" under a second. Null when nothing measured it. */
export function formatDuration(ms: number | null): string | null {
  if (ms === null) return null;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}
