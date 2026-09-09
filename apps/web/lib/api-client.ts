import type { Datasource, Profile, ThemePreference, ThreadDetail, ThreadSummary, TurnResponse } from './types';

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
