# GenQL Phase 9 — Frontend, Auth, and Thread History

## 1. Purpose

Phase 8 put the engine behind FastAPI with SSE streaming and left explicit notes that the first
consumer of `GET /v1/queries/stream` would be "Phase 9's frontend." This phase delivers that
frontend — a Next.js chat console — and the two backend capabilities it cannot work without:
multi-user authentication and durable, listable thread history. Neither exists today. Every route
in `genql/api/controllers/` is unauthenticated, and while LangGraph's `PostgresSaver` already
checkpoints turn state under a `thread_id`, nothing records *who* started a thread or lets a client
list them.

Scope, as settled in brainstorming (revised after a spike — see §2a):

- **Auth**: self-hosted Supabase Auth (GoTrue) running as a `docker compose` service against the
  existing ParadeDB/Postgres instance — email/password and Google/GitHub social login. Not
  Supabase Cloud: GoTrue is one open-source binary, self-hosted on infrastructure GenQL already
  controls, storing its `auth.*` tables in the same database as GenQL's own `genql.*` schema. GenQL
  writes no credential-handling code at all — no password hashing, no JWT issuance, no OAuth
  client code — it only *verifies* the JWTs GoTrue issues. Flat permission model — every signed-in
  user has equal rights; no roles table.
- **Datasource scope**: the picker offers datasource selection only. `domain_id` narrowing stays a
  server-side, mostly-automatic concern (§ Phase 3's `DomainScopingService`) and is not exposed as
  a user control in this phase.
- **Thread history**: private per user. A new `genql_thread` table owns visibility; a new
  `genql_turn` table stores each turn's rendered content directly, rather than reshaping the
  checkpointer's internal graph state for display (the checkpointer stays the execution engine's
  concern; the turn table is the UI's read model).
- **Frontend**: Next.js (App Router, TypeScript), shadcn/ui + Tailwind, deployed on Vercel against
  the self-hosted FastAPI backend (and, for auth, the self-hosted GoTrue service). Chat-style
  console: sidebar (datasource + thread list), a message thread per conversation, SQL shown with a
  dialect selector, results gated behind an explicit Execute action, feedback captured
  post-execution. Visual direction is Swiss Modernism 2.0 (black / white / paper, one accent,
  strict grid) with the "Developer Mono" font pairing (IBM Plex Sans for UI text, JetBrains Mono
  for SQL/data) — validated against two rounds of reviewed mockups.
- **Settings**: profile info (email, from the JWT) and theme preference (GenQL's own
  `genql_user_profile` table — GoTrue has no concept of app-specific preferences). No API keys (not
  applicable to this product).
- **Export/inspection**: full SQL, plan text, and provenance fields (already on `TurnResponseDto`)
  are surfaced in the UI; results export as CSV/JSON from data already in the response — no new
  backend endpoint.

Out of scope, explicitly deferred: table-level (as opposed to datasource-level) query scoping,
any admin-only role, shared/team-visible threads, API key management.

---

## 2a. Why self-hosted GoTrue, and what the spike confirmed

Brainstorming first specified a fully custom DB-driven OAuth2 stack (hand-rolled password hashing,
JWT issuance, OAuth client code against Google/GitHub). That work is real and risky enough to
warrant care — password/token handling is exactly the kind of code where a subtle mistake is a
security incident, not a bug report. Self-hosted GoTrue (the same auth server Supabase Cloud runs)
eliminates that entire category of custom code while keeping every property the original brainstorm
wanted: no external managed dependency, the app's own schemas living in the same database, full
infrastructure control.

**Spike, run against the actual ParadeDB instance this project already deploys** (not a synthetic
environment): `supabase/auth:v2.196.0` (the current GoTrue image; the project was renamed from
`supabase/gotrue` to `supabase/auth` upstream) was pointed at ParadeDB with `DATABASE_URL=postgres://genql:genql@paradedb:5432/genql?search_path=auth`. Three prerequisites, none of them
GoTrue-specific quirks — every one is just "this Postgres instance doesn't happen to already have
what Supabase's own bundled Postgres image ships by convention":

1. **The `auth` schema must exist before GoTrue's own migrations run.** GoTrue creates its tables
   inside `auth.*` but does not create the schema itself.
2. **The `pgcrypto` and `uuid-ossp` extensions must be enabled.** GoTrue's migrations use both.
3. **A `postgres` role must exist** (`NOLOGIN` is fine — it only needs to be a valid grant target).
   One migration (`enable_rls_update_grants`) hardcodes `GRANT ... TO postgres`, because Supabase's
   own Postgres image always ships a superuser named `postgres`; ParadeDB's superuser here is
   `genql`.

With those three prerequisites in place, all 21 of GoTrue's migrations applied cleanly, the
container started and stayed up, and a real `POST /signup` against it created working rows in
`auth.users` and `auth.identities` and returned a valid session. No ParadeDB-specific incompatibility
exists. This spec proceeds on that basis; §3's migration handles all three prerequisites.

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/thread_summary.py
class ThreadSummary(BaseModel):
    """The sidebar's row and the ownership check's source of truth. `title`
    is the first question, truncated — good enough without a summarisation
    pass, and consistent with how the mockups render thread names."""
    model_config = ConfigDict(frozen=True)

    thread_id: str
    user_id: str                  # GoTrue's auth.users.id (a uuid, carried as text)
    datasource_name: str
    title: str
    created_at: datetime
    last_active_at: datetime

# domain/entities/turn_record.py
class TurnRecord(BaseModel):
    """One rendered turn, written after `TurnResponse` is known, so a client
    re-opening a thread gets exactly what it would have streamed live —
    without an adapter that reverse-engineers LangGraph checkpoint state."""
    model_config = ConfigDict(frozen=True)

    turn_id: str
    thread_id: str
    sequence: int                 # 0-based order within the thread
    question: str
    recap: str | None = None      # the one-line "Understood — ..." summary
    validated_sql: str | None = None
    clarifying_question: str | None = None
    result: ExecutionResult | None = None   # None until the user clicks Execute
    applied_defaults: tuple[tuple[str, str], ...] = ()
    created_at: datetime

# domain/entities/user_profile.py
class UserProfile(BaseModel):
    """The one piece of per-user state GoTrue has no concept of. `user_id`
    is GoTrue's auth.users.id, carried as plain text — GenQL never writes to
    or joins against auth.* directly, only stores this id as an opaque key,
    matching genql_feedback's existing no-cross-table-FK convention for a
    table this codebase does not own the lifecycle of."""
    model_config = ConfigDict(frozen=True)

    user_id: str
    theme_preference: Literal["light", "dark", "system"] = "system"
```

New value objects (`genql/domain/value_objects/`):

```python
# domain/value_objects/authenticated_user.py
class AuthenticatedUser(BaseModel):
    """What a verified GoTrue JWT tells GenQL about the caller. Built purely
    from JWT claims — no database round trip. `email` comes along for
    display (the settings page, feedback attribution) without a second
    lookup against auth.users, which GenQL has no standing port to query
    anyway (GoTrue owns that table's access pattern, not GenQL)."""
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/token_verifier.py
class TokenVerifier(Protocol):
    """Verifies a GoTrue-issued access token and extracts the caller's
    identity. GenQL never issues a token — only verifies one — so this port
    has no issue()/refresh() methods; token lifecycle is entirely GoTrue's."""
    def verify(self, access_token: str) -> AuthenticatedUser: ...

# domain/ports/thread_repository.py
class ThreadRepository(Protocol):
    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None: ...
    def touch(self, thread_id: str) -> None: ...                      # bumps last_active_at
    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]: ...
    def by_id(self, thread_id: str) -> ThreadSummary | None: ...      # None also covers "not yours"

