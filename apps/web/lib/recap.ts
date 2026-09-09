import type { TurnRecord, TurnResponse } from './types';

export function buildRecap(response: TurnResponse): string | null {
  if (response.clarifying_question) return null;
  if (response.intent) return null; // a short-circuited, non-analytical turn — nothing to recap
  const parts: string[] = [];
  if (response.narrowing_suggestion) parts.push(response.narrowing_suggestion);
  if (response.applied_defaults.length > 0) {
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
  };
}
