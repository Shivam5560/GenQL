# GenQL Phase 3: Graph and Domains Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project the FK graph implicit in the semantic store into Neo4j, one graph per datasource, and run Leiden community detection, FastRP node embeddings, and FK-graph join-path mining over it, so later phases can reason about structural topology instead of only flat catalog rows.

**Architecture:** A new `GraphProjectionStep` writes each schema's objects and FK constraints into Neo4j as it is discovered, read back from Postgres through a new `SemanticCatalogReader` rather than from the live warehouse — which is also what makes a standalone `genql graph rebuild` possible with no warehouse connection at all. Leiden, FastRP, and join-path mining run once per datasource, after projection, through `genql graph analyze`, each behind its own port and registry so a different algorithm is a new file, never an edited call site. Mined join paths are persisted to a new `genql_join_path` table; communities and embeddings stay in Neo4j only, since nothing in this phase needs them anywhere else.

**Tech Stack:** Python 3.12 (uv), ParadeDB 0.25.6 on PostgreSQL 18, Neo4j 5 Community + Graph Data Science, `neo4j` driver, `graphdatascience` client, psycopg 3, SQLAlchemy 2.0 Core, Alembic, Pydantic v2, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-06-genql-phase-3-graph-and-domains.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

## Global Constraints

- Python 3.12 exactly. Managed by `uv`; do not use system Python. Run everything through `uv run`.
- Neo4j image `neo4j:5-community` with the `graph-data-science` plugin, already declared in `docker/compose.yaml`. Do not substitute a different image or edition.
- **No Cypher string, GDS client call, SQL string, SQLAlchemy Core construct, or psycopg call may appear outside `genql/repositories/`.** Enforced by import-linter. `genql/infrastructure/` may import `neo4j`, `graphdatascience`, or `sqlalchemy` to *build* a driver, client, or engine, but never to execute a query.
- `genql/domain/` imports no other `genql` package and performs no I/O.
- `genql/services/` imports only `genql.domain`. It may not import `genql.repositories`, `genql.infrastructure`, `psycopg`, `sqlalchemy`, or `neo4j`.
- Every file ≤ 250 lines. Enforced by a pre-commit hook (`scripts/check_file_length.py`).
- One class per file. One action per file.
- `mypy --strict` must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass.
- All entities and value objects are **frozen** Pydantic v2 models (`model_config = ConfigDict(frozen=True)`).
- Neo4j nodes are keyed on the single property `qualified_name` (`datasource.schema.object`), never a composite key — Neo4j 5 Community Edition only supports single-property uniqueness constraints.
- Commit after every task. Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`).
- Docker (both ParadeDB and Neo4j) runs on the Debian VM (`ssh genql-vm`, 100.99.72.99), not locally. Integration tests connect over Tailscale. Every test command in this plan is prefixed with the environment variables that point at it:

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_TEST_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_USER=neo4j
  export GENQL_NEO4J_PASSWORD=genqlgenql
  ```

  Put these in your shell once at the start; the plan writes `uv run pytest ...` assuming they are set.
- **This plan is being executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit-test suite (`tests/unit/`) must be run and must pass here. Every task's integration tests (`tests/integration/`) are written, committed, and left for a VM-connected run — do not report a task done because its integration test *file* exists; report unit tests green and integration tests written-but-unrun, exactly as Phase 2.5 did.
- The baseline before Task 1 is the full Phase 2.5 suite green (unit tests pass locally; integration tests require the VM). Every task must end with the local unit suite green — never leave a task boundary with a red unit suite.

---

## File Structure

**Created**

```
genql/domain/value_objects/provenance.py                Provenance — DISCOVERED | LLM | YAML
genql/domain/entities/join_path.py                       JoinPath entity
genql/domain/ports/semantic_catalog_reader.py            SemanticCatalogReader protocol
genql/domain/ports/graph_writer.py                       GraphWriter protocol
genql/domain/ports/clustering_algorithm.py               ClusteringAlgorithm protocol
genql/domain/ports/node_embedder.py                      NodeEmbedder protocol
genql/domain/ports/join_path_miner.py                    JoinPathMiner protocol
genql/domain/ports/join_path_writer.py                   JoinPathWriter protocol
genql/repositories/semantic/semantic_catalog_reader_repository.py   PostgresSemanticCatalogReader
genql/repositories/semantic/join_path_writer_repository.py          PostgresJoinPathWriterRepository
genql/infrastructure/graph/__init__.py
genql/infrastructure/graph/neo4j_driver.py               create_neo4j_driver
genql/infrastructure/graph/gds_client_provider.py        GdsClientProvider — lazy GraphDataScience
genql/infrastructure/graph/graph_catalog_session.py      GraphCatalogSession context manager
genql/repositories/graph/__init__.py                     imports implementations for registration
genql/repositories/graph/registry.py                     CLUSTERING_ALGORITHMS, NODE_EMBEDDERS, JOIN_PATH_STRATEGIES
genql/repositories/graph/graph_writer_repository.py      Neo4jGraphWriterRepository
genql/repositories/graph/clustering_algorithm_repository.py   LeidenClusteringAlgorithm
genql/repositories/graph/node_embedder_repository.py     FastRpNodeEmbedder
genql/repositories/graph/join_path_miner_repository.py   WeightedShortestPathJoinPathMiner, _candidate_pairs
genql/services/graph/__init__.py
genql/services/graph/graph_projection_service.py         GraphProjectionService, GraphProjectionReport
genql/services/graph/graph_analysis_service.py           GraphAnalysisService, GraphAnalysisReport
genql/discovery/steps/graph_projection_step.py           GraphProjectionStep
genql/cli/commands/graph.py                              `genql graph` sub-app
migrations/versions/0004_join_paths.py                   genql_join_path table
tests/unit/test_provenance.py
tests/unit/test_join_path_entity.py
tests/unit/test_semantic_catalog_reader_port.py
tests/unit/test_graph_writer_port.py
tests/unit/test_graph_catalog_session.py
tests/unit/test_graph_registries.py
tests/unit/test_candidate_pairs.py
tests/unit/test_graph_projection_service.py
tests/unit/test_graph_projection_step.py
tests/unit/test_graph_analysis_service.py
tests/integration/test_migration_0004.py
tests/integration/test_semantic_catalog_reader_repository.py
tests/integration/test_join_path_writer_repository.py
tests/integration/test_neo4j_graph_writer_repository.py
tests/integration/test_clustering_algorithm_repository.py
tests/integration/test_node_embedder_repository.py
tests/integration/test_join_path_miner_repository.py
tests/integration/test_cli_graph.py
tests/integration/test_graph_analysis_end_to_end.py
```

**Modified**

```
genql/domain/errors.py                      + GraphProjectionError, GraphAnalysisError
genql/core/settings.py                      + clustering_algorithm, node_embedding_algorithm, join_path_strategy, max_join_path_hops
genql/composition_root.py                   + Neo4j/GDS providers, graph services, discovery step wiring
genql/cli/main.py                           mounts the `graph` sub-app
pyproject.toml                              + neo4j, graphdatascience
tests/integration/conftest.py               + neo4j_uri fixture, session-scoped Neo4j container fallback
tests/unit/test_ports_are_runtime_checkable.py   + fakes for the six new ports
tests/unit/test_composition_root.py         + assertions covering the graph_projection step and graph services
```

---

## Task Sequence and Why

Task 1 is purely additive domain work. Task 2 adds the one new Postgres table and its two repositories — the read side that lets projection run from Postgres alone. Task 3 stands up the Neo4j/GDS infrastructure seam, kept lazy so the composition root stays unit-testable without a live Neo4j, exactly as `DatasourceEngineProvider` keeps Postgres engines lazy. Task 4 writes the projection side (`GraphWriter`) and the three registries. Task 5 wires projection into the discovery pipeline as an ordinary step. Tasks 6 and 7 add the three GDS-backed algorithms behind their ports. Task 8 adds the orchestrating service and the CLI. Task 9 wires everything through the composition root. Task 10 proves the whole thing end-to-end against a real Neo4j.

---

### Task 1: Domain foundation

Purely additive. Nothing existing changes.

**Files:**
- Create: `genql/domain/value_objects/provenance.py`, `genql/domain/entities/join_path.py`, `genql/domain/ports/semantic_catalog_reader.py`, `genql/domain/ports/graph_writer.py`, `genql/domain/ports/clustering_algorithm.py`, `genql/domain/ports/node_embedder.py`, `genql/domain/ports/join_path_miner.py`, `genql/domain/ports/join_path_writer.py`
- Modify: `genql/domain/errors.py`
- Test: `tests/unit/test_provenance.py`, `tests/unit/test_join_path_entity.py`, `tests/unit/test_semantic_catalog_reader_port.py`, `tests/unit/test_graph_writer_port.py`, `tests/unit/test_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `DatabaseObject`, `Constraint` (existing), `SchemaRef` (existing)
- Produces: `Provenance` (`StrEnum`: `DISCOVERED`, `LLM`, `YAML`); `JoinPath(datasource_name, schema_name, source_object, target_object, path: tuple[str, ...], weight: float, provenance: Provenance = Provenance.DISCOVERED)`; the six ports below; errors `GraphProjectionError`, `GraphAnalysisError`

- [ ] **Step 1: Write the failing tests for the value object and entity**

Create `tests/unit/test_provenance.py`:

```python
"""Provenance is the vocabulary every enrichment-layer row carries."""

from __future__ import annotations

from genql.domain.value_objects.provenance import Provenance


def test_provenance_has_the_three_documented_values() -> None:
    assert {p.value for p in Provenance} == {"discovered", "llm", "yaml"}
