# GenQL Phase 2.5: Datasource and Schema Levels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert `datasource` above `schema` and make `schema` a registered first-class object, so GenQL can ingest *n* schemas across *n* databases and address a subset of them as the scope of a discovery run or a query.

**Architecture:** Identity becomes a three-level natural key — `datasource → schema → object → column` — with `Datasource.name` as a `TEXT` primary key and `ON DELETE CASCADE` doing the cleanup. Services never see an `Engine`: a new `CatalogReaderFactory` port hands them a reader bound to a `Datasource` they loaded through a repository port, so the existing import-linter contracts hold unchanged. Warehouse credentials stay out of the semantic store — a datasource row names an environment variable, and the DSN is read from the process environment at connect time.

**Tech Stack:** Python 3.12 (uv), ParadeDB 0.25.6 on PostgreSQL 18, psycopg 3, SQLAlchemy 2.0 Core, Alembic, Pydantic v2, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-06-genql-phase-2-5-datasource-and-schema-levels.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

## Global Constraints

- Python 3.12 exactly. Managed by `uv`; do not use system Python. Run everything through `uv run`.
- ParadeDB image `paradedb/paradedb:0.25.6-pg18`. Do not substitute plain `postgres`.
- **No SQL string, SQLAlchemy Core construct, or psycopg call may appear outside `genql/repositories/`.** Enforced by import-linter. `genql/infrastructure/db/` may import `sqlalchemy` to *build* an engine, but never to execute a statement.
- `genql/domain/` imports no other `genql` package and performs no I/O.
- `genql/services/` imports only `genql.domain`. It may not import `genql.repositories`, `genql.infrastructure`, `psycopg`, `sqlalchemy`, or `neo4j`.
- Every file ≤ 250 lines. Enforced by a pre-commit hook (`scripts/check_file_length.py`).
- One class per file. One action per file.
- `mypy --strict` must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass.
- All entities and value objects are **frozen** Pydantic v2 models (`model_config = ConfigDict(frozen=True)`).
- Pydantic v2 forbids a field named `schema` (it shadows the deprecated `BaseModel.schema()` and raises `NameError`). The field is always `schema_name`.
- Commit after every task. Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`).
- Docker runs on the Debian VM (`ssh genql-vm`, 100.99.72.99), not locally. Integration tests connect over Tailscale. Every test command in this plan is prefixed with the three environment variables that point at it:

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  ```

  Put these in your shell once at the start; the plan writes `uv run pytest ...` assuming they are set.
- The baseline before Task 1 is **49 passing tests**. Every task must end with the full suite green — never leave a task boundary with a red suite.

---

## File Structure

**Created**

```
genql/domain/value_objects/schema_ref.py              SchemaRef — (datasource, schema) identity
genql/domain/value_objects/query_scope.py             QueryScope — one datasource, n schemas
genql/domain/entities/datasource.py                   Datasource entity
genql/domain/entities/schema_registration.py          SchemaRegistration entity
genql/domain/ports/datasource_repository.py           DatasourceRepository protocol
genql/domain/ports/schema_registration_repository.py  SchemaRegistrationRepository protocol
genql/domain/ports/catalog_reader_factory.py          CatalogReaderFactory protocol
genql/domain/ports/profile_reader_factory.py          ProfileReaderFactory protocol
genql/domain/ports/scope_resolver.py                  ScopeResolver protocol
genql/repositories/warehouse/registry.py              CATALOG_READERS, PROFILE_READERS
genql/repositories/semantic/datasource_repository.py          SQL over genql_datasource
genql/repositories/semantic/schema_registration_repository.py SQL over genql_schema
genql/infrastructure/db/engine_provider.py            DatasourceEngineProvider
genql/infrastructure/catalog/__init__.py
genql/infrastructure/catalog/catalog_reader_factory.py   CatalogReaderFactoryImpl
genql/infrastructure/catalog/profile_reader_factory.py   ProfileReaderFactoryImpl
genql/services/datasource/__init__.py
genql/services/datasource/datasource_service.py       register/list/remove datasources
genql/services/datasource/schema_registration_service.py  register/list/remove schemas
genql/services/scope/__init__.py                      imports both resolvers for registration
genql/services/scope/registry.py                      SCOPE_RESOLVERS
genql/services/scope/explicit_scope_resolver.py       ExplicitScopeResolver
genql/services/scope/default_scope_resolver.py        DefaultScopeResolver
genql/cli/commands/__init__.py
genql/cli/commands/datasource.py                      `genql datasource` sub-app
genql/cli/commands/schema.py                          `genql schema` sub-app
migrations/versions/0003_datasource_and_schema.py     the re-keying migration
data/seed_pagila.sh                                   MODIFIED — runs through docker exec on the VM
tests/unit/test_schema_ref.py
tests/unit/test_query_scope.py
tests/unit/test_datasource_entities.py
tests/unit/test_engine_provider.py
tests/unit/test_catalog_reader_factory.py
tests/unit/test_datasource_service.py
tests/unit/test_schema_registration_service.py
tests/unit/test_scope_resolvers.py
tests/unit/test_run_scope.py
tests/integration/test_migration_0003.py
tests/integration/test_datasource_repository.py
tests/integration/test_schema_registration_repository.py
tests/integration/test_cli_datasource.py
tests/integration/test_multi_datasource_discovery.py
```

**Modified**

```
genql/domain/entities/database_object.py    + datasource_name
genql/domain/entities/column.py             + datasource_name
genql/domain/entities/constraint.py         + datasource_name
genql/domain/entities/column_profile.py     + datasource_name
genql/domain/ports/catalog_reader.py        schema: str -> ref: SchemaRef
genql/domain/ports/discovery_step.py        DiscoveryContext + datasource_name, + ref property
genql/domain/errors.py                      + five typed errors
genql/repositories/warehouse/catalog_reader_repository.py   stamps datasource_name; registers as "postgres"
genql/repositories/warehouse/profile_reader_repository.py   stamps datasource_name; registers as "postgres"
genql/repositories/semantic/catalog_writer_repository.py    binds datasource_name
genql/repositories/semantic/profile_writer_repository.py    binds datasource_name
genql/services/discovery/catalog_scan_service.py            takes SchemaRef, then a factory
genql/services/discovery/profiling_service.py               takes SchemaRef, then a factory
genql/discovery/steps/catalog_scan_step.py                  passes ctx.ref
genql/discovery/steps/data_profiling_step.py                passes ctx.ref
genql/discovery/runner.py                                   + run_scope
genql/core/settings.py                                      - warehouse_dsn, + default_datasource, + scope_resolver
genql/composition_root.py                                   rewired for multi-datasource
genql/cli/main.py                                           mounts sub-apps; discover takes scope flags
.env.example                                                + GENQL_WH2_DSN, + GENQL_DEFAULT_DATASOURCE
data/README.md                                              Pagila verified; wh2 documented
tests/integration/conftest.py                               + registered_schema helper fixture
tests/unit/test_catalog_scan_service.py                     fakes updated
tests/unit/test_profiling_service.py                        fakes updated
tests/unit/test_domain_entities.py                          + datasource_name
tests/unit/test_catalog_scan_step.py                        ctx gains datasource_name
tests/unit/test_data_profiling_step.py                      ctx gains datasource_name
tests/unit/test_discovery_runner.py                         ctx gains datasource_name
tests/unit/test_composition_root.py                         env vars updated
tests/integration/test_catalog_reader_repository.py         SchemaRef args
tests/integration/test_catalog_writer_repository.py         datasource_name
tests/integration/test_profile_reader_repository.py         datasource_name
tests/integration/test_cli_discover.py                      registers the schema first
```

---

## Task Sequence and Why

Tasks 1–2 do the re-keying while wiring stays single-datasource, so the suite is green at every boundary. Tasks 3–5 introduce the connection machinery and flip the wiring to multi-datasource. Tasks 6–9 add the services and CLI surface. Task 10 proves the whole thing against a genuinely second database.

---

### Task 1: Domain foundation

Purely additive. Nothing existing changes, so the suite stays green on 49 plus the new tests.

**Files:**
- Create: `genql/domain/value_objects/schema_ref.py`, `genql/domain/value_objects/query_scope.py`, `genql/domain/entities/datasource.py`, `genql/domain/entities/schema_registration.py`, `genql/domain/ports/datasource_repository.py`, `genql/domain/ports/schema_registration_repository.py`, `genql/domain/ports/catalog_reader_factory.py`, `genql/domain/ports/profile_reader_factory.py`, `genql/domain/ports/scope_resolver.py`
- Modify: `genql/domain/errors.py`
- Test: `tests/unit/test_schema_ref.py`, `tests/unit/test_query_scope.py`, `tests/unit/test_datasource_entities.py`, `tests/unit/test_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: nothing
- Produces: `SchemaRef(datasource_name, schema_name)` with `.qualified_name -> str`; `QueryScope(datasource_name, schema_names: tuple[str, ...])` with `.refs() -> tuple[SchemaRef, ...]`; `Datasource(name, dialect, dsn_env_var, description, enabled)`; `SchemaRegistration(datasource_name, schema_name, description, enabled, last_discovered_at)` with `.ref -> SchemaRef`; the five ports; errors `UnknownDatasourceError`, `DuplicateDatasourceError`, `MissingDatasourceSecretError`, `UnknownSchemaRegistrationError`, `AmbiguousScopeError`

- [ ] **Step 1: Write the failing tests for the value objects**

Create `tests/unit/test_schema_ref.py`:

```python
"""SchemaRef is the identity every catalog row is keyed on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.value_objects.schema_ref import SchemaRef


def test_qualified_name_joins_datasource_and_schema() -> None:
    assert SchemaRef(datasource_name="local", schema_name="tpcds").qualified_name == "local.tpcds"


def test_schema_ref_is_frozen() -> None:
    ref = SchemaRef(datasource_name="local", schema_name="tpcds")
    with pytest.raises(ValidationError):
        ref.schema_name = "other"  # type: ignore[misc]


def test_schema_ref_is_hashable_so_it_can_key_a_dict() -> None:
    ref = SchemaRef(datasource_name="local", schema_name="tpcds")
    assert {ref: 1}[SchemaRef(datasource_name="local", schema_name="tpcds")] == 1
```

Create `tests/unit/test_query_scope.py`:

```python
"""A QueryScope names exactly one datasource. Cross-datasource is unrepresentable."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef


def test_refs_yields_one_ref_per_schema() -> None:
    scope = QueryScope(datasource_name="local", schema_names=("tpcds", "shop"))

    assert scope.refs() == (
        SchemaRef(datasource_name="local", schema_name="tpcds"),
        SchemaRef(datasource_name="local", schema_name="shop"),
    )


def test_scope_rejects_an_empty_schema_list() -> None:
    with pytest.raises(ValidationError):
        QueryScope(datasource_name="local", schema_names=())


def test_scope_is_frozen() -> None:
    scope = QueryScope(datasource_name="local", schema_names=("tpcds",))
    with pytest.raises(ValidationError):
        scope.datasource_name = "wh2"  # type: ignore[misc]
```

Create `tests/unit/test_datasource_entities.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.value_objects.schema_ref import SchemaRef


def test_datasource_defaults_to_enabled() -> None:
    ds = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
    assert ds.enabled is True
    assert ds.description is None


def test_datasource_is_frozen() -> None:
    ds = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
    with pytest.raises(ValidationError):
        ds.name = "other"  # type: ignore[misc]


def test_schema_registration_exposes_its_ref() -> None:
    reg = SchemaRegistration(datasource_name="local", schema_name="tpcds")

    assert reg.ref == SchemaRef(datasource_name="local", schema_name="tpcds")
    assert reg.enabled is True
    assert reg.last_discovered_at is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schema_ref.py tests/unit/test_query_scope.py tests/unit/test_datasource_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.value_objects.schema_ref'`

- [ ] **Step 3: Write the value objects**

Create `genql/domain/value_objects/schema_ref.py`:

```python
"""Identifies one schema inside one datasource.

Every catalog row is keyed on this pair. It is a value object rather than two
loose strings so a function signature cannot silently accept them in the wrong
order, and so the pair can key a dict of per-schema results.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}"
```

Create `genql/domain/value_objects/query_scope.py`:

```python
"""The set of schemas a discovery run or a query addresses.

A scope names exactly ONE datasource. That is the federation decision made
into a type: a scope spanning two datasources is unrepresentable, so no
downstream stage can assume cross-datasource joins work. PostgreSQL joins
across schemas natively, which is why n schemas within one datasource costs
nothing and n datasources would cost an execution layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.schema_ref import SchemaRef


class QueryScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_names: tuple[str, ...] = Field(min_length=1)

    def refs(self) -> tuple[SchemaRef, ...]:
        return tuple(
            SchemaRef(datasource_name=self.datasource_name, schema_name=name)
            for name in self.schema_names
        )
```

- [ ] **Step 4: Write the entities**

Create `genql/domain/entities/datasource.py`:

```python
"""A registered connection to a warehouse GenQL may discover.

`dsn_env_var` holds the NAME of an environment variable, never a connection
string. The DSN is read from the process environment at connect time, so
warehouse credentials never enter the semantic store and a dump of that store
is safe to share.

`dialect` is a free-text registry key rather than an enum: an enum would have
to be edited to add a dialect, which is the modification the registry exists to
avoid.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Datasource(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dialect: str
    dsn_env_var: str
    description: str | None = None
    enabled: bool = True
```

