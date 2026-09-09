# GenQL Phase 9b — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with these process overrides from the human partner:
> 1. **No tests during implementation tasks** (Tasks 1-9). Each task ends with a commit of working code, no test-writing step. Tests are written in dedicated Task 10, after all implementation is complete.
> 2. **No per-task code review.** Do not dispatch a task reviewer after each task. Implement, commit, move to the next task. The only review is the final whole-branch review after Task 10, per subagent-driven-development's existing final-review step.
> 3. **Task briefs are copied verbatim** from this plan file via `scripts/task-brief` — never re-authored by the controller.
> 4. **Task reports must stay under 15 lines** — status, commits, one-line summary of what changed, concerns if any. No narrative.
> 5. **Model tier per task is fixed below** (marked haiku / sonnet / opus) — this replaces subagent-driven-development's own model-selection heuristic; use the tier stated on each task, not the heuristic's judgment call.
> No token budget constraint applies to implementation work itself — completeness and correctness over brevity there.

This is **Phase 9b** — the frontend half of Phase 9, and the companion to **Phase 9a**
(`docs/superpowers/plans/2026-09-09-genql-phase-9-frontend-and-auth.md`), which must have a clean
final review before this plan starts: every task below calls an HTTP surface Phase 9a creates
(`GET/PATCH /v1/profile`, `GET /v1/threads*`, the now-authenticated `/v1/queries*` and
`/v1/queries/stream`) or proxies to the self-hosted GoTrue service Phase 9a's `docker/compose.yaml`
change adds.

**Goal:** Ship the Phase 9 frontend — a Next.js chat console, deployable to Vercel — implementing
the reviewed mockup's Industrial Terminal / Swiss Modernism 2.0 direction with a real chat flow,
execute-gated results, dialect selection, thread history, datasource picker, and settings.

**Architecture:** Next.js 15 App Router app in a new `apps/web/` directory. Only auth calls go
through a Route Handler proxy (Task 3) — the refresh token has to stay out of client-side
JavaScript, so it lives in an `httpOnly` cookie the Route Handler alone reads and writes, and the
access token is handed to client code per-page-load and refreshed on a timer coordinated across
tabs. Every other backend call (`/v1/queries*`, `/v1/threads*`, `/v1/datasources`, `/v1/profile`)
goes **directly** from client-side JavaScript to the FastAPI backend with `Authorization: Bearer
<access token>` — there is no cookie to hide and no `EventSource` header limitation in play for
these (this phase does not consume the SSE stream — the reviewed UI shows no per-stage progress, so
there is no live consumer for it yet; a future phase that adds one would need the Route-Handler-proxy
approach the original spec described, since `EventSource` cannot carry a `Bearer` header), so a
Route Handler hop here would add latency and complexity for no security benefit. This does mean the
FastAPI backend needs CORS enabled for the frontend's origin — Phase 9a's plan has been amended with
a CORS task ahead of this plan's Task 1 dependency on it; confirm that task is complete before
relying on direct cross-origin calls working.

**Tech Stack:** Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Google Fonts (IBM Plex
Sans, JetBrains Mono, Space Mono).

**Spec:** `docs/superpowers/specs/2026-09-09-genql-phase-9-frontend-and-auth.md` — this plan argues
from that spec; every task below implements one of its frontend sections (§7, §8). Read §7
(Frontend) and §8 (SSE across origins) before Task 1. The reviewed visual reference is the mockup
artifact `genql-chat-mockup.html` (published during this project's brainstorming session) — its
markup and CSS are the literal source for Task 6's component styling; do not redesign from scratch.

## Global Constraints

- Design tokens are Swiss Modernism 2.0: paper `#f5f4ef` / panel `#ffffff` / ink `#0a0a0a` / mute
  `#5c594e` / hairline `rgba(10,10,10,.15)` / accent `#ff5a1f` in light; `#0c0b0a` / `#151412` /
  `#f2efe8` / `#a39b8c` / `rgba(255,255,255,.14)` / `#ff7a45` in dark. One accent only — no second
  brand color.
- Typography: IBM Plex Sans for UI text, JetBrains Mono for SQL/data/tabular figures, Space Mono for
  uppercase eyebrow labels and thread-scoped ids. No Inter, no Roboto, no system-default sans as the
  primary face.
- No stage/tool-call track in the chat UI — a single plain-language recap line replaces it (spec §7,
  confirmed via user feedback during brainstorming).
- SQL is always shown with a dialect selector (Postgres/Snowflake/BigQuery/MySQL/DuckDB) next to it.
- Results render only after an explicit `Execute` action — never automatically alongside the SQL.
- The datasource picker offers datasource selection only — no domain/table scoping control.
- The frontend never talks to the FastAPI backend or GoTrue directly from client-side JavaScript —
  every call goes through a Next.js Route Handler under `app/api/`.
- The frontend never builds an OAuth authorization-code exchange itself — it only links to
  `{GOTRUE_URL}/authorize?provider=...` and lets GoTrue handle the whole flow (spec §7).
- Feedback controls (`Helpful` / `Needs work` / `Suggest SQL`) appear only once a turn has executed
  — never on an unexecuted turn.

---

## File Structure

```
apps/web/app/(auth)/login/page.tsx, (auth)/signup/page.tsx, (auth)/callback/page.tsx
apps/web/app/(chat)/layout.tsx, (chat)/page.tsx, (chat)/thread/[id]/page.tsx
apps/web/app/datasources/page.tsx, settings/page.tsx
apps/web/app/api/auth/[...action]/route.ts
apps/web/components/chat/message-turn.tsx, sql-card.tsx, dialect-select.tsx,
                        execute-button.tsx, result-table.tsx, feedback-row.tsx
apps/web/components/sidebar/datasource-card.tsx, thread-list.tsx
apps/web/components/ui/*             # shadcn primitives, generated by the shadcn CLI
apps/web/lib/api-client.ts, auth.ts, types.ts
apps/web/styles/tokens.css
apps/web/tailwind.config.ts, next.config.ts, package.json, tsconfig.json
```

Test suite (written last, Task 10):
```
apps/web/tests/chat-flow.test.tsx, auth-forms.test.tsx
apps/web/e2e/register-ask-execute.spec.ts
```

---

## Task 1: Next.js scaffold, Tailwind, and design tokens

**Model:** sonnet

**Files:**
- Create: `apps/web/package.json`, `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`,
  `postcss.config.mjs`, `components.json`
- Create: `apps/web/app/layout.tsx`, `app/globals.css`
- Create: `apps/web/styles/tokens.css`
- Create: `apps/web/lib/types.ts`

**Interfaces:**
- Produces: the whole Next.js project shell every later task builds inside — `apps/web/`'s
  `package.json` scripts (`dev`, `build`, `lint`), the Tailwind config every component task's
  className usage depends on, `styles/tokens.css`'s CSS custom properties (`--bg`, `--panel`,
  `--ink`, `--mute`, `--line`, `--accent`, etc.) every later component references, and
  `lib/types.ts`'s shared TypeScript types (`ThreadSummary`, `TurnRecord`, `TurnResponse`,
  `Profile`) that Task 2's `api-client.ts` and every component task import.

- [ ] **Step 1: Scaffold the project**