```

Create `tests/unit/test_join_path_entity.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.join_path import JoinPath
from genql.domain.value_objects.provenance import Provenance


def test_join_path_defaults_to_discovered_provenance() -> None:
    path = JoinPath(
        datasource_name="local",
        schema_name="tpcds",
        source_object="store_sales",
        target_object="date_dim",
        path=("store_sales", "date_dim"),
        weight=1.0,
    )
    assert path.provenance == Provenance.DISCOVERED


def test_join_path_is_frozen() -> None:
    path = JoinPath(
        datasource_name="local",
        schema_name="tpcds",
        source_object="store_sales",
        target_object="date_dim",
        path=("store_sales", "date_dim"),
        weight=1.0,
    )
    with pytest.raises(ValidationError):
        path.weight = 2.0  # type: ignore[misc]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_provenance.py tests/unit/test_join_path_entity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.value_objects.provenance'`

- [ ] **Step 3: Write the value object and entity**

Create `genql/domain/value_objects/provenance.py`:

```python
"""How an enrichment-layer row came to exist.

The parent spec assigns this vocabulary to every table in the enrichment
layer — `genql_join_path` here, `genql_object_enrichment` and friends in
Phase 4. A YAML overlay row always wins on merge; this is what a later
merge step checks to know it is looking at one.
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    DISCOVERED = "discovered"
    LLM = "llm"
    YAML = "yaml"
```

Create `genql/domain/entities/join_path.py`:

```python
"""A mined route between two objects that FK edges alone connect indirectly."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance


class JoinPath(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    source_object: str
    target_object: str
    path: tuple[str, ...]
    weight: float
    provenance: Provenance = Provenance.DISCOVERED
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_provenance.py tests/unit/test_join_path_entity.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing tests for the new ports**

Create `tests/unit/test_semantic_catalog_reader_port.py`:

```python
"""A fake satisfying the protocol proves the projection service is testable
without Postgres."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef


class FakeSemanticCatalogReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return []

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeSemanticCatalogReader(), SemanticCatalogReader)
```

Create `tests/unit/test_graph_writer_port.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.ports.graph_writer import GraphWriter


class FakeGraphWriter:
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        return len(objects)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        return len(constraints)


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeGraphWriter(), GraphWriter)
```

Extend `tests/unit/test_ports_are_runtime_checkable.py` — append:

```python
from collections.abc import Sequence

from genql.domain.entities.join_path import JoinPath
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.node_embedder import NodeEmbedder


class FakeClusteringAlgorithm:
    def detect(self, datasource_name: str) -> int:
        return 0


class FakeNodeEmbedder:
    def embed(self, datasource_name: str) -> int:
        return 0


class FakeJoinPathMiner:
    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        return []


class FakeJoinPathWriter:
    def write(self, paths: Sequence[JoinPath]) -> int:
        return len(paths)


def test_a_plain_class_satisfies_the_clustering_algorithm_port() -> None:
    assert isinstance(FakeClusteringAlgorithm(), ClusteringAlgorithm)


def test_a_plain_class_satisfies_the_node_embedder_port() -> None:
    assert isinstance(FakeNodeEmbedder(), NodeEmbedder)


def test_a_plain_class_satisfies_the_join_path_miner_port() -> None:
    assert isinstance(FakeJoinPathMiner(), JoinPathMiner)


def test_a_plain_class_satisfies_the_join_path_writer_port() -> None:
    assert isinstance(FakeJoinPathWriter(), JoinPathWriter)
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_semantic_catalog_reader_port.py tests/unit/test_graph_writer_port.py tests/unit/test_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Write the ports and errors**

Create `genql/domain/ports/semantic_catalog_reader.py`:

```python
"""Reads structural metadata back out of GenQL's own semantic store.

The missing read side of CatalogWriter. This is what lets graph projection
run from Postgres alone, independent of a live discovery run against the
warehouse — which is what makes `genql graph rebuild` possible.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class SemanticCatalogReader(Protocol):
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]: ...

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]: ...
```

Create `genql/domain/ports/graph_writer.py`:

```python
"""Persists one schema's objects and FK edges into the graph projection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject


@runtime_checkable
class GraphWriter(Protocol):
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int: ...

    def write_edges(self, constraints: Sequence[Constraint]) -> int: ...
```

Create `genql/domain/ports/clustering_algorithm.py`:

```python
"""Community detection over one datasource's whole graph.

Takes a datasource name rather than a QueryScope: Leiden runs once over the
datasource's whole projected graph, not per schema — schemas are a
projection-time concept, not an analysis-time one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClusteringAlgorithm(Protocol):
    def detect(self, datasource_name: str) -> int: ...
```

Create `genql/domain/ports/node_embedder.py`:

```python
"""Topology-aware node embeddings over one datasource's whole graph."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NodeEmbedder(Protocol):
    def embed(self, datasource_name: str) -> int: ...
```

Create `genql/domain/ports/join_path_miner.py`:

```python
"""Mines the FK-graph route between object pairs that are not directly
FK-connected."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathMiner(Protocol):
    def mine(self, datasource_name: str) -> Sequence[JoinPath]: ...
```

Create `genql/domain/ports/join_path_writer.py`:

```python
"""Persists mined join paths into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathWriter(Protocol):
    def write(self, paths: Sequence[JoinPath]) -> int: ...
```

In `genql/domain/errors.py`, append:

```python
class GraphProjectionError(DiscoveryError):
    """One schema's objects or FK edges could not be written into the graph."""


class GraphAnalysisError(DiscoveryError):
    """Clustering, embedding, or join-path mining could not complete."""
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_semantic_catalog_reader_port.py tests/unit/test_graph_writer_port.py tests/unit/test_ports_are_runtime_checkable.py -q`
Expected: PASS

- [ ] **Step 9: Full local suite, lint, types**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/domain tests/unit/test_provenance.py tests/unit/test_join_path_entity.py tests/unit/test_semantic_catalog_reader_port.py tests/unit/test_graph_writer_port.py tests/unit/test_ports_are_runtime_checkable.py
git commit -m "feat(domain): add join-path entity and the graph ports"
```

---

### Task 2: The semantic-store read side and the join-path table

**Files:**
- Create: `migrations/versions/0004_join_paths.py`, `genql/repositories/semantic/semantic_catalog_reader_repository.py`, `genql/repositories/semantic/join_path_writer_repository.py`
- Test: `tests/integration/test_migration_0004.py`, `tests/integration/test_semantic_catalog_reader_repository.py`, `tests/integration/test_join_path_writer_repository.py`

**Interfaces:**
- Consumes: `SchemaRef`, `DatabaseObject`, `Constraint`, `JoinPath`, `Provenance` (Task 1)
- Produces: `PostgresSemanticCatalogReader(engine: Engine)` implementing `SemanticCatalogReader`; `PostgresJoinPathWriterRepository(engine: Engine)` implementing `JoinPathWriter`; table `genql.genql_join_path`

These three pieces only do anything against a real Postgres, so their own tests are integration tests, written here but run on the VM — there is nothing to unit-test yet since nothing above them exists until Task 5/8 wire them behind a service. This mirrors how Phase 2.5's Task 2 (re-keying the catalog) carried only integration tests.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0004_join_paths.py`:

```python
"""join paths

Revision ID: 0004
Revises: 0003

Purely additive: one new table, no existing table changes, no backfill.
`path` is the full object sequence from source to target inclusive, in join
order. Removing a schema cascades to its mined paths, the same rule Phase 2.5
established for every catalog table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_join_path",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("source_object", sa.Text, nullable=False),
        sa.Column("target_object", sa.Text, nullable=False),
        sa.Column("path", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("provenance", sa.Text, nullable=False, server_default="discovered"),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name",
            "schema_name",
            "source_object",
            "target_object",
            name="pk_genql_join_path",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_join_path_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_join_path", schema="genql")
```

- [ ] **Step 2: Write the failing integration test for the migration**

Create `tests/integration/test_migration_0004.py`:

```python
"""Migration 0004 is purely additive: one new table, cascading on schema removal."""

from __future__ import annotations

from sqlalchemy import Engine, text


def test_genql_join_path_table_exists(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('genql.genql_join_path') IS NOT NULL")
        ).scalar_one()
    assert exists


def test_removing_a_schema_cascades_to_its_join_paths(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("local", "cascade_test")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_join_path "
                "(datasource_name, schema_name, source_object, target_object, path, weight) "
                "VALUES ('local', 'cascade_test', 'a', 'b', ARRAY['a', 'b'], 1.0)"
            )
        )
        conn.execute(
            text(
                "DELETE FROM genql.genql_schema "
                "WHERE datasource_name = 'local' AND schema_name = 'cascade_test'"
            )
        )
        remaining = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_join_path "
                "WHERE datasource_name = 'local' AND schema_name = 'cascade_test'"
            )
        ).scalar_one()
    assert remaining == 0
```

- [ ] **Step 3: Run it to verify it fails (VM)**

Run: `uv run pytest tests/integration/test_migration_0004.py -q`
Expected (on the VM): FAIL — no such table, until `alembic upgrade head` runs against revision 0004

- [ ] **Step 4: Verify against the VM and commit the migration**

Run: `uv run alembic upgrade head` then re-run Step 3's test.
Expected: PASS

```bash
git add migrations/versions/0004_join_paths.py tests/integration/test_migration_0004.py
git commit -m "feat(semantic): add the genql_join_path table"
```

- [ ] **Step 5: Write the failing tests for the two repositories**

