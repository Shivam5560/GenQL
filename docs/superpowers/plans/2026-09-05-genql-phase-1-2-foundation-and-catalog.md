# GenQL Phase 1–2: Foundation and Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build GenQL's layered skeleton with mechanically enforced architecture, then use it to scan and profile a real Postgres warehouse catalog into the semantic store.

**Architecture:** Strict one-directional layering — `api` → `services` → `domain`, with `repositories` and `infrastructure` implementing `domain` ports. No SQL exists outside `repositories/`. Extension happens through name-keyed registries rather than modification. Every rule is enforced by `import-linter` contracts in CI, not by convention.

**Tech Stack:** Python 3.12 (uv), ParadeDB 0.25.6 on PostgreSQL 18, psycopg 3, SQLAlchemy 2.0 Core, Alembic, Pydantic v2, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

## Global Constraints

- Python 3.12 exactly. Managed by `uv`; do not use system Python.
- ParadeDB image `paradedb/paradedb:0.25.6-pg18`. Do not substitute plain `postgres`.
- **No SQL string, SQLAlchemy Core construct, or psycopg call may appear outside `genql/repositories/`.** Enforced by import-linter.
- `genql/domain/` imports no other `genql` package and performs no I/O.
- `genql/services/` imports only `genql.domain`. It may not import `genql.repositories`, `genql.infrastructure`, `psycopg`, `sqlalchemy`, or `neo4j`.
- Every file ≤ 250 lines. Enforced by a pre-commit hook.
- One class per file. One action per file.
- `mypy --strict` must pass with zero errors.
- All entities are frozen Pydantic v2 models.
- Commit after every task. Conventional-commit prefixes (`feat:`, `test:`, `chore:`, `refactor:`).
- Docker runs on the Debian VM (`ssh genql-vm`, 100.99.72.99), not locally. The compose stack
  runs there persistently; integration tests connect over Tailscale via
  `GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql`.
  Verified: Docker 29.8.0, x86_64, PG 18.6, pg_search + vector present, volume persistence
  confirmed across container destroy/recreate.

---

## File Structure

```
pyproject.toml                                   deps, ruff, mypy, pytest config
.importlinter                                    layer contracts
.pre-commit-config.yaml                          ruff, mypy, file-length gate
scripts/check_file_length.py                     250-line gate
docker/compose.yaml                              paradedb + neo4j
genql/
  core/settings.py                               pydantic-settings config
  registries/registry.py                         generic Registry[T]
  registries/errors.py                           registry errors
  domain/value_objects/object_type.py            ObjectType enum
  domain/value_objects/constraint_type.py        ConstraintType enum
  domain/entities/database_object.py             DatabaseObject
  domain/entities/column.py                      Column
  domain/entities/constraint.py                  Constraint
  domain/entities/column_profile.py              ColumnProfile
  domain/errors.py                               GenqlError hierarchy
  domain/ports/catalog_reader.py                 CatalogReader protocol
  domain/ports/catalog_writer.py                 CatalogWriter protocol
  domain/ports/profile_reader.py                 ProfileReader protocol
  domain/ports/profile_writer.py                 ProfileWriter protocol
  domain/ports/discovery_step.py                 DiscoveryStep protocol + DiscoveryContext + StepResult
  repositories/warehouse/catalog_reader_repository.py   SQL over pg_catalog
  repositories/warehouse/profile_reader_repository.py   SQL sampling per column
  repositories/semantic/catalog_writer_repository.py    SQL into genql tables
  repositories/semantic/profile_writer_repository.py    SQL into genql_column_profile
  infrastructure/db/engine.py                    SQLAlchemy engine factory
  services/discovery/catalog_scan_service.py     orchestration, no SQL
  services/discovery/profiling_service.py        orchestration, no SQL
  discovery/steps/catalog_scan_step.py           registered step
  discovery/steps/data_profiling_step.py         registered step
  discovery/runner.py                            resumable step runner
  discovery/registry.py                          DiscoveryStepRegistry instance
  composition_root.py                            dependency-injector container
  cli/main.py                                    Typer app
migrations/                                      alembic
tests/                                           unit + integration + contract
data/seed_pagila.sh, data/seed_tpcds.py          warehouse seeds
```

---

### Task 1: Project scaffold and architecture gates

The architecture rules must be enforceable *before* any code exists to violate them.

**Files:**
- Create: `pyproject.toml`, `.importlinter`, `.pre-commit-config.yaml`, `scripts/check_file_length.py`, `genql/__init__.py`, `genql/domain/__init__.py`, `genql/services/__init__.py`, `genql/repositories/__init__.py`, `genql/infrastructure/__init__.py`, `genql/api/__init__.py`, `genql/registries/__init__.py`
- Test: `tests/contract/test_architecture.py`

**Interfaces:**
- Consumes: nothing
- Produces: the `genql` package root; `lint-imports` as a passing command

- [ ] **Step 1: Initialise the project**

```bash
cd /Users/shivamsourav/Desktop/AI/GenQL
uv init --package --name genql --python 3.12 .
uv add pydantic pydantic-settings sqlalchemy "psycopg[binary]" alembic dependency-injector typer structlog
uv add --dev pytest pytest-asyncio mypy ruff import-linter pre-commit testcontainers paramiko
```

- [ ] **Step 2: Write `pyproject.toml` tool config**

Append to `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "PL"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create the package layer directories**

```bash
mkdir -p genql/{core,registries,domain/{entities,value_objects,ports},repositories/{warehouse,semantic},infrastructure/db,services/discovery,discovery/steps,api,cli}
find genql -type d -exec touch {}/__init__.py \;
mkdir -p tests/{unit,integration,contract} scripts
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/contract/__init__.py
```

- [ ] **Step 4: Write the import-linter contracts**

Create `.importlinter`:

```ini
[importlinter]
root_package = genql

[importlinter:contract:layers]
name = GenQL layered architecture
type = layers
layers =
    genql.api
    genql.services
    genql.domain
containers =

[importlinter:contract:domain-is-pure]
name = Domain imports no sibling package
type = forbidden
source_modules =
    genql.domain
forbidden_modules =
    genql.services
    genql.repositories
    genql.infrastructure
    genql.api
    sqlalchemy
    psycopg
    neo4j

[importlinter:contract:no-sql-in-services]
name = Services never touch a database driver
type = forbidden
source_modules =
    genql.services
forbidden_modules =
    genql.repositories
    genql.infrastructure
    sqlalchemy
    psycopg
    neo4j
```

- [ ] **Step 5: Write the file-length gate**

Create `scripts/check_file_length.py`:

```python
"""Fail if any staged Python file exceeds the project line limit."""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 250


def main(paths: list[str]) -> int:
    failures: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > LIMIT:
            failures.append(f"{path}: {lines} lines (limit {LIMIT})")
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 6: Write the pre-commit config**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: file-length
        name: file length under 250 lines
        entry: python scripts/check_file_length.py
        language: system
        types: [python]
      - id: import-linter
        name: architecture contracts
        entry: uv run lint-imports
        language: system
        pass_filenames: false
      - id: mypy
        name: mypy strict
        entry: uv run mypy genql
        language: system
        pass_filenames: false
```

- [ ] **Step 7: Write the failing architecture test**

Create `tests/contract/test_architecture.py`:

```python
"""The layering is enforced mechanically, so it is tested mechanically."""

from __future__ import annotations

import subprocess