Create `genql/domain/entities/schema_registration.py`:

```python
"""A schema of a datasource that GenQL has been told to manage.

Registration is explicit: discovery writes catalog rows that carry a foreign
key to this table, so a schema must be registered before it can be discovered.
That is what makes `genql schema list` an accurate inventory rather than a
side effect of whatever anyone last scanned.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.schema_ref import SchemaRef


class SchemaRegistration(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    description: str | None = None
    enabled: bool = True
    last_discovered_at: datetime | None = None

    @property
    def ref(self) -> SchemaRef:
        return SchemaRef(datasource_name=self.datasource_name, schema_name=self.schema_name)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_schema_ref.py tests/unit/test_query_scope.py tests/unit/test_datasource_entities.py -q`
Expected: PASS — 9 passed

- [ ] **Step 6: Add the typed errors**

Append to `genql/domain/errors.py`:

```python
class DatasourceError(GenqlError):
    """A datasource or schema registration could not be resolved."""


class UnknownDatasourceError(DatasourceError):
    def __init__(self, name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{name!r} is not a registered datasource. Available: {options}")
        self.name = name


class DuplicateDatasourceError(DatasourceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"datasource {name!r} is already registered")
        self.name = name


class MissingDatasourceSecretError(DatasourceError):
    """The environment variable a datasource names is unset or empty."""

    def __init__(self, datasource_name: str, env_var: str) -> None:
        super().__init__(
            f"datasource {datasource_name!r} names environment variable {env_var!r}, "
            "which is unset or empty"
        )
        self.datasource_name = datasource_name
        self.env_var = env_var


class UnknownSchemaRegistrationError(DatasourceError):
    def __init__(self, qualified_name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{qualified_name!r} is not a registered schema. Available: {options}")
        self.qualified_name = qualified_name


class AmbiguousScopeError(DatasourceError):
    """No datasource was given and more than one is enabled."""

    def __init__(self, candidates: list[str]) -> None:
        options = ", ".join(candidates)
        super().__init__(
            f"no datasource given and {len(candidates)} are enabled ({options}). "
            "Pass --datasource, or set GENQL_DEFAULT_DATASOURCE."
        )
        self.candidates = candidates
```

- [ ] **Step 7: Write the five ports**

Create `genql/domain/ports/datasource_repository.py`:

```python
"""Reads and writes registered datasources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource


@runtime_checkable
class DatasourceRepository(Protocol):
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource: ...

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]: ...

    def remove(self, name: str) -> None: ...
```

Create `genql/domain/ports/schema_registration_repository.py`:

```python
"""Reads and writes the schemas GenQL has been told to manage."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class SchemaRegistrationRepository(Protocol):
    def add(self, registration: SchemaRegistration) -> None: ...

    def get(self, ref: SchemaRef) -> SchemaRegistration: ...

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]: ...

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None: ...
```

Create `genql/domain/ports/catalog_reader_factory.py`:

```python
"""Produces a CatalogReader bound to one datasource.

This is the seam that keeps multi-datasource discovery inside the layering. A
service must never see an Engine, a DSN, or a dialect, but it does need a
reader for a PARTICULAR warehouse. It loads the Datasource through a
repository port and hands it here; the infrastructure implementation resolves
the connection and the dialect.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.catalog_reader import CatalogReader


@runtime_checkable
class CatalogReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> CatalogReader: ...
```

Create `genql/domain/ports/profile_reader_factory.py`:

```python
"""Produces a ProfileReader bound to one datasource."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.profile_reader import ProfileReader


@runtime_checkable
class ProfileReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> ProfileReader: ...
```

Create `genql/domain/ports/scope_resolver.py`:

```python
"""Turns optional user input into a concrete QueryScope.

Phase 5 registers an LLM-backed resolver that picks the datasource from a
natural-language question. It implements this same protocol, so no call site
changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.value_objects.query_scope import QueryScope


@runtime_checkable
class ScopeResolver(Protocol):
    def resolve(
        self, datasource_name: str | None, schema_names: Sequence[str]
    ) -> QueryScope: ...
```

- [ ] **Step 8: Extend the runtime-checkable port test**

`tests/unit/test_ports_are_runtime_checkable.py` currently proves one port. Append these two tests to it, keeping the existing `FakeCatalogReader` and its test untouched:

```python
class FakeDatasourceRepository:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return []

    def remove(self, name: str) -> None: ...


class FakeScopeResolver:
    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        return QueryScope(datasource_name="local", schema_names=("tpcds",))


def test_a_plain_class_satisfies_the_datasource_repository_port() -> None:
    assert isinstance(FakeDatasourceRepository(), DatasourceRepository)


def test_a_plain_class_satisfies_the_scope_resolver_port() -> None:
    assert isinstance(FakeScopeResolver(), ScopeResolver)
```

with these imports added at the top:

```python
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.scope_resolver import ScopeResolver
from genql.domain.value_objects.query_scope import QueryScope
```

Note that `runtime_checkable` protocols only check method *names*, not signatures — these tests prove the ports are usable with `isinstance`, which is what lets fakes stand in for repositories in every service test.

- [ ] **Step 9: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```
Expected: all green, 58+ passed.

- [ ] **Step 10: Commit**

```bash
git add genql/domain tests/unit
git commit -m "feat(domain): add datasource, schema registration, scope, and factory ports"
```

---

### Task 2: Re-key the catalog to three levels

Migration 0003 and every entity, port, repository, service, and step that carries object identity. Wiring stays single-datasource: the CLI passes a fixed `--datasource local` default, replaced by the scope resolver in Task 9. This is the largest task in the plan; it is one task because the migration and the writers that satisfy its `NOT NULL` must land together or the suite is red between them.

**Files:**
- Create: `migrations/versions/0003_datasource_and_schema.py`, `tests/integration/test_migration_0003.py`
- Modify: `genql/domain/entities/database_object.py`, `genql/domain/entities/column.py`, `genql/domain/entities/constraint.py`, `genql/domain/entities/column_profile.py`, `genql/domain/ports/catalog_reader.py`, `genql/domain/ports/discovery_step.py`, `genql/repositories/warehouse/catalog_reader_repository.py`, `genql/repositories/warehouse/profile_reader_repository.py`, `genql/repositories/semantic/catalog_writer_repository.py`, `genql/repositories/semantic/profile_writer_repository.py`, `genql/services/discovery/catalog_scan_service.py`, `genql/services/discovery/profiling_service.py`, `genql/discovery/steps/catalog_scan_step.py`, `genql/discovery/steps/data_profiling_step.py`, `genql/cli/main.py`, `tests/integration/conftest.py`
- Test: all existing unit and integration tests listed under "Modified" in the File Structure section

**Interfaces:**
- Consumes: `SchemaRef` from Task 1
- Produces: `genql.genql_datasource` and `genql.genql_schema` tables; `datasource_name` on all four catalog tables and all four entities; `CatalogReader.read_objects(ref: SchemaRef)`, `.read_columns(ref)`, `.read_constraints(ref)`; `DiscoveryContext(datasource_name, schema_name, sample_limit, artifacts)` with `.ref -> SchemaRef`; `CatalogScanService.scan(ref: SchemaRef) -> CatalogScanReport`; `ProfilingService.profile(ref: SchemaRef, sample_limit: int) -> int`

- [ ] **Step 1: Write the failing migration test**

Create `tests/integration/test_migration_0003.py`:

```python
"""0003 re-keys the catalog. It must not lose rows discovered under 0002."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


@pytest.fixture()
def at_0002(engine: Engine, paradedb_dsn: str) -> Iterator[Config]:
    """Rewind to 0002, plant a row, and hand back the config to upgrade with."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "0002")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object "
                "(schema_name, object_name, object_type, row_estimate) "
                "VALUES ('legacy', 'orders', 'TABLE', 42)"
            )
        )
    yield cfg
    command.upgrade(cfg, "head")


def test_upgrade_backfills_existing_rows_to_the_local_datasource(
    at_0002: Config, engine: Engine
) -> None:
    command.upgrade(at_0002, "0003")

    with engine.connect() as conn:
        datasource_name = conn.execute(
            text("SELECT datasource_name FROM genql.genql_object WHERE object_name = 'orders'")
        ).scalar_one()
        registered = conn.execute(
            text("SELECT count(*) FROM genql.genql_schema WHERE schema_name = 'legacy'")
        ).scalar_one()
        dsn_env_var = conn.execute(
            text("SELECT dsn_env_var FROM genql.genql_datasource WHERE name = 'local'")
        ).scalar_one()

    assert datasource_name == "local"
    assert registered == 1
    assert dsn_env_var == "GENQL_WAREHOUSE_DSN"


def test_removing_a_datasource_cascades_to_its_catalog(at_0002: Config, engine: Engine) -> None:
    command.upgrade(at_0002, "0003")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'local'"))
    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT count(*) FROM genql.genql_object")).scalar_one()

    assert remaining == 0


def test_downgrade_removes_the_new_tables_and_column(at_0002: Config, engine: Engine) -> None:
    command.upgrade(at_0002, "0003")
    command.downgrade(at_0002, "0002")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('genql.genql_datasource')")).scalar_one() is None
        has_column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'genql' AND table_name = 'genql_object' "
                "AND column_name = 'datasource_name'"
            )
        ).scalar_one()
    assert has_column == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0003.py -q`
Expected: FAIL — `alembic.util.exc.CommandError: Can't locate revision identified by '0003'`

- [ ] **Step 3: Write migration 0003**

Create `migrations/versions/0003_datasource_and_schema.py`:

```python
"""datasource and schema levels

Revision ID: 0003
Revises: 0002

Inserts the two identity levels above `object`. The upgrade is non-destructive:
`datasource_name` is added with a server default of 'local', so PostgreSQL
backfills every existing row as part of the DDL, and the default is dropped
only afterwards. Rows discovered in Phase 2 become addressable as
`local.<schema>` rather than being thrown away.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_CATALOG_TABLES = ("genql_object", "genql_column", "genql_constraint", "genql_column_profile")
_IDENTITY_CONSTRAINTS = {
    "genql_object": ("uq_genql_object_identity", ["schema_name", "object_name"]),
    "genql_column": ("uq_genql_column_identity", ["schema_name", "object_name", "column_name"]),
    "genql_constraint": (
        "uq_genql_constraint_identity",
        ["schema_name", "object_name", "constraint_name"],
    ),
    "genql_column_profile": (
        "uq_genql_profile_identity",
        ["schema_name", "object_name", "column_name"],
    ),
}


def upgrade() -> None:
    op.create_table(
        "genql_datasource",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("dialect", sa.Text, nullable=False),
        sa.Column("dsn_env_var", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="genql",
    )

    op.create_table(
        "genql_schema",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("datasource_name", "schema_name", name="pk_genql_schema"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_schema_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    # The datasource Phase 2 was pointed at. Named for the environment variable
    # that already carries its DSN, so nothing about the local setup changes.
    op.execute(
        """
        INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var, description)
        VALUES ('local', 'postgres', 'GENQL_WAREHOUSE_DSN',
                'Datasource migrated from the single-warehouse configuration')
        """
    )

    for table in _CATALOG_TABLES:
        op.add_column(
            table,
            sa.Column("datasource_name", sa.Text, nullable=False, server_default="local"),
            schema="genql",
        )

    op.execute(
        """
        INSERT INTO genql.genql_schema (datasource_name, schema_name)
        SELECT DISTINCT 'local', schema_name FROM genql.genql_object
        ON CONFLICT ON CONSTRAINT pk_genql_schema DO NOTHING
        """
    )

    for table in _CATALOG_TABLES:
        op.alter_column(table, "datasource_name", server_default=None, schema="genql")
        constraint_name, columns = _IDENTITY_CONSTRAINTS[table]
        op.drop_constraint(constraint_name, table, type_="unique", schema="genql")
        op.create_unique_constraint(
            constraint_name, table, ["datasource_name", *columns], schema="genql"
        )
        op.create_foreign_key(
            f"fk_{table}_schema",
            table,
            "genql_schema",
            ["datasource_name", "schema_name"],
            ["datasource_name", "schema_name"],
            source_schema="genql",
            referent_schema="genql",
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in _CATALOG_TABLES:
        op.drop_constraint(f"fk_{table}_schema", table, type_="foreignkey", schema="genql")
        constraint_name, columns = _IDENTITY_CONSTRAINTS[table]
        op.drop_constraint(constraint_name, table, type_="unique", schema="genql")
        op.create_unique_constraint(constraint_name, table, columns, schema="genql")
        op.drop_column(table, "datasource_name", schema="genql")

    op.drop_table("genql_schema", schema="genql")
    op.drop_table("genql_datasource", schema="genql")
```

- [ ] **Step 4: Run the migration test to verify it passes**

Run: `uv run pytest tests/integration/test_migration_0003.py -q`
Expected: PASS — 3 passed

- [ ] **Step 5: Add `datasource_name` to the four entities**

In each of `genql/domain/entities/database_object.py`, `column.py`, `constraint.py`, and `column_profile.py`, add `datasource_name: str` as the **first** field and extend `qualified_name`. For example, `database_object.py` becomes:

```python
class DatabaseObject(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    object_type: ObjectType
    row_estimate: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}.{self.object_name}"
```