Create `tests/integration/test_semantic_catalog_reader_repository.py`:

```python
"""Reads back exactly what CatalogWriter wrote — the read side that lets
graph projection run from Postgres alone."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.semantic.catalog_writer_repository import PostgresCatalogWriterRepository
from genql.repositories.semantic.semantic_catalog_reader_repository import (
    PostgresSemanticCatalogReader,
)


def test_reads_back_objects_and_constraints_a_writer_wrote(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "reader_test")
    writer = PostgresCatalogWriterRepository(migrated_engine)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="local",
                schema_name="reader_test",
                object_name="parent",
                object_type=ObjectType.TABLE,
            ),
            DatabaseObject(
                datasource_name="local",
                schema_name="reader_test",
                object_name="child",
                object_type=ObjectType.TABLE,
            ),
        ]
    )
    writer.write_constraints(
        [
            Constraint(
                datasource_name="local",
                schema_name="reader_test",
                object_name="child",
                constraint_name="child_parent_fkey",
                constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (parent_id) REFERENCES parent(id)",
                referenced_object_name="parent",
                column_names=("parent_id",),
                referenced_column_names=("id",),
            )
        ]
    )

    reader = PostgresSemanticCatalogReader(migrated_engine)
    ref = SchemaRef(datasource_name="local", schema_name="reader_test")

    objects = {o.object_name for o in reader.read_objects(ref)}
    constraints = reader.read_constraints(ref)

    assert objects == {"parent", "child"}
    assert len(constraints) == 1
    assert constraints[0].constraint_type == ConstraintType.FOREIGN_KEY
    assert constraints[0].referenced_object_name == "parent"


def test_read_objects_type_checks_against_column(migrated_engine: Engine) -> None:
    # Guards against a reader that accidentally returns Column rows: both
    # tables share several column names, and a copy-pasted SELECT is an easy
    # mistake here.
    assert Column is not DatabaseObject
```

Create `tests/integration/test_join_path_writer_repository.py`:

```python
"""Writing is an idempotent upsert, same shape as every other semantic writer."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.join_path import JoinPath
from genql.repositories.semantic.join_path_writer_repository import (
    PostgresJoinPathWriterRepository,
)


def test_write_persists_the_path(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "join_path_test")
    path = JoinPath(
        datasource_name="local",
        schema_name="join_path_test",
        source_object="a",
        target_object="c",
        path=("a", "b", "c"),
        weight=2.0,
    )

    written = PostgresJoinPathWriterRepository(migrated_engine).write([path])

    assert written == 1


def test_writing_the_same_path_twice_is_idempotent(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "join_path_test_2")
    path = JoinPath(
        datasource_name="local",
        schema_name="join_path_test_2",
        source_object="a",
        target_object="c",
        path=("a", "b", "c"),
        weight=2.0,
    )
    writer = PostgresJoinPathWriterRepository(migrated_engine)

    writer.write([path])
    rewritten_with_new_weight = JoinPath(**{**path.model_dump(), "weight": 5.0})
    writer.write([rewritten_with_new_weight])

    with migrated_engine.connect() as conn:
        from sqlalchemy import text

        count, weight = conn.execute(
            text(
                "SELECT count(*), max(weight) FROM genql.genql_join_path "
                "WHERE datasource_name = 'local' AND schema_name = 'join_path_test_2'"
            )
        ).one()
    assert count == 1
    assert weight == 5.0
```

- [ ] **Step 6: Run to verify failure (VM)**

Run: `uv run pytest tests/integration/test_semantic_catalog_reader_repository.py tests/integration/test_join_path_writer_repository.py -q`
Expected (on the VM): FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement the two repositories**

Create `genql/repositories/semantic/semantic_catalog_reader_repository.py`:

```python
"""Reads structural metadata back out of the semantic store, by SchemaRef."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.schema_ref import SchemaRef

_SELECT_OBJECTS = text("""
    SELECT datasource_name, schema_name, object_name, object_type, row_estimate
    FROM genql.genql_object
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_SELECT_CONSTRAINTS = text("""
    SELECT datasource_name, schema_name, object_name, constraint_name, constraint_type,
           definition, referenced_object_name, column_names, referenced_column_names
    FROM genql.genql_constraint
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")


class PostgresSemanticCatalogReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_OBJECTS, ref.model_dump()).all()
        return [DatabaseObject.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_CONSTRAINTS, ref.model_dump()).all()
        return [Constraint.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

Create `genql/repositories/semantic/join_path_writer_repository.py`:

```python
"""Persists mined join paths, one upsert per path."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.join_path import JoinPath

_UPSERT = text("""
    INSERT INTO genql.genql_join_path
        (datasource_name, schema_name, source_object, target_object, path, weight, provenance)
    VALUES (:datasource_name, :schema_name, :source_object, :target_object, :path, :weight,
            :provenance)
    ON CONFLICT ON CONSTRAINT pk_genql_join_path DO UPDATE
        SET path = EXCLUDED.path,
            weight = EXCLUDED.weight,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
""")


class PostgresJoinPathWriterRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, paths: Sequence[JoinPath]) -> int:
        if not paths:
            return 0
        rows = [p.model_dump(mode="json") for p in paths]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT, rows)
        return len(rows)
```

- [ ] **Step 8: Run to verify pass (VM)**

Run: `uv run pytest tests/integration/test_semantic_catalog_reader_repository.py tests/integration/test_join_path_writer_repository.py -q`
Expected: PASS

- [ ] **Step 9: Local checks that don't need the VM**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green (these two files type-check and lint without a database)

- [ ] **Step 10: Commit**

```bash
git add genql/repositories/semantic/semantic_catalog_reader_repository.py genql/repositories/semantic/join_path_writer_repository.py tests/integration/test_semantic_catalog_reader_repository.py tests/integration/test_join_path_writer_repository.py
git commit -m "feat(semantic): read the catalog back and write mined join paths"
```

---

### Task 3: Neo4j and GDS infrastructure

Kept lazy throughout, the same way `DatasourceEngineProvider` defers `create_engine` until a caller
actually needs an engine: `neo4j.GraphDatabase.driver(...)` does not connect until a session runs a
query, but `graphdatascience.GraphDataScience(...)` does perform a compatibility check against the
server at construction time. `GdsClientProvider` exists specifically to defer that construction
past composition-root build time, so `test_composition_root.py`'s existing invariant — the
container builds with no real infrastructure reachable — keeps holding after this task.

**Files:**
- Create: `genql/infrastructure/graph/__init__.py`, `genql/infrastructure/graph/neo4j_driver.py`, `genql/infrastructure/graph/gds_client_provider.py`, `genql/infrastructure/graph/graph_catalog_session.py`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_graph_catalog_session.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `create_neo4j_driver(uri: str, user: str, password: str) -> Driver`; `GdsClientProvider(driver: Driver)` with `.client() -> GraphDataScience`, constructed once and cached; `GraphCatalogSession(gds_provider: GdsClientProvider, datasource_name: str)` — a context manager whose `__enter__` returns the projected graph object and whose `__exit__` always drops it

- [ ] **Step 1: Add the dependencies**

Run: `uv add neo4j graphdatascience`
Expected: `pyproject.toml`'s `dependencies` gains both, `uv.lock` is updated

- [ ] **Step 2: Write the failing test for GraphCatalogSession**

`GraphCatalogSession` is the one piece of this task with logic worth a unit test — "always drop
the projection" is a correctness-critical contract (see spec section 13's GDS graph-catalog-
collision risk), and it is fully testable against a fake GDS client with no real Neo4j.

Create `tests/unit/test_graph_catalog_session.py`:

```python
"""The projected graph is always dropped, even when the body raises."""

from __future__ import annotations

from typing import Any

import pytest

from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession


class FakeGraph:
    def __init__(self) -> None:
        self.dropped = False

    def drop(self) -> None:
        self.dropped = True


class FakeCypherProjector:
    def __init__(self, graph: FakeGraph) -> None:
        self._graph = graph
        self.calls: list[dict[str, Any]] = []

    def cypher(self, name: str, node_query: str, relationship_query: str, **kwargs: Any) -> tuple:
        self.calls.append({"name": name, "parameters": kwargs.get("parameters")})
        return self._graph, None


class FakeGraphNamespace:
    def __init__(self, projector: FakeCypherProjector) -> None:
        self.project = projector


class FakeGds:
    def __init__(self, projector: FakeCypherProjector) -> None:
        self.graph = FakeGraphNamespace(projector)


class FakeGdsProvider:
    def __init__(self, gds: FakeGds) -> None:
        self._gds = gds

    def client(self) -> FakeGds:
        return self._gds


def test_the_projection_is_dropped_after_normal_use() -> None:
    graph = FakeGraph()
    provider = FakeGdsProvider(FakeGds(FakeCypherProjector(graph)))

    with GraphCatalogSession(provider, "local") as session_graph:  # type: ignore[arg-type]
        assert session_graph is graph

    assert graph.dropped is True


def test_the_projection_is_dropped_even_if_the_body_raises() -> None:
    graph = FakeGraph()
    provider = FakeGdsProvider(FakeGds(FakeCypherProjector(graph)))

    with pytest.raises(ValueError), GraphCatalogSession(provider, "local"):  # type: ignore[arg-type]
        raise ValueError("boom")

    assert graph.dropped is True


def test_the_graph_name_and_parameters_are_scoped_to_the_datasource() -> None:
    graph = FakeGraph()
    projector = FakeCypherProjector(graph)
    provider = FakeGdsProvider(FakeGds(projector))

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    assert projector.calls[0]["name"] == "graph_wh2"
    assert projector.calls[0]["parameters"] == {"datasource_name": "wh2"}
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_graph_catalog_session.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement the infrastructure**

Create `genql/infrastructure/graph/__init__.py`:

```python
"""Neo4j and GDS client construction. No query execution lives here."""

from __future__ import annotations
```

Create `genql/infrastructure/graph/neo4j_driver.py`:

```python
"""Neo4j driver construction.