def test_import_contracts_hold() -> None:
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_file_length_gate_rejects_a_long_file(tmp_path) -> None:
    offender = tmp_path / "too_long.py"
    offender.write_text("x = 1\n" * 300, encoding="utf-8")
    result = subprocess.run(
        ["python", "scripts/check_file_length.py", str(offender)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "limit 250" in result.stderr
```

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/contract/test_architecture.py -v`
Expected: both PASS. The contracts hold trivially because no modules exist yet — that is the point; the gate is live before there is anything to catch.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold genql package with enforced layering gates"
```

---

### Task 2: Generic registry

**Files:**
- Create: `genql/registries/errors.py`, `genql/registries/registry.py`
- Test: `tests/unit/test_registry.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Registry[T]` with `register(key) -> decorator`, `get(key) -> type[T]`, `keys() -> list[str]`, `create(key, *args, **kwargs) -> T`; `DuplicateRegistrationError`, `UnknownRegistryKeyError`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_registry.py`:

```python
from __future__ import annotations

from typing import Protocol

import pytest

from genql.registries.errors import DuplicateRegistrationError, UnknownRegistryKeyError
from genql.registries.registry import Registry


class Greeter(Protocol):
    def greet(self) -> str: ...


def test_registered_implementation_is_retrievable() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class English:
        def greet(self) -> str:
            return "hello"

    assert registry.get("english") is English
    assert registry.create("english").greet() == "hello"


def test_keys_are_sorted() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("zulu")
    class Zulu:
        def greet(self) -> str:
            return "sawubona"

    @registry.register("arabic")
    class Arabic:
        def greet(self) -> str:
            return "marhaba"

    assert registry.keys() == ["arabic", "zulu"]


def test_duplicate_key_is_rejected() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class First:
        def greet(self) -> str:
            return "hello"

    with pytest.raises(DuplicateRegistrationError) as excinfo:
        @registry.register("english")
        class Second:
            def greet(self) -> str:
                return "hi"

    assert "greeters" in str(excinfo.value)


def test_unknown_key_lists_available_options() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class English:
        def greet(self) -> str:
            return "hello"

    with pytest.raises(UnknownRegistryKeyError) as excinfo:
        registry.get("klingon")

    assert "english" in str(excinfo.value)
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.registries.errors'`

- [ ] **Step 3: Write the errors**

Create `genql/registries/errors.py`:

```python
"""Errors raised by registries."""

from __future__ import annotations


class RegistryError(Exception):
    """Base class for registry failures."""


class DuplicateRegistrationError(RegistryError):
    def __init__(self, registry_name: str, key: str) -> None:
        super().__init__(f"{key!r} is already registered in registry {registry_name!r}")


class UnknownRegistryKeyError(RegistryError):
    def __init__(self, registry_name: str, key: str, available: list[str]) -> None:
        options = ", ".join(available) or "<empty>"
        super().__init__(
            f"{key!r} is not registered in registry {registry_name!r}. Available: {options}"
        )
```

- [ ] **Step 4: Write the registry**

Create `genql/registries/registry.py`:

```python
"""Name-keyed registry.

Adding an implementation is one file plus one decorator. No existing call site
changes, which is the open/closed principle made operational.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

from genql.registries.errors import DuplicateRegistrationError, UnknownRegistryKeyError

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, name: str) -> None:
        self._name = name
        self._items: dict[str, type[T]] = {}

    @property
    def name(self) -> str:
        return self._name

    def register(self, key: str) -> Callable[[type[T]], type[T]]:
        def decorator(implementation: type[T]) -> type[T]:
            if key in self._items:
                raise DuplicateRegistrationError(self._name, key)
            self._items[key] = implementation
            return implementation

        return decorator

    def get(self, key: str) -> type[T]:
        try:
            return self._items[key]
        except KeyError:
            raise UnknownRegistryKeyError(self._name, key, self.keys()) from None

    def create(self, key: str, *args: Any, **kwargs: Any) -> T:
        return self.get(key)(*args, **kwargs)

    def keys(self) -> list[str]:
        return sorted(self._items)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_registry.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add genql/registries tests/unit/test_registry.py
git commit -m "feat: add generic name-keyed registry"
```

---

### Task 3: Domain value objects, entities and errors

**Files:**
- Create: `genql/domain/value_objects/object_type.py`, `genql/domain/value_objects/constraint_type.py`, `genql/domain/entities/database_object.py`, `genql/domain/entities/column.py`, `genql/domain/entities/constraint.py`, `genql/domain/entities/column_profile.py`, `genql/domain/errors.py`
- Test: `tests/unit/test_domain_entities.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ObjectType`, `ConstraintType`, `DatabaseObject(schema_name, object_name, object_type, row_estimate)`, `Column(schema_name, object_name, column_name, ordinal, data_type, is_nullable, is_primary_key)`, `Constraint(schema_name, object_name, constraint_name, constraint_type, definition, referenced_object_name)`, `ColumnProfile(schema_name, object_name, column_name, distinct_count, null_fraction, sample_values)`, `GenqlError`, `DiscoveryError`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_domain_entities.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType


def test_database_object_is_frozen() -> None:
    obj = DatabaseObject(
        schema_name="public",
        object_name="store_sales",
        object_type=ObjectType.TABLE,
        row_estimate=2_880_404,
    )
    with pytest.raises(ValidationError):
        obj.object_name = "other"  # type: ignore[misc]


def test_qualified_name_joins_schema_and_object() -> None:
    obj = DatabaseObject(
        schema_name="public", object_name="store_sales", object_type=ObjectType.TABLE
    )
    assert obj.qualified_name == "public.store_sales"


def test_column_qualified_name_includes_column() -> None:
    column = Column(
        schema_name="public",
        object_name="store_sales",
        column_name="ss_ext_sales_price",
        ordinal=14,
        data_type="numeric(7,2)",
        is_nullable=True,
    )
    assert column.qualified_name == "public.store_sales.ss_ext_sales_price"
    assert column.is_primary_key is False


def test_null_fraction_must_be_a_proportion() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(
            schema_name="public",
            object_name="store_sales",
            column_name="ss_item_sk",
            distinct_count=18_000,
            null_fraction=1.4,
        )


def test_sample_values_are_immutable() -> None:
    profile = ColumnProfile(
        schema_name="public",
        object_name="store",
        column_name="s_state",
        distinct_count=13,
        null_fraction=0.0,
        sample_values=("CA", "OR", "WA"),
    )
    assert isinstance(profile.sample_values, tuple)
    assert profile.sample_values[0] == "CA"
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_domain_entities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.column'`

- [ ] **Step 3: Write the value objects**

Create `genql/domain/value_objects/object_type.py`:

```python
"""Kinds of database object GenQL discovers."""

from __future__ import annotations

from enum import StrEnum


class ObjectType(StrEnum):
    TABLE = "TABLE"
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
```

Create `genql/domain/value_objects/constraint_type.py`:

```python
"""Kinds of constraint that carry relationship meaning."""

from __future__ import annotations

from enum import StrEnum


class ConstraintType(StrEnum):
    PRIMARY_KEY = "PRIMARY_KEY"
    FOREIGN_KEY = "FOREIGN_KEY"
    UNIQUE = "UNIQUE"
```

- [ ] **Step 4: Write the entities**

Create `genql/domain/entities/database_object.py`:

```python
"""A table, view, or materialized view in the target warehouse."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.object_type import ObjectType


class DatabaseObject(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    object_type: ObjectType
    row_estimate: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}"
```

Create `genql/domain/entities/column.py`:

```python
"""A single column of a database object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Column(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    column_name: str
    ordinal: int
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}.{self.column_name}"
```

Create `genql/domain/entities/constraint.py`:

```python
"""A primary key, foreign key, or unique constraint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.constraint_type import ConstraintType


class Constraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    constraint_name: str
    constraint_type: ConstraintType
    definition: str
    referenced_object_name: str | None = None
```

Create `genql/domain/entities/column_profile.py`:

```python
"""Observed statistics for a column.

Sample values are what let a column named TYPE with values
[CREDIT, DEBIT, TRANSFER] be understood as a payment transaction type.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    column_name: str
    distinct_count: int | None = None
    null_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_values: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}.{self.column_name}"
```

- [ ] **Step 5: Write the error hierarchy**

Create `genql/domain/errors.py`:

```python
"""Typed failures. Every stage returns one of these so callers can route."""

from __future__ import annotations


class GenqlError(Exception):
    """Base class for every GenQL failure."""


class DiscoveryError(GenqlError):
    """A discovery step could not complete."""


class CatalogAccessError(DiscoveryError):
    """The target warehouse catalog could not be read."""


class ProfilingError(DiscoveryError):
    """A column could not be profiled."""

    def __init__(self, qualified_name: str, reason: str) -> None:
        super().__init__(f"failed to profile {qualified_name}: {reason}")
        self.qualified_name = qualified_name
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_domain_entities.py tests/contract -v`
Expected: all PASS. The contract test confirms `genql.domain` still imports nothing outward.

- [ ] **Step 7: Commit**

```bash
git add genql/domain tests/unit/test_domain_entities.py
git commit -m "feat: add domain entities, value objects and error hierarchy"
```

---

### Task 4: Domain ports

Ports are how services stay ignorant of SQL. Defining them before any repository exists forces the dependency direction.

**Files:**
- Create: `genql/domain/ports/catalog_reader.py`, `genql/domain/ports/catalog_writer.py`, `genql/domain/ports/profile_reader.py`, `genql/domain/ports/profile_writer.py`
- Test: `tests/unit/test_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `DatabaseObject`, `Column`, `Constraint`, `ColumnProfile` from Task 3
- Produces:
  - `CatalogReader.read_objects(schema: str) -> Sequence[DatabaseObject]`, `.read_columns(schema: str) -> Sequence[Column]`, `.read_constraints(schema: str) -> Sequence[Constraint]`
  - `CatalogWriter.write_objects(Sequence[DatabaseObject]) -> int`, `.write_columns(...) -> int`, `.write_constraints(...) -> int`
  - `ProfileReader.profile_column(column: Column, sample_limit: int) -> ColumnProfile`
  - `ProfileWriter.write_profiles(Sequence[ColumnProfile]) -> int`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ports_are_runtime_checkable.py`:

```python
"""A fake satisfying the protocol proves services can be tested without a database."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.ports.catalog_reader import CatalogReader


class FakeCatalogReader:
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, schema: str) -> Sequence[Column]:
        return []

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return []


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeCatalogReader(), CatalogReader)
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_ports_are_runtime_checkable.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.catalog_reader'`

- [ ] **Step 3: Write the read ports**

Create `genql/domain/ports/catalog_reader.py`:

```python
"""Reads structural metadata from the target warehouse."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class CatalogReader(Protocol):
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]: ...

    def read_columns(self, schema: str) -> Sequence[Column]: ...

    def read_constraints(self, schema: str) -> Sequence[Constraint]: ...
```

Create `genql/domain/ports/profile_reader.py`:

```python
"""Samples real values and statistics for one column."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile


@runtime_checkable
class ProfileReader(Protocol):
    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile: ...
```

- [ ] **Step 4: Write the write ports**

Create `genql/domain/ports/catalog_writer.py`:

```python
"""Persists structural metadata into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class CatalogWriter(Protocol):
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int: ...

    def write_columns(self, columns: Sequence[Column]) -> int: ...

    def write_constraints(self, constraints: Sequence[Constraint]) -> int: ...
```

Create `genql/domain/ports/profile_writer.py`:

```python
"""Persists column profiles into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_profile import ColumnProfile


@runtime_checkable
class ProfileWriter(Protocol):
    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int: ...
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit -v && uv run lint-imports`
Expected: all PASS, contracts hold

- [ ] **Step 6: Commit**

```bash
git add genql/domain/ports tests/unit/test_ports_are_runtime_checkable.py
git commit -m "feat: add catalog and profiling domain ports"
```

---

### Task 5: Settings, Docker Compose and a live connection

**Files:**
- Create: `docker/compose.yaml`, `.env.example`, `genql/core/settings.py`, `genql/infrastructure/db/engine.py`
- Test: `tests/integration/conftest.py`, `tests/integration/test_paradedb_connection.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Settings` (fields `warehouse_dsn`, `semantic_dsn`, `neo4j_uri`, `neo4j_user`, `neo4j_password`, `profile_sample_limit`), `create_engine_from_dsn(dsn: str) -> Engine`

- [ ] **Step 1: Write the compose file**

Create `docker/compose.yaml`:

```yaml
services:
  paradedb:
    image: paradedb/paradedb:0.25.6-pg18
    environment:
      POSTGRES_USER: genql
      POSTGRES_PASSWORD: genql
      POSTGRES_DB: genql
    ports: ["5433:5432"]
    healthcheck:
      # -h 127.0.0.1 is required: pg_isready on the unix socket succeeds against initdb's
      # temporary bootstrap server, reporting healthy before the genql database exists.
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U genql -d genql"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      # PostgreSQL 18 sets PGDATA=/var/lib/postgresql/18/docker and declares its VOLUME at
      # /var/lib/postgresql. Mounting the pre-18 path (/var/lib/postgresql/data) creates an
      # empty volume while the real data stays in the container layer and is lost on `down`.
      - paradedb-data:/var/lib/postgresql

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/genqlgenql
      NEO4J_PLUGINS: '["graph-data-science"]'
      NEO4J_server_memory_heap_max__size: 1G
      NEO4J_server_memory_pagecache_size: 512M
    ports: ["7474:7474", "7687:7687"]
    volumes:
      - neo4j-data:/data

volumes:
  paradedb-data:
  neo4j-data:
```

- [ ] **Step 2: Write `.env.example`**

```bash
GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@localhost:5433/genql
GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@localhost:5433/genql
GENQL_NEO4J_URI=bolt://localhost:7687
GENQL_NEO4J_USER=neo4j
GENQL_NEO4J_PASSWORD=genqlgenql
GENQL_PROFILE_SAMPLE_LIMIT=5
```

- [ ] **Step 3: Write the failing integration test**

Create `tests/integration/conftest.py`:

```python
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from testcontainers.postgres import PostgresContainer

from genql.infrastructure.db.engine import create_engine_from_dsn


@pytest.fixture(scope="session")
def paradedb_dsn() -> Iterator[str]:
    """Prefer a running stack; fall back to an ephemeral container.

    GENQL_TEST_DSN points at the compose stack on the Debian VM. Testcontainers
    against a remote daemon over SSH works but spends minutes per container on
    readiness polling across the link, so it is the fallback, not the default.
    """
    dsn = os.environ.get("GENQL_TEST_DSN")
    if dsn:
        yield dsn
        return

    container = PostgresContainer(
        image="paradedb/paradedb:0.25.6-pg18",
        username="genql",
        password="genql",
        dbname="genql",
        driver="psycopg",
    )
    with container as running:
        yield running.get_connection_url()


@pytest.fixture(scope="session")
def engine(paradedb_dsn: str) -> Engine:
    eng = create_engine_from_dsn(paradedb_dsn)
    with eng.begin() as conn:
        # Order matters: pg_search declares a dependency on vector and fails without it.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
    return eng
```

Create `tests/integration/test_paradedb_connection.py`:

```python
from __future__ import annotations

from sqlalchemy import Engine, text


def test_postgres_is_version_18(engine: Engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SHOW server_version_num")).scalar_one()
    assert int(version) >= 180000


def test_paradedb_extensions_are_available(engine: Engine) -> None:
    with engine.connect() as conn:
        installed = {
            row[0]
            for row in conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('pg_search', 'vector')")
            )
        }
    assert installed == {"pg_search", "vector"}
```

- [ ] **Step 4: Run it to confirm failure**

Run: `uv run pytest tests/integration -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.db.engine'`

- [ ] **Step 5: Write the settings**

Create `genql/core/settings.py`:

```python
"""Process configuration, read once from the environment."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENQL_", env_file=".env", extra="ignore")

    warehouse_dsn: str
    semantic_dsn: str
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "genqlgenql"
    profile_sample_limit: int = 5
```

- [ ] **Step 6: Write the engine factory**

Create `genql/infrastructure/db/engine.py`:

```python
"""SQLAlchemy engine construction.

Engines are created here and injected. No module builds its own.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine


def create_engine_from_dsn(dsn: str) -> Engine:
    return create_engine(dsn, pool_pre_ping=True, future=True)
```

- [ ] **Step 7: Run the tests**

Run: `docker compose -f docker/compose.yaml up -d && uv run pytest tests/integration -v`
Expected: 2 passed. First run pulls the ParadeDB image, which takes a few minutes.

- [ ] **Step 8: Commit**

```bash
git add docker .env.example genql/core genql/infrastructure tests/integration
git commit -m "feat: add ParadeDB and Neo4j compose stack with settings and engine factory"
```

---

### Task 6: Alembic baseline and the catalog schema

**Files:**
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_catalog_tables.py`
- Test: `tests/integration/test_migrations.py`

**Interfaces:**
- Consumes: `create_engine_from_dsn`
- Produces: schema `genql` containing tables `genql_object`, `genql_column`, `genql_constraint`, `genql_column_profile`

- [ ] **Step 1: Initialise alembic**

```bash
uv run alembic init -t generic migrations
```

Then set in `alembic.ini`: `script_location = migrations` and leave `sqlalchemy.url` empty — the DSN is injected in `env.py`.

- [ ] **Step 2: Point `env.py` at settings**

Replace the config section of `migrations/env.py` so the URL comes from settings:

```python
from genql.core.settings import Settings

config = context.config
config.set_main_option("sqlalchemy.url", Settings().semantic_dsn)
```

- [ ] **Step 3: Write the failing test**

Create `tests/integration/test_migrations.py`:

```python
from __future__ import annotations

from sqlalchemy import Engine, text

EXPECTED = {"genql_object", "genql_column", "genql_constraint", "genql_column_profile"}


def test_catalog_tables_exist(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'genql'")
            )
        }
    assert EXPECTED.issubset(tables)


def test_column_is_unique_per_object(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        constraint = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'genql.genql_column'::regclass AND contype = 'u'"
            )
        ).scalar_one()
    assert constraint == "uq_genql_column_identity"