Run (from the repo root):
```bash
npx --yes create-next-app@latest apps/web --typescript --tailwind --app --src-dir=false --import-alias "@/*" --eslint --no-turbopack --use-npm
```

Accept the generated `apps/web/` structure as the base; the steps below overwrite/extend specific
files it creates.

- [ ] **Step 2: Install shadcn/ui and generate primitives**

Run (from `apps/web/`):
```bash
npx --yes shadcn@latest init -d
npx --yes shadcn@latest add button card select input label badge dialog scroll-area
```

This creates `apps/web/components.json` and populates `apps/web/components/ui/*` — accept the
defaults `shadcn init -d` chooses (they target the same Tailwind config Step 1 scaffolded).

- [ ] **Step 3: Write the design tokens**

```css
/* apps/web/styles/tokens.css */
:root {
  --bg: #f5f4ef;
  --panel: #ffffff;
  --panel-2: #faf9f5;
  --ink: #0a0a0a;
  --mute: #5c594e;
  --line: rgba(10, 10, 10, 0.15);
  --accent: #ff5a1f;
  --accent-ink: #ffffff;
  --ok: #1f7a4d;
  --ok-soft: #e5f3ea;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme='light']) {
    --bg: #0c0b0a;
    --panel: #151412;
    --panel-2: #1b1a17;
    --ink: #f2efe8;
    --mute: #a39b8c;
    --line: rgba(255, 255, 255, 0.14);
    --accent: #ff7a45;
    --ok: #59d692;
    --ok-soft: rgba(89, 214, 146, 0.12);
  }
}

:root[data-theme='dark'] {
  --bg: #0c0b0a;
  --panel: #151412;
  --panel-2: #1b1a17;
  --ink: #f2efe8;
  --mute: #a39b8c;
  --line: rgba(255, 255, 255, 0.14);
  --accent: #ff7a45;
  --ok: #59d692;
  --ok-soft: rgba(89, 214, 146, 0.12);
}

body {
  background: var(--bg);
  color: var(--ink);
}
```

- [ ] **Step 4: Wire fonts and tokens into the root layout**

```tsx
// apps/web/app/layout.tsx
import type { Metadata } from 'next';
import { IBM_Plex_Sans, JetBrains_Mono, Space_Mono } from 'next/font/google';
import '@/styles/tokens.css';
import './globals.css';

const plexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
});
const spaceMono = Space_Mono({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-eyebrow',
});

export const metadata: Metadata = {
  title: 'GenQL',
  description: 'Ask your warehouse a question.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${jetbrainsMono.variable} ${spaceMono.variable}`}>
      <body className="font-sans">{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: Extend the Tailwind config with the font variables**

Edit `apps/web/tailwind.config.ts` (generated by Step 1) to add, inside `theme.extend`:

```ts
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
        eyebrow: ['var(--font-eyebrow)', 'ui-monospace', 'monospace'],
      },
```

- [ ] **Step 6: Write the shared TypeScript types**

These mirror the backend DTOs from Phase 9a's Tasks 13-14 (`ThreadSummaryDto`, `TurnRecordDto`,
`ThreadDetailDto`, `ProfileDto`) and the existing `TurnResponseDto` from Phase 8
(`genql/api/dtos/query_dtos.py`) field-for-field.

```ts
// apps/web/lib/types.ts
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
```

- [ ] **Step 7: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 8: Commit**

```bash
git add apps/web
git commit -m "feat(web): scaffold Next.js app with Tailwind, shadcn/ui, and design tokens"
```

---

## Task 2: `api-client.ts` — typed fetch wrappers

**Model:** sonnet

**Files:**
- Create: `apps/web/lib/api-client.ts`

**Interfaces:**
- Consumes: the types from Task 1's `lib/types.ts`.
- Produces: `startTurn`, `resumeTurn`, `listThreads`, `getThread`, `listDatasources`,
  `getProfile`, `updateTheme` — every later page/component task calls these rather than raw
  `fetch`. Every function takes an `accessToken: string` as its first argument (from `lib/auth.ts`,
  Task 3) and throws `ApiError` (carrying the HTTP status and backend error body) on a non-2xx
  response — callers decide how to render that, this module never renders anything.

- [ ] **Step 1: Write the client**

All calls go to `NEXT_PUBLIC_GENQL_API_ORIGIN` — a **public** env var is correct here (unlike
`GOTRUE_URL`/`GENQL_API_ORIGIN` used server-side in Route Handlers): the FastAPI backend's
`/v1/*` routes are meant to be called with a `Bearer` token the client already holds, directly from
client components, since they are not the auth-cookie-bearing calls Route Handlers exist to hide —
only the SSE stream (Task 7) and auth (Task 3) need a server-side proxy, per spec §7-§8.

```ts
// apps/web/lib/api-client.ts
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
```

- [ ] **Step 2: Add the env var to `.env.local.example`**

Create `apps/web/.env.local.example`:

```
NEXT_PUBLIC_GENQL_API_ORIGIN=http://localhost:8000
GENQL_API_ORIGIN=http://localhost:8000
GOTRUE_URL=http://localhost:9999
NEXT_PUBLIC_APP_ORIGIN=http://localhost:3000
```

(`GENQL_API_ORIGIN` and `GOTRUE_URL` are server-side-only vars Tasks 3 and 7 read inside Route
Handlers — listed here so the whole set is documented in one place, even though this task only
consumes the `NEXT_PUBLIC_` one.)

- [ ] **Step 3: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/api-client.ts apps/web/.env.local.example
git commit -m "feat(web): add typed API client for the FastAPI backend"
```

---

## Task 3: Auth proxy route and `lib/auth.ts` session management

**Model:** opus — the multi-tab refresh coordination (spec §12's named risk) is a genuine
concurrency judgment call with no existing precedent in this codebase to mirror, and getting it
wrong produces a hard-to-reproduce bug (a stampede of refresh calls, or a tab silently logged out).

**Files:**
- Create: `apps/web/app/api/auth/[...action]/route.ts`
- Create: `apps/web/lib/auth.ts`

**Interfaces:**
- Consumes: the self-hosted GoTrue service (Phase 9a's `docker/compose.yaml`), `GOTRUE_URL` (server
  env var).
- Produces: `AuthProvider` (a React context provider) and `useAuth()` (a hook returning
  `{ session, loading, login, signup, logout }`), consumed by every later page task (4, 5, 8, 9, 10)
  to read the current access token and trigger auth actions. `session.accessToken` is what Task 2's
  `api-client.ts` functions take as their first argument.

- [ ] **Step 1: Write the Route Handler**

GoTrue's `/logout` invalidates a session given the **access** token as `Bearer` (not the refresh
token) — the client must send its current access token in the logout request body for the Route
Handler to forward.

```ts
// apps/web/app/api/auth/[...action]/route.ts
import { NextRequest, NextResponse } from 'next/server';

const GOTRUE_URL = process.env.GOTRUE_URL ?? 'http://localhost:9999';
const REFRESH_COOKIE = 'gq_refresh';

function setRefreshCookie(response: NextResponse, refreshToken: string): void {
  response.cookies.set(REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/api/auth',
    maxAge: 60 * 60 * 24 * 30,
  });
}

interface GoTrueSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: { id: string; email: string };
}