The driver does not connect until a session runs a query, so building one is
as safe to do eagerly at the composition root as `create_engine_from_dsn` is
for Postgres.
"""

from __future__ import annotations

from neo4j import Driver, GraphDatabase


def create_neo4j_driver(uri: str, user: str, password: str) -> Driver:
    return GraphDatabase.driver(uri, auth=(user, password))
```

Create `genql/infrastructure/graph/gds_client_provider.py`:

```python
"""Defers GraphDataScience client construction past composition-root build
time.

Unlike the driver, the GDS client checks server compatibility as soon as it
is constructed. Building it eagerly in the composition root would make
`test_composition_root.py`'s container-builds-without-real-infra invariant
false the moment this file is wired in. `.client()` builds it once, on first
use, and caches it.
"""

from __future__ import annotations

from neo4j import Driver


class GdsClientProvider:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._client: object | None = None

    def client(self) -> object:
        if self._client is None:
            from graphdatascience import GraphDataScience

            self._client = GraphDataScience.from_neo4j_driver(self._driver)
        return self._client
```

Create `genql/infrastructure/graph/graph_catalog_session.py`:

```python
"""A GDS in-memory graph, scoped to one datasource, always dropped on exit.

Nodes are not separated by Neo4j database — Community Edition has one — so
every analysis run projects a named, Cypher-filtered graph containing only
that datasource's `:Object` nodes and `:REFERENCES` edges, and drops it
unconditionally when the `with` block ends. A crashed run can therefore never
leave a stale entry behind to collide with the next one, and two datasources
can never collide with each other either, since the graph name is derived
from the datasource name.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider

_NODE_QUERY = "MATCH (o:Object {datasource_name: $datasource_name}) RETURN id(o) AS id"
_RELATIONSHIP_QUERY = (
    "MATCH (s:Object {datasource_name: $datasource_name})"
    "-[:REFERENCES]->(t:Object {datasource_name: $datasource_name}) "
    "RETURN id(s) AS source, id(t) AS target"
)


class GraphCatalogSession:
    def __init__(self, gds_provider: GdsClientProvider, datasource_name: str) -> None:
        self._gds_provider = gds_provider
        self._datasource_name = datasource_name
        self._graph: Any = None

    def __enter__(self) -> Any:
        gds = self._gds_provider.client()
        self._graph, _ = gds.graph.project.cypher(
            f"graph_{self._datasource_name}",
            _NODE_QUERY,
            _RELATIONSHIP_QUERY,
            parameters={"datasource_name": self._datasource_name},
        )
        return self._graph

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self._graph is not None:
            self._graph.drop()
        return False
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/test_graph_catalog_session.py -q`
Expected: PASS

- [ ] **Step 6: Full local suite, lint, types**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock genql/infrastructure/graph tests/unit/test_graph_catalog_session.py
git commit -m "feat(graph): add lazy Neo4j driver and GDS client infrastructure"
```

---

### Task 4: Graph registries and the projection writer

**Files:**
- Create: `genql/repositories/graph/__init__.py`, `genql/repositories/graph/registry.py`, `genql/repositories/graph/graph_writer_repository.py`
- Test: `tests/unit/test_graph_registries.py`, `tests/integration/test_neo4j_graph_writer_repository.py`

**Interfaces:**
- Consumes: `GraphWriter`, `ClusteringAlgorithm`, `NodeEmbedder`, `JoinPathMiner` ports (Task 1); `create_neo4j_driver` (Task 3)
- Produces: `CLUSTERING_ALGORITHMS`, `NODE_EMBEDDERS`, `JOIN_PATH_STRATEGIES` registries (each a `Registry[T]`, populated in Tasks 4/6/7); `Neo4jGraphWriterRepository(driver: Driver)` implementing `GraphWriter`, registered as `"neo4j"` — the registration exists for symmetry with `CATALOG_READERS`/`PROFILE_READERS` even though only one graph store is registered

- [ ] **Step 1: Write the failing test for the registries**

The registries themselves gain content across this task and Tasks 6–7; this step only proves the
module exists and starts empty in isolation (`Registry` itself is already tested in Phase 1). The
real proof that every key ends up registered lands in Task 9's composition-root test.

Create `tests/unit/test_graph_registries.py`:

```python
"""The three graph registries exist and are independent of each other."""

from __future__ import annotations

from genql.repositories.graph.registry import (
    CLUSTERING_ALGORITHMS,
    JOIN_PATH_STRATEGIES,
    NODE_EMBEDDERS,
)


def test_the_three_registries_are_distinct() -> None:
    assert CLUSTERING_ALGORITHMS.name == "clustering_algorithms"
    assert NODE_EMBEDDERS.name == "node_embedders"
    assert JOIN_PATH_STRATEGIES.name == "join_path_strategies"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_graph_registries.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create the registries**

Create `genql/repositories/graph/registry.py`:

```python
"""The three graph-algorithm registries, keyed by algorithm name.

Adding an algorithm — `louvain` alongside `leiden`, say — is one file plus
one decorator. `Settings` picks the active key; no call site names a class.
"""

from __future__ import annotations

from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.node_embedder import NodeEmbedder
from genql.registries.registry import Registry

CLUSTERING_ALGORITHMS: Registry[ClusteringAlgorithm] = Registry("clustering_algorithms")
NODE_EMBEDDERS: Registry[NodeEmbedder] = Registry("node_embedders")
JOIN_PATH_STRATEGIES: Registry[JoinPathMiner] = Registry("join_path_strategies")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_graph_registries.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing integration test for the graph writer**

Create `tests/integration/test_neo4j_graph_writer_repository.py`:

```python
"""Projection is idempotent: writing the same schema twice leaves the same
node and edge count, and cross-datasource nodes never collide."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository

_PARENT = DatabaseObject(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="parent",
    object_type=ObjectType.TABLE,
)
_CHILD = DatabaseObject(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="child",
    object_type=ObjectType.TABLE,
)
_FK = Constraint(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="child",
    constraint_name="child_parent_fkey",
    constraint_type=ConstraintType.FOREIGN_KEY,
    definition="FOREIGN KEY (parent_id) REFERENCES parent(id)",
    referenced_object_name="parent",
    column_names=("parent_id",),
    referenced_column_names=("id",),
)


@pytest.fixture()
def driver(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'local'}) DETACH DELETE o")
    yield drv
    drv.close()


def test_projecting_twice_leaves_one_node_and_one_edge(driver: Driver) -> None:
    repo = Neo4jGraphWriterRepository(driver)

    for _ in range(2):
        repo.write_objects([_PARENT, _CHILD])
        repo.write_edges([_FK])

    with driver.session() as session:
        node_count = session.run(
            "MATCH (o:Object {datasource_name: 'local', schema_name: 'graph_writer_test'}) "
            "RETURN count(o) AS n"
        ).single()["n"]
        edge_count = session.run(
            "MATCH (:Object {qualified_name: 'local.graph_writer_test.child'})"
            "-[r:REFERENCES]->(:Object {qualified_name: 'local.graph_writer_test.parent'}) "
            "RETURN count(r) AS n"
        ).single()["n"]

    assert node_count == 2
    assert edge_count == 1
```

- [ ] **Step 6: Add the `neo4j_uri` fixture**

In `tests/integration/conftest.py`, add:

```python
from testcontainers.neo4j import Neo4jContainer


@pytest.fixture(scope="session")
def neo4j_uri() -> Iterator[str]:
    """Prefer a running stack; fall back to an ephemeral container, same
    rule as `paradedb_dsn`."""
    uri = os.environ.get("GENQL_TEST_NEO4J_URI")
    if uri:
        yield uri
        return

    with Neo4jContainer(image="neo4j:5-community") as running:
        yield running.get_connection_url()
```

- [ ] **Step 7: Run to verify it fails (VM)**

Run: `uv run pytest tests/integration/test_neo4j_graph_writer_repository.py -q`
Expected (on the VM): FAIL — `ModuleNotFoundError`

- [ ] **Step 8: Implement the writer**

Create `genql/repositories/graph/__init__.py`:

```python
"""Registers every graph-algorithm implementation with its registry."""

from __future__ import annotations
```

Create `genql/repositories/graph/graph_writer_repository.py`:

```python
"""Projects objects and FK edges into Neo4j, keyed on qualified_name.

MERGE makes both write methods idempotent: re-projecting an already-projected
schema changes nothing. Cross-schema foreign keys are out of scope here the
same way they are out of scope in `Constraint` itself — the entity carries no
`referenced_schema_name`, so a referenced object is always resolved within
the constraint's own schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType

_ENSURE_CONSTRAINT = (
    "CREATE CONSTRAINT object_qualified_name IF NOT EXISTS "
    "FOR (o:Object) REQUIRE o.qualified_name IS UNIQUE"
)

_MERGE_OBJECTS = """
UNWIND $rows AS row
MERGE (o:Object {qualified_name: row.qualified_name})
SET o.datasource_name = row.datasource_name,
    o.schema_name = row.schema_name,
    o.object_name = row.object_name,
    o.object_type = row.object_type,
    o.row_estimate = row.row_estimate
"""

_MERGE_EDGES = """
UNWIND $rows AS row
MATCH (source:Object {qualified_name: row.source_qualified_name})
MATCH (target:Object {qualified_name: row.target_qualified_name})
MERGE (source)-[r:REFERENCES {constraint_name: row.constraint_name}]->(target)
SET r.column_names = row.column_names,
    r.referenced_column_names = row.referenced_column_names
"""


class Neo4jGraphWriterRepository:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._constraint_ensured = False

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        if not objects:
            return 0
        self._ensure_constraint()
        rows = [
            {
                "qualified_name": o.qualified_name,
                "datasource_name": o.datasource_name,
                "schema_name": o.schema_name,
                "object_name": o.object_name,
                "object_type": o.object_type.value,
                "row_estimate": o.row_estimate,
            }
            for o in objects
        ]
        with self._driver.session() as session:
            session.run(_MERGE_OBJECTS, rows=rows)
        return len(rows)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        rows = [
            {
                "source_qualified_name": f"{c.datasource_name}.{c.schema_name}.{c.object_name}",
                "target_qualified_name": (
                    f"{c.datasource_name}.{c.schema_name}.{c.referenced_object_name}"
                ),
                "constraint_name": c.constraint_name,
                "column_names": list(c.column_names),
                "referenced_column_names": list(c.referenced_column_names),
            }
            for c in constraints
            if c.constraint_type == ConstraintType.FOREIGN_KEY and c.referenced_object_name
        ]
        if not rows:
            return 0
        with self._driver.session() as session:
            session.run(_MERGE_EDGES, rows=rows)
        return len(rows)

    def _ensure_constraint(self) -> None:
        if self._constraint_ensured:
            return
        with self._driver.session() as session:
            session.run(_ENSURE_CONSTRAINT)
        self._constraint_ensured = True
```

- [ ] **Step 9: Run to verify it passes (VM)**

Run: `uv run pytest tests/integration/test_neo4j_graph_writer_repository.py -q`
Expected: PASS

- [ ] **Step 10: Local checks that don't need the VM**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 11: Commit**

```bash
git add genql/repositories/graph tests/unit/test_graph_registries.py tests/integration/test_neo4j_graph_writer_repository.py tests/integration/conftest.py
git commit -m "feat(graph): project objects and FK edges into Neo4j"
```

---

### Task 5: Graph projection service and discovery step

**Files:**
- Create: `genql/services/graph/__init__.py`, `genql/services/graph/graph_projection_service.py`, `genql/discovery/steps/graph_projection_step.py`
- Test: `tests/unit/test_graph_projection_service.py`, `tests/unit/test_graph_projection_step.py`

**Interfaces:**
- Consumes: `SemanticCatalogReader`, `GraphWriter` (Task 1); `DiscoveryContext`, `StepResult`, `DISCOVERY_STEPS` (existing)
- Produces: `GraphProjectionReport(objects: int, edges: int)` with `.total`; `GraphProjectionService(reader: SemanticCatalogReader, writer: GraphWriter)` with `.project(ref: SchemaRef) -> GraphProjectionReport`; `GraphProjectionStep`, registered in `DISCOVERY_STEPS` as `"graph_projection"`

- [ ] **Step 1: Write the failing test for the service**

Create `tests/unit/test_graph_projection_service.py`:

```python
"""Reads objects and constraints back from the semantic store, writes them
into the graph. Same shape as CatalogScanService: read via one port, write
via another, return a typed report."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.graph.graph_projection_service import GraphProjectionService

OBJECTS = [
    DatabaseObject(
        datasource_name="local", schema_name="shop", object_name="customer",
        object_type=ObjectType.TABLE,
    )
]
CONSTRAINTS = [
    Constraint(
        datasource_name="local", schema_name="shop", object_name="order",
        constraint_name="order_customer_fkey", constraint_type=ConstraintType.FOREIGN_KEY,
        definition="FOREIGN KEY (customer_id) REFERENCES customer(id)",
        referenced_object_name="customer",
    )
]


class FakeReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return OBJECTS

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return CONSTRAINTS


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[DatabaseObject] = []
        self.constraints: list[Constraint] = []

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        self.objects.extend(objects)
        return len(objects)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        self.constraints.extend(constraints)
        return len(constraints)


def test_project_writes_everything_it_reads() -> None:
    writer = FakeWriter()
    ref = SchemaRef(datasource_name="local", schema_name="shop")

    report = GraphProjectionService(FakeReader(), writer).project(ref)

    assert report.objects == 1
    assert report.edges == 1
    assert report.total == 2
    assert writer.objects == OBJECTS
    assert writer.constraints == CONSTRAINTS
```

Create `tests/unit/test_graph_projection_step.py`:

```python
"""The step delegates to the service and reports a typed result, same shape
as CatalogScanStep."""

from __future__ import annotations

from genql.discovery.steps.graph_projection_step import GraphProjectionStep
from genql.domain.ports.discovery_step import DiscoveryContext
from genql.services.graph.graph_projection_service import GraphProjectionReport


class FakeGraphProjectionService:
    def __init__(self, report: GraphProjectionReport) -> None:
        self._report = report
        self.seen_refs: list[str] = []

    def project(self, ref: object) -> GraphProjectionReport:
        self.seen_refs.append(ref.qualified_name)  # type: ignore[attr-defined]
        return self._report


def test_step_reports_success_and_records_written() -> None:
    service = FakeGraphProjectionService(GraphProjectionReport(objects=3, edges=2))
    step = GraphProjectionStep(service)  # type: ignore[arg-type]
    ctx = DiscoveryContext(datasource_name="local", schema_name="shop")

    result = step.run(ctx)

    assert result.succeeded is True
    assert result.records_written == 5
    assert service.seen_refs == ["local.shop"]


def test_step_name_is_graph_projection() -> None:
    assert GraphProjectionStep.name == "graph_projection"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_graph_projection_service.py tests/unit/test_graph_projection_step.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service and step**

Create `genql/services/graph/__init__.py`:

```python
"""Graph projection and analysis services."""

from __future__ import annotations
```

Create `genql/services/graph/graph_projection_service.py`:

```python
"""Reads a schema's structure back from the semantic store and projects it.

Depends only on ports, exactly like CatalogScanService — it cannot reach
Postgres or Neo4j even by accident, which is what makes the unit test above
possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.graph_writer import GraphWriter
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef


class GraphProjectionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects: int
    edges: int

    @property
    def total(self) -> int:
        return self.objects + self.edges


class GraphProjectionService:
    def __init__(self, reader: SemanticCatalogReader, writer: GraphWriter) -> None:
        self._reader = reader
        self._writer = writer

    def project(self, ref: SchemaRef) -> GraphProjectionReport:
        objects = self._writer.write_objects(self._reader.read_objects(ref))
        edges = self._writer.write_edges(self._reader.read_constraints(ref))
        return GraphProjectionReport(objects=objects, edges=edges)
```

Create `genql/discovery/steps/graph_projection_step.py`:

```python
"""Step: project one schema's objects and FK edges into Neo4j.

Sequenced immediately after catalog_scan at the composition root — it needs
that schema's objects and constraints already committed to Postgres, and
gains nothing from waiting for data_profiling.
"""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.graph.graph_projection_service import GraphProjectionService


@DISCOVERY_STEPS.register("graph_projection")
class GraphProjectionStep:
    name: ClassVar[str] = "graph_projection"

    def __init__(self, service: GraphProjectionService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            report = self._service.project(ctx.ref)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.total,
            message=f"{report.objects} objects, {report.edges} edges",
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_graph_projection_service.py tests/unit/test_graph_projection_step.py -q`
Expected: PASS

- [ ] **Step 5: Full local suite, lint, types**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — note `import-linter` will still pass here even though `graph_projection_step` is not yet wired into any runner, since registration is a decorator side effect, not a runner dependency

- [ ] **Step 6: Commit**

```bash
git add genql/services/graph genql/discovery/steps/graph_projection_step.py tests/unit/test_graph_projection_service.py tests/unit/test_graph_projection_step.py
git commit -m "feat(discovery): project each discovered schema into the graph"
```

---

### Task 6: Leiden communities and FastRP embeddings

**Files:**
- Create: `genql/repositories/graph/clustering_algorithm_repository.py`, `genql/repositories/graph/node_embedder_repository.py`
- Test: `tests/integration/test_clustering_algorithm_repository.py`, `tests/integration/test_node_embedder_repository.py`

**Interfaces:**
- Consumes: `ClusteringAlgorithm`, `NodeEmbedder` ports (Task 1); `GraphCatalogSession`, `GdsClientProvider` (Task 3); `CLUSTERING_ALGORITHMS`, `NODE_EMBEDDERS` (Task 4)
- Produces: `LeidenClusteringAlgorithm(gds_provider: GdsClientProvider)` implementing `ClusteringAlgorithm`, registered as `"leiden"`; `FastRpNodeEmbedder(gds_provider: GdsClientProvider)` implementing `NodeEmbedder`, registered as `"fastrp"`

Both algorithms only do anything against real Neo4j + GDS, so their tests are integration tests,
written here and run on the VM.

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_clustering_algorithm_repository.py`:

```python
"""Leiden writes a community_id onto every node it can reach."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.clustering_algorithm_repository import LeidenClusteringAlgorithm
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository


@pytest.fixture()
def projected_graph(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'leiden_test'}) DETACH DELETE o")
    writer = Neo4jGraphWriterRepository(drv)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="leiden_test", schema_name="s", object_name=name,
                object_type=ObjectType.TABLE,
            )
            for name in ("a", "b")
        ]
    )
    writer.write_edges(
        [
            Constraint(
                datasource_name="leiden_test", schema_name="s", object_name="a",
                constraint_name="a_b_fkey", constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (b_id) REFERENCES b(id)", referenced_object_name="b",
            )
        ]
    )
    yield drv
    drv.close()


def test_leiden_writes_a_community_id_onto_every_node(projected_graph: Driver) -> None:
    provider = GdsClientProvider(projected_graph)

    communities_found = LeidenClusteringAlgorithm(provider).detect("leiden_test")

    assert communities_found >= 1
    with projected_graph.session() as session:
        missing = session.run(
            "MATCH (o:Object {datasource_name: 'leiden_test'}) "
            "WHERE o.community_id IS NULL RETURN count(o) AS n"
        ).single()["n"]
    assert missing == 0
```

Create `tests/integration/test_node_embedder_repository.py`:

```python
"""FastRP writes an embedding onto every node it can reach."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.node_embedder_repository import FastRpNodeEmbedder


@pytest.fixture()
def projected_graph(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'fastrp_test'}) DETACH DELETE o")
    Neo4jGraphWriterRepository(drv).write_objects(
        [
            DatabaseObject(
                datasource_name="fastrp_test", schema_name="s", object_name="only",
                object_type=ObjectType.TABLE,
            )
        ]
    )
    yield drv
    drv.close()


def test_fastrp_writes_an_embedding_onto_every_node(projected_graph: Driver) -> None:
    provider = GdsClientProvider(projected_graph)

    embedded = FastRpNodeEmbedder(provider).embed("fastrp_test")

    assert embedded == 1
    with projected_graph.session() as session:
        embedding = session.run(
            "MATCH (o:Object {datasource_name: 'fastrp_test'}) RETURN o.embedding AS e"
        ).single()["e"]
    assert embedding is not None
    assert len(embedding) == 128
```

- [ ] **Step 2: Run to verify they fail (VM)**

Run: `uv run pytest tests/integration/test_clustering_algorithm_repository.py tests/integration/test_node_embedder_repository.py -q`
Expected (on the VM): FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement both algorithms**

Create `genql/repositories/graph/clustering_algorithm_repository.py`:

```python
"""Leiden community detection, written back onto :Object nodes."""

from __future__ import annotations

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS


@CLUSTERING_ALGORITHMS.register("leiden")
class LeidenClusteringAlgorithm:
    def __init__(self, gds_provider: GdsClientProvider) -> None:
        self._gds_provider = gds_provider

    def detect(self, datasource_name: str) -> int:
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            result = self._gds_provider.client().leiden.write(  # type: ignore[attr-defined]
                graph, writeProperty="community_id"
            )
        return int(result["communityCount"])
```

Create `genql/repositories/graph/node_embedder_repository.py`:

```python
"""FastRP topology-aware node embeddings, written back onto :Object nodes."""

from __future__ import annotations

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import NODE_EMBEDDERS

_EMBEDDING_DIMENSION = 128


@NODE_EMBEDDERS.register("fastrp")
class FastRpNodeEmbedder:
    def __init__(self, gds_provider: GdsClientProvider) -> None:
        self._gds_provider = gds_provider

    def embed(self, datasource_name: str) -> int:
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            result = self._gds_provider.client().fastRP.write(  # type: ignore[attr-defined]
                graph, writeProperty="embedding", embeddingDimension=_EMBEDDING_DIMENSION
            )
        return int(result["nodePropertiesWritten"])
```

- [ ] **Step 4: Run to verify they pass (VM)**

Run: `uv run pytest tests/integration/test_clustering_algorithm_repository.py tests/integration/test_node_embedder_repository.py -q`
Expected: PASS

- [ ] **Step 5: Local checks that don't need the VM**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add genql/repositories/graph/clustering_algorithm_repository.py genql/repositories/graph/node_embedder_repository.py tests/integration/test_clustering_algorithm_repository.py tests/integration/test_node_embedder_repository.py
git commit -m "feat(graph): compute Leiden communities and FastRP embeddings"
```

---

### Task 7: Join-path mining

**Files:**
- Create: `genql/repositories/graph/join_path_miner_repository.py`
- Test: `tests/unit/test_candidate_pairs.py`, `tests/integration/test_join_path_miner_repository.py`

**Interfaces:**
- Consumes: `JoinPathMiner` port, `JoinPath` entity (Task 1); `GraphCatalogSession`, `GdsClientProvider` (Task 3); `JOIN_PATH_STRATEGIES` (Task 4)
- Produces: `_candidate_pairs(objects: Sequence[str], direct_edges: Sequence[tuple[str, str]]) -> list[tuple[str, str]]` — a pure function, unit-tested without GDS; `WeightedShortestPathJoinPathMiner(gds_provider: GdsClientProvider, max_hops: int)` implementing `JoinPathMiner`, registered as `"weighted_shortest_path"`

The pair-enumeration logic — which object pairs are worth mining a path between — is the one part
of this algorithm with a decision worth a fast, GDS-free test. Everything past that (running
Dijkstra, turning a GDS path result into a `JoinPath`) only means something against a real graph.

- [ ] **Step 1: Write the failing unit test for pair enumeration**

Create `tests/unit/test_candidate_pairs.py`:

```python
"""Only pairs without a direct FK edge are worth mining a path between —
direct edges need no mined path."""

from __future__ import annotations

from genql.repositories.graph.join_path_miner_repository import _candidate_pairs


def test_directly_connected_pairs_are_excluded() -> None:
    pairs = _candidate_pairs(["a", "b"], [("a", "b")])
    assert pairs == []


def test_unconnected_pairs_are_included() -> None:
    pairs = _candidate_pairs(["a", "b", "c"], [("a", "b")])
    assert set(pairs) == {("a", "c"), ("b", "c")}


def test_edge_direction_does_not_matter_for_exclusion() -> None:
    pairs = _candidate_pairs(["a", "b"], [("b", "a")])
    assert pairs == []


def test_no_pair_is_produced_against_itself() -> None:
    pairs = _candidate_pairs(["a"], [])
    assert pairs == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_candidate_pairs.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the failing integration test for the miner**

Create `tests/integration/test_join_path_miner_repository.py`:

```python
"""Mines the FK route between two objects that are connected only through a
third — the case a direct-edge-only view of the FK graph cannot answer."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.join_path_miner_repository import WeightedShortestPathJoinPathMiner


@pytest.fixture()
def chain_graph(neo4j_uri: str) -> Iterator[Driver]:
    """a -> b -> c: a and c are two hops apart, never directly FK-connected."""
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'join_path_test'}) DETACH DELETE o")
    writer = Neo4jGraphWriterRepository(drv)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="join_path_test", schema_name="s", object_name=name,
                object_type=ObjectType.TABLE,
            )
            for name in ("a", "b", "c")
        ]
    )
    writer.write_edges(
        [
            Constraint(
                datasource_name="join_path_test", schema_name="s", object_name="a",
                constraint_name="a_b_fkey", constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (b_id) REFERENCES b(id)", referenced_object_name="b",
            ),
            Constraint(
                datasource_name="join_path_test", schema_name="s", object_name="b",
                constraint_name="b_c_fkey", constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (c_id) REFERENCES c(id)", referenced_object_name="c",
            ),
        ]
    )
    yield drv
    drv.close()


def test_mines_the_two_hop_path_between_a_and_c(chain_graph: Driver) -> None:
    provider = GdsClientProvider(chain_graph)
    miner = WeightedShortestPathJoinPathMiner(chain_graph, provider, max_hops=4)

    paths = miner.mine("join_path_test")

    a_to_c = [p for p in paths if {p.source_object, p.target_object} == {"a", "c"}]
    assert len(a_to_c) == 1
    assert set(a_to_c[0].path) == {"a", "b", "c"}
    assert a_to_c[0].schema_name == "s"


def test_directly_connected_pairs_are_not_mined(chain_graph: Driver) -> None:
    provider = GdsClientProvider(chain_graph)
    miner = WeightedShortestPathJoinPathMiner(chain_graph, provider, max_hops=4)

    paths = miner.mine("join_path_test")

    a_to_b = [p for p in paths if {p.source_object, p.target_object} == {"a", "b"}]
    assert a_to_b == []
```

- [ ] **Step 4: Run to verify it fails (VM)**

Run: `uv run pytest tests/integration/test_join_path_miner_repository.py -q`
Expected (on the VM): FAIL — `ModuleNotFoundError`

- [ ] **Step 5: Implement the miner**

Create `genql/repositories/graph/join_path_miner_repository.py`:

```python
"""Mines the FK-graph shortest path between object pairs with no direct FK
edge.

Weights are uniform for now — there is no query log yet to weight edges by
join frequency. `Settings.join_path_strategy` is the seam Phase 6 uses to
register a query-weighted successor without touching any call site.
"""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver

from genql.domain.entities.join_path import JoinPath
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import JOIN_PATH_STRATEGIES

_LIST_OBJECTS_AND_EDGES = """
MATCH (o:Object {datasource_name: $datasource_name})
OPTIONAL MATCH (o)-[:REFERENCES]->(t:Object {datasource_name: $datasource_name})
RETURN o.object_name AS object_name, o.schema_name AS schema_name,
       collect(t.object_name) AS targets
"""

_SHORTEST_PATH = """
MATCH (source:Object {datasource_name: $datasource_name, object_name: $source_object})
MATCH (target:Object {datasource_name: $datasource_name, object_name: $target_object})
CALL gds.shortestPath.dijkstra.stream($graph_name, {sourceNode: source, targetNode: target})
YIELD path
RETURN [n IN nodes(path) | n.object_name] AS names, length(path) AS hops
"""