```

Append to `tests/integration/conftest.py`:

```python
from alembic import command
from alembic.config import Config


@pytest.fixture(scope="session")
def migrated_engine(engine: Engine, paradedb_dsn: str) -> Engine:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")
    return engine
```

- [ ] **Step 4: Run it to confirm failure**

Run: `uv run pytest tests/integration/test_migrations.py -v`
Expected: FAIL — the `genql` schema does not exist

- [ ] **Step 5: Write the migration**

Create `migrations/versions/0001_catalog_tables.py`:

```python
"""catalog tables

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS genql")

    op.create_table(
        "genql_object",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("object_type", sa.Text, nullable=False),
        sa.Column("row_estimate", sa.BigInteger),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("schema_name", "object_name", name="uq_genql_object_identity"),
        schema="genql",
    )

    op.create_table(
        "genql_column",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("data_type", sa.Text, nullable=False),
        sa.Column("is_nullable", sa.Boolean, nullable=False),
        sa.Column("is_primary_key", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "schema_name", "object_name", "column_name", name="uq_genql_column_identity"
        ),
        schema="genql",
    )

    op.create_table(
        "genql_constraint",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("constraint_name", sa.Text, nullable=False),
        sa.Column("constraint_type", sa.Text, nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("referenced_object_name", sa.Text),
        sa.UniqueConstraint(
            "schema_name", "object_name", "constraint_name", name="uq_genql_constraint_identity"
        ),
        schema="genql",
    )

    op.create_table(
        "genql_column_profile",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("distinct_count", sa.BigInteger),
        sa.Column("null_fraction", sa.Float),
        sa.Column("sample_values", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("profiled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "schema_name", "object_name", "column_name", name="uq_genql_profile_identity"
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_column_profile", schema="genql")
    op.drop_table("genql_constraint", schema="genql")
    op.drop_table("genql_column", schema="genql")
    op.drop_table("genql_object", schema="genql")
    op.execute("DROP SCHEMA IF EXISTS genql")
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/integration/test_migrations.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add alembic.ini migrations tests/integration/test_migrations.py tests/integration/conftest.py
git commit -m "feat: add alembic baseline with catalog tables"
```

---

### Task 7: Warehouse catalog reader repository

All `pg_catalog` SQL lives here and nowhere else.

**Files:**
- Create: `genql/repositories/warehouse/catalog_reader_repository.py`
- Test: `tests/integration/test_catalog_reader_repository.py`

**Interfaces:**
- Consumes: `CatalogReader` port, `DatabaseObject`, `Column`, `Constraint`, `Engine`
- Produces: `PostgresCatalogReaderRepository(engine: Engine)` implementing `CatalogReader`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_catalog_reader_repository.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)

FIXTURE = """
CREATE SCHEMA IF NOT EXISTS shop;
CREATE TABLE shop.customer (
    c_customer_sk BIGINT PRIMARY KEY,
    c_state       TEXT
);
CREATE TABLE shop.orders (
    o_order_sk    BIGINT PRIMARY KEY,
    o_customer_sk BIGINT NOT NULL REFERENCES shop.customer(c_customer_sk),
    o_amount      NUMERIC(10,2)
);
CREATE VIEW shop.order_summary AS SELECT o_customer_sk, SUM(o_amount) AS total
FROM shop.orders GROUP BY o_customer_sk;
"""


@pytest.fixture(scope="module")
def shop_schema(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text(FIXTURE))
    return engine


def test_reads_tables_and_views(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    objects = {o.object_name: o for o in repo.read_objects("shop")}
    assert set(objects) == {"customer", "orders", "order_summary"}
    assert objects["customer"].object_type is ObjectType.TABLE
    assert objects["order_summary"].object_type is ObjectType.VIEW


def test_reads_columns_with_primary_key_flag(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    columns = {c.qualified_name: c for c in repo.read_columns("shop")}
    pk = columns["shop.customer.c_customer_sk"]
    assert pk.is_primary_key is True
    assert pk.is_nullable is False
    assert pk.ordinal == 1
    assert columns["shop.orders.o_amount"].data_type == "numeric(10,2)"


def test_reads_foreign_key_with_referenced_object(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    fks = [
        c for c in repo.read_constraints("shop") if c.constraint_type is ConstraintType.FOREIGN_KEY
    ]
    assert len(fks) == 1
    assert fks[0].object_name == "orders"
    assert fks[0].referenced_object_name == "customer"
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/integration/test_catalog_reader_repository.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the repository**

Create `genql/repositories/warehouse/catalog_reader_repository.py`:

```python
"""Reads structural metadata from a PostgreSQL warehouse catalog."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType

_RELKIND_TO_TYPE = {
    "r": ObjectType.TABLE,
    "p": ObjectType.TABLE,
    "v": ObjectType.VIEW,
    "m": ObjectType.MATERIALIZED_VIEW,
}
_CONTYPE_TO_TYPE = {
    "p": ConstraintType.PRIMARY_KEY,
    "f": ConstraintType.FOREIGN_KEY,
    "u": ConstraintType.UNIQUE,
}

_OBJECTS_SQL = text("""
    SELECT c.relname, c.relkind, CAST(c.reltuples AS BIGINT) AS row_estimate
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY c.relname
""")

_COLUMNS_SQL = text("""
    SELECT c.relname, a.attname, a.attnum,
           format_type(a.atttypid, a.atttypmod) AS data_type,
           NOT a.attnotnull AS is_nullable,
           COALESCE(pk.is_pk, false) AS is_primary_key
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN LATERAL (
        SELECT true AS is_pk FROM pg_index i
        WHERE i.indrelid = c.oid AND i.indisprimary AND a.attnum = ANY(i.indkey)
    ) pk ON true
    WHERE n.nspname = :schema
      AND a.attnum > 0 AND NOT a.attisdropped
      AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY c.relname, a.attnum
""")

_CONSTRAINTS_SQL = text("""
    SELECT src.relname, con.conname, con.contype,
           pg_get_constraintdef(con.oid) AS definition,
           tgt.relname AS referenced_object_name
    FROM pg_constraint con
    JOIN pg_class src ON src.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = src.relnamespace
    LEFT JOIN pg_class tgt ON tgt.oid = con.confrelid
    WHERE n.nspname = :schema AND con.contype IN ('p', 'f', 'u')
    ORDER BY src.relname, con.conname
""")


class PostgresCatalogReaderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        with self._engine.connect() as conn:
            rows = conn.execute(_OBJECTS_SQL, {"schema": schema}).all()
        return [
            DatabaseObject(
                schema_name=schema,
                object_name=row.relname,
                object_type=_RELKIND_TO_TYPE[row.relkind],
                row_estimate=max(row.row_estimate, 0) if row.row_estimate is not None else None,
            )
            for row in rows
        ]

    def read_columns(self, schema: str) -> Sequence[Column]:
        with self._engine.connect() as conn:
            rows = conn.execute(_COLUMNS_SQL, {"schema": schema}).all()
        return [
            Column(
                schema_name=schema,
                object_name=row.relname,
                column_name=row.attname,
                ordinal=row.attnum,
                data_type=row.data_type,
                is_nullable=row.is_nullable,
                is_primary_key=row.is_primary_key,
            )
            for row in rows
        ]

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        with self._engine.connect() as conn:
            rows = conn.execute(_CONSTRAINTS_SQL, {"schema": schema}).all()
        return [
            Constraint(
                schema_name=schema,
                object_name=row.relname,
                constraint_name=row.conname,
                constraint_type=_CONTYPE_TO_TYPE[row.contype],
                definition=row.definition,
                referenced_object_name=row.referenced_object_name,
            )
            for row in rows
        ]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/integration/test_catalog_reader_repository.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add genql/repositories/warehouse tests/integration/test_catalog_reader_repository.py
git commit -m "feat: add postgres catalog reader repository"
```

---

### Task 8: Semantic catalog writer repository

**Files:**
- Create: `genql/repositories/semantic/catalog_writer_repository.py`
- Test: `tests/integration/test_catalog_writer_repository.py`

**Interfaces:**
- Consumes: `CatalogWriter` port, entities from Task 3, `Engine`
- Produces: `PostgresCatalogWriterRepository(engine: Engine)` implementing `CatalogWriter`. Writes are idempotent upserts keyed on the unique identity constraints from Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_catalog_writer_repository.py`:

```python
from __future__ import annotations

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)


def test_writing_objects_is_idempotent(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    obj = DatabaseObject(
        schema_name="shop",
        object_name="customer",
        object_type=ObjectType.TABLE,
        row_estimate=100,
    )
    assert repo.write_objects([obj]) == 1
    assert repo.write_objects([obj]) == 1

    with migrated_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE schema_name = 'shop' AND object_name = 'customer'"
            )
        ).scalar_one()
    assert count == 1


def test_rewriting_an_object_updates_the_row_estimate(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    base = {
        "schema_name": "shop",
        "object_name": "orders",
        "object_type": ObjectType.TABLE,
    }
    repo.write_objects([DatabaseObject(**base, row_estimate=10)])
    repo.write_objects([DatabaseObject(**base, row_estimate=999)])

    with migrated_engine.connect() as conn:
        estimate = conn.execute(
            text(
                "SELECT row_estimate FROM genql.genql_object "
                "WHERE schema_name = 'shop' AND object_name = 'orders'"
            )
        ).scalar_one()
    assert estimate == 999


def test_writes_columns(migrated_engine: Engine) -> None:
    repo = PostgresCatalogWriterRepository(migrated_engine)
    column = Column(
        schema_name="shop",
        object_name="customer",
        column_name="c_state",
        ordinal=2,
        data_type="text",
        is_nullable=True,
    )
    assert repo.write_columns([column]) == 1
    assert repo.write_columns([column]) == 1
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/integration/test_catalog_writer_repository.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the repository**

Create `genql/repositories/semantic/catalog_writer_repository.py`:

```python
"""Persists catalog metadata into the semantic store.

Every write is an idempotent upsert so a rediscovery run is safe to repeat.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject

_UPSERT_OBJECT = text("""
    INSERT INTO genql.genql_object
        (schema_name, object_name, object_type, row_estimate)
    VALUES (:schema_name, :object_name, :object_type, :row_estimate)
    ON CONFLICT ON CONSTRAINT uq_genql_object_identity DO UPDATE
        SET object_type = EXCLUDED.object_type,
            row_estimate = EXCLUDED.row_estimate,
            discovered_at = now()
""")

_UPSERT_COLUMN = text("""
    INSERT INTO genql.genql_column
        (schema_name, object_name, column_name, ordinal,
         data_type, is_nullable, is_primary_key)
    VALUES (:schema_name, :object_name, :column_name, :ordinal,
            :data_type, :is_nullable, :is_primary_key)
    ON CONFLICT ON CONSTRAINT uq_genql_column_identity DO UPDATE
        SET ordinal = EXCLUDED.ordinal,
            data_type = EXCLUDED.data_type,
            is_nullable = EXCLUDED.is_nullable,
            is_primary_key = EXCLUDED.is_primary_key
""")

_UPSERT_CONSTRAINT = text("""
    INSERT INTO genql.genql_constraint
        (schema_name, object_name, constraint_name, constraint_type,
         definition, referenced_object_name)
    VALUES (:schema_name, :object_name, :constraint_name, :constraint_type,
            :definition, :referenced_object_name)
    ON CONFLICT ON CONSTRAINT uq_genql_constraint_identity DO UPDATE
        SET constraint_type = EXCLUDED.constraint_type,
            definition = EXCLUDED.definition,
            referenced_object_name = EXCLUDED.referenced_object_name
""")


class PostgresCatalogWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        return self._execute(_UPSERT_OBJECT, [o.model_dump(mode="json") for o in objects])

    def write_columns(self, columns: Sequence[Column]) -> int:
        return self._execute(_UPSERT_COLUMN, [c.model_dump(mode="json") for c in columns])

    def write_constraints(self, constraints: Sequence[Constraint]) -> int:
        return self._execute(_UPSERT_CONSTRAINT, [c.model_dump(mode="json") for c in constraints])

    def _execute(self, statement: object, payload: list[dict[str, object]]) -> int:
        if not payload:
            return 0
        with self._engine.begin() as conn:
            conn.execute(statement, payload)  # type: ignore[arg-type]
        return len(payload)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/integration/test_catalog_writer_repository.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add genql/repositories/semantic tests/integration/test_catalog_writer_repository.py
git commit -m "feat: add semantic catalog writer repository with idempotent upserts"
```

---

### Task 9: Discovery step framework

**Files:**
- Create: `genql/domain/ports/discovery_step.py`, `genql/discovery/registry.py`, `genql/discovery/runner.py`
- Test: `tests/unit/test_discovery_runner.py`

**Interfaces:**
- Consumes: `Registry`, `DiscoveryError`
- Produces:
  - `DiscoveryContext(schema: str, sample_limit: int, artifacts: dict[str, object])`
  - `StepResult(step_name: str, succeeded: bool, records_written: int, message: str)`
  - `DiscoveryStep` protocol with `name: ClassVar[str]` and `run(ctx) -> StepResult`
  - `DISCOVERY_STEPS: Registry[DiscoveryStep]`
  - `DiscoveryRunner(steps: Sequence[DiscoveryStep])` with `run(ctx, start_from: str | None) -> list[StepResult]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_discovery_runner.py`:

```python
from __future__ import annotations

from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.discovery.runner import DiscoveryRunner


class RecordingStep:
    def __init__(self, name: str, log: list[str], fail: bool = False) -> None:
        self.name = name
        self._log = log
        self._fail = fail

    def run(self, ctx: DiscoveryContext) -> StepResult:
        self._log.append(self.name)
        if self._fail:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message="boom"
            )
        return StepResult(step_name=self.name, succeeded=True, records_written=1, message="ok")


def _ctx() -> DiscoveryContext:
    return DiscoveryContext(schema_name="shop", sample_limit=5)


def test_steps_run_in_order() -> None:
    log: list[str] = []
    runner = DiscoveryRunner([RecordingStep("a", log), RecordingStep("b", log)])
    results = runner.run(_ctx())
    assert log == ["a", "b"]
    assert [r.step_name for r in results] == ["a", "b"]


def test_run_halts_on_first_failure() -> None:
    log: list[str] = []
    runner = DiscoveryRunner(
        [RecordingStep("a", log), RecordingStep("b", log, fail=True), RecordingStep("c", log)]
    )
    results = runner.run(_ctx())
    assert log == ["a", "b"]
    assert results[-1].succeeded is False


def test_start_from_skips_earlier_steps() -> None:
    log: list[str] = []
    runner = DiscoveryRunner(
        [RecordingStep("a", log), RecordingStep("b", log), RecordingStep("c", log)]
    )
    runner.run(_ctx(), start_from="b")
    assert log == ["b", "c"]
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_discovery_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.discovery_step'`

- [ ] **Step 3: Write the port**

Create `genql/domain/ports/discovery_step.py`:

```python
"""One step of the offline discovery pipeline."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryContext(BaseModel):
    """Carries state between discovery steps.

    The field is `schema_name`, not `schema`: Pydantic v2 raises NameError when a
    field shadows an attribute of BaseModel, and `BaseModel.schema()` still exists
    as a deprecated method. It also matches the entities, which all use schema_name.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_name: str
    sample_limit: int = 5
    artifacts: dict[str, object] = Field(default_factory=dict)


class StepResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_name: str
    succeeded: bool
    records_written: int
    message: str


@runtime_checkable
class DiscoveryStep(Protocol):
    name: ClassVar[str]

    def run(self, ctx: DiscoveryContext) -> StepResult: ...
```

- [ ] **Step 4: Write the registry instance**

Create `genql/discovery/registry.py`:

```python
"""The registry of discovery steps.

A new step is one file plus one decorator.
"""

from __future__ import annotations

from genql.domain.ports.discovery_step import DiscoveryStep
from genql.registries.registry import Registry

DISCOVERY_STEPS: Registry[DiscoveryStep] = Registry("discovery_steps")
```

- [ ] **Step 5: Write the runner**

Create `genql/discovery/runner.py`:

```python
"""Runs discovery steps in order, resumably.

Early steps such as profiling are expensive and need not be repeated when
iterating on later ones, so the runner supports starting from a named step.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from genql.domain.ports.discovery_step import DiscoveryContext, DiscoveryStep, StepResult

_log = structlog.get_logger(__name__)


