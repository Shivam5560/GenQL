# GenQL Phase 9a — Backend (Auth and Thread History) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with these process overrides from the human partner:
> 1. **No tests during implementation tasks** (Tasks 1-14). Each task ends with a commit of working code, no test-writing step. Tests are written in dedicated Task 15, after all implementation is complete.
> 2. **No per-task code review.** Do not dispatch a task reviewer after each task. Implement, commit, move to the next task. The only review is the final whole-branch review after Task 15, per subagent-driven-development's existing final-review step.
> 3. **Task briefs are copied verbatim** from this plan file via `scripts/task-brief` — never re-authored by the controller.
> 4. **Task reports must stay under 15 lines** — status, commits, one-line summary of what changed, concerns if any. No narrative.
> 5. **Model tier per task is fixed below** (marked haiku / sonnet / opus) — this replaces subagent-driven-development's own model-selection heuristic; use the tier stated on each task, not the heuristic's judgment call.
> No token budget constraint applies to implementation work itself — completeness and correctness over brevity there.

This is **Phase 9a** — the backend half of Phase 9. It stands alone: every task here touches only
Python/Postgres/docker-compose files and can be fully implemented, tested, and reviewed without the
frontend existing yet. **Phase 9b** (`docs/superpowers/plans/2026-09-09-genql-phase-9b-frontend.md`)
is the companion Next.js plan — it consumes the HTTP surface this plan produces (`GET/PATCH
/v1/profile`, `GET /v1/threads*`, the now-authenticated `/v1/queries*` and `/v1/queries/stream`) and
should not start until this plan's final review is clean, since its SSE-proxy and auth-proxy tasks
call routes this plan creates.

**Goal:** Ship self-hosted Supabase Auth (GoTrue) and the thread-history backend the Phase 9
frontend depends on, exactly as designed in the spec.

**Architecture:** FastAPI backend (self-hosted) verifies JWTs issued by a self-hosted GoTrue service (added to `docker/compose.yaml`, running against the existing ParadeDB instance) and owns a `threads` read-model (ownership + rendered turn history) plus a minimal `genql_user_profile` table, on that same Postgres database, following the codebase's established domain → services → repositories → composition layering. GenQL writes no credential-handling code — GoTrue owns registration, login, password storage, refresh-token rotation, and the entire OAuth provider flow.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, Alembic, dependency-injector, PyJWT (new, verification only), self-hosted `supabase/auth:v2.196.0` (GoTrue) via `docker compose`.

**Spec:** `docs/superpowers/specs/2026-09-09-genql-phase-9-frontend-and-auth.md` — this plan argues from that spec; every task below implements one of its backend sections (§2 through §6, §9). Read the spec's §1 (Purpose), §2a (why GoTrue, and the spike that verified it), and §2 (Domain) before Task 1.

## Global Constraints

- Flat permission model: no roles table, no admin-only routes. Every signed-in user has equal rights (spec §1).
- Datasource picker offers datasource selection only — no domain/table scoping control in the UI (spec §1).
- Thread history is private per user; no shared/team visibility (spec §1).
- GenQL writes zero credential-handling code: no password hashing, no JWT issuance, no OAuth client code. GoTrue (self-hosted) owns all of it; GenQL only verifies the JWTs it issues (spec §2a, §4).
- `GENQL_GOTRUE_JWT_SECRET` must be identical between the `gotrue` docker-compose service and `Settings.gotrue_jwt_secret` — both read from the same `.env` variable name (spec §3, §12).
- GoTrue image is pinned exactly to `supabase/auth:v2.196.0` — the version the spike verified against ParadeDB. Do not float to `latest` (spec §12).
- `genql_turn` stores rendered turn content directly — never derive thread history by reshaping LangGraph checkpoint state (spec §1, §2).
- All new Python modules follow the existing clean-architecture layering: `domain/` has no I/O; `services/` depends on ports, never on `repositories/` or `infrastructure/` directly; `composition/` is the only place concrete implementations are wired to ports.
- Every new backend route follows the existing controller convention: DTO in, service call, DTO out, no `try` in the controller — all error translation happens in `genql/api/app.py`'s single exception handler.
- GenQL never calls Google or GitHub directly, and never sees an OAuth authorization code — GoTrue's `/authorize` and its own callback handle the entire provider flow (spec §7) — this plan writes no OAuth client code anywhere.

---

## File Structure

```
genql/domain/entities/thread_summary.py, turn_record.py, user_profile.py
genql/domain/value_objects/authenticated_user.py
genql/domain/ports/token_verifier.py, thread_repository.py, turn_record_repository.py,
                   user_profile_repository.py
genql/domain/errors/auth.py, thread_history.py   # + entries in errors/__init__.py
genql/infrastructure/auth/gotrue_jwt_verifier.py
genql/repositories/auth/sqlalchemy_user_profile_repository.py
genql/repositories/query/sqlalchemy_thread_repository.py, sqlalchemy_turn_record_repository.py
genql/services/auth/profile_service.py
genql/services/query/thread_service.py
genql/composition/auth_container.py                # + composition_root.py flips to subclass it
genql/api/dtos/thread_dtos.py, profile_dtos.py
genql/api/controllers/threads_controller.py, profile_controller.py
genql/api/deps.py                                    # + get_current_user
genql/api/app.py                                     # + router registration, 401/404 mapping
genql/api/query_turn.py                              # + user_id param, history writes
genql/core/settings.py                                # + gotrue_jwt_secret
migrations/versions/0011_thread_history_and_gotrue_prereqs.py
docker/compose.yaml                                   # + gotrue service
pyproject.toml                                        # + pyjwt
```

Test suite (written last, Task 15):
```
tests/unit/test_thread_service.py, test_profile_service.py, test_gotrue_jwt_verifier.py,
                test_query_turn_history.py
```

---

## Task 1: Migration 0011 — GoTrue prerequisites and thread/profile tables

**Model:** sonnet

**Files:**
- Create: `migrations/versions/0011_thread_history_and_gotrue_prereqs.py`

**Interfaces:**
- Produces: the `auth` schema, `pgcrypto`/`uuid-ossp` extensions, and a placeholder `postgres` role
  that Task 2's `gotrue` service depends on to run its own migrations successfully (verified live in
  the spec's §2a spike — do not skip or reorder any of the three). Also produces `genql_thread`,
  `genql_turn`, `genql_user_profile` tables that every later backend task reads or writes through
  SQLAlchemy Core `text()` statements against `schema="genql"`, matching
  `migrations/versions/0010_feedback.py`'s style.

- [ ] **Step 1: Write the migration**

Follow `migrations/versions/0010_feedback.py`'s exact shape (docstring explaining the "why", explicit
`revision`/`down_revision`, `op.create_table` per table, `schema="genql"` on every GenQL-owned table
and index — note `auth` is NOT `schema="genql"`, it is its own schema GoTrue owns). Determine
`down_revision` by reading the current latest revision id in `migrations/versions/` (it was `"0010"`
as of the spec being written — confirm by checking for any newer file before setting this).

```python
"""thread history and GoTrue prerequisites

Revision ID: 0011
Revises: 0010

Two unrelated things share one revision because the second depends on the
first being live before the `gotrue` docker-compose service (Task 2) can
boot successfully — GoTrue's migrations were confirmed live against this
exact ParadeDB instance in the spec's §2a spike, needing exactly these three
prerequisites (auth schema, two extensions, a placeholder postgres role)
before they apply cleanly. genql_thread/genql_turn/genql_user_profile are
GenQL's own read-model tables, additive and independent of GoTrue's auth.*
tables, which this migration never touches.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
                CREATE ROLE postgres NOLOGIN;
            END IF;
        END
        $$
    """)

    op.create_table(
        "genql_thread",
        sa.Column("thread_id", sa.Text(), primary_key=True),
        # No foreign key into auth.users: GoTrue owns that table's lifecycle,
        # not this migration set, matching genql_feedback.thread_id's existing
        # no-cross-table-FK precedent.
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("datasource_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="genql",
    )
    op.create_index(
        "genql_thread_user_active_idx",
        "genql_thread",
        ["user_id", "last_active_at"],
        schema="genql",
    )

    op.create_table(
        "genql_turn",
        sa.Column("turn_id", sa.Text(), primary_key=True),
        sa.Column(
            "thread_id", sa.Text(), sa.ForeignKey("genql.genql_thread.thread_id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("recap", sa.Text(), nullable=True),
        sa.Column("validated_sql", sa.Text(), nullable=True),
        sa.Column("clarifying_question", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("applied_defaults_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("thread_id", "sequence", name="genql_turn_thread_sequence_uq"),
        schema="genql",
    )
    op.create_index("genql_turn_thread_idx", "genql_turn", ["thread_id"], schema="genql")

    op.create_table(
        "genql_user_profile",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column(
            "theme_preference", sa.Text(), nullable=False, server_default="system"
        ),
        sa.CheckConstraint(
            "theme_preference IN ('light', 'dark', 'system')",
            name="genql_user_profile_theme_check",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_user_profile", schema="genql")
    op.drop_index("genql_turn_thread_idx", table_name="genql_turn", schema="genql")
    op.drop_table("genql_turn", schema="genql")
    op.drop_index("genql_thread_user_active_idx", table_name="genql_thread", schema="genql")
    op.drop_table("genql_thread", schema="genql")
    # auth schema, its extensions, and the postgres role are intentionally
    # left in place on downgrade: GoTrue owns tables inside auth.* by then,
    # and dropping the schema here would destroy live GoTrue data this
    # migration set does not own.
```