`Column.qualified_name` becomes `f"{self.datasource_name}.{self.schema_name}.{self.object_name}.{self.column_name}"`, and `ColumnProfile.qualified_name` the same. `Constraint` has no `qualified_name` property; it only gains the field.

- [ ] **Step 6: Change the `CatalogReader` port to take a `SchemaRef`**

Rewrite `genql/domain/ports/catalog_reader.py`:

```python
"""Reads structural metadata from the target warehouse.

Methods take a SchemaRef rather than a schema string: the reader is already
bound to one datasource by its factory, but it needs the datasource NAME to
stamp onto the entities it returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class CatalogReader(Protocol):
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]: ...

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]: ...

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]: ...
```

- [ ] **Step 7: Update the warehouse reader repositories**

In `genql/repositories/warehouse/catalog_reader_repository.py`, change each of the three methods to take `ref: SchemaRef`, bind `{"schema": ref.schema_name}`, and pass `datasource_name=ref.datasource_name` plus `schema_name=ref.schema_name` into every constructed entity. The three `text()` statements are unchanged. Example for `read_objects`:

```python
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        with self._engine.connect() as conn:
            rows = conn.execute(_OBJECTS_SQL, {"schema": ref.schema_name}).all()
        return [
            DatabaseObject(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                object_name=row.relname,
                object_type=_RELKIND_TO_TYPE[row.relkind],
                row_estimate=(
                    row.row_estimate
                    if row.row_estimate is not None and row.row_estimate >= 0
                    else None
                ),
            )
            for row in rows
        ]
```

In `genql/repositories/warehouse/profile_reader_repository.py`, the signature is unchanged — a `Column` already carries its full identity — but the returned `ColumnProfile` gains `datasource_name=column.datasource_name`.

- [ ] **Step 8: Update the semantic writer repositories**

In `genql/repositories/semantic/catalog_writer_repository.py`, add `datasource_name` to the column list and `VALUES` clause of all three `text()` statements. For example:

```python
_UPSERT_OBJECT = text("""
    INSERT INTO genql.genql_object
        (datasource_name, schema_name, object_name, object_type, row_estimate)
    VALUES (:datasource_name, :schema_name, :object_name, :object_type, :row_estimate)
    ON CONFLICT ON CONSTRAINT uq_genql_object_identity DO UPDATE
        SET object_type = EXCLUDED.object_type,
            row_estimate = EXCLUDED.row_estimate,
            discovered_at = now()
""")
```

Do the same for `_UPSERT_COLUMN` and `_UPSERT_CONSTRAINT`. The `model_dump(mode="json")` payload already supplies the key, so the Python is unchanged.

In `genql/repositories/semantic/profile_writer_repository.py`, add `datasource_name` to the statement and to the hand-built payload dict:

```python
        payload = [
            {
                "datasource_name": p.datasource_name,
                "schema_name": p.schema_name,
                ...
            }
            for p in profiles
        ]
```

- [ ] **Step 9: Update the two services to take a `SchemaRef`**

In `genql/services/discovery/catalog_scan_service.py`, change the signature and pass the ref through:

```python
    def scan(self, ref: SchemaRef) -> CatalogScanReport:
        return CatalogScanReport(
            objects=self._writer.write_objects(self._reader.read_objects(ref)),
            columns=self._writer.write_columns(self._reader.read_columns(ref)),
            constraints=self._writer.write_constraints(self._reader.read_constraints(ref)),
        )
```

In `genql/services/discovery/profiling_service.py`:

```python
    def profile(self, ref: SchemaRef, sample_limit: int) -> int:
        self.skipped = []
        profiles: list[ColumnProfile] = []
        for column in self._catalog.read_columns(ref):
            try:
                profiles.append(self._reader.profile_column(column, sample_limit))
            except ProfilingError as exc:
                self.skipped.append(exc.qualified_name)
                _log.warning("profiling.skipped", column=exc.qualified_name, reason=str(exc))
        return self._writer.write_profiles(profiles)
```

Both files need `from genql.domain.value_objects.schema_ref import SchemaRef`.

- [ ] **Step 10: Add `datasource_name` to `DiscoveryContext`**

In `genql/domain/ports/discovery_step.py`, add the field and the `ref` property to `DiscoveryContext`:

```python
class DiscoveryContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    datasource_name: str
    schema_name: str
    sample_limit: int = 5
    artifacts: dict[str, object] = Field(default_factory=dict)

    @property
    def ref(self) -> SchemaRef:
        return SchemaRef(datasource_name=self.datasource_name, schema_name=self.schema_name)
```

Import `SchemaRef` at the top. Keep the existing docstring explaining why the field is `schema_name` and not `schema`.

- [ ] **Step 11: Update the two steps**

In `genql/discovery/steps/catalog_scan_step.py`, change `self._service.scan(ctx.schema_name)` to `self._service.scan(ctx.ref)`.
In `genql/discovery/steps/data_profiling_step.py`, change `self._service.profile(ctx.schema_name, ctx.sample_limit)` to `self._service.profile(ctx.ref, ctx.sample_limit)`.

- [ ] **Step 12: Give the CLI a temporary `--datasource` flag**

In `genql/cli/main.py`, add the option and pass it into the context. Task 9 replaces this with scope resolution:

```python
@app.command()
def discover(
    schema: str = typer.Option(..., "--schema", help="Warehouse schema to discover"),
    datasource: str = typer.Option("local", "--datasource", help="Registered datasource"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from this step"),
) -> None:
    """Run the offline discovery pipeline."""
    container = Container()
    runner = container.discovery_runner()
    ctx = DiscoveryContext(
        datasource_name=datasource,
        schema_name=schema,
        sample_limit=container.settings().profile_sample_limit,
    )
    ...
```

- [ ] **Step 13: Add a `registered_schema` fixture to the integration conftest**

Catalog rows now carry a foreign key to `genql_schema`, so an integration test that writes them must register the schema first. Add to `tests/integration/conftest.py`:

```python
@pytest.fixture()
def register_schema(migrated_engine: Engine):
    """Register (datasource, schema) so catalog writes satisfy their foreign key.

    Task 9 gives the CLI `genql schema add`; until then, and for tests that are
    not exercising the CLI, registration is a direct insert.
    """

    def _register(datasource_name: str, schema_name: str) -> None:
        with migrated_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var) "
                    "VALUES (:ds, 'postgres', 'GENQL_WAREHOUSE_DSN') "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"ds": datasource_name},
            )
            conn.execute(
                text(
                    "INSERT INTO genql.genql_schema (datasource_name, schema_name) "
                    "VALUES (:ds, :schema) ON CONFLICT ON CONSTRAINT pk_genql_schema DO NOTHING"
                ),
                {"ds": datasource_name, "schema": schema_name},
            )

    return _register
```

- [ ] **Step 14: Update every existing test**

Run the suite and fix each failure mechanically:

```bash
uv run pytest -q
```

The changes are:
- `tests/unit/test_catalog_scan_service.py` — the three module-level fixtures gain `datasource_name="local"`; `FakeReader`'s three methods take `ref: SchemaRef`; both tests call `.scan(SchemaRef(datasource_name="local", schema_name="shop"))`.
- `tests/unit/test_profiling_service.py` — same shape: fakes take `SchemaRef`, entities gain `datasource_name`, `.profile(ref, 5)`.
- `tests/unit/test_domain_entities.py` — every constructed entity gains `datasource_name="local"`; `qualified_name` assertions gain the `local.` prefix.
- `tests/unit/test_catalog_scan_step.py`, `tests/unit/test_data_profiling_step.py`, `tests/unit/test_discovery_runner.py` — every `DiscoveryContext(...)` gains `datasource_name="local"`.
- `tests/unit/test_ports_are_runtime_checkable.py` — `FakeCatalogReader`'s three methods take `ref: SchemaRef` instead of `schema: str`.
- `tests/integration/test_catalog_reader_repository.py`, `tests/integration/test_profile_reader_repository.py` — reader calls take `SchemaRef(datasource_name="local", schema_name=...)`; expected entities gain `datasource_name`.
- `tests/integration/test_catalog_writer_repository.py` — request the `register_schema` fixture and call `register_schema("local", "<schema>")` before writing; entities gain `datasource_name="local"`.
- `tests/integration/test_cli_discover.py` — request `register_schema` and call `register_schema("local", "e2e")` inside the `wired` fixture, after the `FIXTURE` DDL runs.

- [ ] **Step 15: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```
Expected: all green.

- [ ] **Step 16: Commit**

```bash
git add -A
git commit -m "feat(catalog): key every catalog row on datasource and schema"
```

---

### Task 3: Semantic repositories for the two new tables

**Files:**
- Create: `genql/repositories/semantic/datasource_repository.py`, `genql/repositories/semantic/schema_registration_repository.py`, `tests/integration/test_datasource_repository.py`, `tests/integration/test_schema_registration_repository.py`
- Test: the two files above

**Interfaces:**
- Consumes: `Datasource`, `SchemaRegistration`, `SchemaRef`, `DatasourceRepository`, `SchemaRegistrationRepository`, `UnknownDatasourceError`, `DuplicateDatasourceError`, `UnknownSchemaRegistrationError` from Task 1; the `genql_datasource` and `genql_schema` tables from Task 2
- Produces: `PostgresDatasourceRepository(engine: Engine)` and `PostgresSchemaRegistrationRepository(engine: Engine)`, both satisfying their ports

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_datasource_repository.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import DuplicateDatasourceError, UnknownDatasourceError
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository

WH2 = Datasource(
    name="repo_wh2", dialect="postgres", dsn_env_var="GENQL_WH2_DSN", description="second"
)
DISABLED = Datasource(
    name="repo_off", dialect="postgres", dsn_env_var="GENQL_OFF_DSN", enabled=False
)


@pytest.fixture()
def repo(migrated_engine: Engine) -> PostgresDatasourceRepository:
    with migrated_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM genql.genql_datasource WHERE name IN ('repo_wh2', 'repo_off')")
        )
    return PostgresDatasourceRepository(engine=migrated_engine)


def test_add_then_get_round_trips(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    assert repo.get("repo_wh2") == WH2


def test_add_twice_raises_duplicate(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    with pytest.raises(DuplicateDatasourceError):
        repo.add(WH2)


def test_get_unknown_raises_and_names_the_alternatives(
    repo: PostgresDatasourceRepository,
) -> None:
    repo.add(WH2)
    with pytest.raises(UnknownDatasourceError, match="repo_wh2"):
        repo.get("nope")


def test_list_all_can_filter_to_enabled(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    repo.add(DISABLED)

    names = {d.name for d in repo.list_all(enabled_only=True)}

    assert "repo_wh2" in names
    assert "repo_off" not in names


def test_remove_deletes_the_row(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    repo.remove("repo_wh2")
    with pytest.raises(UnknownDatasourceError):
        repo.get("repo_wh2")


def test_remove_unknown_raises(repo: PostgresDatasourceRepository) -> None:
    with pytest.raises(UnknownDatasourceError):
        repo.remove("never_existed")
```

Create `tests/integration/test_schema_registration_repository.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository
from genql.repositories.semantic.schema_registration_repository import (
    PostgresSchemaRegistrationRepository,
)

DS = Datasource(name="reg_ds", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
REF = SchemaRef(datasource_name="reg_ds", schema_name="sales")


@pytest.fixture()
def repo(migrated_engine: Engine) -> PostgresSchemaRegistrationRepository:
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'reg_ds'"))
    PostgresDatasourceRepository(engine=migrated_engine).add(DS)
    return PostgresSchemaRegistrationRepository(engine=migrated_engine)


def test_add_then_get_round_trips(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))

    stored = repo.get(REF)

    assert stored.ref == REF
    assert stored.enabled is True
    assert stored.last_discovered_at is None


def test_get_unknown_raises(repo: PostgresSchemaRegistrationRepository) -> None:
    with pytest.raises(UnknownSchemaRegistrationError):
        repo.get(SchemaRef(datasource_name="reg_ds", schema_name="absent"))


def test_list_for_datasource_can_filter_to_enabled(
    repo: PostgresSchemaRegistrationRepository,
) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="stale", enabled=False))

    names = {r.schema_name for r in repo.list_for_datasource("reg_ds", enabled_only=True)}

    assert names == {"sales"}


def test_mark_discovered_stamps_a_timestamp(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))

    repo.mark_discovered(REF)

    assert repo.get(REF).last_discovered_at is not None


def test_remove_deletes_the_registration(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))
    repo.remove(REF)
    with pytest.raises(UnknownSchemaRegistrationError):
        repo.get(REF)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/integration/test_datasource_repository.py tests/integration/test_schema_registration_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.semantic.datasource_repository'`

- [ ] **Step 3: Write the datasource repository**

Create `genql/repositories/semantic/datasource_repository.py`:

```python
"""Persists registered datasources.

Note what is NOT here: a DSN. The row carries the name of an environment
variable and nothing else, so the semantic store never holds a warehouse
credential.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import DuplicateDatasourceError, UnknownDatasourceError

_INSERT = text("""
    INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var, description, enabled)
    VALUES (:name, :dialect, :dsn_env_var, :description, :enabled)
    ON CONFLICT (name) DO NOTHING
    RETURNING name
""")

_SELECT_ONE = text("""
    SELECT name, dialect, dsn_env_var, description, enabled
    FROM genql.genql_datasource WHERE name = :name
""")

_SELECT_ALL = text("""
    SELECT name, dialect, dsn_env_var, description, enabled
    FROM genql.genql_datasource
    WHERE (NOT :enabled_only) OR enabled
    ORDER BY name
""")

_SELECT_NAMES = text("SELECT name FROM genql.genql_datasource ORDER BY name")

_DELETE = text("DELETE FROM genql.genql_datasource WHERE name = :name RETURNING name")


class PostgresDatasourceRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, datasource: Datasource) -> None:
        with self._engine.begin() as conn:
            inserted = conn.execute(_INSERT, datasource.model_dump(mode="json")).scalar()
        if inserted is None:
            raise DuplicateDatasourceError(datasource.name)

    def get(self, name: str) -> Datasource:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT_ONE, {"name": name}).one_or_none()
            if row is None:
                raise UnknownDatasourceError(name, self._names(conn))
        return Datasource.model_validate(row._mapping)  # noqa: SLF001 - Row mapping is public API

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_ALL, {"enabled_only": enabled_only}).all()
        return [Datasource.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def remove(self, name: str) -> None:
        with self._engine.begin() as conn:
            deleted = conn.execute(_DELETE, {"name": name}).scalar()
            if deleted is None:
                raise UnknownDatasourceError(name, self._names(conn))

    @staticmethod
    def _names(conn: Connection) -> list[str]:
        return [r[0] for r in conn.execute(_SELECT_NAMES).all()]
```

Import `Connection` alongside `Engine` and `text`: `from sqlalchemy import Connection, Engine, text`. `Row._mapping` is public API despite the leading underscore, which is why the `SLF001` suppressions are there rather than being worked around.

- [ ] **Step 4: Write the schema registration repository**

Create `genql/repositories/semantic/schema_registration_repository.py`:

```python
"""Persists the schemas GenQL has been told to manage."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, Engine, text

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.schema_ref import SchemaRef

_COLUMNS = "datasource_name, schema_name, description, enabled, last_discovered_at"

_INSERT = text(f"""
    INSERT INTO genql.genql_schema ({_COLUMNS})
    VALUES (:datasource_name, :schema_name, :description, :enabled, :last_discovered_at)
    ON CONFLICT ON CONSTRAINT pk_genql_schema DO UPDATE
        SET description = EXCLUDED.description,
            enabled = EXCLUDED.enabled
""")

_SELECT_ONE = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_SELECT_FOR_DATASOURCE = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND ((NOT :enabled_only) OR enabled)
    ORDER BY schema_name
""")

_SELECT_NAMES = text("""
    SELECT datasource_name || '.' || schema_name FROM genql.genql_schema ORDER BY 1
""")

_DELETE = text("""
    DELETE FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
    RETURNING schema_name
""")

_MARK_DISCOVERED = text("""
    UPDATE genql.genql_schema SET last_discovered_at = now()
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
    RETURNING schema_name
""")


class PostgresSchemaRegistrationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, registration: SchemaRegistration) -> None:
        with self._engine.begin() as conn:
            conn.execute(_INSERT, registration.model_dump(mode="json"))

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT_ONE, ref.model_dump()).one_or_none()
            if row is None:
                raise UnknownSchemaRegistrationError(ref.qualified_name, self._names(conn))
        return SchemaRegistration.model_validate(row._mapping)  # noqa: SLF001

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_FOR_DATASOURCE,
                {"datasource_name": datasource_name, "enabled_only": enabled_only},
            ).all()
        return [SchemaRegistration.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def remove(self, ref: SchemaRef) -> None:
        self._mutate(_DELETE, ref)

    def mark_discovered(self, ref: SchemaRef) -> None:
        self._mutate(_MARK_DISCOVERED, ref)

    def _mutate(self, statement: TextClause, ref: SchemaRef) -> None:
        with self._engine.begin() as conn:
            affected = conn.execute(statement, ref.model_dump()).scalar()
            if affected is None:
                raise UnknownSchemaRegistrationError(ref.qualified_name, self._names(conn))

    @staticmethod
    def _names(conn: Connection) -> list[str]:
        return [r[0] for r in conn.execute(_SELECT_NAMES).all()]
```

Import line: `from sqlalchemy import Connection, Engine, TextClause, text`. `_COLUMNS` is interpolated into the f-string statements rather than repeated five times; it holds only a literal column list written in this file, never anything derived from input.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_datasource_repository.py tests/integration/test_schema_registration_repository.py -q`
Expected: PASS — 11 passed

- [ ] **Step 6: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```

- [ ] **Step 7: Commit**

```bash
git add genql/repositories tests/integration
git commit -m "feat(repositories): add datasource and schema registration repositories"
```

---

### Task 4: Dialect registries and the engine provider

**Files:**
- Create: `genql/repositories/warehouse/registry.py`, `genql/infrastructure/db/engine_provider.py`, `tests/unit/test_engine_provider.py`
- Modify: `genql/repositories/warehouse/catalog_reader_repository.py`, `genql/repositories/warehouse/profile_reader_repository.py`, `genql/repositories/warehouse/__init__.py`
- Test: `tests/unit/test_engine_provider.py`

**Interfaces:**
- Consumes: `Datasource`, `MissingDatasourceSecretError` from Task 1; `Registry` from `genql/registries/registry.py`
- Produces: `CATALOG_READERS: Registry[CatalogReader]` and `PROFILE_READERS: Registry[ProfileReader]`, both with `"postgres"` registered; `DatasourceEngineProvider(env: Mapping[str, str], engine_factory: Callable[[str], Engine])` with `.engine_for(datasource: Datasource) -> Engine` and `.invalidate(name: str) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_engine_provider.py`:

```python
"""The provider resolves a DSN from an injected environment, never os.environ.

Injecting the mapping is what lets this run as a unit test: nothing here
mutates process state, and no test needs monkeypatch to describe a datasource
whose secret is missing.
"""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider

DS = Datasource(name="wh2", dialect="postgres", dsn_env_var="GENQL_WH2_DSN")


class FakeEngine:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


def _provider(env: dict[str, str]) -> DatasourceEngineProvider:
    return DatasourceEngineProvider(env=env, engine_factory=FakeEngine)  # type: ignore[arg-type]


def test_engine_is_built_from_the_named_environment_variable() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})

    engine = provider.engine_for(DS)

    assert engine.dsn == "postgresql+psycopg://u:p@host/db"  # type: ignore[attr-defined]


def test_the_same_datasource_gets_the_same_engine() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})

    assert provider.engine_for(DS) is provider.engine_for(DS)


def test_a_missing_variable_raises_a_typed_error_naming_both() -> None:
    provider = _provider({})

    with pytest.raises(MissingDatasourceSecretError, match="GENQL_WH2_DSN"):
        provider.engine_for(DS)


def test_an_empty_variable_is_treated_as_missing() -> None:
    provider = _provider({"GENQL_WH2_DSN": "   "})

    with pytest.raises(MissingDatasourceSecretError):
        provider.engine_for(DS)


def test_invalidate_drops_the_cached_engine() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})
    first = provider.engine_for(DS)

    provider.invalidate("wh2")

    assert provider.engine_for(DS) is not first
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_engine_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.db.engine_provider'`

- [ ] **Step 3: Write the engine provider**

Create `genql/infrastructure/db/engine_provider.py`:

```python
"""Maps a Datasource to a pooled Engine, one per datasource name.

The environment is injected rather than read from `os.environ` directly, so
unit tests describe a datasource whose secret is missing without mutating
process state.

Engines are cached for the process lifetime, which is right for a CLI
invocation and for a long-lived API process. `invalidate` exists so removing a
datasource cannot leave a stale connection behind inside one process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy import Engine

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.infrastructure.db.engine import create_engine_from_dsn


class DatasourceEngineProvider:
    def __init__(
        self,
        env: Mapping[str, str],
        engine_factory: Callable[[str], Engine] = create_engine_from_dsn,
    ) -> None:
        self._env = env
        self._engine_factory = engine_factory
        self._engines: dict[str, Engine] = {}

    def engine_for(self, datasource: Datasource) -> Engine:
        cached = self._engines.get(datasource.name)
        if cached is not None:
            return cached
        engine = self._engine_factory(self._dsn_for(datasource))
        self._engines[datasource.name] = engine
        return engine

    def invalidate(self, name: str) -> None:
        self._engines.pop(name, None)

    def _dsn_for(self, datasource: Datasource) -> str:
        dsn = self._env.get(datasource.dsn_env_var, "").strip()
        if not dsn:
            raise MissingDatasourceSecretError(datasource.name, datasource.dsn_env_var)
        return dsn
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_engine_provider.py -q`
Expected: PASS — 5 passed

- [ ] **Step 5: Write the dialect registries**

Create `genql/repositories/warehouse/registry.py`:

```python
"""Warehouse readers, keyed by SQL dialect.

Adding Snowflake or BigQuery is one file plus one decorator: nothing in
services, discovery, or the CLI mentions a dialect by name.
"""

from __future__ import annotations

from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.profile_reader import ProfileReader
from genql.registries.registry import Registry

CATALOG_READERS: Registry[CatalogReader] = Registry("catalog_readers")
PROFILE_READERS: Registry[ProfileReader] = Registry("profile_readers")
```

- [ ] **Step 6: Register the Postgres implementations**

In `genql/repositories/warehouse/catalog_reader_repository.py`, add the import and decorate the class:

```python
from genql.repositories.warehouse.registry import CATALOG_READERS


@CATALOG_READERS.register("postgres")
class PostgresCatalogReaderRepository:
    ...
```

In `genql/repositories/warehouse/profile_reader_repository.py`:

```python
from genql.repositories.warehouse.registry import PROFILE_READERS


@PROFILE_READERS.register("postgres")
class PostgresProfileReaderRepository:
    ...
```

- [ ] **Step 7: Make the package import both modules for their side effect**

Replace `genql/repositories/warehouse/__init__.py` with:

```python
"""Registers every warehouse reader with its dialect registry.

This is the one place that imports the reader modules purely for their
`@CATALOG_READERS.register(...)` / `@PROFILE_READERS.register(...)` decorator
side effect, mirroring how `genql.discovery.steps` registers discovery steps.
"""

from __future__ import annotations

from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)

__all__ = ["PostgresCatalogReaderRepository", "PostgresProfileReaderRepository"]
```

- [ ] **Step 8: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```
Expected: all green. If `lint-imports` fails because `genql.repositories.warehouse.registry` imports `genql.registries`, that import is legal — `registries` is not a forbidden module for `repositories`. Read the failure before changing anything.

- [ ] **Step 9: Commit**

```bash
git add genql/repositories genql/infrastructure tests/unit
git commit -m "feat(infrastructure): add dialect registries and the datasource engine provider"
```

---

### Task 5: Reader factories and multi-datasource wiring

This is the task that flips the system from one warehouse to many. `Settings.warehouse_dsn` disappears — the value survives as the environment variable the `local` datasource row names.

**Files:**
- Create: `genql/infrastructure/catalog/__init__.py`, `genql/infrastructure/catalog/catalog_reader_factory.py`, `genql/infrastructure/catalog/profile_reader_factory.py`, `tests/unit/test_catalog_reader_factory.py`
- Modify: `genql/services/discovery/catalog_scan_service.py`, `genql/services/discovery/profiling_service.py`, `genql/core/settings.py`, `genql/composition_root.py`, `tests/unit/test_catalog_scan_service.py`, `tests/unit/test_profiling_service.py`, `tests/unit/test_composition_root.py`
- Test: `tests/unit/test_catalog_reader_factory.py`

**Interfaces:**
- Consumes: `DatasourceEngineProvider`, `CATALOG_READERS`, `PROFILE_READERS` from Task 4; `CatalogReaderFactory`, `ProfileReaderFactory`, `DatasourceRepository` ports from Task 1
- Produces: `CatalogReaderFactoryImpl(provider: DatasourceEngineProvider)` and `ProfileReaderFactoryImpl(provider: DatasourceEngineProvider)`; `CatalogScanService(datasources, readers, writer)` and `ProfilingService(datasources, catalog_readers, profile_readers, writer)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_catalog_reader_factory.py`:

```python
"""The factory picks an implementation by dialect and binds it to an engine."""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.infrastructure.catalog.catalog_reader_factory import CatalogReaderFactoryImpl
from genql.infrastructure.catalog.profile_reader_factory import ProfileReaderFactoryImpl
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.registries.errors import UnknownRegistryKeyError

POSTGRES = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
UNSUPPORTED = Datasource(name="odd", dialect="db2", dsn_env_var="GENQL_WAREHOUSE_DSN")
ENV = {"GENQL_WAREHOUSE_DSN": "postgresql+psycopg://u:p@host/db"}


class FakeEngine:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


@pytest.fixture()
def provider() -> DatasourceEngineProvider:
    return DatasourceEngineProvider(env=ENV, engine_factory=FakeEngine)  # type: ignore[arg-type]


def test_postgres_dialect_yields_the_postgres_catalog_reader(
    provider: DatasourceEngineProvider,
) -> None:
    reader = CatalogReaderFactoryImpl(provider=provider).for_datasource(POSTGRES)

    assert type(reader).__name__ == "PostgresCatalogReaderRepository"