class DiscoveryRunner:
    def __init__(self, steps: Sequence[DiscoveryStep]) -> None:
        self._steps = list(steps)

    def run(self, ctx: DiscoveryContext, start_from: str | None = None) -> list[StepResult]:
        results: list[StepResult] = []
        for step in self._select(start_from):
            _log.info("discovery.step.start", step=step.name, schema=ctx.schema_name)
            result = step.run(ctx)
            results.append(result)
            _log.info(
                "discovery.step.end",
                step=step.name,
                succeeded=result.succeeded,
                records=result.records_written,
            )
            if not result.succeeded:
                break
        return results

    def _select(self, start_from: str | None) -> list[DiscoveryStep]:
        if start_from is None:
            return self._steps
        names = [s.name for s in self._steps]
        return self._steps[names.index(start_from) :]
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_discovery_runner.py -v && uv run lint-imports`
Expected: 3 passed, contracts hold

- [ ] **Step 7: Commit**

```bash
git add genql/domain/ports/discovery_step.py genql/discovery tests/unit/test_discovery_runner.py
git commit -m "feat: add resumable discovery step framework"
```

---

### Task 10: Catalog scan service and step

The service proves the layering: it orchestrates a full catalog scan while importing nothing but `genql.domain`.

**Files:**
- Create: `genql/services/discovery/catalog_scan_service.py`, `genql/discovery/steps/catalog_scan_step.py`
- Test: `tests/unit/test_catalog_scan_service.py`

**Interfaces:**
- Consumes: `CatalogReader`, `CatalogWriter`, `DiscoveryContext`, `StepResult`
- Produces: `CatalogScanService(reader: CatalogReader, writer: CatalogWriter)` with `scan(schema: str) -> CatalogScanReport`; `CatalogScanReport(objects, columns, constraints)`; `CatalogScanStep` registered under `"catalog_scan"`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_catalog_scan_service.py`:

```python
"""Services are tested with fakes. No database, no network, no container."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.services.discovery.catalog_scan_service import CatalogScanService

OBJECT = DatabaseObject(
    schema_name="shop", object_name="customer", object_type=ObjectType.TABLE, row_estimate=7
)
COLUMN = Column(
    schema_name="shop",
    object_name="customer",
    column_name="c_state",
    ordinal=2,
    data_type="text",
    is_nullable=True,
)
CONSTRAINT = Constraint(
    schema_name="shop",
    object_name="customer",
    constraint_name="customer_pkey",
    constraint_type=ConstraintType.PRIMARY_KEY,
    definition="PRIMARY KEY (c_customer_sk)",
)


class FakeReader:
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return [OBJECT]

    def read_columns(self, schema: str) -> Sequence[Column]:
        return [COLUMN]

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return [CONSTRAINT]


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[DatabaseObject] = []
        self.columns: list[Column] = []
        self.constraints: list[Constraint] = []

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        self.objects.extend(objects)
        return len(objects)

    def write_columns(self, columns: Sequence[Column]) -> int:
        self.columns.extend(columns)
        return len(columns)

    def write_constraints(self, constraints: Sequence[Constraint]) -> int:
        self.constraints.extend(constraints)
        return len(constraints)


def test_scan_persists_everything_it_reads() -> None:
    writer = FakeWriter()
    report = CatalogScanService(FakeReader(), writer).scan("shop")

    assert report.objects == 1
    assert report.columns == 1
    assert report.constraints == 1
    assert writer.objects == [OBJECT]
    assert writer.columns == [COLUMN]
    assert writer.constraints == [CONSTRAINT]


def test_total_counts_all_records() -> None:
    report = CatalogScanService(FakeReader(), FakeWriter()).scan("shop")
    assert report.total == 3
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_catalog_scan_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the service**

Create `genql/services/discovery/catalog_scan_service.py`:

```python
"""Reads a warehouse catalog and persists it to the semantic store.

Depends only on ports. It cannot reach a database even by accident, which is
what makes the unit tests above possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.catalog_writer import CatalogWriter


class CatalogScanReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects: int
    columns: int
    constraints: int

    @property
    def total(self) -> int:
        return self.objects + self.columns + self.constraints


class CatalogScanService:
    def __init__(self, reader: CatalogReader, writer: CatalogWriter) -> None:
        self._reader = reader
        self._writer = writer

    def scan(self, schema: str) -> CatalogScanReport:
        return CatalogScanReport(
            objects=self._writer.write_objects(self._reader.read_objects(schema)),
            columns=self._writer.write_columns(self._reader.read_columns(schema)),
            constraints=self._writer.write_constraints(self._reader.read_constraints(schema)),
        )
```

- [ ] **Step 4: Write the step adapter**

Create `genql/discovery/steps/catalog_scan_step.py`:

```python
"""Step 1 of the discovery pipeline: scan the warehouse catalog."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.catalog_scan_service import CatalogScanService


@DISCOVERY_STEPS.register("catalog_scan")
class CatalogScanStep:
    name: ClassVar[str] = "catalog_scan"

    def __init__(self, service: CatalogScanService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        report = self._service.scan(ctx.schema_name)
        ctx.artifacts["catalog_scan"] = report
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.total,
            message=(
                f"{report.objects} objects, {report.columns} columns, "
                f"{report.constraints} constraints"
            ),
        )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit -v && uv run lint-imports`
Expected: all PASS. `lint-imports` confirms `genql.services` imported no driver.

- [ ] **Step 6: Commit**

```bash
git add genql/services genql/discovery/steps/catalog_scan_step.py tests/unit/test_catalog_scan_service.py
git commit -m "feat: add catalog scan service and discovery step"
```

---

### Task 11: Data profiling

Sampled values are what anchor later LLM descriptions to reality rather than guesswork.

**Files:**
- Create: `genql/repositories/warehouse/profile_reader_repository.py`, `genql/repositories/semantic/profile_writer_repository.py`, `genql/services/discovery/profiling_service.py`, `genql/discovery/steps/data_profiling_step.py`
- Test: `tests/unit/test_profiling_service.py`, `tests/integration/test_profile_reader_repository.py`

**Interfaces:**
- Consumes: `ProfileReader`, `ProfileWriter`, `Column`, `ColumnProfile`, `CatalogReader`
- Produces: `PostgresProfileReaderRepository(engine)`, `PostgresProfileWriterRepository(engine)`, `ProfilingService(catalog, reader, writer)` with `profile(schema, sample_limit) -> int`, `DataProfilingStep` registered under `"data_profiling"`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_profile_reader_repository.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)

FIXTURE = """
CREATE SCHEMA IF NOT EXISTS prof;
DROP TABLE IF EXISTS prof.payment;
CREATE TABLE prof.payment (id BIGINT, kind TEXT);
INSERT INTO prof.payment (id, kind)
SELECT g, (ARRAY['CREDIT','DEBIT','TRANSFER'])[1 + g % 3] FROM generate_series(1, 90) g;
INSERT INTO prof.payment (id, kind) VALUES (91, NULL), (92, NULL);
"""


@pytest.fixture(scope="module")
def prof_schema(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text(FIXTURE))
    return engine


def _column(name: str, data_type: str) -> Column:
    return Column(
        schema_name="prof",
        object_name="payment",
        column_name=name,
        ordinal=1,
        data_type=data_type,
        is_nullable=True,
    )


def test_profiles_distinct_count_and_samples(prof_schema: Engine) -> None:
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column("kind", "text"), sample_limit=5)

    assert profile.distinct_count == 3
    assert set(profile.sample_values) <= {"CREDIT", "DEBIT", "TRANSFER"}
    assert profile.null_fraction == pytest.approx(2 / 92, abs=1e-3)


def test_sample_limit_is_respected(prof_schema: Engine) -> None:
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column("id", "bigint"), sample_limit=2)
    assert len(profile.sample_values) == 2


def test_identifiers_are_quoted_not_interpolated(prof_schema: Engine) -> None:
    """A hostile column name must not become SQL."""
    with prof_schema.begin() as conn:
        conn.execute(text('ALTER TABLE prof.payment ADD COLUMN "weird ""name" TEXT'))
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column('weird "name', "text"), sample_limit=5)
    assert profile.distinct_count == 0
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/integration/test_profile_reader_repository.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the profile reader repository**

Identifiers are dynamic here, so they are composed with psycopg's `Identifier` rather than interpolated into a string.

Create `genql/repositories/warehouse/profile_reader_repository.py`:

```python
"""Samples statistics and real values for a single column.

Column and table names are dynamic, so they are composed through
psycopg.sql.Identifier. Never format an identifier into a query string.
"""

from __future__ import annotations

from psycopg import sql
from sqlalchemy import Engine

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.errors import ProfilingError

_STATS = sql.SQL("""
    SELECT count(DISTINCT {col}) AS distinct_count,
           avg(CASE WHEN {col} IS NULL THEN 1.0 ELSE 0.0 END) AS null_fraction
    FROM {tbl}
""")

_SAMPLES = sql.SQL("""
    SELECT DISTINCT {col}::text AS value
    FROM {tbl}
    WHERE {col} IS NOT NULL
    LIMIT %(limit)s
""")


class PostgresProfileReaderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile:
        col = sql.Identifier(column.column_name)
        tbl = sql.Identifier(column.schema_name, column.object_name)
        try:
            with self._engine.raw_connection() as raw:
                with raw.cursor() as cur:  # type: ignore[union-attr]
                    cur.execute(_STATS.format(col=col, tbl=tbl))
                    distinct_count, null_fraction = cur.fetchone()
                    cur.execute(
                        _SAMPLES.format(col=col, tbl=tbl), {"limit": sample_limit}
                    )
                    samples = tuple(row[0] for row in cur.fetchall())
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed domain error
            raise ProfilingError(column.qualified_name, str(exc)) from exc

        return ColumnProfile(
            schema_name=column.schema_name,
            object_name=column.object_name,
            column_name=column.column_name,
            distinct_count=distinct_count,
            null_fraction=float(null_fraction) if null_fraction is not None else None,
            sample_values=samples,
        )
```

- [ ] **Step 4: Write the profile writer repository**

Create `genql/repositories/semantic/profile_writer_repository.py`:

```python
"""Persists column profiles into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column_profile import ColumnProfile

_UPSERT = text("""
    INSERT INTO genql.genql_column_profile
        (schema_name, object_name, column_name, distinct_count, null_fraction, sample_values)
    VALUES (:schema_name, :object_name, :column_name,
            :distinct_count, :null_fraction, :sample_values)
    ON CONFLICT ON CONSTRAINT uq_genql_profile_identity DO UPDATE
        SET distinct_count = EXCLUDED.distinct_count,
            null_fraction = EXCLUDED.null_fraction,
            sample_values = EXCLUDED.sample_values,
            profiled_at = now()
""")


class PostgresProfileWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int:
        if not profiles:
            return 0
        payload = [
            {
                "schema_name": p.schema_name,
                "object_name": p.object_name,
                "column_name": p.column_name,
                "distinct_count": p.distinct_count,
                "null_fraction": p.null_fraction,
                "sample_values": list(p.sample_values),
            }
            for p in profiles
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT, payload)
        return len(payload)
```

- [ ] **Step 5: Write the failing service test**

Create `tests/unit/test_profiling_service.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.errors import ProfilingError
from genql.services.discovery.profiling_service import ProfilingService

COLUMNS = [
    Column(
        schema_name="shop",
        object_name="customer",
        column_name=name,
        ordinal=i + 1,
        data_type="text",
        is_nullable=True,
    )
    for i, name in enumerate(["c_state", "c_broken"])
]


class FakeCatalog:
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, schema: str) -> Sequence[Column]:
        return COLUMNS

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return []


class FakeProfileReader:
    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile:
        if column.column_name == "c_broken":
            raise ProfilingError(column.qualified_name, "type not comparable")
        return ColumnProfile(
            schema_name=column.schema_name,
            object_name=column.object_name,
            column_name=column.column_name,
            distinct_count=13,
            null_fraction=0.0,
            sample_values=("CA", "OR"),
        )


class FakeProfileWriter:
    def __init__(self) -> None:
        self.written: list[ColumnProfile] = []

    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int:
        self.written.extend(profiles)
        return len(profiles)


def test_a_failing_column_does_not_abort_the_run() -> None:
    writer = FakeProfileWriter()
    service = ProfilingService(FakeCatalog(), FakeProfileReader(), writer)

    written = service.profile("shop", sample_limit=5)

    assert written == 1
    assert [p.column_name for p in writer.written] == ["c_state"]


def test_skipped_columns_are_reported() -> None:
    service = ProfilingService(FakeCatalog(), FakeProfileReader(), FakeProfileWriter())
    service.profile("shop", sample_limit=5)
    assert service.skipped == ["shop.customer.c_broken"]
```

- [ ] **Step 6: Run it to confirm failure**

Run: `uv run pytest tests/unit/test_profiling_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Write the service**

Create `genql/services/discovery/profiling_service.py`:

```python
"""Profiles every column of a schema.

One unprofilable column must not lose the other four hundred, so failures are
collected and reported rather than raised.
"""

from __future__ import annotations

import structlog

from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.errors import ProfilingError
from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.profile_reader import ProfileReader
from genql.domain.ports.profile_writer import ProfileWriter

_log = structlog.get_logger(__name__)


class ProfilingService:
    def __init__(
        self, catalog: CatalogReader, reader: ProfileReader, writer: ProfileWriter
    ) -> None:
        self._catalog = catalog
        self._reader = reader
        self._writer = writer
        self.skipped: list[str] = []

    def profile(self, schema: str, sample_limit: int) -> int:
        self.skipped = []
        profiles: list[ColumnProfile] = []
        for column in self._catalog.read_columns(schema):
            try:
                profiles.append(self._reader.profile_column(column, sample_limit))
            except ProfilingError as exc:
                self.skipped.append(exc.qualified_name)
                _log.warning("profiling.skipped", column=exc.qualified_name, reason=str(exc))
        return self._writer.write_profiles(profiles)
```

- [ ] **Step 8: Write the step adapter**

Create `genql/discovery/steps/data_profiling_step.py`:

```python
"""Step 2 of the discovery pipeline: sample real values per column."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.profiling_service import ProfilingService


@DISCOVERY_STEPS.register("data_profiling")
class DataProfilingStep:
    name: ClassVar[str] = "data_profiling"

    def __init__(self, service: ProfilingService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        written = self._service.profile(ctx.schema_name, ctx.sample_limit)
        skipped = self._service.skipped
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=written,
            message=f"{written} columns profiled, {len(skipped)} skipped",
        )
```

- [ ] **Step 9: Run every test**

Run: `uv run pytest -v && uv run lint-imports && uv run mypy genql`
Expected: all PASS, contracts hold, zero type errors

- [ ] **Step 10: Commit**

```bash
git add genql/repositories genql/services genql/discovery tests
git commit -m "feat: add column profiling repositories, service and discovery step"
```

---

### Task 12: Composition root and CLI

**Files:**
- Create: `genql/composition_root.py`, `genql/cli/main.py`
- Modify: `pyproject.toml` (add the `genql` script entry point)
- Test: `tests/integration/test_cli_discover.py`

**Interfaces:**
- Consumes: every repository and service above
- Produces: `Container` (dependency-injector) with providers `settings`, `warehouse_engine`, `semantic_engine`, `catalog_scan_service`, `profiling_service`, `discovery_runner`; CLI commands `genql discover --schema NAME [--start-from STEP]` and `genql steps`

- [ ] **Step 1: Write the container**

Create `genql/composition_root.py`:

```python
"""The only place that constructs dependencies."""

from __future__ import annotations

from dependency_injector import containers, providers

from genql.core.settings import Settings
from genql.discovery.runner import DiscoveryRunner
from genql.discovery.steps.catalog_scan_step import CatalogScanStep
from genql.discovery.steps.data_profiling_step import DataProfilingStep
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.repositories.semantic.catalog_writer_repository import (
    PostgresCatalogWriterRepository,
)
from genql.repositories.semantic.profile_writer_repository import (
    PostgresProfileWriterRepository,
)
from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)
from genql.services.discovery.catalog_scan_service import CatalogScanService
from genql.services.discovery.profiling_service import ProfilingService


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(Settings)

    warehouse_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.warehouse_dsn
    )
    semantic_engine = providers.Singleton(
        create_engine_from_dsn, dsn=settings.provided.semantic_dsn
    )

    catalog_reader = providers.Singleton(PostgresCatalogReaderRepository, engine=warehouse_engine)
    catalog_writer = providers.Singleton(PostgresCatalogWriterRepository, engine=semantic_engine)
    profile_reader = providers.Singleton(PostgresProfileReaderRepository, engine=warehouse_engine)
    profile_writer = providers.Singleton(PostgresProfileWriterRepository, engine=semantic_engine)

    catalog_scan_service = providers.Singleton(
        CatalogScanService, reader=catalog_reader, writer=catalog_writer
    )
    profiling_service = providers.Factory(
        ProfilingService,
        catalog=catalog_reader,
        reader=profile_reader,
        writer=profile_writer,
    )

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(
            providers.Factory(CatalogScanStep, service=catalog_scan_service),
            providers.Factory(DataProfilingStep, service=profiling_service),
        ),
    )
```

- [ ] **Step 2: Write the CLI**

Create `genql/cli/main.py`:

```python
"""GenQL command line."""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.ports.discovery_step import DiscoveryContext

app = typer.Typer(help="GenQL — enterprise NL2SQL with semantic enrichment")


@app.command()
def steps() -> None:
    """List registered discovery steps."""
    for name in DISCOVERY_STEPS.keys():
        typer.echo(name)


