export interface TurnResponse {
  thread_id: string;
  clarifying_question: string | null;
  intent: string | null;
  validated_sql: string | null;
  narrowing_suggestion: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  applied_defaults: [string, string][];
  rewrite_rules_applied: string[];
  plan_text: string | null;
  referenced_objects: string[];
  selection_method: string | null;
  selection_rationale: string | null;
  candidate_count: number;
  probe_count: number;
}

export interface ThreadSummary {
  thread_id: string;
  datasource_name: string;
  title: string;
  created_at: string;
  last_active_at: string;
}

export interface TurnRecord {
  turn_id: string;
  sequence: number;
  question: string;
  recap: string | null;
  validated_sql: string | null;
  clarifying_question: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  applied_defaults: [string, string][];
  created_at: string;
}

export interface ThreadDetail {
  summary: ThreadSummary;
  turns: TurnRecord[];
}

export interface Datasource {
  name: string;
  dialect: string;
  description: string | null;
  enabled: boolean;
}

export type ThemePreference = 'light' | 'dark' | 'system';

export interface Profile {
  theme_preference: ThemePreference;
}