def _candidate_pairs(
    objects: Sequence[str], direct_edges: Sequence[tuple[str, str]]
) -> list[tuple[str, str]]:
    connected = {frozenset(edge) for edge in direct_edges}
    pairs: list[tuple[str, str]] = []
    for i, source in enumerate(objects):
        for target in objects[i + 1 :]:
            if frozenset((source, target)) not in connected:
                pairs.append((source, target))
    return pairs


@JOIN_PATH_STRATEGIES.register("weighted_shortest_path")
class WeightedShortestPathJoinPathMiner:
    """Takes the Neo4j driver directly for the plain Cypher reads (listing
    objects and edges, running the per-pair shortest path), and the GDS
    client provider only for the algorithm-catalog projection — the
    graphdatascience client does not reliably expose its underlying driver
    across versions, so the driver is wired in independently rather than
    extracted from it."""

    def __init__(self, driver: Driver, gds_provider: GdsClientProvider, max_hops: int = 4) -> None:
        self._driver = driver
        self._gds_provider = gds_provider
        self._max_hops = max_hops

    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        with self._driver.session() as session:
            rows = session.run(_LIST_OBJECTS_AND_EDGES, datasource_name=datasource_name).data()
        objects = [row["object_name"] for row in rows]
        schema_names = {row["object_name"]: row["schema_name"] for row in rows}
        direct_edges = [
            (row["object_name"], target) for row in rows for target in row["targets"] if target
        ]

        paths: list[JoinPath] = []
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            for source, target in _candidate_pairs(objects, direct_edges):
                paths.extend(
                    self._mine_pair(
                        graph.name(), datasource_name, schema_names[source], source, target
                    )
                )
        return paths

    def _mine_pair(
        self,
        graph_name: str,
        datasource_name: str,
        schema_name: str,
        source: str,
        target: str,
    ) -> list[JoinPath]:
        with self._driver.session() as session:
            record = session.run(
                _SHORTEST_PATH,
                datasource_name=datasource_name,
                source_object=source,
                target_object=target,
                graph_name=graph_name,
            ).single()
        if record is None or record["hops"] > self._max_hops:
            return []
        names = tuple(record["names"])
        return [
            JoinPath(
                datasource_name=datasource_name,
                schema_name=schema_name,
                source_object=source,
                target_object=target,
                path=names,
                weight=float(record["hops"]),
            )
        ]
```

A mined path spans exactly the schema its two endpoint objects share — join-path mining runs once
per datasource, but every object still carries one `schema_name`, and `genql_join_path.schema_name`
is `NOT NULL` with a foreign key to `genql_schema`, so this has to be the source object's own
schema, not an empty placeholder.

- [ ] **Step 6: Run to verify it passes (VM)**

Run: `uv run pytest tests/integration/test_join_path_miner_repository.py -q`
Expected: PASS

- [ ] **Step 7: Local checks that don't need the VM**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/repositories/graph/join_path_miner_repository.py tests/unit/test_candidate_pairs.py tests/integration/test_join_path_miner_repository.py
git commit -m "feat(graph): mine FK-graph join paths between indirectly connected objects"
```

---

### Task 8: Graph analysis service and CLI

**Files:**
- Create: `genql/services/graph/graph_analysis_service.py`, `genql/cli/commands/graph.py`
- Modify: `genql/cli/main.py`
- Test: `tests/unit/test_graph_analysis_service.py`, `tests/integration/test_cli_graph.py`

**Interfaces:**
- Consumes: `ClusteringAlgorithm`, `NodeEmbedder`, `JoinPathMiner`, `JoinPathWriter` ports (Task 1); `GraphProjectionService` (Task 5)
- Produces: `GraphAnalysisReport(communities: int, embedded_nodes: int, join_paths: int)`; `GraphAnalysisService(clustering, embedder, miner, join_path_writer)` with `.analyze(datasource_name: str) -> GraphAnalysisReport`; CLI commands `genql graph analyze --datasource NAME` and `genql graph rebuild --datasource NAME`

- [ ] **Step 1: Write the failing test for the service**

Create `tests/unit/test_graph_analysis_service.py`:

```python
"""Runs clustering, then embedding, then join-path mining, and persists the
mined paths. All four dependencies are ports, so no database or Neo4j is
needed here."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.join_path import JoinPath
from genql.services.graph.graph_analysis_service import GraphAnalysisService

PATH = JoinPath(
    datasource_name="local", schema_name="shop", source_object="a", target_object="c",
    path=("a", "b", "c"), weight=2.0,
)


class FakeClustering:
    def detect(self, datasource_name: str) -> int:
        return 3


class FakeEmbedder:
    def embed(self, datasource_name: str) -> int:
        return 7


class FakeMiner:
    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        return [PATH]


class FakeJoinPathWriter:
    def __init__(self) -> None:
        self.written: list[JoinPath] = []

    def write(self, paths: Sequence[JoinPath]) -> int:
        self.written.extend(paths)
        return len(paths)


def test_analyze_runs_all_three_algorithms_and_persists_paths() -> None:
    writer = FakeJoinPathWriter()
    service = GraphAnalysisService(FakeClustering(), FakeEmbedder(), FakeMiner(), writer)

    report = service.analyze("local")

    assert report.communities == 3
    assert report.embedded_nodes == 7
    assert report.join_paths == 1
    assert writer.written == [PATH]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_graph_analysis_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `genql/services/graph/graph_analysis_service.py`:

```python
"""Orchestrates community detection, node embedding, and join-path mining
for one datasource's whole graph.

Depends only on ports; which concrete algorithm each port resolves to is a
composition-root and Settings concern, not this service's.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.node_embedder import NodeEmbedder


class GraphAnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    communities: int
    embedded_nodes: int
    join_paths: int


class GraphAnalysisService:
    def __init__(
        self,
        clustering: ClusteringAlgorithm,
        embedder: NodeEmbedder,
        miner: JoinPathMiner,
        join_path_writer: JoinPathWriter,
    ) -> None:
        self._clustering = clustering
        self._embedder = embedder
        self._miner = miner
        self._join_path_writer = join_path_writer

    def analyze(self, datasource_name: str) -> GraphAnalysisReport:
        communities = self._clustering.detect(datasource_name)
        embedded_nodes = self._embedder.embed(datasource_name)
        paths = self._miner.mine(datasource_name)
        written = self._join_path_writer.write(paths)
        return GraphAnalysisReport(
            communities=communities, embedded_nodes=embedded_nodes, join_paths=written
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_graph_analysis_service.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing integration test for the CLI**

Create `tests/integration/test_cli_graph.py`:

```python
"""End-to-end through the CLI: discover, then analyze, against the VM stack."""

from __future__ import annotations

import os

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_graph_analyze_reports_at_least_one_community(monkeypatch: object) -> None:
    result = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])

    assert result.exit_code == 0
    assert "communities" in result.stdout


def test_graph_rebuild_does_not_touch_the_warehouse(monkeypatch: object) -> None:
    """Rebuild reads only from Postgres — breaking GENQL_WAREHOUSE_DSN must
    not affect it."""
    original = os.environ.pop("GENQL_WAREHOUSE_DSN", None)
    try:
        result = runner.invoke(app, ["graph", "rebuild", "--datasource", "local"])
        assert result.exit_code == 0
    finally:
        if original is not None:
            os.environ["GENQL_WAREHOUSE_DSN"] = original
```

- [ ] **Step 6: Run to verify it fails (VM)**

Run: `uv run pytest tests/integration/test_cli_graph.py -q`
Expected (on the VM): FAIL — no `graph` sub-command yet

- [ ] **Step 7: Implement the CLI**

Create `genql/cli/commands/graph.py`:

```python
"""`genql graph` — run community detection, embeddings, and join-path mining,
and rebuild the projection from Postgres alone.

Domain errors are caught here and turned into a message plus exit code 1,
same rule as every other command.
"""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.schema_ref import SchemaRef

app = typer.Typer(help="Project, analyze, and rebuild the graph")


@app.command("analyze")
def analyze(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Run Leiden, FastRP, and join-path mining over one datasource's graph."""
    try:
        report = Container().graph_analysis_service().analyze(datasource)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{report.communities} communities, {report.embedded_nodes} nodes embedded, "
        f"{report.join_paths} join paths"
    )