- [ ] **Step 2: Verify the revision chain**

Run: `grep -rn "down_revision" migrations/versions/*.py | sort` and confirm exactly one file has
`down_revision = "0010"` (this new one) and no other file already claims it — if the codebase has
since grown an `0011` for something else, renumber this migration and adjust `down_revision`/
`revision` accordingly.

- [ ] **Step 3: Apply and check**

Run: `uv run alembic upgrade head`
Expected: migration applies with no errors; a `psql` check (or the project's usual DB-inspection
path) shows the `auth` schema, `pgcrypto`/`uuid-ossp` extensions, the `postgres` role, and all three
new `genql.*` tables.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0011_thread_history_and_gotrue_prereqs.py
git commit -m "feat(db): add GoTrue prerequisites and thread-history tables"
```

---

## Task 2: `gotrue` docker-compose service

**Model:** sonnet

**Files:**
- Modify: `docker/compose.yaml`

**Interfaces:**
- Consumes: the `paradedb` service (existing) and Task 1's migration having already run against it.
- Produces: a running GoTrue instance on port 9999, whose REST API (`/signup`, `/token`, `/logout`,
  `/authorize`) is what the frontend's `app/api/auth/[...action]/route.ts` (a later frontend task)
  proxies to, and whose issued JWTs (signed with `GENQL_GOTRUE_JWT_SECRET`) `GoTrueJwtVerifier`
  (Task 5) verifies.

- [ ] **Step 1: Add the service**

Insert into `docker/compose.yaml`, after the `paradedb` service and before `neo4j` (read the current
file first — it was last read with `paradedb` then `neo4j`, so insert between them):

```yaml
  gotrue:
    image: supabase/auth:v2.196.0
    depends_on:
      paradedb:
        condition: service_healthy
    environment:
      GOTRUE_DB_DRIVER: postgres
      # search_path=auth: GoTrue's migrations qualify every table as auth.*,
      # but its runtime queries do not — confirmed by this spec's spike,
      # which 500'd on every request without this until it was added.
      DATABASE_URL: "postgres://genql:genql@paradedb:5432/genql?search_path=auth"
      GOTRUE_SITE_URL: ${GENQL_APP_ORIGIN:-http://localhost:3000}
      # Must exactly match Settings.gotrue_jwt_secret (genql/core/settings.py)
      # — GoTrue signs with this, GenQL's GoTrueJwtVerifier verifies with it.
      GOTRUE_JWT_SECRET: ${GENQL_GOTRUE_JWT_SECRET}
      GOTRUE_JWT_EXP: "900"
      PORT: "9999"
      API_EXTERNAL_URL: ${GENQL_GOTRUE_EXTERNAL_URL:-http://localhost:9999}
      GOTRUE_DISABLE_SIGNUP: "false"
      # No SMTP is configured (the spike's logs show "Noop mail client being
      # used") so GoTrue's default confirm-by-email flow has no way to ever
      # deliver a confirmation link — without this, /signup returns a user
      # with no session, and the frontend's login-after-signup flow silently
      # gets no tokens back. Revisit if/when real email delivery is added.
      GOTRUE_MAILER_AUTOCONFIRM: "true"
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

Every `${VAR:-default}` reads from the shell/`.env` at `docker compose up` time, matching how
`POSTGRES_USER`/`POSTGRES_PASSWORD` are already handled for `paradedb` in this same file (read the
file's existing top of `paradedb`'s `environment:` block for the exact style to match, even though
those two happen to be hardcoded rather than `${...}`-substituted — the substitution syntax itself
is standard `docker compose` behavior, not a new pattern).

- [ ] **Step 2: Verify the compose file parses**

Run: `cd docker && docker compose config --quiet`
Expected: no errors (this only validates YAML/interpolation syntax; it does not require the daemon
to actually start the service — do not run `docker compose up` here unless you have been told this
task's environment has a Docker daemon available and a target Postgres to test against; the spec's
§2a spike already verified the service starts and migrates cleanly against the project's real
ParadeDB instance).

- [ ] **Step 3: Commit**

```bash
git add docker/compose.yaml
git commit -m "feat(auth): add self-hosted GoTrue service to docker compose"
```

---

## Task 3: Domain entities and value objects

**Model:** sonnet

**Files:**
- Create: `genql/domain/entities/thread_summary.py`, `turn_record.py`, `user_profile.py`
- Create: `genql/domain/value_objects/authenticated_user.py`

**Interfaces:**
- Consumes: `genql.domain.entities.execution_result.ExecutionResult` (already exists — used
  unmodified as `TurnRecord.result`'s type).
- Produces: the three entity classes and `AuthenticatedUser`, imported by every later domain/
  service/repository/controller task exactly as named below.

- [ ] **Step 1: Write each entity/value object**, matching the codebase's frozen-pydantic-model
convention (`genql/domain/entities/datasource.py`'s shape: docstring, `from __future__ import
annotations`, `BaseModel` with `model_config = ConfigDict(frozen=True)`).

```python
# genql/domain/entities/thread_summary.py
"""The sidebar's row and the ownership check's source of truth. `title` is
the first question, truncated — good enough without a summarisation pass,
and consistent with how the mockups render thread names."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ThreadSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    user_id: str
    datasource_name: str
    title: str
    created_at: datetime
    last_active_at: datetime


# genql/domain/entities/turn_record.py
"""One rendered turn, written after TurnResponse is known, so a client
re-opening a thread gets exactly what it would have streamed live — without
an adapter that reverse-engineers LangGraph checkpoint state."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_result import ExecutionResult


class TurnRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn_id: str
    thread_id: str
    sequence: int
    question: str
    recap: str | None = None
    validated_sql: str | None = None
    clarifying_question: str | None = None
    result: ExecutionResult | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
    created_at: datetime


# genql/domain/entities/user_profile.py
"""The one piece of per-user state GoTrue has no concept of. `user_id` is
GoTrue's auth.users.id, carried as plain text — GenQL never writes to or
joins against auth.* directly, only stores this id as an opaque key."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    theme_preference: Literal["light", "dark", "system"] = "system"


# genql/domain/value_objects/authenticated_user.py
"""What a verified GoTrue JWT tells GenQL about the caller. Built purely
from JWT claims — no database round trip."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
```

- [ ] **Step 2: Type-check**

Run: `uv run mypy genql/domain/entities/thread_summary.py genql/domain/entities/turn_record.py genql/domain/entities/user_profile.py genql/domain/value_objects/authenticated_user.py --strict`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add genql/domain/entities/thread_summary.py genql/domain/entities/turn_record.py genql/domain/entities/user_profile.py genql/domain/value_objects/authenticated_user.py
git commit -m "feat(domain): add thread-history and user-profile entities"
```

---

## Task 4: Domain ports and errors

**Model:** sonnet

**Files:**
- Create: `genql/domain/ports/token_verifier.py`, `thread_repository.py`,
  `turn_record_repository.py`, `user_profile_repository.py`
- Create: `genql/domain/errors/auth.py`, `genql/domain/errors/thread_history.py`
- Modify: `genql/domain/errors/__init__.py`

**Interfaces:**
- Consumes: the entities and `AuthenticatedUser` from Task 3.
- Produces: the four `Protocol` ports every repository (Task 6), infrastructure adapter (Task 5),
  and service (Tasks 9-10) implements or depends on by these exact names and signatures;
  `InvalidAccessTokenError` and `ThreadOwnershipError` that Tasks 11-14's controllers and `app.py`'s
  exception handler reference by name.

- [ ] **Step 1: Write the ports**

```python
# genql/domain/ports/token_verifier.py
"""Verifies a GoTrue-issued access token and extracts the caller's
identity. GenQL never issues a token — only verifies one — so this port has
no issue()/refresh() methods; token lifecycle is entirely GoTrue's."""

from __future__ import annotations

from typing import Protocol

from genql.domain.value_objects.authenticated_user import AuthenticatedUser


class TokenVerifier(Protocol):
    def verify(self, access_token: str) -> AuthenticatedUser: ...


# genql/domain/ports/thread_repository.py
from __future__ import annotations

from typing import Protocol

from genql.domain.entities.thread_summary import ThreadSummary


class ThreadRepository(Protocol):
    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None: ...
    def touch(self, thread_id: str) -> None: ...
    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]: ...
    def by_id(self, thread_id: str) -> ThreadSummary | None: ...


# genql/domain/ports/turn_record_repository.py
from __future__ import annotations

from typing import Protocol

from genql.domain.entities.turn_record import TurnRecord


class TurnRecordRepository(Protocol):
    def append(self, record: TurnRecord) -> None: ...
    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]: ...


# genql/domain/ports/user_profile_repository.py
from __future__ import annotations

from typing import Protocol

from genql.domain.entities.user_profile import UserProfile


class UserProfileRepository(Protocol):
    def get_or_default(self, user_id: str) -> UserProfile: ...
    def update_theme(self, user_id: str, theme: str) -> None: ...
```

- [ ] **Step 2: Write the new errors**

```python
# genql/domain/errors/auth.py
"""Failures verifying a caller's identity. GenQL issues nothing here — this
is entirely about rejecting a bad GoTrue-issued token."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class InvalidAccessTokenError(GenqlError):
    """The presented access token is missing, malformed, expired, or fails
    signature verification against Settings.gotrue_jwt_secret."""


# genql/domain/errors/thread_history.py
"""Failures raised reading thread history."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class ThreadOwnershipError(GenqlError):
    """A thread exists but does not belong to the requesting user.

    Controllers translate this to 404, not 403 — thread existence is not
    leaked to a non-owner.
    """
```

- [ ] **Step 3: Re-export from `genql/domain/errors/__init__.py`**

Add, following the file's existing per-module grouping:

```python
from genql.domain.errors.auth import InvalidAccessTokenError
from genql.domain.errors.thread_history import ThreadOwnershipError
```

and add `"InvalidAccessTokenError"`, `"ThreadOwnershipError"` to `__all__`.

- [ ] **Step 4: Type-check**

Run: `uv run mypy genql/domain/ports genql/domain/errors --strict`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add genql/domain/ports/token_verifier.py genql/domain/ports/thread_repository.py genql/domain/ports/turn_record_repository.py genql/domain/ports/user_profile_repository.py genql/domain/errors/auth.py genql/domain/errors/thread_history.py genql/domain/errors/__init__.py
git commit -m "feat(domain): add auth and thread-history ports and errors"
```

---

## Task 5: GoTrue JWT verifier

**Model:** sonnet

**Files:**
- Create: `genql/infrastructure/auth/gotrue_jwt_verifier.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `genql.domain.ports.token_verifier.TokenVerifier` (Task 4),
  `genql.domain.value_objects.authenticated_user.AuthenticatedUser` (Task 3),
  `genql.domain.errors.InvalidAccessTokenError` (Task 4).
- Produces: `GoTrueJwtVerifier`, wired into `AuthContainer` in Task 8, consumed by
  `deps.get_current_user` in Task 11. This is the only auth-related infrastructure code in the
  entire backend — it only ever calls `jwt.decode`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`'s `dependencies` list (alphabetical, matching the existing order), add:

```toml
    "pyjwt>=2.10.1",
```

Run: `uv sync`

- [ ] **Step 2: Write the verifier**

```python
# genql/infrastructure/auth/gotrue_jwt_verifier.py
"""Verifies HS256 access tokens issued by the self-hosted GoTrue service
(docker/compose.yaml's `gotrue`), using the same shared secret GoTrue signs
with (Settings.gotrue_jwt_secret == the gotrue service's GOTRUE_JWT_SECRET).

GenQL never issues a token here — this class only ever calls jwt.decode.
`sub` and `email` are the claims GoTrue's own tokens always carry; reading
them is not a guess about GoTrue's token shape, it is GoTrue's documented
JWT contract.
"""

from __future__ import annotations

import jwt

from genql.domain.errors import InvalidAccessTokenError
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

_ALGORITHM = "HS256"


class GoTrueJwtVerifier:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify(self, access_token: str) -> AuthenticatedUser:
        try:
            payload = jwt.decode(
                access_token, self._secret, algorithms=[_ALGORITHM], options={"require": ["sub", "exp"]}
            )
        except jwt.PyJWTError as exc:
            raise InvalidAccessTokenError(f"access token is invalid or expired: {exc}") from exc

        email = payload.get("email")
        if not email:
            raise InvalidAccessTokenError("access token carries no email claim")
        return AuthenticatedUser(user_id=str(payload["sub"]), email=str(email))
```

- [ ] **Step 3: Type-check**

Run: `uv run mypy genql/infrastructure/auth/gotrue_jwt_verifier.py --strict`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock genql/infrastructure/auth/gotrue_jwt_verifier.py
git commit -m "feat(auth): add GoTrue JWT verifier"
```

---

## Task 6: Thread, turn-record, and user-profile repositories

**Model:** sonnet

**Files:**
- Create: `genql/repositories/query/sqlalchemy_thread_repository.py`,
  `sqlalchemy_turn_record_repository.py`
- Create: `genql/repositories/auth/sqlalchemy_user_profile_repository.py`

**Interfaces:**
- Consumes: `genql.domain.entities.{thread_summary,turn_record,user_profile}` (Task 3), the matching
  ports (Task 4), `genql_thread`/`genql_turn`/`genql_user_profile` tables (Task 1),
  `ExecutionResult` (existing).
- Produces: `SqlAlchemyThreadRepository`, `SqlAlchemyTurnRecordRepository`,
  `SqlAlchemyUserProfileRepository`, wired into `AuthContainer` in Task 8, consumed by
  `ThreadService`/`ProfileService` (Tasks 9-10) and the modified `start_turn`/`resume_turn`
  (Task 12).

- [ ] **Step 1: Write the thread repository**

Mirror `genql/repositories/semantic/feedback_repository.py`'s shape: `text()` statements as
module-level constants, a class taking `engine: Engine`, no ORM sessions, writes wrapped in
`with self._engine.begin() as conn:`, reads via `conn.execute(...).mappings().first()` /
`.mappings().all()`.

```python
# genql/repositories/query/sqlalchemy_thread_repository.py
"""Reads and writes genql_thread — ownership and sidebar listing. `thread_id`
is never generated here: it always comes in already assigned, either by
`new_thread_id()` in query_turn.py or by an existing checkpoint, because the
checkpointer and this table must agree on the same id."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.errors import QueryError

_INSERT = text("""
    INSERT INTO genql.genql_thread (thread_id, user_id, datasource_name, title)
    VALUES (:thread_id, :user_id, :datasource_name, :title)
    ON CONFLICT (thread_id) DO NOTHING
""")
_TOUCH = text("""
    UPDATE genql.genql_thread SET last_active_at = now() WHERE thread_id = :thread_id
""")
_LIST_FOR_USER = text("""
    SELECT thread_id, user_id, datasource_name, title, created_at, last_active_at
    FROM genql.genql_thread WHERE user_id = :user_id ORDER BY last_active_at DESC
""")
_BY_ID = text("""
    SELECT thread_id, user_id, datasource_name, title, created_at, last_active_at
    FROM genql.genql_thread WHERE thread_id = :thread_id
""")


class SqlAlchemyThreadRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "datasource_name": datasource_name,
                        "title": title,
                    },
                )
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to create thread {thread_id!r}: {exc}") from exc

    def touch(self, thread_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(_TOUCH, {"thread_id": thread_id})

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_LIST_FOR_USER, {"user_id": user_id}).mappings().all()
        return tuple(ThreadSummary.model_validate(dict(row)) for row in rows)

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        with self._engine.connect() as conn:
            row = conn.execute(_BY_ID, {"thread_id": thread_id}).mappings().first()
        return ThreadSummary.model_validate(dict(row)) if row else None
```

- [ ] **Step 2: Write the turn-record repository**

`ExecutionResult` and `applied_defaults` are stored as JSON — `result_json` is `None` when the turn
has no result (paused or not yet executed), and round-trips through
`ExecutionResult.model_dump(mode="json")` / `ExecutionResult.model_validate(...)`.

```python
# genql/repositories/query/sqlalchemy_turn_record_repository.py
"""Reads and writes genql_turn — the UI's read model for a thread's history.
ExecutionResult and applied_defaults round-trip as JSON columns; nothing
here interprets their contents, matching this layer's job everywhere else
in the codebase (move bytes, don't reason about them)."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import QueryError

_INSERT = text("""
    INSERT INTO genql.genql_turn
        (turn_id, thread_id, sequence, question, recap, validated_sql,
         clarifying_question, result_json, applied_defaults_json)
    VALUES
        (:turn_id, :thread_id, :sequence, :question, :recap, :validated_sql,
         :clarifying_question, :result_json, :applied_defaults_json)
""")
_LIST_FOR_THREAD = text("""
    SELECT turn_id, thread_id, sequence, question, recap, validated_sql,
           clarifying_question, result_json, applied_defaults_json, created_at
    FROM genql.genql_turn WHERE thread_id = :thread_id ORDER BY sequence ASC
""")


class SqlAlchemyTurnRecordRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, record: TurnRecord) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "turn_id": record.turn_id,
                        "thread_id": record.thread_id,
                        "sequence": record.sequence,
                        "question": record.question,
                        "recap": record.recap,
                        "validated_sql": record.validated_sql,
                        "clarifying_question": record.clarifying_question,
                        "result_json": (
                            record.result.model_dump(mode="json") if record.result else None
                        ),
                        "applied_defaults_json": [list(pair) for pair in record.applied_defaults],
                    },
                )
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to append turn record {record.turn_id!r}: {exc}") from exc

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_LIST_FOR_THREAD, {"thread_id": thread_id}).mappings().all()
        return tuple(self._to_entity(row) for row in rows)

    @staticmethod
    def _to_entity(row: object) -> TurnRecord:
        data = dict(row)  # type: ignore[call-overload]
        result_json = data.pop("result_json")
        defaults_json = data.pop("applied_defaults_json")
        return TurnRecord(
            **data,
            result=ExecutionResult.model_validate(result_json) if result_json else None,
            applied_defaults=tuple((pair[0], pair[1]) for pair in (defaults_json or [])),
        )
```

- [ ] **Step 3: Write the user-profile repository**

`get_or_default` never raises for an unseen `user_id` — a user GenQL has never stored a preference
for gets `theme_preference="system"` without a row existing, matching `UserProfile`'s own default.

```python
# genql/repositories/auth/sqlalchemy_user_profile_repository.py
"""Reads and writes genql_user_profile — the one piece of per-user state
GoTrue has no concept of. No foreign key into auth.users, same reasoning as
genql_thread.user_id: GoTrue owns that table's lifecycle, not this
migration set."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.user_profile import UserProfile
from genql.domain.errors import QueryError

_SELECT = text("""
    SELECT user_id, theme_preference FROM genql.genql_user_profile WHERE user_id = :user_id
""")
_UPSERT = text("""
    INSERT INTO genql.genql_user_profile (user_id, theme_preference)
    VALUES (:user_id, :theme)
    ON CONFLICT (user_id) DO UPDATE SET theme_preference = EXCLUDED.theme_preference
""")


class SqlAlchemyUserProfileRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_or_default(self, user_id: str) -> UserProfile:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT, {"user_id": user_id}).mappings().first()
        return UserProfile.model_validate(dict(row)) if row else UserProfile(user_id=user_id)

    def update_theme(self, user_id: str, theme: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(_UPSERT, {"user_id": user_id, "theme": theme})
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to update theme for {user_id!r}: {exc}") from exc
```

- [ ] **Step 4: Type-check**

Run: `uv run mypy genql/repositories/query/sqlalchemy_thread_repository.py genql/repositories/query/sqlalchemy_turn_record_repository.py genql/repositories/auth/sqlalchemy_user_profile_repository.py --strict`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add genql/repositories/query/sqlalchemy_thread_repository.py genql/repositories/query/sqlalchemy_turn_record_repository.py genql/repositories/auth/sqlalchemy_user_profile_repository.py
git commit -m "feat(query): add thread, turn-record, and user-profile repositories"
```

---

## Task 7: Settings addition

**Model:** haiku

**Files:**
- Modify: `genql/core/settings.py`

**Interfaces:**
- Produces: `Settings.gotrue_jwt_secret`, consumed by `AuthContainer` (Task 8).

- [ ] **Step 1: Add the field**

Insert after the existing `golden_set_dir: str = "golden"` line, following the file's existing
comment-above-nonobvious-default convention:

```python
    # Must exactly match docker/compose.yaml's gotrue service's
    # GOTRUE_JWT_SECRET — GoTrue signs access tokens with it, GoTrueJwtVerifier
    # verifies with it. Empty by default so Settings() still constructs in
    # every test and CLI path that never touches auth, matching the
    # readonly_db_password pattern: a typed error at first use, not at import.
    gotrue_jwt_secret: str = ""
```

- [ ] **Step 2: Type-check**

Run: `uv run mypy genql/core/settings.py --strict`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add genql/core/settings.py
git commit -m "feat(config): add GoTrue JWT secret setting"
```

---

## Task 8: Composition wiring — AuthContainer

**Model:** sonnet

**Files:**
- Create: `genql/composition/auth_container.py`
- Modify: `genql/composition_root.py`

**Interfaces:**
- Consumes: `GoTrueJwtVerifier` (Task 5), the three repositories from Task 6,
  `CoreContainer.semantic_engine` and `CoreContainer.settings` (existing), `EvalContainer`
  (existing, current top of the chain).
- Produces: `AuthContainer`, providing `token_verifier`, `thread_repository`,
  `turn_record_repository`, `user_profile_repository` — every name later tasks (9-14) reference as
  `AuthContainer.<name>` when wiring services and controllers depend on `container.<name>()`
  through `genql/api/deps.py`. `composition_root.Container` now subclasses `AuthContainer` instead
  of `EvalContainer`, so every existing consumer (`serve.py`, the CLI, tests) gets these providers
  automatically.

- [ ] **Step 1: Write the container**

```python
# genql/composition/auth_container.py
"""Auth and thread-history providers: the GoTrue JWT verifier and every
repository Tasks 9-14 depend on.

Extends EvalContainer rather than adding to it in place, matching the
split-by-bounded-context convention the rest of genql/composition/ follows.
All repositories reuse CoreContainer.semantic_engine — this is the same
ParadeDB/Postgres instance the catalog and semantic store already use, not a
second database. No password hasher, no OAuth client providers, no token
issuer: GoTrue is a separate process this container never talks to directly
— it only shares a JWT secret with it.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.composition.eval_container import EvalContainer
from genql.infrastructure.auth.gotrue_jwt_verifier import GoTrueJwtVerifier
from genql.repositories.auth.sqlalchemy_user_profile_repository import (
    SqlAlchemyUserProfileRepository,
)
from genql.repositories.query.sqlalchemy_thread_repository import SqlAlchemyThreadRepository
from genql.repositories.query.sqlalchemy_turn_record_repository import (
    SqlAlchemyTurnRecordRepository,
)


class AuthContainer(EvalContainer):
    token_verifier = providers.Singleton(
        GoTrueJwtVerifier, secret=EvalContainer.settings.provided.gotrue_jwt_secret
    )

    thread_repository = providers.Singleton(
        SqlAlchemyThreadRepository, engine=EvalContainer.semantic_engine
    )
    turn_record_repository = providers.Singleton(
        SqlAlchemyTurnRecordRepository, engine=EvalContainer.semantic_engine
    )
    user_profile_repository = providers.Singleton(
        SqlAlchemyUserProfileRepository, engine=EvalContainer.semantic_engine
    )
```

- [ ] **Step 2: Flip the composition root**

In `genql/composition_root.py`, change the import and base class:

```python
from genql.composition.auth_container import AuthContainer
```

replacing the existing `from genql.composition.eval_container import EvalContainer` line, and change
`class Container(EvalContainer):` to `class Container(AuthContainer):` (read the file first to find
the exact current class declaration line before editing it).

- [ ] **Step 3: Verify the container builds**

Run: `uv run python -c "from genql.composition_root import Container; c = Container(); c.thread_repository()"`
Expected: no import or wiring error (a connection error against a real database is fine here — this
only checks that the provider graph resolves).

- [ ] **Step 4: Type-check**

Run: `uv run mypy genql/composition/auth_container.py genql/composition_root.py --strict`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add genql/composition/auth_container.py genql/composition_root.py
git commit -m "feat(composition): wire AuthContainer into the composition root"
```

---

## Task 9: ThreadService

**Model:** sonnet

**Files:**
- Create: `genql/services/query/thread_service.py`

**Interfaces:**
- Consumes: `ThreadRepository`, `TurnRecordRepository` ports (Task 4), `ThreadSummary`,
  `TurnRecord` entities (Task 3), `ThreadOwnershipError` (Task 4), `UnknownThreadError` (existing).
- Produces: `ThreadService` with `list_threads(user_id) -> tuple[ThreadSummary, ...]` and
  `get_thread(user_id, thread_id) -> tuple[ThreadSummary, tuple[TurnRecord, ...]]` — consumed by
  `threads_controller.py` (Task 13).

- [ ] **Step 1: Write the service**

```python
# genql/services/query/thread_service.py
"""The read side of thread history. Writing happens inline in
start_turn/resume_turn (Task 12), not here, so a turn's persistence can
never race its own execution."""

from __future__ import annotations

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import ThreadOwnershipError, UnknownThreadError
from genql.domain.ports.thread_repository import ThreadRepository
from genql.domain.ports.turn_record_repository import TurnRecordRepository


class ThreadService:
    def __init__(self, threads: ThreadRepository, turns: TurnRecordRepository) -> None:
        self._threads = threads
        self._turns = turns

    def list_threads(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return self._threads.list_for_user(user_id)

    def get_thread(
        self, user_id: str, thread_id: str
    ) -> tuple[ThreadSummary, tuple[TurnRecord, ...]]:
        summary = self._threads.by_id(thread_id)
        if summary is None:
            raise UnknownThreadError(thread_id)
        if summary.user_id != user_id:
            raise ThreadOwnershipError(f"thread {thread_id!r} does not belong to {user_id!r}")
        return summary, self._turns.list_for_thread(thread_id)
```

- [ ] **Step 2: Type-check**

Run: `uv run mypy genql/services/query/thread_service.py --strict`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add genql/services/query/thread_service.py
git commit -m "feat(query): add ThreadService"
```

---

## Task 10: ProfileService

**Model:** haiku

**Files:**
- Create: `genql/services/auth/profile_service.py`

**Interfaces:**
- Consumes: `UserProfileRepository` port (Task 4), `UserProfile` entity (Task 3).
- Produces: `ProfileService` with `get_profile(user_id) -> UserProfile` and
  `update_theme(user_id, theme) -> None` — consumed by `profile_controller.py` (Task 14).

- [ ] **Step 1: Write the service**

```python
# genql/services/auth/profile_service.py
"""A thin pass-through over UserProfileRepository. Exists as its own service
(rather than the controller calling the repository directly) only to match
the codebase's controller-never-touches-a-repository convention."""

from __future__ import annotations

from genql.domain.entities.user_profile import UserProfile
from genql.domain.ports.user_profile_repository import UserProfileRepository


class ProfileService:
    def __init__(self, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    def get_profile(self, user_id: str) -> UserProfile:
        return self._profiles.get_or_default(user_id)

    def update_theme(self, user_id: str, theme: str) -> None:
        self._profiles.update_theme(user_id, theme)
```

- [ ] **Step 2: Type-check**

Run: `uv run mypy genql/services/auth/profile_service.py --strict`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add genql/services/auth/profile_service.py
git commit -m "feat(auth): add ProfileService"
```

---

## Task 11: `get_current_user` dependency, auth wiring across existing routes, and CORS

**Model:** sonnet

**Files:**
- Modify: `genql/api/deps.py`
- Modify: `genql/api/controllers/query_controller.py`, `stream_controller.py`,
  `feedback_controller.py`, `datasource_controller.py`
- Modify: `genql/api/app.py`
- Modify: `genql/core/settings.py`

**Interfaces:**
- Consumes: `TokenVerifier` (Task 4), `AuthenticatedUser` (Task 3), `InvalidAccessTokenError`
  (Task 4), `AuthContainer.token_verifier` (Task 8).
- Produces: `get_current_user`, a FastAPI dependency every later controller task (12-14) uses;
  every existing route now requires a valid `Authorization: Bearer` header; `Settings.cors_allowed_origins`
  and CORS middleware, which Phase 9b's frontend plan depends on for its direct (non-proxied)
  browser-to-backend calls to be accepted at all.

- [ ] **Step 1: Add `get_current_user` to `deps.py`**

Read `genql/api/deps.py` first — it currently has one function, `get_container`. Add beside it:

```python
from typing import Annotated

from fastapi import Depends, Header

from genql.domain.errors import InvalidAccessTokenError
from genql.domain.value_objects.authenticated_user import AuthenticatedUser


def get_current_user(
    container: Annotated[Any, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if authorization is None or not authorization.startswith("Bearer "):
        raise InvalidAccessTokenError("missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ")
    return container.token_verifier().verify(token)
```

(`Any` and the existing `get_container` import are already present in the file — add the new
imports above alongside them, not as a second import block.)

- [ ] **Step 2: Apply the dependency to every existing route**

In `genql/api/controllers/query_controller.py`: both routes (`start`, `resume`) gain
`user: Annotated[AuthenticatedUser, Depends(get_current_user)]` as a parameter (import
`get_current_user` and `AuthenticatedUser`). Do not yet change what the route bodies do with
`user` — Task 12 wires `user.user_id` into `start_turn`/`resume_turn`'s new parameter; this task
only adds the dependency so Task 12 has it available.

In `genql/api/controllers/stream_controller.py`: the `stream` route gains the same dependency
parameter — but see the important note below before changing this file.

In `genql/api/controllers/feedback_controller.py`: the `submit` route gains the same dependency
parameter (unused beyond requiring auth — feedback is not scoped per-user in this design, matching
the flat permission model, so `user` is accepted but not threaded into `FeedbackService.record`).

In `genql/api/controllers/datasource_controller.py`: the `list_datasources` route gains the same
dependency parameter (also unused beyond requiring auth — no per-user filtering).

**Important note on `stream_controller.py`:** the SSE route is called by the Next.js proxy
(`app/api/stream/route.ts`, a later frontend task), which attaches the `Authorization` header
server-side — never by a browser `EventSource` directly (spec §8). Adding
`Depends(get_current_user)` here is correct and required; it does not conflict with the SSE
transport since the proxy, not the browser, is the one setting the header.

- [ ] **Step 3: Map `InvalidAccessTokenError` and `ThreadOwnershipError` in `app.py`**

Read `genql/api/app.py` first — it currently has `_NOT_FOUND = (UnknownDatasourceError,
UnknownThreadError)` and a single exception handler that returns 404 for anything in that tuple, 400
otherwise. Add:

```python
from genql.domain.errors import InvalidAccessTokenError, ThreadOwnershipError

_NOT_FOUND = (UnknownDatasourceError, UnknownThreadError, ThreadOwnershipError)
_UNAUTHORIZED = (InvalidAccessTokenError,)
```

and change the handler's status computation from:

```python
        status = 404 if isinstance(exc, _NOT_FOUND) else 400
```

to:

```python
        status = 404 if isinstance(exc, _NOT_FOUND) else 401 if isinstance(exc, _UNAUTHORIZED) else 400
```

(`ThreadOwnershipError` joins `_NOT_FOUND` here rather than getting its own tuple, per spec §6: a
non-owner must see the same 404 an unknown thread would produce.)

- [ ] **Step 4: Enable CORS for the frontend's origin**

The Phase 9b frontend plan calls this backend directly from client-side JavaScript (with
`Authorization: Bearer`, not cookies — no CSRF exposure from enabling CORS here), which the browser
will refuse without an explicit CORS allow-list. Add to `genql/core/settings.py`, alongside
`gotrue_jwt_secret`:

```python
    # Comma-separated origins allowed to call this API directly from
    # client-side JavaScript (the Phase 9b frontend). Empty by default —
    # same pattern as every other required-at-use secret in this file —
    # so no origin is trusted until explicitly configured.
    cors_allowed_origins: str = ""
```

In `genql/api/app.py`, add CORS middleware in `create_app`, immediately after the `FastAPI(...)`
construction:

```python
from fastapi.middleware.cors import CORSMiddleware


def create_app(container: Any) -> FastAPI:
    app = FastAPI(title="GenQL", version="0.1.0")
    app.state.container = container

    settings = container.settings()
    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Authorization", "Content-Type"],
        )
```

(Read `genql/api/app.py`'s current `create_app` first — this inserts after the existing
`app.state.container = container` line and before the exception handler registration, not as a
full replacement of the function.)

- [ ] **Step 5: Type-check**

Run: `uv run mypy genql/api/deps.py genql/api/controllers genql/api/app.py genql/core/settings.py --strict`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add genql/api/deps.py genql/api/controllers/query_controller.py genql/api/controllers/stream_controller.py genql/api/controllers/feedback_controller.py genql/api/controllers/datasource_controller.py genql/api/app.py genql/core/settings.py
git commit -m "feat(api): require authentication on every existing route, enable CORS for the frontend"
```

---

## Task 12: Wire thread/turn history into `start_turn` and `resume_turn`

**Model:** sonnet

**Files:**
- Modify: `genql/api/query_turn.py`
- Modify: `genql/api/controllers/query_controller.py`, `stream_controller.py`

**Interfaces:**
- Consumes: `ThreadRepository`, `TurnRecordRepository` (Task 4), `ThreadSummary`, `TurnRecord`
  (Task 3), `AuthenticatedUser` and `get_current_user` (Task 11).
- Produces: `start_turn`/`resume_turn` gain three **keyword-only, optional** parameters
  (`user_id`, `threads`, `turn_records`, each defaulting to `None`) and write history after every
  turn *only when all three are supplied* — this is the one place a `TurnRecord` is ever produced.

**Why optional, not required:** `start_turn`/`resume_turn` have three other callers beyond
`query_controller.py` — `genql/cli/commands/query.py` (the CLI), `genql/api/graph_turn_runner.py`
(the eval/ablation harness), and `tests/integration/test_phase6_5_end_to_end.py` — none of which
have a signed-in user or any business writing to `genql_thread`/`genql_turn` (the CLI is a local
single-user tool with no auth concept; the eval harness runs synthetic golden-set turns that must
never pollute real thread history). Making the three new parameters required would break all three
call sites for no benefit. Keyword-only with a `None` default means every existing positional call
in those three files, and in `tests/unit/test_query_turn.py`, keeps working completely unchanged —
history recording activates only for the one caller (the authenticated HTTP API) that opts in by
passing all three.

- [ ] **Step 1: Modify `query_turn.py`**

Read the file first (already shown in full during design). Add a helper and extend both public
functions with keyword-only parameters after their existing ones:

```python
import uuid as _uuid
from datetime import UTC, datetime

from genql.domain.entities.turn_record import TurnRecord
from genql.domain.ports.thread_repository import ThreadRepository
from genql.domain.ports.turn_record_repository import TurnRecordRepository

_TITLE_MAX_LEN = 80


def _record_turn(
    threads: ThreadRepository,
    turn_records: TurnRecordRepository,
    thread_id: str,
    user_id: str,
    datasource_name: str | None,
    question: str,
    response: TurnResponse,
) -> None:
    existing = turn_records.list_for_thread(thread_id)
    sequence = len(existing)
    if sequence == 0:
        assert datasource_name is not None  # the first turn on a thread always has one
        threads.create(thread_id, user_id, datasource_name, question[:_TITLE_MAX_LEN])
    else:
        threads.touch(thread_id)
    turn_records.append(
        TurnRecord(
            turn_id=f"tr-{_uuid.uuid4().hex}",
            thread_id=thread_id,
            sequence=sequence,
            question=question,
            validated_sql=response.validated_sql,
            clarifying_question=response.clarifying_question,
            result=response.result,
            applied_defaults=response.applied_defaults,
            created_at=datetime.now(UTC),
        )
    )


def start_turn(  # noqa: PLR0913, PLR0917 - mirrors the graph's own start parameters
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
    *,
    user_id: str | None = None,
    threads: ThreadRepository | None = None,
    turn_records: TurnRecordRepository | None = None,
) -> TurnResponse:
    resolved = thread_id or new_thread_id()
    with locks.for_thread(resolved):
        raw = run_query(graph, question, datasource_name, resolved, domain_id)
    response = to_response(resolved, raw)
    if user_id is not None and threads is not None and turn_records is not None:
        _record_turn(threads, turn_records, resolved, user_id, datasource_name, question, response)
    return response


def resume_turn(
    graph: Any,
    locks: ThreadLockFactory,
    answer: str,
    thread_id: str,
    *,
    user_id: str | None = None,
    threads: ThreadRepository | None = None,
    turn_records: TurnRecordRepository | None = None,
) -> TurnResponse:
    with locks.for_thread(thread_id):
        raw = resume_query(graph, answer, thread_id)
    response = to_response(thread_id, raw)
    if user_id is not None and threads is not None and turn_records is not None:
        _record_turn(threads, turn_records, thread_id, user_id, None, answer, response)
    return response
```

Remove the old `start_turn`/`resume_turn` definitions this replaces (their bodies are shown in full
above — this is a full replacement of both functions, not an addition beside them; every parameter
that existed before keeps its exact name, order, and default, so every existing positional call
site — the CLI, the eval harness, the integration test, `tests/unit/test_query_turn.py` — resolves
identically to before). Add the new imports at the top with the existing ones
(`from __future__ import annotations` is already present).

- [ ] **Step 2: Update `query_controller.py`'s call sites**

```python
@router.post("/queries", response_model=TurnResponseDto)
def start(
    request: StartTurnRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> TurnResponseDto:
    response = start_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.question,
        request.datasource,
        request.domain_id,
        request.thread_id,
        user_id=user.user_id,
        threads=container.thread_repository(),
        turn_records=container.turn_record_repository(),
    )
    return TurnResponseDto.from_domain(response)


@router.post("/queries/{thread_id}/resume", response_model=TurnResponseDto)
def resume(
    thread_id: str,
    request: ResumeTurnRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> TurnResponseDto:
    response = resume_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.answer,
        thread_id,
        user_id=user.user_id,
        threads=container.thread_repository(),
        turn_records=container.turn_record_repository(),
    )
    return TurnResponseDto.from_domain(response)
```

- [ ] **Step 3: Update `stream_controller.py`'s call site**

`stage_event_stream` (in `genql/api/sse/event_stream.py`) calls `run_query`/`resume_query`
internally, not `start_turn`/`resume_turn` — it does not need the new parameters, since the SSE path
never persisted history before this phase and this task does not change that: streaming stays a
live progress view, and the turn's persisted record is written when the client subsequently calls
`POST /queries` or `POST /queries/{thread_id}/resume` to actually execute (matching the frontend
design in spec §7, where `Execute` calls the POST routes, not the stream, for the persisted turn).
No change is needed in `stream_controller.py` beyond what Task 11 already added
(`Depends(get_current_user)`) — confirm this by reading `genql/api/sse/event_stream.py` and
`genql/api/query_stream.py` and verifying neither calls `start_turn`/`resume_turn` before treating
this step as a no-op.

- [ ] **Step 4: Type-check**

Run: `uv run mypy genql/api/query_turn.py genql/api/controllers/query_controller.py genql/api/controllers/stream_controller.py --strict`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add genql/api/query_turn.py genql/api/controllers/query_controller.py genql/api/controllers/stream_controller.py
git commit -m "feat(query): persist thread and turn history on every turn"
```

---

## Task 13: `threads_controller` and thread DTOs

**Model:** sonnet

**Files:**
- Create: `genql/api/dtos/thread_dtos.py`
- Create: `genql/api/controllers/threads_controller.py`
- Modify: `genql/api/app.py`

**Interfaces:**
- Consumes: `ThreadService` (Task 9), `ThreadSummary`/`TurnRecord` (Task 3), `get_current_user`
  (Task 11).
- Produces: `GET /v1/threads`, `GET /v1/threads/{thread_id}`, registered in `app.py`.

- [ ] **Step 1: Write the DTOs**

```python
# genql/api/dtos/thread_dtos.py
"""The wire contract for GET /threads and GET /threads/{id}."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord


class ThreadSummaryDto(BaseModel):
    thread_id: str
    datasource_name: str
    title: str
    created_at: datetime
    last_active_at: datetime

    @classmethod
    def from_domain(cls, summary: ThreadSummary) -> ThreadSummaryDto:
        return cls(
            thread_id=summary.thread_id,
            datasource_name=summary.datasource_name,
            title=summary.title,
            created_at=summary.created_at,
            last_active_at=summary.last_active_at,
        )


class TurnRecordDto(BaseModel):
    turn_id: str
    sequence: int
    question: str
    recap: str | None = None
    validated_sql: str | None = None
    clarifying_question: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    applied_defaults: list[list[str]] = []
    created_at: datetime

    @classmethod
    def from_domain(cls, record: TurnRecord) -> TurnRecordDto:
        result = record.result
        return cls(
            turn_id=record.turn_id,
            sequence=record.sequence,
            question=record.question,
            recap=record.recap,
            validated_sql=record.validated_sql,
            clarifying_question=record.clarifying_question,
            columns=list(result.columns) if result else [],
            rows=[list(row) for row in result.rows] if result else [],
            row_count=result.row_count if result else 0,
            applied_defaults=[list(pair) for pair in record.applied_defaults],
            created_at=record.created_at,
        )


class ThreadDetailDto(BaseModel):
    summary: ThreadSummaryDto
    turns: list[TurnRecordDto]
```

- [ ] **Step 2: Write the controller**

```python
# genql/api/controllers/threads_controller.py
"""Two routes, no logic: list the caller's threads, or read one thread's
full history. Ownership is enforced by ThreadService, which raises
ThreadOwnershipError — translated to 404 by app.py's exception handler, same
as an unknown thread, so a non-owner cannot distinguish the two."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.thread_dtos import ThreadDetailDto, ThreadSummaryDto, TurnRecordDto
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["threads"])


@router.get("/threads", response_model=list[ThreadSummaryDto])
def list_threads(
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[ThreadSummaryDto]:
    summaries = container.thread_service().list_threads(user.user_id)
    return [ThreadSummaryDto.from_domain(summary) for summary in summaries]


@router.get("/threads/{thread_id}", response_model=ThreadDetailDto)
def get_thread(
    thread_id: str,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ThreadDetailDto:
    summary, turns = container.thread_service().get_thread(user.user_id, thread_id)
    return ThreadDetailDto(
        summary=ThreadSummaryDto.from_domain(summary),
        turns=[TurnRecordDto.from_domain(turn) for turn in turns],
    )
```

- [ ] **Step 3: Add `thread_service` to `AuthContainer`**

`ThreadService` (Task 9) was not yet wired into a container — add it to `genql/composition/auth_container.py`:

```python
    thread_service = providers.Singleton(
        ThreadService,
        threads=AuthContainer.thread_repository,
        turns=AuthContainer.turn_record_repository,
    )
```

`thread_repository`/`turn_record_repository` are referenced as `AuthContainer.thread_repository` /
`AuthContainer.turn_record_repository` — Task 8 declared them on `AuthContainer` itself, and a
provider referencing a sibling provider on the same class uses the class's own name, matching how
`TurnContainer` in `genql/composition/turn_container.py` references `QueryContainer.chat_provider`.
Add the import `from genql.services.query.thread_service import ThreadService` at the top of
`auth_container.py` alongside the existing ones.

- [ ] **Step 4: Register the router in `app.py`**

Add `from genql.api.controllers import threads_controller` to the existing import block, and
`app.include_router(threads_controller.router, prefix="/v1")` alongside the other
`app.include_router` calls.

- [ ] **Step 5: Type-check**

Run: `uv run mypy genql/api/dtos/thread_dtos.py genql/api/controllers/threads_controller.py genql/composition/auth_container.py genql/api/app.py --strict`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add genql/api/dtos/thread_dtos.py genql/api/controllers/threads_controller.py genql/composition/auth_container.py genql/api/app.py
git commit -m "feat(api): add GET /threads and GET /threads/{id}"
```

---

## Task 14: `profile_controller` and profile DTOs

**Model:** haiku

**Files:**
- Create: `genql/api/dtos/profile_dtos.py`
- Create: `genql/api/controllers/profile_controller.py`
- Modify: `genql/api/app.py`
- Modify: `genql/composition/auth_container.py`

**Interfaces:**
- Consumes: `ProfileService` (Task 10), `UserProfile` (Task 3), `get_current_user` (Task 11).
- Produces: `GET /v1/profile`, `PATCH /v1/profile`, registered in `app.py`.

- [ ] **Step 1: Write the DTOs**

```python
# genql/api/dtos/profile_dtos.py
"""The wire contract for GET/PATCH /profile."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from genql.domain.entities.user_profile import UserProfile


class ProfileDto(BaseModel):
    theme_preference: Literal["light", "dark", "system"]

    @classmethod
    def from_domain(cls, profile: UserProfile) -> ProfileDto:
        return cls(theme_preference=profile.theme_preference)


class UpdateThemeRequest(BaseModel):
    theme_preference: Literal["light", "dark", "system"]
```

- [ ] **Step 2: Write the controller**

```python
# genql/api/controllers/profile_controller.py
"""Two routes, no logic: read the caller's profile, or update its theme.
Email and display name are not here — they come from the JWT, which the
frontend already has from GoTrue's own session response, so there is
nothing this route would add for them."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.profile_dtos import ProfileDto, UpdateThemeRequest
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileDto)
def get_profile(
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileDto:
    profile = container.profile_service().get_profile(user.user_id)
    return ProfileDto.from_domain(profile)


@router.patch("/profile", response_model=ProfileDto)
def update_theme(
    request: UpdateThemeRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileDto:
    container.profile_service().update_theme(user.user_id, request.theme_preference)
    profile = container.profile_service().get_profile(user.user_id)
    return ProfileDto.from_domain(profile)
```

- [ ] **Step 3: Add `profile_service` to `AuthContainer`**

In `genql/composition/auth_container.py`, add:

```python
    profile_service = providers.Singleton(
        ProfileService, profiles=AuthContainer.user_profile_repository
    )
```

with `from genql.services.auth.profile_service import ProfileService` added to the imports.

- [ ] **Step 4: Register the router in `app.py`**

Add `from genql.api.controllers import profile_controller` to the existing import block, and
`app.include_router(profile_controller.router, prefix="/v1")` alongside the other
`app.include_router` calls.

- [ ] **Step 5: Type-check**

Run: `uv run mypy genql/api/dtos/profile_dtos.py genql/api/controllers/profile_controller.py genql/composition/auth_container.py genql/api/app.py --strict`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add genql/api/dtos/profile_dtos.py genql/api/controllers/profile_controller.py genql/composition/auth_container.py genql/api/app.py
git commit -m "feat(api): add GET/PATCH /profile"
```

---

## Task 15: Backend test suite

**Model:** sonnet

**Files:**
- Create: `tests/unit/test_thread_service.py`, `test_profile_service.py`,
  `test_gotrue_jwt_verifier.py`, `test_query_turn_history.py`

**Interfaces:**
- Consumes: every domain/service/infrastructure module from Tasks 3-5, 9, 10, 12 — this task writes
  no new production code, only tests against what already exists.

This is the one task in this plan that writes tests — every prior task (1-14) intentionally skipped
them. Follow `tests/unit/test_feedback_service.py`'s convention exactly: plain pytest functions, a
small in-file fake class per port (never a mocking library), no fixtures beyond what a function
needs inline.

- [ ] **Step 1: `test_thread_service.py`**

```python
"""ThreadService's one piece of logic: a thread that exists but belongs to
someone else is indistinguishable, from the caller's side, from a thread
that never existed — both raise, never a silent None."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import ThreadOwnershipError, UnknownThreadError
from genql.services.query.thread_service import ThreadService

_NOW = datetime(2026, 9, 9, tzinfo=UTC)


class _Threads:
    def __init__(self, summaries: dict[str, ThreadSummary]) -> None:
        self._summaries = summaries

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return tuple(s for s in self._summaries.values() if s.user_id == user_id)

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        return self._summaries.get(thread_id)


class _Turns:
    def __init__(self, records: dict[str, tuple[TurnRecord, ...]]) -> None:
        self._records = records

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        return self._records.get(thread_id, ())


def _summary(thread_id: str, user_id: str) -> ThreadSummary:
    return ThreadSummary(
        thread_id=thread_id,
        user_id=user_id,
        datasource_name="retail_warehouse",
        title="a question",
        created_at=_NOW,
        last_active_at=_NOW,
    )


def test_list_threads_returns_only_the_callers_threads() -> None:
    threads = _Threads({"t-1": _summary("t-1", "u-1"), "t-2": _summary("t-2", "u-2")})
    service = ThreadService(threads, _Turns({}))

    result = service.list_threads("u-1")

    assert [t.thread_id for t in result] == ["t-1"]


def test_get_thread_returns_summary_and_turns_for_the_owner() -> None:
    turn = TurnRecord(turn_id="tr-1", thread_id="t-1", sequence=0, question="q", created_at=_NOW)
    threads = _Threads({"t-1": _summary("t-1", "u-1")})
    service = ThreadService(threads, _Turns({"t-1": (turn,)}))

    summary, turns = service.get_thread("u-1", "t-1")

    assert summary.thread_id == "t-1"
    assert turns == (turn,)


def test_get_thread_raises_for_an_unknown_thread() -> None:
    service = ThreadService(_Threads({}), _Turns({}))

    with pytest.raises(UnknownThreadError):
        service.get_thread("u-1", "t-missing")


def test_get_thread_raises_ownership_error_for_someone_elses_thread() -> None:
    threads = _Threads({"t-1": _summary("t-1", "u-2")})
    service = ThreadService(threads, _Turns({}))

    with pytest.raises(ThreadOwnershipError):
        service.get_thread("u-1", "t-1")
```

- [ ] **Step 2: `test_profile_service.py`**

```python
"""ProfileService is a thin pass-through — the one thing worth testing is
that an unseen user_id still gets a usable default rather than an error."""

from __future__ import annotations

from genql.domain.entities.user_profile import UserProfile
from genql.services.auth.profile_service import ProfileService


class _Profiles:
    def __init__(self) -> None:
        self._rows: dict[str, UserProfile] = {}

    def get_or_default(self, user_id: str) -> UserProfile:
        return self._rows.get(user_id, UserProfile(user_id=user_id))

    def update_theme(self, user_id: str, theme: str) -> None:
        self._rows[user_id] = UserProfile(user_id=user_id, theme_preference=theme)  # type: ignore[arg-type]


def test_get_profile_defaults_to_system_theme_for_an_unseen_user() -> None:
    profile = ProfileService(_Profiles()).get_profile("u-new")

    assert profile.theme_preference == "system"


def test_update_theme_persists_and_is_readable() -> None:
    service = ProfileService(_Profiles())

    service.update_theme("u-1", "dark")

    assert service.get_profile("u-1").theme_preference == "dark"
```

- [ ] **Step 3: `test_gotrue_jwt_verifier.py`**

```python
"""GoTrueJwtVerifier's whole job: accept a token signed with the right
secret carrying the right claims, reject everything else."""

from __future__ import annotations

import time

import jwt
import pytest

from genql.domain.errors import InvalidAccessTokenError
from genql.infrastructure.auth.gotrue_jwt_verifier import GoTrueJwtVerifier

_SECRET = "test-secret-do-not-use-in-production"


def _token(secret: str = _SECRET, **overrides: object) -> str:
    now = int(time.time())
    payload = {
        "sub": "u-1",
        "email": "shivam@example.com",
        "iat": now,
        "exp": now + 900,
        **overrides,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_a_validly_signed_token_verifies() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)

    user = verifier.verify(_token())

    assert user.user_id == "u-1"
    assert user.email == "shivam@example.com"


def test_a_token_signed_with_the_wrong_secret_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(_token(secret="wrong-secret"))


def test_an_expired_token_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)
    expired = _token(exp=int(time.time()) - 60)

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(expired)


def test_a_token_with_no_email_claim_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)
    now = int(time.time())
    no_email = jwt.encode(
        {"sub": "u-1", "iat": now, "exp": now + 900}, _SECRET, algorithm="HS256"
    )

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(no_email)
```

- [ ] **Step 4: `test_query_turn_history.py`**

This test exercises `_record_turn` through `start_turn` and `resume_turn`, reusing
`tests/unit/test_query_turn.py`'s own `FakeGraph`, `FakeLocks`, and `finished_state()` helpers by
importing them directly from that module rather than redefining a second, possibly-inconsistent
fake-graph shape.

```python
"""start_turn/resume_turn's one new responsibility: when called with
threads/turn_records/user_id, the thread and its turn are both persisted —
not merely that TurnResponse comes back correctly, which
test_query_turn.py already covers exhaustively. Reuses that file's
FakeGraph/FakeLocks/finished_state() rather than redefining them."""

from __future__ import annotations

from datetime import UTC, datetime

from genql.api.query_turn import resume_turn, start_turn
from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from tests.unit.test_query_turn import FakeGraph, FakeLocks, finished_state


class _Threads:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str, str]] = []
        self.touched: list[str] = []

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        self.created.append((thread_id, user_id, datasource_name, title))

    def touch(self, thread_id: str) -> None:
        self.touched.append(thread_id)

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return ()

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        return None


class _TurnRecords:
    def __init__(self) -> None:
        self.appended: list[TurnRecord] = []

    def append(self, record: TurnRecord) -> None:
        self.appended.append(record)

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        return tuple(r for r in self.appended if r.thread_id == thread_id)


def test_start_turn_without_history_args_records_nothing() -> None:
    """The default (no threads/turn_records/user_id) is what the CLI and
    eval harness call today — it must keep writing nothing, exactly as
    before this phase."""
    start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local", thread_id="t-1")
    # No repositories were even constructed; nothing to assert against but
    # that this call raises nothing extra — covered by it simply returning.


def test_start_turn_creates_the_thread_and_appends_the_first_turn_record() -> None:
    threads = _Threads()
    turn_records = _TurnRecords()

    start_turn(
        FakeGraph(finished_state()),
        FakeLocks(),
        "a question",
        "retail_warehouse",
        thread_id="t-1",
        user_id="u-1",
        threads=threads,
        turn_records=turn_records,
    )

    assert threads.created == [("t-1", "u-1", "retail_warehouse", "a question")]
    assert threads.touched == []
    assert len(turn_records.appended) == 1
    assert turn_records.appended[0].sequence == 0
    assert turn_records.appended[0].question == "a question"
    assert turn_records.appended[0].validated_sql == "SELECT 7 LIMIT 1"


def test_resume_turn_touches_the_thread_and_appends_a_later_turn_record() -> None:
    threads = _Threads()
    turn_records = _TurnRecords()
    turn_records.appended.append(
        TurnRecord(
            turn_id="tr-0",
            thread_id="t-1",
            sequence=0,
            question="first",
            created_at=datetime.now(UTC),
        )
    )

    resume_turn(
        FakeGraph(finished_state()),
        FakeLocks(),
        "a follow-up",
        "t-1",
        user_id="u-1",
        threads=threads,
        turn_records=turn_records,
    )

    assert threads.touched == ["t-1"]
    assert threads.created == []
    assert len(turn_records.appended) == 2
    assert turn_records.appended[1].sequence == 1
    assert turn_records.appended[1].question == "a follow-up"
```

- [ ] **Step 5: Run the full new test set**

Run: `uv run pytest tests/unit/test_thread_service.py tests/unit/test_profile_service.py tests/unit/test_gotrue_jwt_verifier.py tests/unit/test_query_turn_history.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_thread_service.py tests/unit/test_profile_service.py tests/unit/test_gotrue_jwt_verifier.py tests/unit/test_query_turn_history.py
git commit -m "test(auth): add backend test suite for thread history, profile, and JWT verification"
```