@app.command()
def discover(
    schema: str = typer.Option(..., "--schema", help="Warehouse schema to discover"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from this step"),
) -> None:
    """Run the offline discovery pipeline."""
    container = Container()
    runner = container.discovery_runner()
    ctx = DiscoveryContext(
        schema_name=schema, sample_limit=container.settings().profile_sample_limit
    )

    failed = False
    for result in runner.run(ctx, start_from=start_from):
        marker = "ok  " if result.succeeded else "FAIL"
        typer.echo(f"{marker} {result.step_name}: {result.message}")
        failed = failed or not result.succeeded

    raise typer.Exit(code=1 if failed else 0)


if __name__ == "__main__":
    app()
```

- [ ] **Step 3: Register the entry point**

Add to `pyproject.toml`:

```toml
[project.scripts]
genql = "genql.cli.main:app"
```

- [ ] **Step 4: Write the failing end-to-end test**

Create `tests/integration/test_cli_discover.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

FIXTURE = """
CREATE SCHEMA IF NOT EXISTS e2e;
DROP TABLE IF EXISTS e2e.region;
CREATE TABLE e2e.region (r_id BIGINT PRIMARY KEY, r_name TEXT);
INSERT INTO e2e.region VALUES (1, 'West'), (2, 'East'), (3, 'North');
"""


@pytest.fixture()
def wired(migrated_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
    monkeypatch.setenv("GENQL_WAREHOUSE_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container.reset_singletons()
    return migrated_engine


def test_discover_scans_and_profiles(wired: Engine) -> None:
    result = CliRunner().invoke(app, ["discover", "--schema", "e2e"])

    assert result.exit_code == 0, result.output
    assert "ok   catalog_scan" in result.output
    assert "ok   data_profiling" in result.output

    with wired.connect() as conn:
        samples = conn.execute(
            text(
                "SELECT sample_values FROM genql.genql_column_profile "
                "WHERE object_name = 'region' AND column_name = 'r_name'"
            )
        ).scalar_one()
    assert set(samples) == {"West", "East", "North"}


def test_steps_lists_the_registry() -> None:
    result = CliRunner().invoke(app, ["steps"])
    assert result.exit_code == 0
    assert result.output.split() == ["catalog_scan", "data_profiling"]
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/integration/test_cli_discover.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add genql/composition_root.py genql/cli pyproject.toml tests/integration/test_cli_discover.py
git commit -m "feat: add composition root and discovery CLI"
```

---

### Task 13: Warehouse seeds

**Files:**
- Create: `data/seed_pagila.sh`, `data/seed_tpcds.py`, `data/README.md`
- Test: `tests/integration/test_tpcds_seed_shape.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: schema `tpcds` populated at scale factor 1; schema `pagila` populated from the upstream dump

- [ ] **Step 1: Add the DuckDB dependency**

```bash
uv add --group data duckdb
```

- [ ] **Step 2: Write the TPC-DS seeder**

Create `data/seed_tpcds.py`:

```python
"""Generate TPC-DS at a given scale factor and load it into Postgres.

TPC-DS is chosen because its column names are deliberately cryptic
(ss_ext_sales_price, d_moy, cd_demo_sk), which gives schema discovery real work.
"""

from __future__ import annotations

import argparse
import pathlib
import tempfile

import duckdb
from sqlalchemy import text

from genql.core.settings import Settings
from genql.infrastructure.db.engine import create_engine_from_dsn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--schema", default="tpcds")
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("INSTALL tpcds; LOAD tpcds;")
    con.execute(f"CALL dsdgen(sf={args.scale})")
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]

    engine = create_engine_from_dsn(Settings().warehouse_dsn)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"'))

    with tempfile.TemporaryDirectory() as tmp:
        for table in tables:
            ddl = con.execute(
                "SELECT sql FROM duckdb_tables() WHERE table_name = ?", [table]
            ).fetchone()[0]
            csv_path = pathlib.Path(tmp) / f"{table}.csv"
            con.execute(f"COPY {table} TO '{csv_path}' (HEADER, DELIMITER ',')")
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO "{args.schema}"'))
                conn.execute(text(ddl))
                raw = conn.connection.driver_connection
                with raw.cursor() as cur, csv_path.open() as fh:
                    with cur.copy(
                        f'COPY "{args.schema}"."{table}" FROM STDIN WITH (FORMAT csv, HEADER)'
                    ) as copy:
                        for line in fh:
                            copy.write(line)
            print(f"loaded {table}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Write the Pagila seeder**

Create `data/seed_pagila.sh`:

```bash
#!/usr/bin/env bash
# Pagila is the Postgres port of Sakila: small, clean, fast test loop.
set -euo pipefail

DSN="${GENQL_WAREHOUSE_DSN_PSQL:-postgresql://genql:genql@localhost:5433/genql}"
BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"
TMP="$(mktemp -d)"

curl -sSfL "$BASE/pagila-schema.sql" -o "$TMP/schema.sql"
curl -sSfL "$BASE/pagila-data.sql"   -o "$TMP/data.sql"

psql "$DSN" -c 'CREATE SCHEMA IF NOT EXISTS pagila'
PGOPTIONS='--search_path=pagila' psql "$DSN" -q -f "$TMP/schema.sql"
PGOPTIONS='--search_path=pagila' psql "$DSN" -q -f "$TMP/data.sql"

echo "pagila loaded"
```

Make it executable: `chmod +x data/seed_pagila.sh`

- [ ] **Step 4: Write the shape test**

Create `tests/integration/test_tpcds_seed_shape.py`:

```python
"""Guards the properties of TPC-DS that make it the right discovery fixture."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

CRYPTIC = ["ss_ext_sales_price", "d_moy", "cd_demo_sk"]


@pytest.mark.skipif_no_tpcds
def test_schema_has_the_expected_object_count(engine: Engine) -> None:
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'tpcds'")
        ).scalar_one()
    assert count >= 24


@pytest.mark.skipif_no_tpcds
def test_cryptic_column_names_are_present(engine: Engine) -> None:
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'tpcds'"
                )
            )
        }
    assert set(CRYPTIC).issubset(names)
```

Add to `tests/integration/conftest.py`:

```python
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "skipif_no_tpcds: skip unless the tpcds schema has been seeded"
    )


@pytest.fixture(autouse=True)
def _skip_without_tpcds(request: pytest.FixtureRequest, engine: Engine) -> None:
    if request.node.get_closest_marker("skipif_no_tpcds") is None:
        return
    with engine.connect() as conn:
        seeded = conn.execute(
            text("SELECT to_regclass('tpcds.store_sales') IS NOT NULL")
        ).scalar_one()
    if not seeded:
        pytest.skip("tpcds schema not seeded; run data/seed_tpcds.py")
```

- [ ] **Step 5: Seed and run the full pipeline**

```bash
uv run python data/seed_tpcds.py --scale 1
uv run genql discover --schema tpcds
```

Expected output shape:

```
ok   catalog_scan: 24 objects, 425 columns, 24 constraints
ok   data_profiling: 425 columns profiled, 0 skipped
```

- [ ] **Step 6: Run every gate**

Run: `uv run pytest -v && uv run lint-imports && uv run mypy genql && uv run pre-commit run --all-files`
Expected: all PASS

- [ ] **Step 7: Write `data/README.md`**

```markdown
# Warehouse seeds

| Seed | Command | Purpose |
|---|---|---|
| TPC-DS SF1 | `uv run python data/seed_tpcds.py --scale 1` | Primary warehouse. 24 tables, cryptic column names, real fiscal date dimension, 99 query templates for later behavioural enrichment. |
| Pagila | `./data/seed_pagila.sh` | Small clean fixture for a fast test loop. |

Olist (messy real-world data, some Portuguese column names) is added in Phase 4
when ambiguity handling is built.
```

- [ ] **Step 8: Commit**

```bash
git add data tests/integration/test_tpcds_seed_shape.py tests/integration/conftest.py
git commit -m "feat: add TPC-DS and Pagila warehouse seeds"
```

---

## Definition of done for Phases 1–2

- `uv run genql discover --schema tpcds` scans and profiles a real 24-table warehouse.
- `uv run genql steps` lists steps from the registry, proving extension needs no call-site edits.
- `uv run lint-imports` passes, so no SQL exists outside `repositories/` and `domain/` imports nothing.
- `uv run mypy genql` reports zero errors under `--strict`.
- Services have unit tests that run with no database and no container.
- Every file is under 250 lines.

## What Phase 3 picks up

The Neo4j projection, Leiden communities, FastRP embeddings, fused clustering, domain naming, and join-path mining — all reading the `genql_object`, `genql_column`, `genql_constraint`, and `genql_column_profile` tables this plan fills.