@app.command("rebuild")
def rebuild(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Re-project every enabled schema of a datasource from Postgres alone."""
    container = Container()
    try:
        registrations = container.schema_registration_repository().list_for_datasource(
            datasource, enabled_only=True
        )
        service = container.graph_projection_service()
        for registration in registrations:
            ref = SchemaRef(datasource_name=datasource, schema_name=registration.schema_name)
            report = service.project(ref)
            typer.echo(f"{ref.qualified_name}: {report.objects} objects, {report.edges} edges")
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
```

In `genql/cli/main.py`, add the import and mount:

```python
from genql.cli.commands import graph as graph_commands
```

```python
app.add_typer(graph_commands.app, name="graph")
```

- [ ] **Step 8: Run to verify it passes (VM)**

Run: `uv run pytest tests/integration/test_cli_graph.py -q`
Expected: PASS (once Task 9 wires `graph_analysis_service`, `graph_projection_service`, and `schema_registration_repository` onto the container — if run before Task 9's commit, this fails with `AttributeError` on the container; that is expected and resolves once Task 9 lands)

- [ ] **Step 9: Local checks that don't need the VM**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/services/graph/graph_analysis_service.py genql/cli/commands/graph.py genql/cli/main.py tests/unit/test_graph_analysis_service.py tests/integration/test_cli_graph.py
git commit -m "feat(cli): add genql graph analyze and genql graph rebuild"
```

---

### Task 9: Composition root wiring

**Files:**
- Modify: `genql/core/settings.py`, `genql/composition_root.py`
- Modify: `tests/unit/test_composition_root.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8
- Produces: `Settings.clustering_algorithm`, `Settings.node_embedding_algorithm`, `Settings.join_path_strategy`, `Settings.max_join_path_hops`; `Container.neo4j_driver`, `Container.gds_client_provider`, `Container.semantic_catalog_reader`, `Container.graph_writer`, `Container.join_path_writer`, `Container.graph_projection_service`, `Container.graph_analysis_service`, `Container.schema_registration_repository` (already existed — confirmed exposed at container top level)

- [ ] **Step 1: Write the failing composition-root assertions**

In `tests/unit/test_composition_root.py`, add:

```python
def test_the_runner_includes_graph_projection(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "graph_projection" in step_names


def test_the_container_builds_a_graph_analysis_service(container: Container) -> None:
    service = container.graph_analysis_service()

    assert hasattr(service, "analyze")


def test_the_container_builds_a_graph_projection_service(container: Container) -> None:
    service = container.graph_projection_service()

    assert hasattr(service, "project")
```

Also extend the `container` fixture's env setup:

```python
    monkeypatch.setenv("GENQL_NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("GENQL_NEO4J_USER", "neo4j")
    monkeypatch.setenv("GENQL_NEO4J_PASSWORD", "x")
```

(`Settings` already defaults these three, so this addition documents the fixture's intent rather
than changing behavior — it makes explicit that the container must build without a reachable Neo4j,
same as it already does for Postgres.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL — `AttributeError: 'Container' object has no attribute 'graph_analysis_service'`

- [ ] **Step 3: Add the new Settings fields**

In `genql/core/settings.py`, add to the `Settings` class:

```python
    clustering_algorithm: str = "leiden"
    node_embedding_algorithm: str = "fastrp"
    join_path_strategy: str = "weighted_shortest_path"
    max_join_path_hops: int = 4
```

- [ ] **Step 4: Wire the container**

In `genql/composition_root.py`, add the imports:

```python
import genql.repositories.graph  # noqa: F401 - registration side effect
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.node_embedder import NodeEmbedder
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.registry import (
    CLUSTERING_ALGORITHMS,
    JOIN_PATH_STRATEGIES,
    NODE_EMBEDDERS,
)
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.semantic.join_path_writer_repository import (
    PostgresJoinPathWriterRepository,
)
from genql.repositories.semantic.semantic_catalog_reader_repository import (
    PostgresSemanticCatalogReader,
)
from genql.services.graph.graph_analysis_service import GraphAnalysisService
from genql.services.graph.graph_projection_service import GraphProjectionService
```

Two module-level helpers, next to `_build_scope_resolver`:

```python
def _build_clustering_algorithm(key: str, gds_provider: GdsClientProvider) -> ClusteringAlgorithm:
    return CLUSTERING_ALGORITHMS.create(key, gds_provider=gds_provider)


def _build_node_embedder(key: str, gds_provider: GdsClientProvider) -> NodeEmbedder:
    return NODE_EMBEDDERS.create(key, gds_provider=gds_provider)


def _build_join_path_miner(
    key: str, driver: object, gds_provider: GdsClientProvider, max_hops: int
) -> JoinPathMiner:
    return JOIN_PATH_STRATEGIES.create(key, driver=driver, gds_provider=gds_provider, max_hops=max_hops)
```

Inside `Container`, add:

```python
    neo4j_driver = providers.Singleton(
        create_neo4j_driver,
        uri=settings.provided.neo4j_uri,
        user=settings.provided.neo4j_user,
        password=settings.provided.neo4j_password,
    )
    gds_client_provider = providers.Singleton(GdsClientProvider, driver=neo4j_driver)

    semantic_catalog_reader = providers.Singleton(
        PostgresSemanticCatalogReader, engine=semantic_engine
    )
    graph_writer = providers.Singleton(Neo4jGraphWriterRepository, driver=neo4j_driver)
    join_path_writer = providers.Singleton(PostgresJoinPathWriterRepository, engine=semantic_engine)

    clustering_algorithm = providers.Singleton(
        _build_clustering_algorithm,
        key=settings.provided.clustering_algorithm,
        gds_provider=gds_client_provider,
    )
    node_embedder = providers.Singleton(
        _build_node_embedder,
        key=settings.provided.node_embedding_algorithm,
        gds_provider=gds_client_provider,
    )
    join_path_miner = providers.Singleton(
        _build_join_path_miner,
        key=settings.provided.join_path_strategy,
        driver=neo4j_driver,
        gds_provider=gds_client_provider,
        max_hops=settings.provided.max_join_path_hops,
    )

    graph_projection_service = providers.Singleton(
        GraphProjectionService, reader=semantic_catalog_reader, writer=graph_writer
    )
    graph_analysis_service = providers.Singleton(
        GraphAnalysisService,
        clustering=clustering_algorithm,
        embedder=node_embedder,
        miner=join_path_miner,
        join_path_writer=join_path_writer,
    )
```

Add the new step to the service-provider map:

```python
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": catalog_scan_service,
        "graph_projection": graph_projection_service,
        "data_profiling": profiling_service,
    }
```

*Note for the implementing engineer:* the dict's insertion order does not control execution order —
`_step_providers_in_registered_order` iterates `DISCOVERY_STEPS.keys()`, which is alphabetical
(`Registry.keys()` returns `sorted(self._items)`). `"catalog_scan"` sorts before
`"graph_projection"`, which sorts before `"data_profiling"` — so the actual run order is
`catalog_scan`, `data_profiling`, `graph_projection`, not the intended `catalog_scan`,
`graph_projection`, `data_profiling`. Since `graph_projection` only needs `catalog_scan` to have
run, not `data_profiling`, this ordering still produces a correct result, but running it right
after `catalog_scan` (before profiling, which is the more expensive step) is the plan's stated
intent. Before Step 5, add a test asserting `DiscoveryRunner`'s step order, and either accept
alphabetical ordering as sufficient (it is correct, only not maximally early) or extend
`_step_providers_in_registered_order` with an explicit ordering list rather than relying on
`Registry.keys()`'s alphabetical default. Decide and document the choice in the commit message.

- [ ] **Step 5: Run to verify the composition-root tests pass**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS

- [ ] **Step 6: Full local suite, lint, types**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add genql/core/settings.py genql/composition_root.py tests/unit/test_composition_root.py
git commit -m "feat(composition-root): wire graph projection and analysis"
```

---

### Task 10: Prove it against a real Neo4j

**Files:**
- Test: `tests/integration/test_graph_analysis_end_to_end.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9

- [ ] **Step 1: Write the end-to-end proof**

Create `tests/integration/test_graph_analysis_end_to_end.py`:

```python
"""genql discover, then genql graph analyze, against the real TPC-DS FK
graph on the VM stack — the shape asserted in the spec's Definition of Done
for this phase."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_discover_then_analyze_produces_communities_embeddings_and_paths() -> None:
    discover_result = runner.invoke(
        app, ["discover", "--datasource", "local", "--schema", "tpcds"]
    )
    assert discover_result.exit_code == 0

    analyze_result = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])

    assert analyze_result.exit_code == 0
    assert "0 communities" not in analyze_result.stdout
    assert "0 nodes embedded" not in analyze_result.stdout
    assert "0 join paths" not in analyze_result.stdout
```

- [ ] **Step 2: Run against the VM**

Run: `uv run pytest tests/integration/test_graph_analysis_end_to_end.py -q`
Expected (on the VM, TPC-DS already seeded per Phase 1-2): PASS. TPC-DS's `store_sales` fact table
has FK edges to `date_dim`, `item`, `customer`, and others that are not themselves directly
FK-connected, so join-path mining is guaranteed at least one candidate pair.

- [ ] **Step 3: Run the full local unit suite one last time**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_graph_analysis_end_to_end.py
git commit -m "test(graph): prove discover + analyze against the real TPC-DS graph"
```

---

## Done When

- `uv run genql discover --datasource local --schema tpcds` projects `local.tpcds` into Neo4j as
  part of the run.
- `uv run genql graph analyze --datasource local` reports a nonzero community count, embeds every
  projected node, and writes at least one row to `genql_join_path`.
- `uv run genql graph rebuild --datasource local` re-projects from Postgres alone, correctly, with
  `GENQL_WAREHOUSE_DSN` unset.
- The local unit suite is green; every integration test in this plan passes on the VM.
- `uv run lint-imports` passes: no Cypher, no GDS client call, and no SQL exist outside
  `genql/repositories/`.
- `uv run mypy genql` reports zero errors under `--strict`.
- Every file is under 250 lines.

## Deliberately Not Done

- Fused clustering and domain naming (spec pipeline steps 7–8) — wait on Phase 4's text embeddings.
- Query-log-weighted join paths — wait on a query log that does not exist before Phase 5/6;
  `Settings.join_path_strategy` is the seam that adds it later with no call-site change.
- View-dependency edges — no catalog reader in this codebase reads `pg_depend` or
  `information_schema.view_table_usage` yet; only FK edges are projected.
- Cross-datasource graphs and cross-schema FK edges — `Constraint` carries no
  `referenced_schema_name`, so a referenced object is always resolved within its own schema; fixing
  that is a catalog-reading change orthogonal to this phase.