def test_postgres_dialect_yields_the_postgres_profile_reader(
    provider: DatasourceEngineProvider,
) -> None:
    reader = ProfileReaderFactoryImpl(provider=provider).for_datasource(POSTGRES)

    assert type(reader).__name__ == "PostgresProfileReaderRepository"


def test_an_unregistered_dialect_raises_and_names_what_is_available(
    provider: DatasourceEngineProvider,
) -> None:
    factory = CatalogReaderFactoryImpl(provider=provider)

    with pytest.raises(UnknownRegistryKeyError, match="postgres"):
        factory.for_datasource(UNSUPPORTED)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_catalog_reader_factory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.catalog'`

- [ ] **Step 3: Write the two factories**

Create `genql/infrastructure/catalog/__init__.py` as an empty module (a docstring only).

Create `genql/infrastructure/catalog/catalog_reader_factory.py`:

```python
"""Binds a CatalogReader to one datasource.

Importing `genql.repositories.warehouse` is what populates CATALOG_READERS:
the package imports each reader module for its registration decorator.
"""

from __future__ import annotations

import genql.repositories.warehouse  # noqa: F401 - registration side effect
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.catalog_reader import CatalogReader
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.registry import CATALOG_READERS


class CatalogReaderFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> CatalogReader:
        engine = self._provider.engine_for(datasource)
        return CATALOG_READERS.create(datasource.dialect, engine=engine)
```

Create `genql/infrastructure/catalog/profile_reader_factory.py`:

```python
"""Binds a ProfileReader to one datasource."""

from __future__ import annotations

import genql.repositories.warehouse  # noqa: F401 - registration side effect
from genql.domain.entities.datasource import Datasource
from genql.domain.ports.profile_reader import ProfileReader
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.registry import PROFILE_READERS


class ProfileReaderFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> ProfileReader:
        engine = self._provider.engine_for(datasource)
        return PROFILE_READERS.create(datasource.dialect, engine=engine)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_catalog_reader_factory.py -q`
Expected: PASS — 3 passed

- [ ] **Step 5: Switch `CatalogScanService` to the factory**

Rewrite the class in `genql/services/discovery/catalog_scan_service.py` (keep `CatalogScanReport` exactly as it is):

```python
class CatalogScanService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        readers: CatalogReaderFactory,
        writer: CatalogWriter,
    ) -> None:
        self._datasources = datasources
        self._readers = readers
        self._writer = writer

    def scan(self, ref: SchemaRef) -> CatalogScanReport:
        reader = self._readers.for_datasource(self._datasources.get(ref.datasource_name))
        return CatalogScanReport(
            objects=self._writer.write_objects(reader.read_objects(ref)),
            columns=self._writer.write_columns(reader.read_columns(ref)),
            constraints=self._writer.write_constraints(reader.read_constraints(ref)),
        )
```

Imports: `CatalogReaderFactory`, `CatalogWriter`, `DatasourceRepository`, `SchemaRef`. The service still imports nothing but `genql.domain` — that is the whole point of the factory port, and `lint-imports` proves it.

- [ ] **Step 6: Switch `ProfilingService` to the factories**

In `genql/services/discovery/profiling_service.py`:

```python
class ProfilingService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        catalog_readers: CatalogReaderFactory,
        profile_readers: ProfileReaderFactory,
        writer: ProfileWriter,
    ) -> None:
        self._datasources = datasources
        self._catalog_readers = catalog_readers
        self._profile_readers = profile_readers
        self._writer = writer
        self.skipped: list[str] = []

    def profile(self, ref: SchemaRef, sample_limit: int) -> int:
        self.skipped = []
        datasource = self._datasources.get(ref.datasource_name)
        catalog = self._catalog_readers.for_datasource(datasource)
        reader = self._profile_readers.for_datasource(datasource)
        profiles: list[ColumnProfile] = []
        for column in catalog.read_columns(ref):
            try:
                profiles.append(reader.profile_column(column, sample_limit))
            except ProfilingError as exc:
                self.skipped.append(exc.qualified_name)
                _log.warning("profiling.skipped", column=exc.qualified_name, reason=str(exc))
        return self._writer.write_profiles(profiles)
```

- [ ] **Step 7: Update the two service unit tests**

In `tests/unit/test_catalog_scan_service.py` and `tests/unit/test_profiling_service.py`, add a `FakeDatasources` and a `FakeReaderFactory` and pass them in:

```python
class FakeDatasources:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [self.get("local")]

    def remove(self, name: str) -> None: ...


class FakeReaderFactory:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def for_datasource(self, datasource: Datasource) -> object:
        return self._reader
```

Then `CatalogScanService(FakeDatasources(), FakeReaderFactory(FakeReader()), writer)` and
`ProfilingService(FakeDatasources(), FakeReaderFactory(FakeCatalog()), FakeReaderFactory(FakeProfileReader()), writer)`.
Add an assertion that the factory received the datasource the ref named — that is the behaviour worth locking in:

```python
def test_the_reader_is_bound_to_the_refs_datasource() -> None:
    seen: list[str] = []

    class RecordingFactory(FakeReaderFactory):
        def for_datasource(self, datasource: Datasource) -> object:
            seen.append(datasource.name)
            return self._reader

    CatalogScanService(
        FakeDatasources(), RecordingFactory(FakeReader()), FakeWriter()
    ).scan(SchemaRef(datasource_name="wh2", schema_name="shop"))

    assert seen == ["wh2"]
```

- [ ] **Step 8: Update `Settings`**

Rewrite `genql/core/settings.py`:

```python
"""Process configuration, read once from the environment.

`warehouse_dsn` is deliberately absent: it described a single warehouse, which
is exactly the assumption Phase 2.5 deletes. The value lives on as the
environment variable that the `local` datasource row names. `semantic_dsn`
stays, because GenQL's own store genuinely is singular.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENQL_", env_file=".env", extra="ignore")

    semantic_dsn: str
    default_datasource: str | None = None
    scope_resolver: str = "default"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "genqlgenql"
    profile_sample_limit: int = 5
```

- [ ] **Step 9: Rewire the composition root**

In `genql/composition_root.py`, delete the `warehouse_engine`, `catalog_reader`, and `profile_reader` providers and add these, keeping `semantic_engine`, the writers, the step-provider mapping, and `discovery_runner` as they are:

```python
import os

    engine_provider = providers.Singleton(DatasourceEngineProvider, env=os.environ)

    datasource_repository = providers.Singleton(
        PostgresDatasourceRepository, engine=semantic_engine
    )
    schema_registration_repository = providers.Singleton(
        PostgresSchemaRegistrationRepository, engine=semantic_engine
    )

    catalog_reader_factory = providers.Singleton(
        CatalogReaderFactoryImpl, provider=engine_provider
    )
    profile_reader_factory = providers.Singleton(
        ProfileReaderFactoryImpl, provider=engine_provider
    )

    catalog_scan_service = providers.Singleton(
        CatalogScanService,
        datasources=datasource_repository,
        readers=catalog_reader_factory,
        writer=catalog_writer,
    )
    profiling_service = providers.Factory(
        ProfilingService,
        datasources=datasource_repository,
        catalog_readers=catalog_reader_factory,
        profile_readers=profile_reader_factory,
        writer=profile_writer,
    )
```

- [ ] **Step 10: Update the composition-root test**

In `tests/unit/test_composition_root.py`, the `container` fixture no longer needs `GENQL_WAREHOUSE_DSN` for `Settings` to validate, but leave it set — the `local` datasource names it, and removing it would make the fixture misleading. Add one assertion:

```python
def test_the_container_builds_a_catalog_reader_factory(container: Container) -> None:
    factory = container.catalog_reader_factory()

    assert hasattr(factory, "for_datasource")
```

- [ ] **Step 11: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```
Expected: all green. `lint-imports` passing here is the evidence that the factory-port design respects the layering — `services/` still imports only `domain/`.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat(discovery): resolve warehouse readers per datasource through factory ports"
```

---

### Task 6: Datasource and schema registration services

**Files:**
- Create: `genql/services/datasource/__init__.py`, `genql/services/datasource/datasource_service.py`, `genql/services/datasource/schema_registration_service.py`, `tests/unit/test_datasource_service.py`, `tests/unit/test_schema_registration_service.py`
- Modify: `genql/composition_root.py`
- Test: the two new unit tests

**Interfaces:**
- Consumes: `DatasourceRepository`, `SchemaRegistrationRepository`, `CatalogReaderFactory` ports; `Datasource`, `SchemaRegistration`, `SchemaRef`; `MissingDatasourceSecretError`
- Produces: `DatasourceService(datasources, readers, env)` with `.register(name, dialect, dsn_env_var, description) -> Datasource`, `.list_all(enabled_only) -> Sequence[Datasource]`, `.remove(name) -> None`; `SchemaRegistrationService(datasources, registrations, readers)` with `.register(ref, description) -> SchemaRegistration`, `.list_for_datasource(name) -> Sequence[SchemaRegistration]`, `.remove(ref) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_datasource_service.py`:

```python
"""Registration validates eagerly, so a misconfiguration fails at `add` time
rather than during the first discovery run half an hour later."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, UnknownDatasourceError
from genql.registries.errors import UnknownRegistryKeyError
from genql.services.datasource.datasource_service import DatasourceService

ENV = {"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"}


class FakeDatasources:
    def __init__(self) -> None:
        self.rows: dict[str, Datasource] = {}

    def add(self, datasource: Datasource) -> None:
        self.rows[datasource.name] = datasource

    def get(self, name: str) -> Datasource:
        try:
            return self.rows[name]
        except KeyError:
            raise UnknownDatasourceError(name, sorted(self.rows)) from None

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [d for d in self.rows.values() if d.enabled or not enabled_only]

    def remove(self, name: str) -> None:
        self.get(name)
        del self.rows[name]


def _service(repo: FakeDatasources) -> DatasourceService:
    return DatasourceService(datasources=repo, dialects=["postgres"], env=ENV)


def test_register_persists_the_datasource() -> None:
    repo = FakeDatasources()

    created = _service(repo).register("wh2", "postgres", "GENQL_WH2_DSN", None)

    assert created.name == "wh2"
    assert repo.rows["wh2"].dsn_env_var == "GENQL_WH2_DSN"


def test_register_refuses_an_unregistered_dialect() -> None:
    with pytest.raises(UnknownRegistryKeyError):
        _service(FakeDatasources()).register("wh2", "db2", "GENQL_WH2_DSN", None)


def test_register_refuses_a_datasource_whose_secret_is_missing() -> None:
    with pytest.raises(MissingDatasourceSecretError, match="GENQL_ABSENT_DSN"):
        _service(FakeDatasources()).register("wh2", "postgres", "GENQL_ABSENT_DSN", None)


def test_remove_delegates_to_the_repository() -> None:
    repo = FakeDatasources()
    service = _service(repo)
    service.register("wh2", "postgres", "GENQL_WH2_DSN", None)

    service.remove("wh2")

    assert repo.rows == {}
```

Create `tests/unit/test_schema_registration_service.py`:

```python
"""A schema is verified to exist in the warehouse before it is registered."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.datasource.schema_registration_service import SchemaRegistrationService

DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
REF = SchemaRef(datasource_name="local", schema_name="shop")


class FakeDatasources:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return DS

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [DS]

    def remove(self, name: str) -> None: ...


class FakeRegistrations:
    def __init__(self) -> None:
        self.rows: list[SchemaRegistration] = []

    def add(self, registration: SchemaRegistration) -> None:
        self.rows.append(registration)

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        for row in self.rows:
            if row.ref == ref:
                return row
        raise UnknownSchemaRegistrationError(ref.qualified_name, [])

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        return [r for r in self.rows if r.datasource_name == datasource_name]

    def remove(self, ref: SchemaRef) -> None:
        self.rows = [r for r in self.rows if r.ref != ref]

    def mark_discovered(self, ref: SchemaRef) -> None: ...


class FakeReader:
    def __init__(self, objects: list[DatabaseObject]) -> None:
        self._objects = objects

    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return self._objects

    def read_columns(self, ref: SchemaRef) -> Sequence[object]:
        return []

    def read_constraints(self, ref: SchemaRef) -> Sequence[object]:
        return []


class FakeFactory:
    def __init__(self, reader: FakeReader) -> None:
        self._reader = reader

    def for_datasource(self, datasource: Datasource) -> FakeReader:
        return self._reader


POPULATED = FakeReader(
    [
        DatabaseObject(
            datasource_name="local",
            schema_name="shop",
            object_name="customer",
            object_type=ObjectType.TABLE,
        )
    ]
)
EMPTY = FakeReader([])


def test_register_persists_a_schema_that_exists() -> None:
    registrations = FakeRegistrations()
    service = SchemaRegistrationService(FakeDatasources(), registrations, FakeFactory(POPULATED))

    created = service.register(REF, "the shop")

    assert created.ref == REF
    assert registrations.rows[0].description == "the shop"


def test_register_refuses_a_schema_the_warehouse_does_not_have() -> None:
    service = SchemaRegistrationService(FakeDatasources(), FakeRegistrations(), FakeFactory(EMPTY))

    with pytest.raises(UnknownSchemaRegistrationError, match="local.shop"):
        service.register(REF, None)


def test_remove_delegates_to_the_repository() -> None:
    registrations = FakeRegistrations()
    service = SchemaRegistrationService(FakeDatasources(), registrations, FakeFactory(POPULATED))
    service.register(REF, None)

    service.remove(REF)

    assert registrations.rows == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_datasource_service.py tests/unit/test_schema_registration_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.datasource'`