function sessionBody(gotrue: GoTrueSession) {
  return {
    access_token: gotrue.access_token,
    expires_in: gotrue.expires_in,
    user: { id: gotrue.user.id, email: gotrue.user.email },
  };
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ action: string[] }> },
): Promise<NextResponse> {
  const { action } = await params;
  const step = action[0];

  if (step === 'signup' || step === 'login') {
    const { email, password } = await request.json();
    const gotrueUrl =
      step === 'signup' ? `${GOTRUE_URL}/signup` : `${GOTRUE_URL}/token?grant_type=password`;
    const gotrueResponse = await fetch(gotrueUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!gotrueResponse.ok) {
      return new NextResponse(await gotrueResponse.text(), { status: gotrueResponse.status });
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }

  if (step === 'refresh') {
    const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
    if (!refreshToken) return new NextResponse('no refresh token', { status: 401 });
    const gotrueResponse = await fetch(`${GOTRUE_URL}/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!gotrueResponse.ok) {
      const response = new NextResponse(await gotrueResponse.text(), { status: gotrueResponse.status });
      response.cookies.delete(REFRESH_COOKIE);
      return response;
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }

  if (step === 'logout') {
    const { access_token } = await request.json().catch(() => ({ access_token: undefined }));
    if (access_token) {
      await fetch(`${GOTRUE_URL}/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${access_token}` },
      }).catch(() => undefined); // best-effort — the cookie clears either way
    }
    const response = new NextResponse(null, { status: 204 });
    response.cookies.delete(REFRESH_COOKIE);
    return response;
  }

  return new NextResponse('unknown auth action', { status: 404 });
}
```

- [ ] **Step 2: Write `lib/auth.ts`**

Multi-tab coordination: a `BroadcastChannel` lets a tab that just refreshed hand its new session to
every other open tab instead of each tab calling `/api/auth/refresh` independently (the race spec
§12 names). A `localStorage` timestamp lock is the fallback for the rare case two tabs' refresh
timers fire in the same tick before either has broadcast anything yet — the loser simply does
nothing and waits for the winner's broadcast, rather than making a redundant network call.

```ts
// apps/web/lib/auth.ts
'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

interface AuthUser {
  id: string;
  email: string;
}

interface Session {
  accessToken: string;
  expiresAt: number;
  user: AuthUser;
}

interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const REFRESH_MARGIN_MS = 60_000;
const CHANNEL_NAME = 'genql-auth';
const LOCK_KEY = 'genql_refresh_lock';
const LOCK_TTL_MS = 10_000;

function broadcastSession(session: Session | null): void {
  try {
    new BroadcastChannel(CHANNEL_NAME).postMessage({ type: 'session', session });
  } catch {
    // BroadcastChannel unsupported — this tab manages its own session only.
  }
}

function tryAcquireRefreshLock(): boolean {
  try {
    const now = Date.now();
    const raw = localStorage.getItem(LOCK_KEY);
    if (raw && now - Number(raw) < LOCK_TTL_MS) return false;
    localStorage.setItem(LOCK_KEY, String(now));
    return true;
  } catch {
    return true; // localStorage unavailable (private mode) — just proceed
  }
}

async function toSession(response: Response): Promise<Session | null> {
  if (!response.ok) return null;
  const data: { access_token: string; expires_in: number; user: AuthUser } = await response.json();
  return {
    accessToken: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
    user: data.user,
  };
}

export function AuthProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRefresh = useCallback((expiresAt: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const delay = Math.max(expiresAt - Date.now() - REFRESH_MARGIN_MS, 0);
    timerRef.current = setTimeout(() => {
      void refreshSession();
    }, delay);
    // refreshSession is declared below and stable across renders via useCallback,
    // so this closure always calls the current one.
    // eslint-disable-next-line @typescript-eslint/no-use-before-define
  }, []);

  const applySession = useCallback(
    (next: Session | null, broadcast = true) => {
      setSession(next);
      if (next) scheduleRefresh(next.expiresAt);
      else if (timerRef.current) clearTimeout(timerRef.current);
      if (broadcast) broadcastSession(next);
    },
    [scheduleRefresh],
  );

  const refreshSession = useCallback(async () => {
    if (!tryAcquireRefreshLock()) return;
    const response = await fetch('/api/auth/refresh', { method: 'POST' });
    applySession(await toSession(response));
  }, [applySession]);

  useEffect(() => {
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(CHANNEL_NAME);
      channel.onmessage = (event: MessageEvent<{ type: string; session: Session | null }>) => {
        if (event.data?.type === 'session') applySession(event.data.session, false);
      };
    } catch {
      // no BroadcastChannel support
    }
    void refreshSession().finally(() => setLoading(false));
    return () => {
      channel?.close();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error('login failed');
      applySession(await toSession(response));
    },
    [applySession],
  );

  const signup = useCallback(
    async (email: string, password: string) => {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error('signup failed');
      applySession(await toSession(response));
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: session?.accessToken }),
    });
    applySession(null);
  }, [applySession, session]);

  return (
    <AuthContext.Provider value={{ session, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
```

- [ ] **Step 3: Wrap the app in `AuthProvider`**

Edit `apps/web/app/layout.tsx` (from Task 1): wrap `{children}` in `<AuthProvider>` inside the
`<body>`, importing `AuthProvider` from `@/lib/auth`. `layout.tsx` itself stays a server component —
`AuthProvider` is a client component (`'use client'`), which Next.js allows nesting inside a server
component's tree without converting the parent.

- [ ] **Step 4: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/api/auth apps/web/lib/auth.ts apps/web/app/layout.tsx
git commit -m "feat(web): add GoTrue auth proxy and multi-tab session management"
```

---

## Task 4: Login, signup, and OAuth callback pages

**Model:** sonnet

**Files:**
- Create: `apps/web/app/(auth)/login/page.tsx`, `(auth)/signup/page.tsx`, `(auth)/callback/page.tsx`
- Modify: `apps/web/app/api/auth/[...action]/route.ts`
- Modify: `apps/web/.env.local.example`

**Interfaces:**
- Consumes: `useAuth()` (Task 3), shadcn `Button`/`Input`/`Label`/`Card` (Task 1).
- Produces: three routed pages; a new `callback` action on the auth proxy.

- [ ] **Step 1: Add `NEXT_PUBLIC_GOTRUE_URL`**

Append to `apps/web/.env.local.example`:
```
NEXT_PUBLIC_GOTRUE_URL=http://localhost:9999
```

This is deliberately public (unlike `GOTRUE_URL`): the OAuth kickoff (`GET /authorize`) is meant to
be navigated to directly by the browser, the same way any OAuth "Sign in with ..." link works — no
secret is exposed by linking to it, since GoTrue itself holds the provider client secret
server-side and this URL only starts the redirect dance.

- [ ] **Step 2: Add the `callback` action to the auth proxy**

Add this branch to `apps/web/app/api/auth/[...action]/route.ts`'s `POST` handler, alongside the
existing `signup`/`login`/`refresh`/`logout` branches — it exchanges a client-supplied refresh token
(handed to the callback page by GoTrue's own OAuth redirect) the same way the `refresh` branch
exchanges a cookie-held one, so the OAuth path ends up with an identical, cookie-backed session:

```ts
  if (step === 'callback') {
    const { refresh_token } = await request.json();
    const gotrueResponse = await fetch(`${GOTRUE_URL}/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token }),
    });
    if (!gotrueResponse.ok) {
      return new NextResponse(await gotrueResponse.text(), { status: gotrueResponse.status });
    }
    const body: GoTrueSession = await gotrueResponse.json();
    const response = NextResponse.json(sessionBody(body));
    setRefreshCookie(response, body.refresh_token);
    return response;
  }
```

- [ ] **Step 3: Write the login page**

```tsx
// apps/web/app/(auth)/login/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const GOTRUE_URL = process.env.NEXT_PUBLIC_GOTRUE_URL ?? 'http://localhost:9999';
const APP_ORIGIN = process.env.NEXT_PUBLIC_APP_ORIGIN ?? 'http://localhost:3000';

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.push('/');
    } catch {
      setError('Email or password is incorrect.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
        GenQL // Sign in
      </h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <div className="flex flex-col gap-2">
        <a
          className="text-center text-sm text-[var(--mute)] underline"
          href={`${GOTRUE_URL}/authorize?provider=google&redirect_to=${encodeURIComponent(`${APP_ORIGIN}/callback`)}`}
        >
          Continue with Google
        </a>
        <a
          className="text-center text-sm text-[var(--mute)] underline"
          href={`${GOTRUE_URL}/authorize?provider=github&redirect_to=${encodeURIComponent(`${APP_ORIGIN}/callback`)}`}
        >
          Continue with GitHub
        </a>
      </div>
      <p className="text-center text-sm text-[var(--mute)]">
        No account? <a className="underline" href="/signup">Sign up</a>
      </p>
    </main>
  );
}
```

- [ ] **Step 4: Write the signup page**

Same shape as login, calling `signup` instead of `login` and posting to `/signup`:

```tsx
// apps/web/app/(auth)/signup/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, password);
      router.push('/');
    } catch {
      setError('Could not create an account with that email.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
        GenQL // Create account
      </h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>
      <p className="text-center text-sm text-[var(--mute)]">
        Already have an account? <a className="underline" href="/login">Sign in</a>
      </p>
    </main>
  );
}
```

- [ ] **Step 5: Write the OAuth callback page**

GoTrue's `/authorize` redirect lands here with the session in the URL **fragment**
(`#access_token=...&refresh_token=...&expires_in=...`), never as query params — fragments never
reach a server, so this must run client-side to read `window.location.hash`, then hand the refresh
token to the `callback` proxy action from Step 2 to get a cookie-backed session the same way
login/signup do.

```tsx
// apps/web/app/(auth)/callback/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function OAuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const refreshToken = params.get('refresh_token');
    if (!refreshToken) {
      setError(true);
      return;
    }
    fetch('/api/auth/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then((response) => {
        if (!response.ok) throw new Error('callback exchange failed');
        // A full reload (not router.push) so AuthProvider's mount-time
        // refresh picks up the now-set cookie from a clean slate — it
        // otherwise has no way to know a new cookie just appeared.
        window.location.href = '/';
      })
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-[var(--mute)]">Sign-in did not complete. Try again.</p>
        <a className="text-sm underline" href="/login">Back to sign in</a>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 px-6">
      <p className="text-sm text-[var(--mute)]">Signing you in…</p>
    </main>
  );
}
```

- [ ] **Step 6: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/\(auth\) apps/web/app/api/auth/\[...action\]/route.ts apps/web/.env.local.example
git commit -m "feat(web): add login, signup, and OAuth callback pages"
```

---

## Task 5: Sidebar shell and `(chat)` layout

**Model:** sonnet

**Files:**
- Create: `apps/web/components/sidebar/datasource-card.tsx`, `thread-list.tsx`
- Create: `apps/web/app/(chat)/layout.tsx`

**Interfaces:**
- Consumes: `useAuth()` (Task 3), `listDatasources`/`listThreads` (Task 2), `Datasource`/
  `ThreadSummary` types (Task 1).
- Produces: `DatasourceCard`, `ThreadList` components and the `(chat)` route group's shared shell
  (sidebar + main content area), consumed by every page under `(chat)/` (Tasks 8 and this plan's
  route structure).

This is a direct build-out of `genql-chat-mockup.html`'s `.side`/`.ds-card`/`.threads`/`.thread`
markup and CSS (read that file's `<style>` block for the exact class definitions this task
translates into Tailwind arbitrary-value classes against the `tokens.css` custom properties from
Task 1 — colors, spacing, and border-radius values below are copied from it verbatim, not
reinvented).

- [ ] **Step 1: Write `DatasourceCard`**

```tsx
// apps/web/components/sidebar/datasource-card.tsx
import type { Datasource } from '@/lib/types';

export function DatasourceCard({ datasource }: { datasource: Datasource }) {
  return (
    <div>
      <p className="font-eyebrow mb-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        Datasource
      </p>
      <div className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] p-3">
        <div className="text-sm font-semibold">{datasource.name}</div>
        <div className="mt-0.5 text-xs text-[var(--mute)]">{datasource.dialect}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `ThreadList`**

```tsx
// apps/web/components/sidebar/thread-list.tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ThreadSummary } from '@/lib/types';

export function ThreadList({ threads }: { threads: ThreadSummary[] }) {
  const pathname = usePathname();

  return (
    <div className="py-1.5">
      <p className="font-eyebrow px-4.5 pb-1 pt-2.5 text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">
        Threads
      </p>
      {threads.map((thread) => {
        const href = `/thread/${thread.thread_id}`;
        const active = pathname === href;
        return (
          <Link
            key={thread.thread_id}
            href={href}
            className={`block border-l-2 px-4.5 py-2 text-sm ${
              active
                ? 'border-l-[var(--accent)] bg-[var(--panel-2)] font-semibold text-[var(--ink)]'
                : 'border-l-transparent text-[var(--mute)]'
            }`}
          >
            {thread.title}
          </Link>
        );
      })}
      {threads.length === 0 && (
        <p className="px-4.5 py-2 text-sm text-[var(--mute)]">No threads yet.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write the `(chat)` layout**

Fetches the caller's datasources and threads once the session is ready, redirects to `/login` when
there is no session. `datasource` here is a placeholder: this layout shows the first enabled
datasource in the sidebar card; the composer (Task 8) is where a user actually picks which
datasource a *new* thread targets — the sidebar card is informational for the currently active
thread's datasource, not a selector itself, matching the mockup's read-only sidebar `.ds-card`.

```tsx
// apps/web/app/(chat)/layout.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, listThreads } from '@/lib/api-client';
import { DatasourceCard } from '@/components/sidebar/datasource-card';
import { ThreadList } from '@/components/sidebar/thread-list';
import type { Datasource, ThreadSummary } from '@/lib/types';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  useEffect(() => {
    if (!loading && !session) router.push('/login');
  }, [loading, session, router]);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken).then(setDatasources).catch(() => setDatasources([]));
    listThreads(session.accessToken).then(setThreads).catch(() => setThreads([]));
  }, [session]);

  if (loading || !session) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--mute)]">Loading…</p>
      </main>
    );
  }

  return (
    <div className="grid min-h-screen grid-cols-[264px_1fr]">
      <aside className="flex flex-col border-r border-[var(--line)]">
        <div className="border-b border-[var(--line)] px-5 py-4 text-base font-bold uppercase tracking-wide">
          Gen<span className="text-[var(--accent)]">QL</span>
        </div>
        <div className="border-b border-[var(--line)] px-4.5 py-4">
          {datasources[0] && <DatasourceCard datasource={datasources[0]} />}
        </div>
        <ThreadList threads={threads} />
        <div className="font-eyebrow mt-auto border-t border-[var(--line)] px-4.5 py-3.5 text-[0.66rem] text-[var(--mute)]">
          {session.user.email}
        </div>
      </aside>
      <div className="flex min-h-screen flex-col">{children}</div>
    </div>
  );
}
```

- [ ] **Step 4: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/sidebar apps/web/app/\(chat\)/layout.tsx
git commit -m "feat(web): add sidebar shell and (chat) layout"
```

