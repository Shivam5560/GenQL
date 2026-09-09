# GenQL Phase 9 — Frontend, Auth, and Thread History

## 1. Purpose

Phase 8 put the engine behind FastAPI with SSE streaming and left explicit notes that the first
consumer of `GET /v1/queries/stream` would be "Phase 9's frontend." This phase delivers that
frontend — a Next.js chat console — and the two backend capabilities it cannot work without:
multi-user authentication and durable, listable thread history. Neither exists today. Every route
in `genql/api/controllers/` is unauthenticated, and while LangGraph's `PostgresSaver` already
checkpoints turn state under a `thread_id`, nothing records *who* started a thread or lets a client
list them.

Scope, as settled in brainstorming:

- **Auth**: DB-driven OAuth2 on the existing ParadeDB/Postgres instance — email/password and
  Google/GitHub social login, JWT access + refresh tokens. No Supabase, no third-party auth
  service. Flat permission model — every signed-in user has equal rights; no roles table.
- **Datasource scope**: the picker offers datasource selection only. `domain_id` narrowing stays a
  server-side, mostly-automatic concern (§ Phase 3's `DomainScopingService`) and is not exposed as
  a user control in this phase.
- **Thread history**: private per user. A new `genql_thread` table owns visibility; a new
  `genql_turn` table stores each turn's rendered content directly, rather than reshaping the
  checkpointer's internal graph state for display (the checkpointer stays the execution engine's
  concern; the turn table is the UI's read model).
- **Frontend**: Next.js (App Router, TypeScript), shadcn/ui + Tailwind, deployed on Vercel against
  the self-hosted FastAPI backend. Chat-style console: sidebar (datasource + thread list), a
  message thread per conversation, SQL shown with a dialect selector, results gated behind an
  explicit Execute action, feedback captured post-execution. Visual direction is Swiss Modernism
  2.0 (black / white / paper, one accent, strict grid) with the "Developer Mono" font pairing
  (IBM Plex Sans for UI text, JetBrains Mono for SQL/data) — validated against two rounds of
  reviewed mockups.
- **Settings**: profile info and theme preference. No API keys (not applicable to this product).
- **Export/inspection**: full SQL, plan text, and provenance fields (already on `TurnResponseDto`)
  are surfaced in the UI; results export as CSV/JSON from data already in the response — no new
  backend endpoint.

Out of scope, explicitly deferred: table-level (as opposed to datasource-level) query scoping,
any admin-only role, shared/team-visible threads, API key management.

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/user.py
class User(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str                 # uuid4, generated at registration
    email: str
    display_name: str
    theme_preference: Literal["light", "dark", "system"] = "system"
    created_at: datetime

# domain/entities/credential.py
class Credential(BaseModel):
    """Password auth only. A user who signs in exclusively via OAuth has no
    row here — `AuthService` checks for one before offering password login,
    rather than storing a sentinel hash."""
    model_config = ConfigDict(frozen=True)

    user_id: str
    password_hash: str           # argon2id

# domain/entities/oauth_identity.py
class OAuthIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    provider: Literal["google", "github"]
    provider_user_id: str        # the provider's own subject/id, never re-derived from email

# domain/entities/refresh_token.py
class RefreshToken(BaseModel):
    """One row per issued refresh token, not per session — rotation on every
    use means a stolen-and-reused token is detectable (the old row is gone),
    which a stateless refresh JWT alone cannot give us."""
    model_config = ConfigDict(frozen=True)

    token_id: str                # uuid4; the value embedded in the JWT's jti claim
    user_id: str
    token_hash: str               # sha256 of the raw token, never the raw value
    expires_at: datetime
    revoked_at: datetime | None = None

# domain/entities/thread_summary.py
class ThreadSummary(BaseModel):
    """The sidebar's row and the ownership check's source of truth. `title`
    is the first question, truncated — good enough without a summarisation
    pass, and consistent with how the mockups render thread names."""
    model_config = ConfigDict(frozen=True)

    thread_id: str
    user_id: str
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
```

New value objects (`genql/domain/value_objects/`):

```python
# domain/value_objects/token_pair.py
class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    access_expires_in: int        # seconds, for the client to schedule a silent refresh
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/user_repository.py
class UserRepository(Protocol):
    def create(self, email: str, display_name: str) -> User: ...
    def by_id(self, user_id: str) -> User | None: ...
    def by_email(self, email: str) -> User | None: ...
    def update_theme(self, user_id: str, theme: str) -> None: ...

# domain/ports/credential_repository.py
class CredentialRepository(Protocol):
    def set(self, user_id: str, password_hash: str) -> None: ...
    def by_user_id(self, user_id: str) -> Credential | None: ...

# domain/ports/oauth_identity_repository.py
class OAuthIdentityRepository(Protocol):
    def link(self, identity: OAuthIdentity) -> None: ...
    def by_provider_id(self, provider: str, provider_user_id: str) -> OAuthIdentity | None: ...

# domain/ports/refresh_token_repository.py
class RefreshTokenRepository(Protocol):
    """Rotation is the caller's responsibility (AuthService issues a new row
    and revokes the old one in one call); the port just persists state."""
    def issue(self, token: RefreshToken) -> None: ...
    def by_id(self, token_id: str) -> RefreshToken | None: ...
    def revoke(self, token_id: str) -> None: ...

# domain/ports/password_hasher.py
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...

# domain/ports/oauth_provider_client.py
class OAuthProviderClient(Protocol):
    """One implementation per provider (Google, GitHub), selected by name in
    the composition root — never branched on inside a service."""
    def authorization_url(self, state: str, redirect_uri: str) -> str: ...
    def exchange_code(self, code: str, redirect_uri: str) -> OAuthUserInfo: ...

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
```

New errors (`genql/domain/errors.py`): `AuthError(GenqlError)`, `InvalidCredentialsError(AuthError)`,
`EmailAlreadyRegisteredError(AuthError)`, `InvalidRefreshTokenError(AuthError)`,
`OAuthExchangeError(AuthError)`, `ThreadOwnershipError(GenqlError)` (raised when a `user_id`
resolved from a JWT does not match a thread's owner — the controller translates it to 404, not
403, so thread existence is not leaked to a non-owner).

---

## 3. Migrations

New Alembic revision, `0011_auth_and_threads.py`, in the same style as `0006_readonly_role.py` and
`0010_feedback.py`:

- `genql_user` (`user_id` uuid pk, `email` unique not null, `display_name`, `theme_preference`,
  `created_at`)
- `genql_credential` (`user_id` fk unique, `password_hash`) — absent row means OAuth-only
- `genql_oauth_identity` (`user_id` fk, `provider`, `provider_user_id`; unique on
  `(provider, provider_user_id)`)
- `genql_refresh_token` (`token_id` uuid pk, `user_id` fk, `token_hash`, `expires_at`,
  `revoked_at` nullable; index on `user_id`)
- `genql_thread` (`thread_id` text pk — matches the checkpointer's own thread id, `user_id` fk,
  `datasource_name`, `title`, `created_at`, `last_active_at`; index on `(user_id, last_active_at)`
  for the sidebar query)
- `genql_turn` (`turn_id` uuid pk, `thread_id` fk, `sequence` int, `question`, `recap` nullable,
  `validated_sql` nullable, `clarifying_question` nullable, `result_json` jsonb nullable,
  `applied_defaults_json` jsonb, `created_at`; unique on `(thread_id, sequence)`)

No new Postgres extensions — this is plain relational data, unlike the vector/search tables Phase 4
added.

---

## 4. Repositories

`genql/repositories/auth/` — `sqlalchemy_user_repository.py`, `sqlalchemy_credential_repository.py`,
`sqlalchemy_oauth_identity_repository.py`, `sqlalchemy_refresh_token_repository.py`, each a thin
SQLAlchemy Core implementation of its port, following `genql/repositories/semantic/feedback_repository.py`'s
precedent (plain `insert`/`select`, no ORM session state leaking past the method boundary).

`genql/repositories/query/` gains `sqlalchemy_thread_repository.py` and
`sqlalchemy_turn_record_repository.py`, next to the existing `thread_lock_repository.py` — same
module, since both are about the lifecycle of a `thread_id`, just a different concern (ownership
and history, not locking).

`genql/infrastructure/auth/` — `argon2_password_hasher.py` (wraps `argon2-cffi`),
`google_oauth_client.py`, `github_oauth_client.py` (each a thin `httpx` wrapper implementing
`OAuthProviderClient`), and `jwt_token_issuer.py` (encodes/decodes access tokens with `pyjwt`,
HS256 with a server-side secret — no asymmetric keys needed since the same backend that issues
tokens is the only one that ever verifies them).

---

## 5. Services

```python
# services/auth/auth_service.py
class AuthService:
    """Owns the full credential lifecycle. Every method returns a TokenPair
    or raises — no method returns None to mean failure, matching the rest of
    the codebase's error-signals-failure convention."""
    def register(self, email: str, password: str, display_name: str) -> TokenPair: ...
    def login(self, email: str, password: str) -> TokenPair: ...
    def refresh(self, refresh_token: str) -> TokenPair: ...   # rotates: issues new, revokes old
    def logout(self, refresh_token: str) -> None: ...          # revokes
    def resolve_user(self, access_token: str) -> User: ...     # decodes + verifies + loads

# services/auth/oauth_service.py
class OAuthService:
    def authorization_url(self, provider: str, redirect_uri: str) -> str: ...
    def complete_login(self, provider: str, code: str, redirect_uri: str) -> TokenPair: ...
    # Finds an existing OAuthIdentity, or creates a new User + identity on
    # first login. Never links to an existing password-auth User by matching
    # email — a provider-verified email is not proof of ownership of an
    # account created another way, and silent linking is an account-takeover
    # vector worth naming explicitly here.

# services/query/thread_service.py
class ThreadService:
    """The read side of thread history. Writing happens inline in
    start_turn/resume_turn (below), not here, so a turn's persistence can
    never race its own execution."""
    def list_threads(self, user_id: str) -> tuple[ThreadSummary, ...]: ...
    def get_thread(self, user_id: str, thread_id: str) -> tuple[ThreadSummary, tuple[TurnRecord, ...]]: ...
    # Raises ThreadOwnershipError if the thread exists but user_id doesn't own it.
```

`genql/api/query_turn.py`'s `start_turn` and `resume_turn` each gain a `user_id` parameter and,
after building the `TurnResponse` exactly as today, write through `ThreadRepository` (create-or-touch)
and `TurnRecordRepository.append` before returning. This is the one place a `TurnRecord` is ever
produced, so the SSE stream and the plain POST routes stay byte-for-byte the same response shape —
history recording is an addition after the fact, not a second code path that could drift from it.

---

## 6. Controllers and auth wiring

`genql/api/controllers/auth_controller.py` — `POST /register`, `/login`, `/refresh`, `/logout`,
`GET /oauth/{provider}/start`, `GET /oauth/{provider}/callback`. Same shape as every existing
controller: DTO in, service call, DTO out, no `try` (the app's single `GenqlError` handler covers
`AuthError` the same way it covers `GenqlError` today — `InvalidCredentialsError` and
`InvalidRefreshTokenError` become 401 by adding them to a `_UNAUTHORIZED` tuple next to the
existing `_NOT_FOUND` one in `app.py`).

`genql/api/controllers/threads_controller.py` — `GET /threads`, `GET /threads/{thread_id}`.

`genql/api/deps.py` gains `get_current_user`, a FastAPI dependency that reads the `Authorization:
Bearer` header, calls `AuthService.resolve_user`, and raises `AuthError` (→ 401) if absent or
invalid. Every route under `/v1/queries*`, `/v1/threads*`, and the feedback route depends on it and
passes `user.user_id` through to the service call; `/v1/datasources` also requires a signed-in user
(no anonymous datasource listing) but performs no per-user filtering, matching the flat permission
model.

`/v1/queries/stream` (SSE) cannot read the `Authorization` header from a browser `EventSource`
directly — see §8. The controller itself is unchanged; the Next.js proxy is where the header gets
attached.

New DTOs (`genql/api/dtos/auth_dtos.py`, `thread_dtos.py`): `RegisterRequest`, `LoginRequest`,
`RefreshRequest`, `TokenPairDto`, `UserDto`, `ThreadSummaryDto`, `ThreadDetailDto` (summary plus
`turns: list[TurnRecordDto]`).

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
      auth/[...action]/route.ts   # proxies register/login/refresh/logout, sets httpOnly cookie
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

Auth pages call the Next.js `api/auth/*` route, never the FastAPI backend directly, so the refresh
token never reaches client-side JavaScript. `lib/auth.ts` reads the access token's expiry (decoded
client-side, not trusted, just used for timing) and calls the refresh route shortly before it
expires.

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

New settings (`genql/core/settings.py`): `jwt_secret` (required, no default — startup fails loudly
without it, matching the existing pattern for other required secrets), `jwt_access_ttl_seconds`
(default 900), `jwt_refresh_ttl_seconds` (default 2_592_000 — 30 days), `google_oauth_client_id` /
`_secret`, `github_oauth_client_id` / `_secret` (each optional; `OAuthService` returns
`OAuthExchangeError` for a provider with no configured client rather than the route 500ing).

Frontend: `NEXT_PUBLIC_APP_ORIGIN` (for OAuth redirect URIs), `GENQL_API_ORIGIN` (server-side only,
the FastAPI backend's URL — never exposed to the client bundle since it's read only inside Route
Handlers).

---

## 10. Testing

Backend, following `tests/unit`'s existing structure: `AuthService` against fake repositories and a
fake `PasswordHasher`/`OAuthProviderClient` (register, login, wrong password, duplicate email,
refresh rotation, revoked-token reuse rejected); `OAuthService` against a fake provider client
(first login creates a user, second login reuses it, no email-based silent linking); `ThreadService`
ownership checks (own thread readable, other user's thread raises); the `start_turn`/`resume_turn`
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
- A future admin/roles phase adds a `role` column to `genql_user` and a dependency check in
  `deps.py`; nothing in this phase's schema needs to change to support it.
- Shared/team-visible threads, if ever wanted, become a `visibility` column on `genql_thread` plus
  a widened `list_for_user` query — the private-by-default model here is the narrower case.

---

## 12. Risks

- **Refresh token rotation UX**: a user with the app open in two tabs can race a refresh, with the
  second tab's request landing after the first tab already rotated the token. Mitigate by having
  `lib/auth.ts` coordinate refresh through a `BroadcastChannel` (or a `localStorage` lock) so only
  one tab refreshes at a time — a frontend concern, not a backend one, since the backend's rotation
  is already atomic per-request.
- **OAuth provider outage**: if Google/GitHub's token endpoint is unreachable, `OAuthExchangeError`
  surfaces as a 400 today; worth a clearer error message on the login page rather than a generic
  failure toast, but not a backend change.
- **`genql_turn` duplicating `TurnResponseDto` shape**: the read-model table and the wire DTO will
  drift over time as fields are added to one and not the other. Accepted for now since it mirrors
  the same trade-off Phase 8 already made for `TurnResponseDto` versus `TurnResponse` itself —
  revisit if the duplication becomes a real maintenance cost.