- [ ] **Step 3: Write `DatasourceService`**

Create `genql/services/datasource/__init__.py` (docstring only), then `genql/services/datasource/datasource_service.py`:

```python
"""Registers, lists, and removes datasources.

Both validations happen at registration rather than at first use. A dialect
nobody implemented and an environment variable nobody set are the two ways a
datasource row can be born useless, and both are cheap to detect here.

`dialects` is a plain list of registered keys rather than the registry itself:
a service may not import from `genql.repositories`, so the composition root
passes the keys in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.registries.errors import UnknownRegistryKeyError


class DatasourceService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        dialects: Sequence[str],
        env: Mapping[str, str],
    ) -> None:
        self._datasources = datasources
        self._dialects = list(dialects)
        self._env = env

    def register(
        self, name: str, dialect: str, dsn_env_var: str, description: str | None
    ) -> Datasource:
        if dialect not in self._dialects:
            raise UnknownRegistryKeyError("catalog_readers", dialect, self._dialects)
        if not self._env.get(dsn_env_var, "").strip():
            raise MissingDatasourceSecretError(name, dsn_env_var)
        datasource = Datasource(
            name=name, dialect=dialect, dsn_env_var=dsn_env_var, description=description
        )
        self._datasources.add(datasource)
        return datasource

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return self._datasources.list_all(enabled_only=enabled_only)

    def remove(self, name: str) -> None:
        self._datasources.remove(name)
```

- [ ] **Step 4: Write `SchemaRegistrationService`**

Create `genql/services/datasource/schema_registration_service.py`:

```python
"""Registers, lists, and removes managed schemas.

Registration reads the datasource's catalog first. A typo in a schema name
would otherwise register happily and then discover nothing, which is a much
worse failure than being refused here.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.ports.catalog_reader_factory import CatalogReaderFactory
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.schema_ref import SchemaRef


class SchemaRegistrationService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        readers: CatalogReaderFactory,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations
        self._readers = readers

    def register(self, ref: SchemaRef, description: str | None) -> SchemaRegistration:
        reader = self._readers.for_datasource(self._datasources.get(ref.datasource_name))
        if not reader.read_objects(ref):
            raise UnknownSchemaRegistrationError(ref.qualified_name, [])
        registration = SchemaRegistration(
            datasource_name=ref.datasource_name,
            schema_name=ref.schema_name,
            description=description,
        )
        self._registrations.add(registration)
        return registration

    def list_for_datasource(self, datasource_name: str) -> Sequence[SchemaRegistration]:
        return self._registrations.list_for_datasource(datasource_name)

    def remove(self, ref: SchemaRef) -> None:
        self._registrations.remove(ref)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_datasource_service.py tests/unit/test_schema_registration_service.py -q`
Expected: PASS — 7 passed

- [ ] **Step 6: Wire both services in the composition root**

Add to `genql/composition_root.py`:

```python
    datasource_service = providers.Singleton(
        DatasourceService,
        datasources=datasource_repository,
        dialects=providers.Callable(CATALOG_READERS.keys),
        env=os.environ,
    )
    schema_registration_service = providers.Singleton(
        SchemaRegistrationService,
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        readers=catalog_reader_factory,
    )
```

Import `CATALOG_READERS` from `genql.repositories.warehouse.registry` and `import genql.repositories.warehouse  # noqa: F401` so the registrations exist by the time `.keys()` is called.

- [ ] **Step 7: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```

- [ ] **Step 8: Commit**

```bash
git add genql/services genql/composition_root.py tests/unit
git commit -m "feat(services): add datasource and schema registration services"
```

---

### Task 7: Scope resolvers

Two implementations behind one registry. `DefaultScopeResolver` fills in what the user omitted; `ExplicitScopeResolver` refuses to guess. The CLI never branches between them — `Settings.scope_resolver` picks the key, so an API process can demand explicitness while the CLI stays convenient.

**Files:**
- Create: `genql/services/scope/__init__.py`, `genql/services/scope/registry.py`, `genql/services/scope/validation.py`, `genql/services/scope/default_scope_resolver.py`, `genql/services/scope/explicit_scope_resolver.py`, `tests/unit/test_scope_resolvers.py`
- Modify: `genql/composition_root.py`
- Test: `tests/unit/test_scope_resolvers.py`

**Interfaces:**
- Consumes: `ScopeResolver`, `QueryScope`, `AmbiguousScopeError`, `UnknownSchemaRegistrationError`, `DatasourceRepository`, `SchemaRegistrationRepository` from Task 1
- Produces: `SCOPE_RESOLVERS: Registry[ScopeResolver]` with `"default"` and `"explicit"` registered; both classes constructed as `(datasources=..., registrations=..., default_datasource=...)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_scope_resolvers.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import (
    AmbiguousScopeError,
    UnknownDatasourceError,
    UnknownSchemaRegistrationError,
)
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.scope.default_scope_resolver import DefaultScopeResolver
from genql.services.scope.explicit_scope_resolver import ExplicitScopeResolver

LOCAL = Datasource(name="local", dialect="postgres", dsn_env_var="A")
WH2 = Datasource(name="wh2", dialect="postgres", dsn_env_var="B")


class FakeDatasources:
    def __init__(self, rows: list[Datasource]) -> None:
        self.rows = {d.name: d for d in rows}

    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        try:
            return self.rows[name]
        except KeyError:
            raise UnknownDatasourceError(name, sorted(self.rows)) from None

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [d for d in self.rows.values() if d.enabled or not enabled_only]

    def remove(self, name: str) -> None: ...


class FakeRegistrations:
    def __init__(self, rows: list[SchemaRegistration]) -> None:
        self.rows = rows

    def add(self, registration: SchemaRegistration) -> None: ...

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        for row in self.rows:
            if row.ref == ref:
                return row
        raise UnknownSchemaRegistrationError(ref.qualified_name, [r.ref.qualified_name for r in self.rows])

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        return [
            r
            for r in self.rows
            if r.datasource_name == datasource_name and (r.enabled or not enabled_only)
        ]

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None: ...


TPCDS = SchemaRegistration(datasource_name="local", schema_name="tpcds")
SHOP = SchemaRegistration(datasource_name="local", schema_name="shop")
STALE = SchemaRegistration(datasource_name="local", schema_name="stale", enabled=False)


def _default(
    datasources: list[Datasource],
    registrations: list[SchemaRegistration],
    default_datasource: str | None = None,
) -> DefaultScopeResolver:
    return DefaultScopeResolver(
        datasources=FakeDatasources(datasources),
        registrations=FakeRegistrations(registrations),
        default_datasource=default_datasource,
    )


def test_sole_enabled_datasource_is_used_when_none_is_given() -> None:
    resolver = _default([LOCAL], [TPCDS, SHOP])

    assert resolver.resolve(None, []) == QueryScope(
        datasource_name="local", schema_names=("tpcds", "shop")
    )


def test_disabled_schemas_are_excluded_from_the_implicit_scope() -> None:
    resolver = _default([LOCAL], [TPCDS, STALE])

    assert resolver.resolve(None, []).schema_names == ("tpcds",)


def test_two_enabled_datasources_and_no_choice_is_ambiguous() -> None:
    resolver = _default([LOCAL, WH2], [TPCDS])

    with pytest.raises(AmbiguousScopeError, match="local"):
        resolver.resolve(None, [])


def test_the_configured_default_settles_ambiguity() -> None:
    resolver = _default([LOCAL, WH2], [TPCDS], default_datasource="local")

    assert resolver.resolve(None, []).datasource_name == "local"


def test_an_explicitly_named_schema_must_be_registered() -> None:
    resolver = _default([LOCAL], [TPCDS])

    with pytest.raises(UnknownSchemaRegistrationError, match="local.absent"):
        resolver.resolve("local", ["absent"])


def test_a_datasource_with_no_registered_schemas_is_rejected() -> None:
    resolver = _default([LOCAL], [])

    with pytest.raises(UnknownSchemaRegistrationError):
        resolver.resolve("local", [])


def test_explicit_resolver_refuses_to_infer_the_datasource() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    with pytest.raises(AmbiguousScopeError):
        resolver.resolve(None, ["tpcds"])


def test_explicit_resolver_refuses_to_infer_the_schemas() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    with pytest.raises(AmbiguousScopeError):
        resolver.resolve("local", [])


