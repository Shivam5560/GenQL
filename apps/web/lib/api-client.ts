import { isAbort, readEventStream, SseHttpError } from './sse';
import type {
  Datasource,
  DatasourceAccepted,
  IngestionJob,
  IngestionStep,
  Profile,
  RegisterDatasourceArgs,
  StageEvent,
  StreamError,
  ThemePreference,
  ThreadDetail,
  ThreadSummary,
  TurnResponse,
} from './types';

const API_ORIGIN = process.env.NEXT_PUBLIC_GENQL_API_ORIGIN ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`GenQL API error ${status}`);
  }
}

async function request<T>(path: string, accessToken: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ORIGIN}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${accessToken}`,
      ...init.headers,
    },
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // body wasn't JSON — leave it null, the status code still tells the caller enough
    }
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function startTurn(
  accessToken: string,
  args: { question: string; datasource: string; domain_id?: number; thread_id?: string },
): Promise<TurnResponse> {
  return request<TurnResponse>('/v1/queries', accessToken, {
    method: 'POST',
    body: JSON.stringify(args),
  });
}

export function resumeTurn(accessToken: string, threadId: string, answer: string): Promise<TurnResponse> {
  return request<TurnResponse>(`/v1/queries/${threadId}/resume`, accessToken, {
    method: 'POST',
    body: JSON.stringify({ answer }),
  });
}

export function listThreads(accessToken: string): Promise<ThreadSummary[]> {
  return request<ThreadSummary[]>('/v1/threads', accessToken);
}

export function getThread(accessToken: string, threadId: string): Promise<ThreadDetail> {
  return request<ThreadDetail>(`/v1/threads/${threadId}`, accessToken);
}

export function listDatasources(accessToken: string): Promise<Datasource[]> {
  return request<Datasource[]>('/v1/datasources', accessToken);
}

export function getProfile(accessToken: string): Promise<Profile> {
  return request<Profile>('/v1/profile', accessToken);
}

export function updateTheme(accessToken: string, theme: ThemePreference): Promise<Profile> {
  return request<Profile>('/v1/profile', accessToken, {
    method: 'PATCH',
    body: JSON.stringify({ theme_preference: theme }),
  });
}

export function submitFeedback(
  accessToken: string,
  threadId: string,
  args: { rating: 'good' | 'bad'; corrected_sql?: string; comment?: string },
): Promise<void> {
  return request<void>(`/v1/queries/${threadId}/feedback`, accessToken, {
    method: 'POST',
    body: JSON.stringify(args),
  });
}

// ---------------------------------------------------------------- streaming

export interface TurnStreamHandlers {
  onStage: (stage: StageEvent) => void;
  /** A turn that finished, or one that paused on a clarifying question. */
  onTerminal: (response: TurnResponse) => void;
  /** The turn failed. Carries the exception class name and its message. */
  onError: (error: StreamError) => void;
  /** Something went wrong beside the turn — history was not written. */
  onWarning?: (warning: StreamError) => void;
}

function turnStreamUrl(args: {
  question: string;
  datasource: string;
  domain_id?: number;
  thread_id?: string;
  answer?: string;
}): string {
  const params = new URLSearchParams({ question: args.question, datasource: args.datasource });
  if (args.domain_id !== undefined) params.set('domain_id', String(args.domain_id));
  if (args.thread_id) params.set('thread_id', args.thread_id);
  if (args.answer !== undefined) params.set('answer', args.answer);
  return `${API_ORIGIN}/v1/queries/stream?${params}`;
}

/**
 * Run one turn, reporting each pipeline stage as it completes.
 *
 * Resolves when the stream reaches its terminal event, so a caller can `await`
 * it to know the turn is over — but the answer arrives through `onTerminal`,
 * not through the return value, because a paused turn and a finished one end
 * the same way and both need rendering the moment they land.
 *
 * A transport failure is delivered through `onError` like any other failure:
 * a caller should never need two error paths for one turn.
 */
export async function streamTurn(
  accessToken: string,
  args: {
    question: string;
    datasource: string;
    domain_id?: number;
    thread_id?: string;
    answer?: string;
  },
  handlers: TurnStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  try {
    for await (const event of readEventStream(turnStreamUrl(args), accessToken, signal)) {
      const payload = JSON.parse(event.data);
      if (event.event === 'stage') handlers.onStage(payload as StageEvent);
      else if (event.event === 'warning') handlers.onWarning?.(payload as StreamError);
      else if (event.event === 'error') handlers.onError(payload as StreamError);
      else if (event.event === 'result' || event.event === 'clarification') {
        handlers.onTerminal(payload as TurnResponse);
      }
    }
  } catch (reason) {
    // An abort is this client hanging up, not a failure worth reporting.
    if (isAbort(reason)) return;
    handlers.onError({
      error: reason instanceof SseHttpError ? `HTTP ${reason.status}` : 'ConnectionError',
      detail:
        reason instanceof SseHttpError
          ? 'The server refused the request. Try again, or sign in if your session expired.'
          : 'Lost the connection to GenQL before the answer arrived.',
    });
  }
}

// ------------------------------------------------------------- datasources

export function registerDatasource(
  accessToken: string,
  args: RegisterDatasourceArgs,
): Promise<DatasourceAccepted> {
  return request<DatasourceAccepted>('/v1/datasources', accessToken, {
    method: 'POST',
    body: JSON.stringify(args),
  });
}

export function getOnboarding(accessToken: string, name: string): Promise<IngestionJob> {
  return request<IngestionJob>(`/v1/datasources/${encodeURIComponent(name)}/onboarding`, accessToken);
}

export function retryOnboarding(
  accessToken: string,
  name: string,
  startFrom?: string,
): Promise<IngestionJob> {
  return request<IngestionJob>(
    `/v1/datasources/${encodeURIComponent(name)}/onboarding/retry`,
    accessToken,
    { method: 'POST', body: JSON.stringify({ start_from: startFrom ?? null }) },
  );
}

export function removeDatasource(accessToken: string, name: string): Promise<void> {
  return request<void>(`/v1/datasources/${encodeURIComponent(name)}`, accessToken, {
    method: 'DELETE',
  });
}

export interface IngestionStreamHandlers {
  onStep: (step: IngestionStep & { datasource: string }) => void;
  /** How far through the whole pipeline the job is, 0-1. Computed server-side
      so a resumed job's bar lands in the right place — see `progress_event`. */
  onProgress?: (event: { datasource: string; progress: number }) => void;
  onDone: (job: IngestionJob) => void;
  onError: (error: StreamError & { step: string | null }) => void;
}

/** Follow one datasource's ingestion until it succeeds or fails. */
export async function streamOnboarding(
  accessToken: string,
  name: string,
  handlers: IngestionStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_ORIGIN}/v1/datasources/${encodeURIComponent(name)}/onboarding/stream`;
  try {
    for await (const event of readEventStream(url, accessToken, signal)) {
      const payload = JSON.parse(event.data);
      if (event.event === 'step') handlers.onStep(payload);
      else if (event.event === 'progress') handlers.onProgress?.(payload);
      else if (event.event === 'done') handlers.onDone(payload.job as IngestionJob);
      else if (event.event === 'error') handlers.onError(payload);
    }
  } catch (reason) {
    if (isAbort(reason)) return;
    handlers.onError({
      error: 'ConnectionError',
      detail: 'Lost the connection while watching this datasource. Reload to check on it.',
      step: null,
    });
  }
}

export interface DatasourceFeedHandlers {
  onReady: (event: { datasource: string; job_id: string }) => void;
  onFailed: (event: { datasource: string; error: string | null; error_step: string | null }) => void;
}

/**
 * The app-wide notification channel, held open for the whole session.
 *
 * Ingestion takes minutes, so the person who submitted a warehouse is
 * somewhere else by the time it finishes. This is how "your warehouse is
 * ready" reaches them wherever they went. Connection failures are silent by
 * design: a background subscription that toasts when the network hiccups is
 * worse than one that quietly reconnects.
 */
export async function streamDatasourceEvents(
  accessToken: string,
  handlers: DatasourceFeedHandlers,
  signal?: AbortSignal,
): Promise<void> {
  try {
    for await (const event of readEventStream(
      `${API_ORIGIN}/v1/datasources/events`,
      accessToken,
      signal,
    )) {
      const payload = JSON.parse(event.data);
      if (event.event === 'ready') handlers.onReady(payload);
      else if (event.event === 'failed') handlers.onFailed(payload);
    }
  } catch {
    // Deliberately silent — see the note above.
  }
}
