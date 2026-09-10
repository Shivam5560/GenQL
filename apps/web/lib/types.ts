export interface TurnResponse {
  thread_id: string;
  clarifying_question: string | null;
  /** What the gate applies if the answer is submitted blank. Best-effort: a
      question can arrive without one. */
  suggested_answer: string | null;
  /** A few one-tap alternatives for the question being asked. */
  clarification_options: string[];
  intent: string | null;
  validated_sql: string | null;
  narrowing_suggestion: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  applied_defaults: [string, string][];
  /** (dimension, value) decisions applied without asking — rule defaults, and
      the gate's own reading of whatever it ran out of budget to ask about.
      Shown so a wrong one is visible and correctable in a follow-up. */
  assumed: [string, string][];
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
  // Optional: not persisted server-side yet (TurnRecord/TurnRecordDto on the backend have no
  // such field), so it's only ever populated for a turn created fresh in this browser session —
  // turns reloaded from GET /v1/threads/{id} will not have it.
  referenced_objects?: string[];
  // Optional for the same reason. A reloaded paused turn therefore shows its
  // question with no chips, which is the pre-suggestion experience rather
  // than a broken one.
  suggested_answer?: string | null;
  clarification_options?: string[];
  assumed?: [string, string][];
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
  /** `host:port/database`. Null for a datasource whose DSN lives in the
      server's environment — the pre-Phase-9 shape, still supported. */
  endpoint?: string | null;
}

export type ThemePreference = 'light' | 'dark' | 'system';

export interface Profile {
  theme_preference: ThemePreference;
}

/** One completed pipeline node, as `GET /v1/queries/stream` reports it. */
export interface StageEvent {
  stage: string;
  status: 'completed' | 'paused' | 'failed';
  detail: string | null;
}

/**
 * A typed failure from either stream. `error` is the exception class name —
 * `CostBudgetExceededError`, `StaticValidationError` — so the UI can branch on
 * the kind of failure without parsing prose out of `detail`.
 */
export interface StreamError {
  error: string;
  detail: string;
}

/** A turn that has been sent but has not reached its terminal event yet. */
export interface PendingTurn {
  /** Stable for the life of the pending turn, so React keys do not churn. */
  localId: string;
  question: string;
  stages: StageEvent[];
  startedAt: number;
  error: StreamError | null;
}

export type IngestionStepStatus = 'pending' | 'running' | 'succeeded' | 'skipped' | 'failed';

export interface IngestionStep {
  name: string;
  status: IngestionStepStatus;
  detail: string | null;
  records_written: number;
  duration_ms: number;
}

export interface IngestionJob {
  job_id: string;
  datasource_name: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  schemas: string[];
  steps: IngestionStep[];
  error: string | null;
  error_step: string | null;
  /** 0-1 across the whole pipeline, so the bar does not have to be derived
      from a step list whose length changes on a resumed job. */
  progress: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DatasourceAccepted {
  datasource: Datasource;
  job: IngestionJob;
  stream_url: string;
}

export interface RegisterDatasourceArgs {
  name: string;
  dialect: string;
  host: string;
  port: number;
  database: string;
  username: string;
  /** Sent once, encrypted server-side, and never returned by any endpoint. */
  password: string;
  /** Driver query string — `sslmode=require`, `connect_timeout=10`. */
  options?: string | null;
  description?: string | null;
  schemas: string[];
}