def test_explicit_resolver_accepts_a_fully_specified_scope() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    assert resolver.resolve("local", ["tpcds"]) == QueryScope(
        datasource_name="local", schema_names=("tpcds",)
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_scope_resolvers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.scope'`

- [ ] **Step 3: Write the shared validation**

Create `genql/services/scope/validation.py`:

```python
"""Turns a datasource name and schema names into a validated QueryScope.

Shared by both resolvers, which differ only in what they are willing to infer
before they get here.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef


def build_scope(
    datasources: DatasourceRepository,
    registrations: SchemaRegistrationRepository,
    datasource_name: str,
    schema_names: Sequence[str],
) -> QueryScope:
    datasources.get(datasource_name)  # raises UnknownDatasourceError
    enabled = registrations.list_for_datasource(datasource_name, enabled_only=True)
    available = [r.schema_name for r in enabled]

    if not schema_names:
        if not available:
            raise UnknownSchemaRegistrationError(f"{datasource_name}.*", [])
        return QueryScope(datasource_name=datasource_name, schema_names=tuple(available))

    for name in schema_names:
        if name not in available:
            raise UnknownSchemaRegistrationError(
                SchemaRef(datasource_name=datasource_name, schema_name=name).qualified_name,
                [f"{datasource_name}.{a}" for a in available],
            )
    return QueryScope(datasource_name=datasource_name, schema_names=tuple(schema_names))
```

- [ ] **Step 4: Write the two resolvers**

Create `genql/services/scope/default_scope_resolver.py`:

```python
"""Fills in whatever the caller omitted, and refuses to guess when it cannot.

Order of preference for the datasource: what was asked for, then the
configured default, then the sole enabled datasource. More than one candidate
and no way to choose is an error naming the candidates, not a coin flip.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import AmbiguousScopeError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.services.scope.registry import SCOPE_RESOLVERS
from genql.services.scope.validation import build_scope


@SCOPE_RESOLVERS.register("default")
class DefaultScopeResolver:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        default_datasource: str | None = None,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations
        self._default_datasource = default_datasource

    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        return build_scope(
            self._datasources,
            self._registrations,
            self._pick_datasource(datasource_name),
            schema_names,
        )

    def _pick_datasource(self, datasource_name: str | None) -> str:
        if datasource_name is not None:
            return datasource_name
        if self._default_datasource is not None:
            return self._default_datasource
        candidates = [d.name for d in self._datasources.list_all(enabled_only=True)]
        if len(candidates) != 1:
            raise AmbiguousScopeError(candidates)
        return candidates[0]
```

Create `genql/services/scope/explicit_scope_resolver.py`:

```python
"""Requires the caller to say exactly what it means.

Registered for contexts where an implicit default would be dangerous — an API
process serving several tenants, for instance, where "the only enabled
datasource" is an accident of configuration rather than an intention.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import AmbiguousScopeError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.services.scope.registry import SCOPE_RESOLVERS
from genql.services.scope.validation import build_scope


@SCOPE_RESOLVERS.register("explicit")
class ExplicitScopeResolver:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        default_datasource: str | None = None,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations

    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        if datasource_name is None:
            raise AmbiguousScopeError([])
        if not schema_names:
            raise AmbiguousScopeError([datasource_name])
        return build_scope(self._datasources, self._registrations, datasource_name, schema_names)
```

`default_datasource` is accepted and ignored so both resolvers share one constructor signature and the registry can build either from the same arguments.

- [ ] **Step 5: Write the registry and the package init**

Create `genql/services/scope/registry.py`:

```python
"""Scope resolvers, keyed by name.

Phase 5 registers an LLM-backed resolver here. `Settings.scope_resolver`
selects one; no call site names a resolver class.
"""

from __future__ import annotations

from genql.domain.ports.scope_resolver import ScopeResolver
from genql.registries.registry import Registry

SCOPE_RESOLVERS: Registry[ScopeResolver] = Registry("scope_resolvers")
```

Create `genql/services/scope/__init__.py`:

```python
"""Registers every scope resolver with SCOPE_RESOLVERS."""

from __future__ import annotations

from genql.services.scope.default_scope_resolver import DefaultScopeResolver
from genql.services.scope.explicit_scope_resolver import ExplicitScopeResolver

__all__ = ["DefaultScopeResolver", "ExplicitScopeResolver"]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_scope_resolvers.py -q`
Expected: PASS — 9 passed

- [ ] **Step 7: Wire the resolver in the composition root**

Add to `genql/composition_root.py`, importing `genql.services.scope` for the registration side effect and `SCOPE_RESOLVERS` from `genql.services.scope.registry`:

```python
    scope_resolver = providers.Singleton(
        providers.Callable(SCOPE_RESOLVERS.get, settings.provided.scope_resolver),
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        default_datasource=settings.provided.default_datasource,
    )
```

If `dependency-injector` will not accept a provider as the first positional argument of `Singleton`, use a module-level helper instead and provide that:

```python
def _build_scope_resolver(
    key: str,
    datasources: DatasourceRepository,
    registrations: SchemaRegistrationRepository,
    default_datasource: str | None,
) -> ScopeResolver:
    return SCOPE_RESOLVERS.create(
        key,
        datasources=datasources,
        registrations=registrations,
        default_datasource=default_datasource,
    )


    scope_resolver = providers.Singleton(
        _build_scope_resolver,
        key=settings.provided.scope_resolver,
        datasources=datasource_repository,
        registrations=schema_registration_repository,
        default_datasource=settings.provided.default_datasource,
    )
```

Prefer whichever of the two works; try the second if the first raises at container-build time.

- [ ] **Step 8: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```

- [ ] **Step 9: Commit**

```bash
git add genql/services genql/composition_root.py tests/unit
git commit -m "feat(scope): resolve a query scope from optional datasource and schema input"
```

---

### Task 8: Run discovery over a scope

**Files:**
- Create: `genql/domain/value_objects/scope_run_result.py`, `tests/unit/test_run_scope.py`
- Modify: `genql/discovery/runner.py`, `genql/composition_root.py`, `tests/unit/test_discovery_runner.py`
- Test: `tests/unit/test_run_scope.py`

**Interfaces:**
- Consumes: `QueryScope`, `SchemaRef`, `SchemaRegistrationRepository`, `StepResult`, `DiscoveryContext`
- Produces: `ScopeRunResult(ref: SchemaRef, results: tuple[StepResult, ...])` with `.succeeded -> bool`; `DiscoveryRunner(steps, registrations)` with `.run_scope(scope: QueryScope, sample_limit: int, start_from: str | None = None) -> list[ScopeRunResult]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_run_scope.py`:

```python
"""run_scope executes the step sequence once per schema in the scope."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.runner import DiscoveryRunner
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef

SCOPE = QueryScope(datasource_name="local", schema_names=("tpcds", "shop"))


class RecordingStep:
    name: ClassVar[str] = "recording"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def run(self, ctx: DiscoveryContext) -> StepResult:
        self.seen.append(ctx.ref.qualified_name)
        return StepResult(step_name=self.name, succeeded=True, records_written=1, message="ok")


class FailingStep:
    name: ClassVar[str] = "failing"

    def run(self, ctx: DiscoveryContext) -> StepResult:
        return StepResult(step_name=self.name, succeeded=False, records_written=0, message="no")


class FakeRegistrations:
    def __init__(self) -> None:
        self.discovered: list[SchemaRef] = []

    def add(self, registration: object) -> None: ...

    def get(self, ref: SchemaRef) -> object:
        raise NotImplementedError

    def list_for_datasource(self, datasource_name: str, enabled_only: bool = False) -> list[object]:
        return []

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None:
        self.discovered.append(ref)


def test_each_schema_in_the_scope_gets_its_own_run() -> None:
    step = RecordingStep()

    results = DiscoveryRunner([step], FakeRegistrations()).run_scope(SCOPE, sample_limit=5)

    assert step.seen == ["local.tpcds", "local.shop"]
    assert [r.ref.schema_name for r in results] == ["tpcds", "shop"]
    assert all(r.succeeded for r in results)


def test_a_successful_run_stamps_last_discovered_at() -> None:
    registrations = FakeRegistrations()

    DiscoveryRunner([RecordingStep()], registrations).run_scope(SCOPE, sample_limit=5)

    assert [r.qualified_name for r in registrations.discovered] == ["local.tpcds", "local.shop"]


def test_a_failed_schema_is_not_stamped_and_does_not_stop_the_others() -> None:
    registrations = FakeRegistrations()

    results = DiscoveryRunner([FailingStep()], registrations).run_scope(SCOPE, sample_limit=5)

    assert registrations.discovered == []
    assert [r.succeeded for r in results] == [False, False]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_run_scope.py -q`
Expected: FAIL — `TypeError: DiscoveryRunner.__init__() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Write `ScopeRunResult`**

Create `genql/domain/value_objects/scope_run_result.py`:

```python
"""Everything one schema's discovery run produced."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.discovery_step import StepResult
from genql.domain.value_objects.schema_ref import SchemaRef


class ScopeRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: SchemaRef
    results: tuple[StepResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(r.succeeded for r in self.results)
```

- [ ] **Step 4: Add `run_scope` to the runner**

In `genql/discovery/runner.py`, take the registration repository in the constructor and add the method. `run` and `_select` are unchanged:

```python
class DiscoveryRunner:
    def __init__(
        self, steps: Sequence[DiscoveryStep], registrations: SchemaRegistrationRepository
    ) -> None:
        self._steps = list(steps)
        self._registrations = registrations

    def run_scope(
        self, scope: QueryScope, sample_limit: int, start_from: str | None = None
    ) -> list[ScopeRunResult]:
        """Run the step sequence once per schema.

        One schema failing must not abandon the rest of the scope: a broken
        permission on one schema is not a reason to skip the other eleven.
        `last_discovered_at` is stamped only for schemas that finished cleanly,
        so the timestamp means what it says.
        """
        outcomes: list[ScopeRunResult] = []
        for ref in scope.refs():
            ctx = DiscoveryContext(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                sample_limit=sample_limit,
            )
            results = self.run(ctx, start_from=start_from)
            outcome = ScopeRunResult(ref=ref, results=tuple(results))
            if outcome.succeeded:
                self._registrations.mark_discovered(ref)
            outcomes.append(outcome)
        return outcomes
```

Add imports for `QueryScope`, `ScopeRunResult`, and `SchemaRegistrationRepository`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_run_scope.py -q`
Expected: PASS — 3 passed

- [ ] **Step 6: Update the existing runner test and the composition root**

In `tests/unit/test_discovery_runner.py`, every `DiscoveryRunner(steps)` becomes `DiscoveryRunner(steps, FakeRegistrations())` — copy the `FakeRegistrations` class from `tests/unit/test_run_scope.py` rather than importing it across test modules.

In `genql/composition_root.py`, add the new argument:

```python
    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
        registrations=schema_registration_repository,
    )
```

- [ ] **Step 7: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```

- [ ] **Step 8: Commit**

```bash
git add genql tests/unit
git commit -m "feat(discovery): run the pipeline over every schema in a scope"
```

---

### Task 9: CLI surface

**Files:**
- Create: `genql/cli/commands/__init__.py`, `genql/cli/commands/datasource.py`, `genql/cli/commands/schema.py`, `tests/integration/test_cli_datasource.py`
- Modify: `genql/cli/main.py`, `tests/integration/test_cli_discover.py`
- Test: `tests/integration/test_cli_datasource.py`, `tests/integration/test_cli_discover.py`

**Interfaces:**
- Consumes: `DatasourceService`, `SchemaRegistrationService`, `ScopeResolver`, `DiscoveryRunner.run_scope` from Tasks 6–8
- Produces: the `genql datasource` and `genql schema` sub-applications; `genql discover [--datasource] [--schema ...] [--start-from]`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_cli_datasource.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

FIXTURE = """
DROP SCHEMA IF EXISTS clidemo CASCADE;
CREATE SCHEMA clidemo;
CREATE TABLE clidemo.widget (w_id BIGINT PRIMARY KEY, w_name TEXT);
INSERT INTO clidemo.widget VALUES (1, 'bolt'), (2, 'nut');
"""


@pytest.fixture()
def wired(migrated_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'clids'"))
    monkeypatch.setenv("GENQL_CLI_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container().reset_singletons()
    return migrated_engine


def test_datasource_add_then_list(wired: Engine) -> None:
    runner = CliRunner()

    added = runner.invoke(
        app,
        ["datasource", "add", "--name", "clids", "--dialect", "postgres",
         "--dsn-env", "GENQL_CLI_DSN"],
    )
    listed = runner.invoke(app, ["datasource", "list"])

    assert added.exit_code == 0, added.output
    assert listed.exit_code == 0, listed.output
    assert "clids" in listed.output
    assert "GENQL_CLI_DSN" in listed.output


def test_datasource_add_refuses_a_missing_secret(wired: Engine) -> None:
    result = CliRunner().invoke(
        app,
        ["datasource", "add", "--name", "clids", "--dialect", "postgres",
         "--dsn-env", "GENQL_NOT_SET_ANYWHERE"],
    )

    assert result.exit_code == 1
    assert "GENQL_NOT_SET_ANYWHERE" in result.output


def test_schema_add_then_discover_uses_the_registered_scope(wired: Engine) -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        ["datasource", "add", "--name", "clids", "--dialect", "postgres",
         "--dsn-env", "GENQL_CLI_DSN"],
    )
    added = runner.invoke(
        app, ["schema", "add", "--datasource", "clids", "--schema", "clidemo"]
    )
    discovered = runner.invoke(app, ["discover", "--datasource", "clids"])

    assert added.exit_code == 0, added.output
    assert discovered.exit_code == 0, discovered.output
    assert "clids.clidemo" in discovered.output

    with wired.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE datasource_name = 'clids' AND schema_name = 'clidemo'"
            )
        ).scalar_one()
        stamped = conn.execute(
            text(
                "SELECT last_discovered_at IS NOT NULL FROM genql.genql_schema "
                "WHERE datasource_name = 'clids' AND schema_name = 'clidemo'"
            )
        ).scalar_one()
    assert count == 1
    assert stamped is True


def test_schema_add_refuses_a_schema_that_does_not_exist(wired: Engine) -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        ["datasource", "add", "--name", "clids", "--dialect", "postgres",
         "--dsn-env", "GENQL_CLI_DSN"],
    )

    result = runner.invoke(
        app, ["schema", "add", "--datasource", "clids", "--schema", "no_such_schema"]
    )

    assert result.exit_code == 1
    assert "no_such_schema" in result.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_cli_datasource.py -q`
Expected: FAIL — `Error: No such command 'datasource'.` (exit code 2)

- [ ] **Step 3: Write the `datasource` sub-app**

Create `genql/cli/commands/__init__.py` (docstring only), then `genql/cli/commands/datasource.py`:

```python
"""`genql datasource` — register, list, and remove warehouses.

Domain errors are caught here and turned into a message plus exit code 1. A
traceback is the wrong thing to show someone who mistyped an environment
variable name.
"""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.registries.errors import RegistryError

app = typer.Typer(help="Register and inspect datasources")


@app.command("add")
def add(
    name: str = typer.Option(..., "--name", help="Unique datasource name"),
    dialect: str = typer.Option("postgres", "--dialect", help="Registered SQL dialect"),
    dsn_env: str = typer.Option(
        ..., "--dsn-env", help="Name of the environment variable holding the DSN"
    ),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a datasource. The DSN itself is never stored."""
    service = Container().datasource_service()
    try:
        created = service.register(name, dialect, dsn_env, description)
    except (GenqlError, RegistryError) as exc:
        typer.echo(str(exc), err=False)
        raise typer.Exit(code=1) from exc
    typer.echo(f"registered {created.name} ({created.dialect}) -> ${created.dsn_env_var}")


@app.command("list")
def list_datasources(
    enabled_only: bool = typer.Option(False, "--enabled-only"),
) -> None:
    """List registered datasources."""
    for datasource in Container().datasource_service().list_all(enabled_only=enabled_only):
        state = "enabled" if datasource.enabled else "disabled"
        typer.echo(
            f"{datasource.name}\t{datasource.dialect}\t{datasource.dsn_env_var}\t{state}"
        )


@app.command("remove")
def remove(name: str = typer.Option(..., "--name")) -> None:
    """Remove a datasource and, by cascade, everything discovered from it."""
    try:
        Container().datasource_service().remove(name)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"removed {name}")
```

- [ ] **Step 4: Write the `schema` sub-app**

Create `genql/cli/commands/schema.py`:

```python
"""`genql schema` — register, list, and remove managed schemas."""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.schema_ref import SchemaRef

app = typer.Typer(help="Register and inspect schemas")


@app.command("add")
def add(
    datasource: str = typer.Option(..., "--datasource"),
    schema: str = typer.Option(..., "--schema"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a schema after verifying it exists in the datasource."""
    ref = SchemaRef(datasource_name=datasource, schema_name=schema)
    try:
        Container().schema_registration_service().register(ref, description)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"registered {ref.qualified_name}")


@app.command("list")
def list_schemas(
    datasource: str | None = typer.Option(None, "--datasource"),
) -> None:
    """List registered schemas, for one datasource or all of them."""
    container = Container()
    names = (
        [datasource]
        if datasource is not None
        else [d.name for d in container.datasource_service().list_all()]
    )
    service = container.schema_registration_service()
    for name in names:
        for registration in service.list_for_datasource(name):
            state = "enabled" if registration.enabled else "disabled"
            discovered = registration.last_discovered_at or "never"
            typer.echo(f"{registration.ref.qualified_name}\t{state}\t{discovered}")


@app.command("remove")
def remove(
    datasource: str = typer.Option(..., "--datasource"),
    schema: str = typer.Option(..., "--schema"),
) -> None:
    """Remove a schema registration and, by cascade, its catalog rows."""
    ref = SchemaRef(datasource_name=datasource, schema_name=schema)
    try:
        Container().schema_registration_service().remove(ref)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"removed {ref.qualified_name}")
```

- [ ] **Step 5: Rewrite `discover` to resolve a scope**

In `genql/cli/main.py`, mount the sub-apps and replace `discover`:

```python
from genql.cli.commands import datasource as datasource_commands
from genql.cli.commands import schema as schema_commands
from genql.domain.errors import GenqlError

app = typer.Typer(help="GenQL — enterprise NL2SQL with semantic enrichment")
app.add_typer(datasource_commands.app, name="datasource")
app.add_typer(schema_commands.app, name="schema")


@app.command()
def discover(
    datasource: str | None = typer.Option(None, "--datasource", help="Registered datasource"),
    schema: list[str] = typer.Option([], "--schema", help="Registered schema; repeatable"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from this step"),
) -> None:
    """Run the offline discovery pipeline over the resolved scope."""
    container = Container()
    try:
        scope = container.scope_resolver().resolve(datasource, schema)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    outcomes = container.discovery_runner().run_scope(
        scope,
        sample_limit=container.settings().profile_sample_limit,
        start_from=start_from,
    )

    failed = False
    for outcome in outcomes:
        typer.echo(outcome.ref.qualified_name)
        for result in outcome.results:
            marker = "ok  " if result.succeeded else "FAIL"
            typer.echo(f"  {marker} {result.step_name}: {result.message}")
        failed = failed or not outcome.succeeded

    raise typer.Exit(code=1 if failed else 0)
```

Keep the `steps` command exactly as it is.

- [ ] **Step 6: Update the existing discover test for the new output shape**

`tests/integration/test_cli_discover.py` asserted `"ok   catalog_scan" in result.output`. Step results are now indented under the schema they belong to, so change the two assertions to:

```python
    assert "local.e2e" in result.output
    assert "ok   catalog_scan" in result.output
    assert "ok   data_profiling" in result.output
```

and invoke `["discover", "--datasource", "local", "--schema", "e2e"]`. The `wired` fixture must set `GENQL_WAREHOUSE_DSN` (the variable the `local` datasource names) and keep calling `register_schema("local", "e2e")`.

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/integration/test_cli_datasource.py tests/integration/test_cli_discover.py -q`
Expected: PASS — 6 passed

- [ ] **Step 8: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```

- [ ] **Step 9: Commit**

```bash
git add genql/cli tests/integration
git commit -m "feat(cli): add datasource and schema commands; discover over a scope"
```

---

### Task 10: Prove it against a second database

Everything up to here is asserted. This task demonstrates it: a genuinely separate database on the VM, seeded with Pagila, discovered alongside the existing TPC-DS schemas. It also discharges the `UNVERIFIED` marker on the Pagila seed, which has never run for want of a local `psql` client.

**Files:**
- Modify: `data/seed_pagila.sh`, `data/README.md`, `.env.example`, `docs/superpowers/specs/2026-09-05-genql-design.md`
- Create: `tests/integration/test_multi_datasource_discovery.py`
- Test: `tests/integration/test_multi_datasource_discovery.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9
- Produces: the `genql_wh2` database on the VM containing schema `pagila`; a verified `data/seed_pagila.sh`

- [ ] **Step 1: Create the second database on the VM**

```bash
ssh genql-vm "docker exec genql-paradedb psql -U genql -d genql -c 'CREATE DATABASE genql_wh2'"
ssh genql-vm "docker exec genql-paradedb psql -U genql -d genql_wh2 -c 'SELECT current_database()'"
```
Expected: `CREATE DATABASE`, then `genql_wh2`.

- [ ] **Step 2: Make the Pagila seed runnable without a local psql**

The script currently shells out to `psql`, which does not exist on this machine — the reason it was never verified. Replace the three `psql` invocations with a configurable command that reads SQL on stdin, so the same script works locally and through `docker exec` on the VM. Rewrite the tail of `data/seed_pagila.sh` (everything from the `sed` line down) as:

```bash
sed -i.bak 's/\bpublic\./pagila./g' "$TMP/schema.sql" "$TMP/data.sql"

# SEED_EXEC is any command that reads SQL on stdin. The default is a local
# psql; the VM has no local client, so CI and the maintainer both point it at
# the container instead:
#   SEED_EXEC='ssh genql-vm docker exec -i genql-paradedb psql -U genql -d genql_wh2 -v ON_ERROR_STOP=1'
# Word splitting on $SEED_EXEC is deliberate — it is a command line, not a path.
SEED_EXEC="${GENQL_SEED_EXEC:-psql $DSN -v ON_ERROR_STOP=1}"

echo 'CREATE SCHEMA IF NOT EXISTS pagila;' | $SEED_EXEC
$SEED_EXEC < "$TMP/schema.sql"
$SEED_EXEC < "$TMP/data.sql"

echo "pagila loaded"
```

Delete the `UNVERIFIED` paragraph from the script's header comment and replace it with a line naming `GENQL_SEED_EXEC`. Keep the long comment explaining the `public.` → `pagila.` rewrite; it documents a real trap.

- [ ] **Step 3: Run the seed against the second database**

```bash
GENQL_SEED_EXEC='ssh genql-vm docker exec -i genql-paradedb psql -U genql -d genql_wh2 -v ON_ERROR_STOP=1' \
  ./data/seed_pagila.sh
ssh genql-vm "docker exec genql-paradedb psql -U genql -d genql_wh2 -tAc 'SELECT count(*) FROM pagila.film'"
```
Expected: `pagila loaded`, then `1000`.

If the count is not 1000, stop and read the seed output rather than proceeding — a partial load makes every assertion below meaningless.

- [ ] **Step 4: Write the failing multi-datasource test**

Create `tests/integration/test_multi_datasource_discovery.py`:

```python
"""n schemas across n databases, shown rather than asserted.

Requires GENQL_WH2_DSN to point at the genql_wh2 database seeded with Pagila
(see data/README.md). Skipped when it is unset, so the suite still runs on a
machine that has only the primary warehouse.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

WH2_DSN = os.environ.get("GENQL_WH2_DSN", "")

pytestmark = pytest.mark.skipif(not WH2_DSN, reason="GENQL_WH2_DSN not set")

FIXTURE = """
DROP SCHEMA IF EXISTS ds_a CASCADE;
CREATE SCHEMA ds_a;
CREATE TABLE ds_a.alpha (a_id BIGINT PRIMARY KEY, a_name TEXT);
INSERT INTO ds_a.alpha VALUES (1, 'one');
DROP SCHEMA IF EXISTS ds_b CASCADE;
CREATE SCHEMA ds_b;
CREATE TABLE ds_b.beta (b_id BIGINT PRIMARY KEY, b_name TEXT);
INSERT INTO ds_b.beta VALUES (1, 'two');
"""


@pytest.fixture()
def wired(migrated_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
        conn.execute(
            text("DELETE FROM genql.genql_datasource WHERE name IN ('primary', 'secondary')")
        )
    monkeypatch.setenv("GENQL_PRIMARY_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SECONDARY_DSN", WH2_DSN)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container().reset_singletons()
    return migrated_engine


def _register(runner: CliRunner) -> None:
    runner.invoke(
        app,
        ["datasource", "add", "--name", "primary", "--dialect", "postgres",
         "--dsn-env", "GENQL_PRIMARY_DSN"],
    )
    runner.invoke(
        app,
        ["datasource", "add", "--name", "secondary", "--dialect", "postgres",
         "--dsn-env", "GENQL_SECONDARY_DSN"],
    )
    runner.invoke(app, ["schema", "add", "--datasource", "primary", "--schema", "ds_a"])
    runner.invoke(app, ["schema", "add", "--datasource", "primary", "--schema", "ds_b"])
    runner.invoke(app, ["schema", "add", "--datasource", "secondary", "--schema", "pagila"])


def test_two_schemas_of_one_datasource_discover_together(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)

    result = runner.invoke(app, ["discover", "--datasource", "primary"])

    assert result.exit_code == 0, result.output
    assert "primary.ds_a" in result.output
    assert "primary.ds_b" in result.output


def test_a_second_database_discovers_into_the_same_semantic_store(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)

    result = runner.invoke(app, ["discover", "--datasource", "secondary"])

    assert result.exit_code == 0, result.output
    with wired.connect() as conn:
        films = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE datasource_name = 'secondary' AND schema_name = 'pagila'"
            )
        ).scalar_one()
    assert films > 10


def test_identically_named_objects_in_two_datasources_do_not_collide(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)
    runner.invoke(app, ["discover", "--datasource", "primary"])
    runner.invoke(app, ["discover", "--datasource", "secondary"])

    with wired.connect() as conn:
        datasources = conn.execute(
            text("SELECT count(DISTINCT datasource_name) FROM genql.genql_object")
        ).scalar_one()
    assert datasources >= 2


def test_removing_a_datasource_cascades_its_catalog_away(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)
    runner.invoke(app, ["discover", "--datasource", "secondary"])

    runner.invoke(app, ["datasource", "remove", "--name", "secondary"])

    with wired.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM genql.genql_object WHERE datasource_name = 'secondary'")
        ).scalar_one()
    assert remaining == 0
```

- [ ] **Step 5: Run it**

```bash
export GENQL_WH2_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql_wh2
uv run pytest tests/integration/test_multi_datasource_discovery.py -q
```
Expected: PASS — 4 passed

- [ ] **Step 6: Update `.env.example`**

Replace its contents with:

```
# The DSN that the `local` datasource row names. Registering another
# datasource means adding another variable here and pointing a row at it.
GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@localhost:5433/genql
GENQL_WH2_DSN=postgresql+psycopg://genql:genql@localhost:5433/genql_wh2
GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@localhost:5433/genql
GENQL_DEFAULT_DATASOURCE=local
GENQL_SCOPE_RESOLVER=default
GENQL_NEO4J_URI=bolt://localhost:7687
GENQL_NEO4J_USER=neo4j
GENQL_NEO4J_PASSWORD=genqlgenql
GENQL_PROFILE_SAMPLE_LIMIT=5
```

- [ ] **Step 7: Update `data/README.md`**

Rewrite the table and add a datasource section:

```markdown
# Warehouse seeds

| Seed | Database | Command | Purpose |
|---|---|---|---|
| TPC-DS SF1 | `genql` | `uv run python data/seed_tpcds.py --scale 1` | Primary warehouse, verified end to end. 24 tables, cryptic column names, real fiscal date dimension, TPC-DS's documented primary/foreign keys added and ANALYZEd after load, 99 query templates for later behavioural enrichment. |
| Pagila | `genql_wh2` | see below | Second **database**, so multi-datasource discovery is demonstrated rather than assumed. Verified: `SELECT count(*) FROM pagila.film` returns 1000. |

Pagila is loaded through `GENQL_SEED_EXEC`, any command that reads SQL on
stdin. There is no local `psql` on the development machine, so it runs inside
the container on the VM:

```bash
ssh genql-vm "docker exec genql-paradedb psql -U genql -d genql -c 'CREATE DATABASE genql_wh2'"
GENQL_SEED_EXEC='ssh genql-vm docker exec -i genql-paradedb psql -U genql -d genql_wh2 -v ON_ERROR_STOP=1' \
  ./data/seed_pagila.sh
```

## Registering them

```bash
uv run genql datasource add --name local --dialect postgres --dsn-env GENQL_WAREHOUSE_DSN
uv run genql datasource add --name wh2   --dialect postgres --dsn-env GENQL_WH2_DSN
uv run genql schema add --datasource local --schema tpcds
uv run genql schema add --datasource wh2   --schema pagila
uv run genql discover --datasource local
```

Olist (messy real-world data, some Portuguese column names) is added in Phase 4
when ambiguity handling is built.
```

- [ ] **Step 8: Record the phase in the parent spec**

In `docs/superpowers/specs/2026-09-05-genql-design.md`, section 18 "Phasing", insert between items 2 and 3:

```markdown
2.5. **Datasource and schema levels** — `genql_datasource` and `genql_schema`; catalog identity
   re-keyed on `datasource.schema.object`; per-datasource engine and reader resolution; scope
   resolvers; `genql datasource` and `genql schema` commands. See
   `docs/superpowers/specs/2026-09-06-genql-phase-2-5-datasource-and-schema-levels.md`.
```

- [ ] **Step 9: Register the real datasources and re-discover TPC-DS**

```bash
uv run genql datasource list
uv run genql schema add --datasource local --schema tpcds
uv run genql discover --datasource local --schema tpcds
uv run genql schema list
```
Expected: `local.tpcds` discovered, and `schema list` shows a `last_discovered_at` that is not `never`.

- [ ] **Step 10: Run the full suite and the gates**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy genql
uv run lint-imports
```
Expected: all green.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "test(discovery): prove n schemas across n databases with a Pagila second warehouse"
```

---

## Done When

- `genql datasource list` shows `local` and `wh2`; `genql schema list` shows `local.tpcds` and `wh2.pagila` with real discovery timestamps.
- `uv run pytest -q` is green, including `tests/integration/test_multi_datasource_discovery.py`.
- `uv run lint-imports` passes unchanged — the factory ports did not require loosening a single contract.
- `SELECT count(DISTINCT datasource_name) FROM genql.genql_object` returns at least 2.
- `data/README.md` no longer says `UNVERIFIED`.

## Deliberately Not Done

- Cross-datasource joins. A `QueryScope` names one datasource by construction.
- A second dialect. `CATALOG_READERS` has one key; adding a second is one file.
- LLM scope routing. `SCOPE_RESOLVERS` is ready for it in Phase 5.
- Enrichment tables. They do not exist yet and will inherit this scope model in Phase 4.