---

## Task 6: Chat components

**Model:** sonnet

**Files:**
- Create: `apps/web/components/chat/dialect-select.tsx`, `execute-button.tsx`,
  `feedback-row.tsx`, `result-table.tsx`, `sql-card.tsx`, `message-turn.tsx`

**Interfaces:**
- Consumes: `TurnRecord` type (Task 1), shadcn `Select`/`Button`/`Badge` (Task 1),
  `submitFeedback` (Task 2).
- Produces: `MessageTurn` — the single component Task 8's thread page renders once per turn, taking
  a `TurnRecord`, a `revealed: boolean`, and an `onReveal: () => void` callback (called only for the
  thread's latest, not-yet-revealed turn). **`revealed` is client-side UI state, not derived from
  the turn's data** — per spec §7's correction, `query_graph.py` runs every stage including
  execution in one uninterrupted chain, so a `TurnRecord`'s `columns`/`rows`/`row_count` are already
  populated the moment the turn exists; `Execute` withholds `ResultTable` from rendering rather than
  triggering a second fetch. Task 8 passes `revealed={true}` for every turn loaded from history (the
  user already saw those results) and tracks a `revealed: false` flag locally for a turn just
  created in the current session, until its `Execute` button is clicked.

This is a direct build-out of `genql-chat-mockup.html`'s `.turn`/`.user-msg`/`.assist`/`.recap`/

This is a direct build-out of `genql-chat-mockup.html`'s `.turn`/`.user-msg`/`.assist`/`.recap`/
`.card`/`.card-head`/`.sql`/`.exec-row`/`.btn-exec`/`.results`/`table`/`.result-foot`/`.fb` markup
and CSS — read that file's `<style>` block for the exact values (colors, spacing, radii, the
`max-height`/`opacity` transition on `.results`) this task translates into Tailwind arbitrary-value
classes against `tokens.css`'s custom properties, not new values invented here.