# domain/ports/turn_record_repository.py
class TurnRecordRepository(Protocol):
    def append(self, record: TurnRecord) -> None: ...
    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]: ...

# domain/ports/user_profile_repository.py
class UserProfileRepository(Protocol):
    def get_or_default(self, user_id: str) -> UserProfile: ...   # a user_id GenQL has never
                                                                    # seen yet gets theme "system"
    def update_theme(self, user_id: str, theme: str) -> None: ...
```

New errors (`genql/domain/errors.py`): `InvalidAccessTokenError(GenqlError)` (a GoTrue access token
that is missing, malformed, expired, or fails signature verification — the controller translates it
to 401), `ThreadOwnershipError(GenqlError)` (raised when a `user_id` resolved from a verified token
does not match a thread's owner — translated to 404, not 403, so thread existence is not leaked to a
non-owner).

---

## 3. Migrations and the GoTrue service

New Alembic revision, `0011_thread_history_and_gotrue_prereqs.py`, in the same style as
`0006_readonly_role.py` and `0010_feedback.py`:

- `CREATE SCHEMA IF NOT EXISTS auth` — GoTrue's own container creates every table inside it on
  first boot; this migration only opens the space for it to do so.
- `CREATE EXTENSION IF NOT EXISTS pgcrypto`, `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` — GoTrue's
  migrations require both.
- A `DO $$ ... CREATE ROLE postgres NOLOGIN ... $$` guarded by an existence check — one of GoTrue's
  migrations hardcodes a grant to a role named `postgres`, which does not otherwise exist on this
  ParadeDB instance (its superuser is `genql`). This role is never granted login or any privilege
  beyond what GoTrue's own migration gives it.
- `genql_thread` (`thread_id` text pk — matches the checkpointer's own thread id, `user_id` text —
  a GoTrue `auth.users.id`, carried with no cross-schema foreign key for the same reason
  `genql_feedback.thread_id` carries none: a constraint against a table this migration set does not
  own is a liability, not a safety net — `datasource_name`, `title`, `created_at`, `last_active_at`;
  index on `(user_id, last_active_at)` for the sidebar query)
- `genql_turn` (`turn_id` uuid pk, `thread_id` fk into `genql_thread`, `sequence` int, `question`,
  `recap` nullable, `validated_sql` nullable, `clarifying_question` nullable, `result_json` jsonb
  nullable, `applied_defaults_json` jsonb, `created_at`; unique on `(thread_id, sequence)`)
- `genql_user_profile` (`user_id` text pk — a GoTrue `auth.users.id`, no cross-schema FK, same
  reasoning as `genql_thread.user_id`, `theme_preference` text with a check constraint)

**The `gotrue` service**, added to `docker/compose.yaml` beside `paradedb`:

```yaml
  gotrue:
    image: supabase/auth:v2.196.0
    depends_on:
      paradedb:
        condition: service_healthy
    environment:
      GOTRUE_DB_DRIVER: postgres
      # search_path=auth: GoTrue's migrations qualify every table as auth.*,
      # but its runtime queries do not — confirmed by the spike, which
      # 500'd on every request without this until it was added.
      DATABASE_URL: "postgres://genql:genql@paradedb:5432/genql?search_path=auth"
      GOTRUE_SITE_URL: ${GENQL_APP_ORIGIN:-http://localhost:3000}
      GOTRUE_JWT_SECRET: ${GENQL_GOTRUE_JWT_SECRET}
      GOTRUE_JWT_EXP: "900"
      PORT: "9999"
      API_EXTERNAL_URL: ${GENQL_GOTRUE_EXTERNAL_URL:-http://localhost:9999}
      GOTRUE_DISABLE_SIGNUP: "false"
      GOTRUE_EXTERNAL_GOOGLE_ENABLED: ${GENQL_GOOGLE_OAUTH_ENABLED:-false}
      GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID: ${GENQL_GOOGLE_OAUTH_CLIENT_ID:-}
      GOTRUE_EXTERNAL_GOOGLE_SECRET: ${GENQL_GOOGLE_OAUTH_CLIENT_SECRET:-}
      GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI: ${GENQL_GOOGLE_OAUTH_REDIRECT_URI:-}
      GOTRUE_EXTERNAL_GITHUB_ENABLED: ${GENQL_GITHUB_OAUTH_ENABLED:-false}
      GOTRUE_EXTERNAL_GITHUB_CLIENT_ID: ${GENQL_GITHUB_OAUTH_CLIENT_ID:-}
      GOTRUE_EXTERNAL_GITHUB_SECRET: ${GENQL_GITHUB_OAUTH_CLIENT_SECRET:-}
      GOTRUE_EXTERNAL_GITHUB_REDIRECT_URI: ${GENQL_GITHUB_OAUTH_REDIRECT_URI:-}
    ports: ["9999:9999"]
```

`GENQL_GOTRUE_JWT_SECRET` is shared between this service and GenQL's own `Settings.gotrue_jwt_secret`
(§9) — GoTrue signs with it, GenQL's `TokenVerifier` verifies with it. It is the one secret this
whole auth design has to keep consistent across two processes; everything else (password hashes,
refresh tokens, OAuth client secrets) lives and stays inside GoTrue.

---

## 4. Repositories

`genql/repositories/query/` gains `sqlalchemy_thread_repository.py` and
`sqlalchemy_turn_record_repository.py`, next to the existing `thread_lock_repository.py` — same
module, since both are about the lifecycle of a `thread_id`, just a different concern (ownership and
history, not locking). `genql/repositories/auth/sqlalchemy_user_profile_repository.py` is the one
repository this phase's auth work still needs — a two-method upsert-and-read over
`genql_user_profile`, following `genql/repositories/semantic/feedback_repository.py`'s precedent
(plain `insert`/`select`, no ORM session state leaking past the method boundary).

`genql/infrastructure/auth/gotrue_jwt_verifier.py` — the one piece of auth infrastructure code this
phase writes: decodes and verifies a GoTrue-issued JWT with `pyjwt`, HS256, against
`Settings.gotrue_jwt_secret`, reading `sub` (user id) and `email` claims into an `AuthenticatedUser`.
No issuance code exists anywhere in GenQL; this class only ever calls `jwt.decode`.

---

## 5. Services

```python
# services/query/thread_service.py
class ThreadService:
    """The read side of thread history. Writing happens inline in
    start_turn/resume_turn (below), not here, so a turn's persistence can
    never race its own execution."""
    def list_threads(self, user_id: str) -> tuple[ThreadSummary, ...]: ...
    def get_thread(self, user_id: str, thread_id: str) -> tuple[ThreadSummary, tuple[TurnRecord, ...]]: ...
    # Raises ThreadOwnershipError if the thread exists but user_id doesn't own it.

# services/auth/profile_service.py
class ProfileService:
    def get_profile(self, user_id: str) -> UserProfile: ...
    def update_theme(self, user_id: str, theme: str) -> None: ...
```

`genql/api/query_turn.py`'s `start_turn` and `resume_turn` each gain a `user_id` parameter and,
after building the `TurnResponse` exactly as today, write through `ThreadRepository` (create-or-touch)
and `TurnRecordRepository.append` before returning. This is the one place a `TurnRecord` is ever
produced, so the SSE stream and the plain POST routes stay byte-for-byte the same response shape —
history recording is an addition after the fact, not a second code path that could drift from it.

---

## 6. Controllers and auth wiring

GenQL exposes **no auth routes of its own** — no register, login, refresh, logout, or OAuth
endpoints. The frontend talks to the self-hosted GoTrue service directly (through its own Next.js
proxy — see §7) for all of that; FastAPI's job starts after a token already exists.

`genql/api/controllers/threads_controller.py` — `GET /threads`, `GET /threads/{thread_id}`.
`genql/api/controllers/profile_controller.py` — `GET /profile`, `PATCH /profile` (theme only).

`genql/api/deps.py` gains `get_current_user`, a FastAPI dependency that reads the `Authorization:
Bearer` header, calls `TokenVerifier.verify`, and raises `InvalidAccessTokenError` (→ 401) if absent
or invalid. Every route under `/v1/queries*`, `/v1/threads*`, `/v1/profile`, and the feedback route
depends on it and passes `user.user_id` through to the service call; `/v1/datasources` also requires
a signed-in user (no anonymous datasource listing) but performs no per-user filtering, matching the
flat permission model.

`/v1/queries/stream` (SSE) cannot read the `Authorization` header from a browser `EventSource`
directly — see §8. The controller itself is unchanged; the Next.js proxy is where the header gets
attached.

New DTOs (`genql/api/dtos/thread_dtos.py`, `profile_dtos.py`): `ThreadSummaryDto`, `ThreadDetailDto`
(summary plus `turns: list[TurnRecordDto]`), `ProfileDto`, `UpdateThemeRequest`.

`app.py`'s single exception handler gains `InvalidAccessTokenError` in a new `_UNAUTHORIZED` tuple
(→ 401), alongside the existing `_NOT_FOUND` tuple, which gains `ThreadOwnershipError`.

---

## 7. Frontend (Next.js)

```
apps/web/
  app/
    (auth)/login/page.tsx
    (auth)/signup/page.tsx
    (chat)/layout.tsx          # sidebar shell: datasource picker + thread list
    (chat)/page.tsx            # redirects to most recent thread or a fresh composer
    (chat)/thread/[id]/page.tsx
    datasources/page.tsx
    settings/page.tsx
    api/
      auth/[...action]/route.ts   # proxies to GoTrue's REST API, sets httpOnly cookie
      stream/route.ts             # proxies GET /v1/queries/stream, attaches Bearer, re-streams SSE
  components/
    chat/ (message-turn, sql-card, dialect-select, execute-button, result-table, feedback-row)
    sidebar/ (datasource-card, thread-list)
    ui/  # shadcn primitives
  lib/
    api-client.ts     # typed fetch wrappers over the DTOs in §6
    auth.ts           # session helpers, silent-refresh scheduling
  styles/
    tokens.css         # Swiss Modernism 2.0 palette + Developer Mono type scale, light/dark
```

`app/api/auth/[...action]/route.ts` proxies directly to GoTrue's own REST API (`GOTRUE_URL`,
server-only): `POST /signup` (register), `POST /token?grant_type=password` (login),
`POST /token?grant_type=refresh_token` (refresh), `POST /logout`. GoTrue's response
(`access_token`, `refresh_token`, `expires_in`, `user`) is stored the same way regardless of which
of these calls produced it: the refresh token in an `httpOnly` cookie the Route Handler sets, the
access token handed back to the client for the current page load only. OAuth needs no exchange code
in GenQL at all — the login page links straight to `{GOTRUE_URL}/authorize?provider=google&redirect_to=...`,
GoTrue runs the entire provider flow itself (it already holds the OAuth client secret, configured
directly on the `gotrue` service in §3) and redirects back to the app with a session, which the
`(auth)` callback page hands to the same Route Handler to set the cookie — there is no
`OAuthService`, no code that calls Google or GitHub, anywhere in this codebase.

The chat components are a direct build-out of the reviewed mockup
(`genql-chat-mockup.html`, published this session): a recap line replaces the raw stage-event
track, the SQL card carries a dialect selector, and the result table only renders once `Execute`
resolves — the same interaction the mockup demonstrates with a live click. `Execute` calls
`POST /v1/queries/{thread_id}/resume` (or the initial `POST /v1/queries` for a fresh turn) rather
than re-invoking the SSE stream, since the SQL was already validated and the user is now asking
specifically for execution — the plan/candidate/validation stages already happened during the
recap.

The recap line itself, and the initial "understood ..." framing, come from the existing
`TurnResponseDto` fields (`intent`, `narrowing_suggestion`, `applied_defaults`) — no new backend
field is needed to produce it; it is a client-side template over data already returned.

Auth pages call the Next.js `api/auth/*` route, never GoTrue directly from client-side JavaScript,
so the refresh token never reaches client-side JavaScript. `lib/auth.ts` reads the access token's
expiry (decoded client-side, not trusted, just used for timing) and calls the refresh route shortly
before it expires — GoTrue's own 900-second access-token TTL (§3) is what this scheduling is timed
against.

---

## 8. SSE across origins

`EventSource` cannot set request headers, which rules out sending a `Bearer` token directly from
the browser to `GET /v1/queries/stream` on the separately-hosted FastAPI origin. The chosen fix:
`app/api/stream/route.ts` is a Next.js Route Handler, same-origin to the browser, that reads the
session cookie, resolves the access token server-side, and does a server-to-server `fetch` to the
FastAPI backend with the `Bearer` header attached — then pipes the response body back to the
browser as its own SSE stream. The browser's `EventSource` (or `fetch` with a streaming reader)
talks only to `/api/stream` on Vercel; the FastAPI origin is never named client-side. This also
sidesteps CORS entirely for the streaming path, and keeps the one route that previously had no
auth check (the SSE route's `GET` handler takes no `Authorization` header today) covered without
changing its FastAPI signature — the query string still carries `question`, `datasource`, etc.,
exactly as today, with the `Authorization` header now added by the proxy rather than the browser.

---

## 9. Configuration

New settings (`genql/core/settings.py`): `gotrue_jwt_secret` (required, no default — startup fails
loudly without it, matching the existing pattern for other required secrets; must equal the
`gotrue` service's `GOTRUE_JWT_SECRET` in `docker/compose.yaml`).

Frontend: `NEXT_PUBLIC_APP_ORIGIN` (for building OAuth `redirect_to` URLs), `GENQL_API_ORIGIN`
(server-side only, the FastAPI backend's URL), `GOTRUE_URL` (server-side only, the self-hosted
GoTrue service's URL) — the latter two are read only inside Route Handlers and never reach the
client bundle.

---

## 10. Testing

Backend, following `tests/unit`'s existing structure: `ThreadService` ownership checks (own thread
readable, other user's thread raises); `ProfileService` (default theme for an unseen user_id, update
persists); `GoTrueJwtVerifier` against a real HS256-signed test token (valid token decodes,
tampered/expired token raises `InvalidAccessTokenError`); the `start_turn`/`resume_turn`
history-write addition, verified against a fake `TurnRecordRepository` so a turn's persisted shape
matches what it returned.

Frontend: component tests for the chat flow (dialect switch re-renders the SQL card's language tag;
clicking Execute reveals results and only then shows feedback controls) and the auth forms
(validation errors, redirect after login); one Playwright smoke test covering register → ask a
question → execute → see results → sign out.

---

## 11. Consequences for later phases

- A future table-level scoping phase can add an explicit object allow-list to `schema_linking`
  without touching auth or thread history — those layers don't know what schema_linking searched.
- A future admin/roles phase adds `app_metadata` claims in GoTrue (it already supports custom
  claims) and a dependency check in `deps.py`; nothing in this phase's own schema needs to change.
- Shared/team-visible threads, if ever wanted, become a `visibility` column on `genql_thread` plus
  a widened `list_for_user` query — the private-by-default model here is the narrower case.
- Upgrading GoTrue versions is an infrastructure change (bump the pinned tag in `docker/compose.yaml`
  and re-run its migrations on boot), not a GenQL code change — GenQL's only coupling to it is the
  shared JWT secret and the claim shape (`sub`, `email`) `GoTrueJwtVerifier` reads.

---

## 12. Risks

- **Refresh token rotation UX**: a user with the app open in two tabs can race a refresh, with the
  second tab's request landing after the first tab already rotated the token. Mitigate by having
  `lib/auth.ts` coordinate refresh through a `BroadcastChannel` (or a `localStorage` lock) so only
  one tab refreshes at a time — a frontend concern; GoTrue's own refresh-token rotation is atomic
  server-side the same way the original custom design's was.
- **Shared-secret drift**: `GENQL_GOTRUE_JWT_SECRET` must match between the `gotrue` service and
  GenQL's `Settings.gotrue_jwt_secret` exactly, or every request fails closed with 401. Both read
  from the same `.env` variable name deliberately, so a single value populates both — documented in
  `docker/compose.yaml`'s comment on the `gotrue` service.
- **GoTrue version pinning**: `supabase/auth:v2.196.0` is pinned exactly (§3) rather than tracking
  `latest`, since an upstream migration change is exactly the kind of surprise this spec's spike
  exists to rule out for the *current* version — an upgrade should re-run the same verification
  spike before the pin moves.
- **`genql_turn` duplicating `TurnResponseDto` shape**: the read-model table and the wire DTO will
  drift over time as fields are added to one and not the other. Accepted for now since it mirrors
  the same trade-off Phase 8 already made for `TurnResponseDto` versus `TurnResponse` itself —
  revisit if the duplication becomes a real maintenance cost.
