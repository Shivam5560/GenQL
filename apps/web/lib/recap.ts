import type { TurnRecord, TurnResponse } from './types';

export function buildRecap(response: TurnResponse): string | null {
  if (response.clarifying_question) return null;
  if (response.intent) return null; // a short-circuited, non-analytical turn — nothing to recap
  const parts: string[] = [];
  if (response.narrowing_suggestion) parts.push(response.narrowing_suggestion);
  // The values, not the rule names: this line is read by someone checking
  // whether the answer means what they wanted, and "time_range → the most
  // recent complete year" tells them that where "time_range →
  // default_period" does not. The rule names stay available on the turn for
  // anyone who wants to go edit one.
  const assumed = response.assumed ?? [];
  if (assumed.length > 0) {
    const stated = assumed.map(([dimension, value]) => `${dimension} → ${value}`).join(', ');
    parts.push(`Assumed: ${stated}.`);
  } else if (response.applied_defaults.length > 0) {
    const defaults = response.applied_defaults
      .map(([dimension, rule]) => `${dimension} → ${rule}`)
      .join(', ');
    parts.push(`Applied defaults: ${defaults}.`);
  }
  return parts.length > 0 ? parts.join(' ') : 'Understood — validated SQL is ready below.';
}

export function toLocalTurnRecord(
  question: string,
  sequence: number,
  response: TurnResponse,
): TurnRecord {
  return {
    turn_id: `local-${response.thread_id}-${sequence}`,
    sequence,
    question,
    recap: buildRecap(response),
    validated_sql: response.validated_sql,
    clarifying_question: response.clarifying_question,
    columns: response.columns,
    rows: response.rows,
    row_count: response.row_count,
    applied_defaults: response.applied_defaults,
    created_at: new Date().toISOString(),
    // Only meaningful when non-empty — an empty array and a missing field both mean "nothing to show".
    referenced_objects: response.referenced_objects.length > 0 ? response.referenced_objects : undefined,
    suggested_answer: response.suggested_answer,
    clarification_options:
      response.clarification_options.length > 0 ? response.clarification_options : undefined,
    assumed: response.assumed.length > 0 ? response.assumed : undefined,
  };
}