- [ ] **Step 1: `DialectSelect`**

```tsx
// apps/web/components/chat/dialect-select.tsx
'use client';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const DIALECTS = ['Postgres', 'Snowflake', 'BigQuery', 'MySQL', 'DuckDB'];

export function DialectSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (dialect: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="font-eyebrow h-7 w-[124px] border-[var(--line)] text-[0.68rem] uppercase">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {DIALECTS.map((dialect) => (
          <SelectItem key={dialect} value={dialect} className="font-eyebrow text-[0.68rem] uppercase">
            {dialect}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

Note: the dialect selector changes only the *label* shown on the SQL card in this phase — GenQL
generates one dialect's SQL server-side (whatever the datasource's own `dialect` is); a true
multi-dialect rewrite is out of this phase's scope per the spec, which names it only as a UI
control. `sql-card.tsx` (Step 5) treats the selection as display-only for now, and the option list
itself documents the intended future scope to whoever reads this component next.

- [ ] **Step 2: `ExecuteButton`**

The result data already exists in the `TurnRecord` (spec §7) — `onReveal` is a synchronous local
state flip, not a network call. A short artificial delay before flipping keeps the "running" feel
the mockup demonstrated, without pretending a second fetch happened.

```tsx
// apps/web/components/chat/execute-button.tsx
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

export function ExecuteButton({ onReveal }: { onReveal: () => void }) {
  const [running, setRunning] = useState(false);

  function handleClick() {
    setRunning(true);
    setTimeout(() => {
      onReveal();
      setRunning(false);
    }, 400);
  }

  return (
    <Button
      onClick={handleClick}
      disabled={running}
      className="bg-[var(--accent)] font-sans text-sm font-semibold text-[var(--accent-ink)] hover:brightness-105"
    >
      {running ? 'Running…' : '▶ Execute'}
    </Button>
  );
}
```

- [ ] **Step 3: `FeedbackRow`**

```tsx
// apps/web/components/chat/feedback-row.tsx
'use client';

import { useState } from 'react';
import { submitFeedback } from '@/lib/api-client';

export function FeedbackRow({ accessToken, threadId }: { accessToken: string; threadId: string }) {
  const [picked, setPicked] = useState<'good' | 'bad' | null>(null);

  async function pick(rating: 'good' | 'bad') {
    setPicked(rating);
    await submitFeedback(accessToken, threadId, { rating }).catch(() => setPicked(null));
  }

  const baseClass = 'font-eyebrow rounded border px-2.5 py-1 text-[0.66rem] uppercase tracking-wide';
  const idleClass = 'border-[var(--line)] bg-[var(--panel)] text-[var(--mute)]';
  const pickedClass = 'border-[var(--ok)] bg-[var(--ok-soft)] text-[var(--ok)]';

  return (
    <div className="flex gap-1.5">
      <button className={`${baseClass} ${picked === 'good' ? pickedClass : idleClass}`} onClick={() => pick('good')}>
        Helpful
      </button>
      <button className={`${baseClass} ${picked === 'bad' ? pickedClass : idleClass}`} onClick={() => pick('bad')}>
        Needs work
      </button>
      <button className={`${baseClass} ${idleClass}`} disabled>
        Suggest SQL
      </button>
    </div>
  );
}
```

- [ ] **Step 4: `ResultTable`**

```tsx
// apps/web/components/chat/result-table.tsx
import type { TurnRecord } from '@/lib/types';
import { FeedbackRow } from './feedback-row';

export function ResultTable({
  turn,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  accessToken: string;
  threadId: string;
}) {
  return (
    <div className="overflow-hidden rounded-b-md border-t border-[var(--line)]">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
          <thead>
            <tr>
              {turn.columns.map((column) => (
                <th
                  key={column}
                  className="font-sans border-b border-[var(--line)] px-3.5 py-2 text-left text-[0.68rem] font-semibold uppercase tracking-wide text-[var(--mute)]"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {turn.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-[var(--line)] px-3.5 py-2 last:border-0">
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2.5">
        <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">{turn.row_count} rows</span>
        <FeedbackRow accessToken={accessToken} threadId={threadId} />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: `SqlCard`**

```tsx
// apps/web/components/chat/sql-card.tsx
'use client';

import { useState } from 'react';
import type { TurnRecord } from '@/lib/types';
import { DialectSelect } from './dialect-select';
import { ExecuteButton } from './execute-button';
import { ResultTable } from './result-table';

export function SqlCard({
  turn,
  revealed,
  onReveal,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
}) {
  const [dialect, setDialect] = useState('Postgres');

  if (!turn.validated_sql) return null;

  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)]">
      <div className="flex items-center justify-between gap-2.5 border-b border-[var(--line)] bg-[var(--panel-2)] px-3.5 py-2">
        <span className="font-eyebrow text-[0.66rem] uppercase tracking-wide text-[var(--mute)]">SQL</span>
        <div className="flex items-center gap-2">
          <DialectSelect value={dialect} onChange={setDialect} />
          <button
            className="font-eyebrow rounded border border-[var(--line)] px-2 py-1 text-[0.68rem] uppercase text-[var(--mute)]"
            onClick={() => navigator.clipboard.writeText(turn.validated_sql ?? '')}
          >
            Copy
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto whitespace-pre-wrap px-4 py-3.5 font-mono text-[0.8rem] leading-relaxed">
        {turn.validated_sql}
      </pre>
      {revealed ? (
        <ResultTable turn={turn} accessToken={accessToken} threadId={threadId} />
      ) : (
        onReveal && (
          <div className="flex items-center justify-end border-t border-[var(--line)] px-3.5 py-2.5">
            <ExecuteButton onReveal={onReveal} />
          </div>
        )
      )}
    </div>
  );
}
```

- [ ] **Step 6: `MessageTurn`**

```tsx
// apps/web/components/chat/message-turn.tsx
import type { TurnRecord } from '@/lib/types';
import { SqlCard } from './sql-card';

export function MessageTurn({
  turn,
  isLatest,
  revealed,
  onReveal,
  accessToken,
  threadId,
}: {
  turn: TurnRecord;
  isLatest: boolean;
  revealed: boolean;
  onReveal?: () => void;
  accessToken: string;
  threadId: string;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="max-w-[70%] self-end rounded-lg rounded-br-sm bg-[var(--ink)] px-4 py-2.5 text-sm text-[var(--bg)]">
        {turn.question}
      </div>
      <div className="flex w-full flex-col gap-3">
        {turn.clarifying_question ? (
          <p className="max-w-[64ch] text-sm text-[var(--mute)]">{turn.clarifying_question}</p>
        ) : (
          <>
            {turn.recap && <p className="max-w-[64ch] text-sm text-[var(--mute)]">{turn.recap}</p>}
            <SqlCard
              turn={turn}
              revealed={revealed}
              onReveal={isLatest ? onReveal : undefined}
              accessToken={accessToken}
              threadId={threadId}
            />
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/chat
git commit -m "feat(web): add chat components (SQL card, execute gate, result table, feedback)"
```

---

## Task 7: Thread page assembly (new thread and existing thread)

**Model:** opus — the most complex integration point in this plan: reconciling the composer's three
states (fresh thread, mid-conversation follow-up, answering a paused clarification), constructing a
locally-rendered turn from a `TurnResponse` that has no `question`/`recap` fields of its own, and
tracking the reveal-gate state per turn without a data model that represents it server-side.

**Files:**
- Create: `apps/web/lib/recap.ts`
- Create: `apps/web/app/(chat)/page.tsx`, `(chat)/thread/[id]/page.tsx`

**Interfaces:**
- Consumes: `useAuth()` (Task 3), `startTurn`/`resumeTurn`/`getThread`/`listDatasources`
  (Task 2), `MessageTurn` (Task 6), `TurnResponse`/`TurnRecord`/`Datasource` types (Task 1).
- Produces: the two routed pages that make up the actual chat experience — no later task depends on
  anything this task exports, so this is the terminal integration point of the plan (aside from
  Task 8's datasources page and Task 9's settings page, which are independent).

**Why `TurnResponse` needs a client-side adapter:** `POST /v1/queries` and `.../resume` return a
`TurnResponse` (Task 1's type), which carries no `question` or `recap` field — Phase 8's backend
never echoes the question back, and "recap" was always meant to be a client-side template over
`intent`/`narrowing_suggestion`/`applied_defaults` (spec §7), not a real backend field. A turn
freshly created in the browser (not yet reloaded from `GET /v1/threads/{id}`, which *does* return
real `TurnRecordDto`s with those fields already computed server-side... except `recap` there is
also `null` today, since Phase 9a's Task 12 never computes one — re-read that task's `_record_turn`
before assuming otherwise) needs the same client-side recap template applied locally, using the
`question` the composer already has in hand. Both paths (fresh turn, reloaded history) end up
calling the same `buildRecap` helper, so a turn looks identical whichever way it arrived.

- [ ] **Step 1: Write the recap template**

```ts
// apps/web/lib/recap.ts
import type { TurnResponse } from './types';

export function buildRecap(response: TurnResponse): string | null {
  if (response.clarifying_question) return null;
  if (response.intent) return null; // a short-circuited, non-analytical turn — nothing to recap
  const parts: string[] = [];
  if (response.narrowing_suggestion) parts.push(response.narrowing_suggestion);
  if (response.applied_defaults.length > 0) {
    const defaults = response.applied_defaults.map(([dimension, rule]) => `${dimension} → ${rule}`).join(', ');
    parts.push(`Applied defaults: ${defaults}.`);
  }
  return parts.length > 0 ? parts.join(' ') : 'Understood — validated SQL is ready below.';
}
```

- [ ] **Step 2: Write a shared local-turn constructor**

Add to `apps/web/lib/recap.ts` (same file — it is the one place both pages need a `TurnResponse` →
`TurnRecord` adapter, so a second file would only split two three-line functions that always change
together):

```ts
import type { TurnRecord } from './types';

export function toLocalTurnRecord(question: string, sequence: number, response: TurnResponse): TurnRecord {
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
```

- [ ] **Step 3: Write the new-thread composer page**

`(chat)/page.tsx` shows a datasource picker and an empty composer — the only page where the user
picks which datasource a *new* thread targets (Global Constraint: datasource selection only, no
domain/table scoping). Submitting creates the thread via `startTurn` (no `thread_id` — the backend
assigns one) and navigates to the thread page, which independently loads it via `GET
/v1/threads/{id}`.

```tsx
// apps/web/app/(chat)/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { listDatasources, startTurn } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Datasource } from '@/lib/types';

export default function NewThreadPage() {
  const { session } = useAuth();
  const router = useRouter();
  const [datasources, setDatasources] = useState<Datasource[]>([]);
  const [datasource, setDatasource] = useState<string>('');
  const [question, setQuestion] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken).then((list) => {
      setDatasources(list);
      if (list[0]) setDatasource(list[0].name);
    });
  }, [session]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !datasource || !question.trim()) return;
    setSubmitting(true);
    try {
      const response = await startTurn(session.accessToken, { question, datasource });
      router.push(`/thread/${response.thread_id}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-[900px] flex-1 flex-col items-center justify-center gap-5 px-7">
      <h1 className="font-eyebrow text-xs uppercase tracking-wide text-[var(--mute)]">
        GenQL // New thread
      </h1>
      <form onSubmit={onSubmit} className="flex w-full flex-col gap-3">
        <Select value={datasource} onValueChange={setDatasource}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Choose a datasource" />
          </SelectTrigger>
          <SelectContent>
            {datasources.map((ds) => (
              <SelectItem key={ds.name} value={ds.name}>
                {ds.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2.5 pl-4">
          <input
            className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
            placeholder="Ask a question about your data…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <Button type="submit" disabled={submitting || !question.trim()}>
            {submitting ? 'Asking…' : 'Send'}
          </Button>
        </div>
      </form>
    </main>
  );
}
```

- [ ] **Step 4: Write the thread page**

Loads history on mount, distinguishes three composer states — `startTurn` for a fresh follow-up,
`resumeTurn` when the latest turn is paused on a clarifying question — and tracks which freshly
created turn (if any) is not yet revealed.

```tsx
// apps/web/app/(chat)/thread/[id]/page.tsx
'use client';

import { useEffect, useState, use as usePromise } from 'react';
import { useAuth } from '@/lib/auth';
import { getThread, resumeTurn, startTurn } from '@/lib/api-client';
import { toLocalTurnRecord } from '@/lib/recap';
import { MessageTurn } from '@/components/chat/message-turn';
import { Button } from '@/components/ui/button';
import type { ThreadDetail } from '@/lib/types';

export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: threadId } = usePromise(params);
  const { session } = useAuth();
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!session) return;
    getThread(session.accessToken, threadId).then((loaded) => {
      setDetail(loaded);
      // Every turn loaded from history was already seen by the user in an
      // earlier session — reveal all of them immediately.
      setRevealedIds(new Set(loaded.turns.map((t) => t.turn_id)));
    });
  }, [session, threadId]);

  if (!session || !detail) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-sm text-[var(--mute)]">Loading…</p>
      </main>
    );
  }

  const latest = detail.turns[detail.turns.length - 1];
  const awaitingClarification = Boolean(latest?.clarifying_question);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!session || !input.trim()) return;
    setSubmitting(true);
    try {
      const question = input;
      setInput('');
      const response = awaitingClarification
        ? await resumeTurn(session.accessToken, threadId, question)
        : await startTurn(session.accessToken, {
            question,
            datasource: detail!.summary.datasource_name,
            thread_id: threadId,
          });
      const nextSequence = detail!.turns.length;
      const localTurn = toLocalTurnRecord(question, nextSequence, response);
      setDetail((prev) => (prev ? { ...prev, turns: [...prev.turns, localTurn] } : prev));
      // A turn with no clarifying question has data to reveal on demand;
      // one that paused again has nothing to gate, so it may as well count
      // as already revealed — there is no ResultTable to withhold either way.
      if (localTurn.clarifying_question) {
        setRevealedIds((prev) => new Set(prev).add(localTurn.turn_id));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-[var(--line)] px-7 py-3.5">
        <h1 className="text-sm font-semibold">{detail.summary.title}</h1>
        <span className="font-eyebrow text-[0.68rem] text-[var(--mute)]">
          THREAD {detail.summary.thread_id}
        </span>
      </div>
      <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-6 overflow-y-auto px-7 py-6">
        {detail.turns.map((turn, index) => (
          <MessageTurn
            key={turn.turn_id}
            turn={turn}
            isLatest={index === detail.turns.length - 1}
            revealed={revealedIds.has(turn.turn_id)}
            onReveal={() => setRevealedIds((prev) => new Set(prev).add(turn.turn_id))}
            accessToken={session.accessToken}
            threadId={threadId}
          />
        ))}
      </div>
      <form onSubmit={onSubmit} className="border-t border-[var(--line)] px-7 py-4">
        <div className="mx-auto flex max-w-[900px] items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2.5 pl-4">
          <input
            className="flex-1 border-none bg-transparent text-sm outline-none placeholder:text-[var(--mute)]"
            placeholder={
              awaitingClarification
                ? 'Answer the question above…'
                : `Ask a follow-up about ${detail.summary.datasource_name}…`
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <Button type="submit" disabled={submitting || !input.trim()}>
            {submitting ? 'Asking…' : 'Send'}
          </Button>
        </div>
      </form>
    </>
  );
}
```

**Known limitation, documented rather than silently accepted:** creating a new thread on
`(chat)/page.tsx` navigates to the new thread's page without refreshing `(chat)/layout.tsx`'s
sidebar thread list (that layout fetches once on mount, per Task 5). A newly created thread will
not appear in the sidebar until the next full page load. Fixing this properly needs a shared
client-side thread-list cache or a layout-level refetch trigger, which is more machinery than this
phase's scope justifies for a cosmetic staleness window — leave it as a known gap rather than
building that machinery here.

- [ ] **Step 5: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/recap.ts apps/web/app/\(chat\)/page.tsx apps/web/app/\(chat\)/thread
git commit -m "feat(web): assemble the new-thread composer and thread conversation page"
```

---

## Task 8: Datasources page

**Model:** sonnet

**Files:**
- Create: `apps/web/app/datasources/page.tsx`

**Interfaces:**
- Consumes: `listDatasources` (Task 2), `Datasource` type (Task 1).
- Produces: a routed page listing every registered datasource.

**Scope note — read before implementing:** brainstorming settled on "datasource add is available to
all users, not just admins" (no roles in this system). But neither Phase 8 nor Phase 9a's backend
plan ever built a `POST /v1/datasources` (or any datasource-creation) endpoint — only `GET
/v1/datasources` exists. This task ships **list-only**; do not add a creation form that calls a
route the backend does not have. Adding one is real new backend scope (a new controller route, a
service method, a repository write, validation of `dsn_env_var` against the actual process
environment) that belongs in its own follow-up plan, not invented here to fill a gap silently.

- [ ] **Step 1: Write the page**

```tsx
// apps/web/app/datasources/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { listDatasources } from '@/lib/api-client';
import type { Datasource } from '@/lib/types';

export default function DatasourcesPage() {
  const { session } = useAuth();
  const [datasources, setDatasources] = useState<Datasource[] | null>(null);

  useEffect(() => {
    if (!session) return;
    listDatasources(session.accessToken).then(setDatasources);
  }, [session]);

  return (
    <main className="mx-auto max-w-[900px] px-7 py-8">
      <h1 className="font-eyebrow mb-6 text-xs uppercase tracking-wide text-[var(--mute)]">
        Datasources
      </h1>
      {datasources === null ? (
        <p className="text-sm text-[var(--mute)]">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2.5">
          {datasources.map((ds) => (
            <div
              key={ds.name}
              className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{ds.name}</span>
                <span className="font-eyebrow text-[0.66rem] uppercase text-[var(--mute)]">
                  {ds.dialect}
                </span>
              </div>
              {ds.description && (
                <p className="mt-1 text-sm text-[var(--mute)]">{ds.description}</p>
              )}
            </div>
          ))}
          {datasources.length === 0 && (
            <p className="text-sm text-[var(--mute)]">No datasources registered.</p>
          )}
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/datasources
git commit -m "feat(web): add datasources list page"
```

---

## Task 9: Settings page (profile and theme)

**Model:** haiku

**Files:**
- Create: `apps/web/app/settings/page.tsx`

**Interfaces:**
- Consumes: `getProfile`/`updateTheme` (Task 2), `useAuth()` (Task 3), `ThemePreference` type
  (Task 1).

- [ ] **Step 1: Write the page**

```tsx
// apps/web/app/settings/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { getProfile, updateTheme } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import type { ThemePreference } from '@/lib/types';

const THEMES: ThemePreference[] = ['light', 'dark', 'system'];

export default function SettingsPage() {
  const { session, logout } = useAuth();
  const [theme, setTheme] = useState<ThemePreference | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!session) return;
    getProfile(session.accessToken).then((profile) => setTheme(profile.theme_preference));
  }, [session]);

  async function onChangeTheme(next: ThemePreference) {
    if (!session) return;
    setSaving(true);
    try {
      const profile = await updateTheme(session.accessToken, next);
      setTheme(profile.theme_preference);
      document.documentElement.setAttribute(
        'data-theme',
        profile.theme_preference === 'system' ? '' : profile.theme_preference,
      );
    } finally {
      setSaving(false);
    }
  }

  if (!session) return null;

  return (
    <main className="mx-auto max-w-[560px] px-7 py-8">
      <h1 className="font-eyebrow mb-6 text-xs uppercase tracking-wide text-[var(--mute)]">
        Settings
      </h1>
      <div className="flex flex-col gap-6">
        <div>
          <p className="mb-1 text-sm font-semibold">Email</p>
          <p className="text-sm text-[var(--mute)]">{session.user.email}</p>
        </div>
        <div>
          <p className="mb-2 text-sm font-semibold">Theme</p>
          <div className="flex gap-2">
            {THEMES.map((option) => (
              <button
                key={option}
                disabled={saving}
                onClick={() => onChangeTheme(option)}
                className={`font-eyebrow rounded border px-3 py-1.5 text-[0.7rem] uppercase tracking-wide ${
                  theme === option
                    ? 'border-[var(--accent)] bg-[var(--panel-2)] text-[var(--ink)]'
                    : 'border-[var(--line)] text-[var(--mute)]'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <Button variant="outline" onClick={() => logout()}>
          Sign out
        </Button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify the app builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/settings
git commit -m "feat(web): add settings page for profile and theme"
```

---

## Task 10: Frontend test suite

**Model:** sonnet

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/vitest.config.ts`, `apps/web/vitest.setup.ts`
- Create: `apps/web/tests/chat-flow.test.tsx`, `tests/auth-forms.test.tsx`
- Create: `apps/web/playwright.config.ts`, `e2e/register-ask-execute.spec.ts`

**Interfaces:**
- Consumes: every component and page from Tasks 4-9 — this task writes no new production code.

This is the one task in this plan that writes tests — every prior task (1-9) intentionally skipped
them, per the human partner's process. No test tooling exists yet; this task installs it.

- [ ] **Step 1: Install test dependencies**

Run (from `apps/web/`):
```bash
npm install --save-dev vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/user-event @playwright/test
```

Add to `apps/web/package.json`'s `scripts`:
```json
    "test": "vitest run",
    "test:e2e": "playwright test"
```

- [ ] **Step 2: Write the Vitest config**

```ts
// apps/web/vitest.config.ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: {
    alias: { '@': __dirname },
  },
});
```

```ts
// apps/web/vitest.setup.ts
import '@testing-library/jest-dom/vitest';
```

Add `@testing-library/jest-dom` to the Step 1 install list (it was omitted above — install it
alongside the others: `npm install --save-dev @testing-library/jest-dom`).

- [ ] **Step 3: `tests/chat-flow.test.tsx`**

Tests the two behaviors Global Constraints names explicitly: results stay hidden until `Execute`,
and feedback controls appear only once a turn is revealed.

```tsx
// apps/web/tests/chat-flow.test.tsx
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageTurn } from '@/components/chat/message-turn';
import type { TurnRecord } from '@/lib/types';

const EXECUTED_TURN: TurnRecord = {
  turn_id: 't-1',
  sequence: 0,
  question: 'What were total orders per region last quarter?',
  recap: 'Understood — total orders, grouped by region.',
  validated_sql: 'select region, count(*) from sales.orders group by region;',
  clarifying_question: null,
  columns: ['region', 'orders'],
  rows: [['NA', 4812]],
  row_count: 1,
  applied_defaults: [],
  created_at: '2026-09-09T00:00:00Z',
};

describe('MessageTurn', () => {
  it('does not render a result table before Execute is clicked', () => {
    render(
      <MessageTurn
        turn={EXECUTED_TURN}
        isLatest
        revealed={false}
        onReveal={() => {}}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    expect(screen.queryByText('NA')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
  });

  it('reveals the result table and feedback controls only after Execute is clicked', async () => {
    const user = userEvent.setup();
    let revealed = false;
    const { rerender } = render(
      <MessageTurn
        turn={EXECUTED_TURN}
        isLatest
        revealed={revealed}
        onReveal={() => {
          revealed = true;
        }}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    await user.click(screen.getByRole('button', { name: /execute/i }));

    await waitFor(() => expect(revealed).toBe(true));
    rerender(
      <MessageTurn
        turn={EXECUTED_TURN}
        isLatest
        revealed={revealed}
        onReveal={() => {}}
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    expect(screen.getByText('NA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /helpful/i })).toBeInTheDocument();
  });

  it('switching the dialect selector updates its displayed value', async () => {
    const user = userEvent.setup();
    render(
      <MessageTurn
        turn={EXECUTED_TURN}
        isLatest={false}
        revealed
        accessToken="test-token"
        threadId="t-thread"
      />,
    );

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Snowflake' }));

    expect(screen.getByRole('combobox')).toHaveTextContent('Snowflake');
  });
});
```

- [ ] **Step 4: `tests/auth-forms.test.tsx`**

```tsx
// apps/web/tests/auth-forms.test.tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from '@/app/(auth)/login/page';

vi.mock('@/lib/auth', () => ({
  useAuth: () => ({
    login: vi.fn().mockRejectedValue(new Error('login failed')),
    session: null,
    loading: false,
    signup: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('LoginPage', () => {
  it('shows an error message when login fails, without redirecting', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), 'shivam@example.com');
    await user.type(screen.getByLabelText(/password/i), 'wrong-password');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/email or password is incorrect/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 5: Run the component test suite**

Run: `cd apps/web && npm run test`
Expected: all tests pass.

- [ ] **Step 6: Write the Playwright e2e smoke test**

```ts
// apps/web/playwright.config.ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
  },
});
```

```ts
// apps/web/e2e/register-ask-execute.spec.ts
import { test, expect } from '@playwright/test';

// Requires the full stack running: FastAPI backend, self-hosted GoTrue, and
// this Next.js app, all pointed at each other per apps/web/.env.local.example.
// Run manually against a real environment — this is not part of `npm run test`.
test('register, ask a question, execute, sign out', async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto('/signup');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill('a-secure-password-1');
  await page.getByRole('button', { name: /create account/i }).click();

  await expect(page).toHaveURL('/');
  await page.getByPlaceholder(/ask a question/i).fill('How many orders were placed last quarter?');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page).toHaveURL(/\/thread\//);
  await expect(page.getByRole('button', { name: /execute/i })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /execute/i }).click();
  await expect(page.getByRole('button', { name: /helpful/i })).toBeVisible();

  await page.goto('/settings');
  await page.getByRole('button', { name: /sign out/i }).click();
  await expect(page).toHaveURL('/login');
});
```

- [ ] **Step 7: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/vitest.config.ts apps/web/vitest.setup.ts apps/web/tests apps/web/playwright.config.ts apps/web/e2e
git commit -m "test(web): add component test suite and a Playwright e2e smoke test"
```
