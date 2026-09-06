# GenQL Phase 4: Semantic Store and Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ground every discovered object and column in an LLM-generated description, fuse text embeddings with Phase 3's FastRP vectors to name business domains, let YAML override any discovered or LLM field, compile the result into `genql_search_document` (BM25 + HNSW), and answer a natural-language question with ranked, reranked candidate objects via `genql semantic search`.

**Architecture:** A new per-schema `ObjectProfilingStep` grounds each object and its columns in one LLM call and embeds the result. A datasource-wide `genql graph domains` command fuses those text embeddings with Neo4j's FastRP vectors (L2-normalized, concatenated, k chosen by silhouette score) to name business domains. `genql semantic overlay` merges `semantic/<datasource>.yaml` over discovered/LLM enrichment through a small `Enricher` registry (YAML always wins). `genql semantic compile` builds one `genql_search_document` row per object, BM25- and HNSW-indexed. `genql semantic search` embeds a question, retrieves through a registered `Retriever` (`bm25`/`dense`/`hybrid_rrf`/`domain_scoped`), and reranks. Every new LLM/embedding/rerank call goes through `ChatProvider`/`EmbeddingProvider`/`RerankProvider` ports, each with an `openrouter` implementation over plain `httpx` — no SDK dependency for three JSON-over-HTTPS calls.

**Tech Stack:** Python 3.12 (uv), ParadeDB 0.25.6 on PostgreSQL 18 (`pg_search` BM25 + `pgvector` HNSW), Neo4j 5 Community + GDS (reused from Phase 3), OpenRouter (chat/embeddings/rerank) + Cohere (rerank fallback) over `httpx`, `numpy` + `scikit-learn` (fused-clustering k-means/silhouette), `pgvector` (SQLAlchemy `Vector` type), psycopg 3, SQLAlchemy 2.0 Core, Alembic, Pydantic v2, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-06-genql-phase-4-semantic-store-and-retrieval.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

## Global Constraints

- Python 3.12 exactly, managed by `uv`. Run everything through `uv run`.
- **No httpx call, Cypher string, GDS client call, SQL string, SQLAlchemy Core construct, or psycopg call may appear outside `genql/repositories/`.** Enforced by import-linter (`httpx` joins `sqlalchemy`/`psycopg`/`neo4j`/`graphdatascience` in the `domain-is-pure` and `no-sql-in-services` forbidden-module lists — Task 4 updates `.importlinter`). `genql/infrastructure/` may import `httpx` to build a client, never to make a request.
- `genql/domain/` imports no other `genql` package and performs no I/O.
- `genql/services/` imports only `genql.domain`. It may not import `genql.repositories`, `genql.infrastructure`, `psycopg`, `sqlalchemy`, `neo4j`, or `httpx`.
- Every file ≤ 250 lines (pre-commit hook). One class per file. One action per file.
- `mypy --strict` must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass.
- All entities and value objects are **frozen** Pydantic v2 models (`model_config = ConfigDict(frozen=True)`).
- `Provenance` (Phase 3, `domain/value_objects/provenance.py`) is reused as-is — no new provenance vocabulary.
- Commit after every task (or every batched group of tasks, per the execution note below). Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`).
- **Execution note for whoever runs this plan under subagent-driven-development:** the user's standing preference is to group small/sequentially-dependent tasks into one dispatch rather than one subagent per task, parallelize genuinely independent tasks, commit at batch/feature-completion boundaries rather than per task, and run only one review at the very end. Tasks 1–3 are a natural first batch (pure declarations plus their migration and repositories, nothing runnable yet); Tasks 5, 6, and 8 have no dependency on each other once Tasks 1–4 land and can be parallelized; Task 11 (composition root) must wait for everything it wires.
- Docker (ParadeDB) runs on the Debian VM (`ssh genql-vm`, 100.99.72.99). **Neo4j is currently NOT deployed on that VM** — only `paradedb` is in its `/home/shivam/genql/compose.yaml`. Before any task's Neo4j-touching integration test can run there, add the `neo4j` service block from this repo's `docker/compose.yaml` to the VM's compose file and bring it up (`docker compose up -d neo4j`). The VM's `genql` schema is also not at migration head as of this plan's writing (no `genql_join_path` table yet) — run `alembic upgrade head` before trusting any existing state there.

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_TEST_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_USER=neo4j
  export GENQL_NEO4J_PASSWORD=genqlgenql
  ```

  Put these in your shell once at the start; the plan writes `uv run pytest ...` assuming they are set. Real-provider tests (Task 4, Task 12) additionally need `GENQL_OPENROUTER_API_KEY` and, optionally, `GENQL_COHERE_API_KEY` — as of this plan's writing **neither exists locally or on the VM**, so those specific tests are written to skip cleanly (with a printed reason) rather than fail when unset. Do not treat their skip as a task failure.
- **This plan may be executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit-test suite (`tests/unit/`) must be run and must pass there. Every task's integration tests are written, committed, and left for a VM-connected run — report unit tests green and integration tests written-but-unrun if the VM is unreachable from wherever a task is executed, exactly as Phase 2.5 and Phase 3 did.
- The baseline before Task 1 is the full Phase 3 suite green (unit tests pass locally; integration tests require the VM). Every task must end with the local unit suite green — never leave a task boundary with a red unit suite.

---

## File Structure

**Created**

```
genql/domain/entities/object_enrichment.py         ObjectEnrichment
genql/domain/entities/column_enrichment.py         ColumnEnrichment
genql/domain/entities/business_domain.py           BusinessDomain
genql/domain/entities/domain_member.py             DomainMember
genql/domain/entities/metric.py                    Metric
genql/domain/entities/search_document.py           SearchDocument
genql/domain/entities/enrichment_field.py          EnrichmentField, EnrichmentKind
genql/domain/entities/semantic_overlay.py          SemanticOverlay, ObjectOverlay, ColumnOverlay, MetricOverlay, JoinHintOverlay
genql/domain/ports/chat_provider.py                ChatProvider
genql/domain/ports/embedding_provider.py           EmbeddingProvider
genql/domain/ports/rerank_provider.py              RerankProvider, RerankScore
genql/domain/ports/enrichment_reader.py            EnrichmentReader
genql/domain/ports/enrichment_writer.py            EnrichmentWriter
genql/domain/ports/domain_writer.py                DomainWriter
genql/domain/ports/domain_namer.py                 DomainNamer
genql/domain/ports/metric_writer.py                MetricWriter
genql/domain/ports/enricher.py                     Enricher
genql/domain/ports/search_document_writer.py       SearchDocumentWriter
genql/domain/ports/comment_writer.py               CommentWriter
genql/domain/ports/retriever.py                    Retriever, SearchResult
genql/domain/ports/cluster_reader.py               ClusterReader
migrations/versions/0005_semantic_store_and_retrieval.py   six tables, two extensions, BM25 + HNSW indexes
genql/repositories/semantic/enrichment_repository.py       PostgresEnrichmentRepository
genql/repositories/semantic/domain_repository.py           PostgresDomainRepository
genql/repositories/semantic/metric_repository.py           PostgresMetricRepository
genql/infrastructure/gateway/__init__.py
genql/infrastructure/gateway/openrouter_client.py          OpenRouterClient, OpenRouterError
genql/infrastructure/gateway/cohere_client.py              CohereClient, CohereError
genql/repositories/gateway/__init__.py                     imports implementations for registration
genql/repositories/gateway/registry.py                     CHAT_PROVIDERS, EMBEDDING_PROVIDERS, RERANK_PROVIDERS
genql/repositories/gateway/chat_provider_repository.py     OpenRouterChatProvider
genql/repositories/gateway/embedding_provider_repository.py OpenRouterEmbeddingProvider
genql/repositories/gateway/rerank_provider_repository.py   OpenRouterRerankProvider, CohereRerankProvider
genql/services/semantic/__init__.py
genql/services/semantic/object_profiling_service.py        ObjectProfilingService, ObjectProfilingReport
genql/discovery/steps/object_profiling_step.py             ObjectProfilingStep
genql/repositories/graph/fused_clustering_algorithm_repository.py  FusedClusteringAlgorithm
genql/repositories/graph/cluster_reader_repository.py      Neo4jClusterReader
genql/repositories/semantic/domain_namer_repository.py     LlmDomainNamer
genql/services/semantic/domain_discovery_service.py        DomainDiscoveryService, DomainDiscoveryReport
genql/repositories/semantic/enricher_repository.py         DescriptionEnricher, AliasEnricher, UnitEnricher
genql/repositories/semantic/registry.py                    ENRICHERS, RETRIEVERS
genql/services/semantic/semantic_overlay_service.py        SemanticOverlayService, OverlayReport
genql/infrastructure/catalog/comment_writer_factory.py     CommentWriterFactory, CommentWriterFactoryImpl
genql/repositories/warehouse/comment_writer_repository.py  PostgresCommentWriter
genql/repositories/semantic/search_document_repository.py  SearchDocumentCompiler
genql/services/semantic/compile_service.py                 CompileService, CompileReport
genql/repositories/semantic/bm25_retriever_repository.py   Bm25Retriever
genql/repositories/semantic/dense_retriever_repository.py  DenseRetriever
genql/repositories/semantic/hybrid_rrf_retriever_repository.py  HybridRrfRetriever
genql/repositories/semantic/domain_scoped_retriever_repository.py  DomainScopedRetriever
genql/services/semantic/retrieval_service.py               RetrievalService
genql/cli/commands/semantic.py                              `genql semantic overlay|compile|search`
tests/unit/test_object_enrichment_entity.py
tests/unit/test_semantic_overlay_entity.py
tests/unit/test_enrichment_field_entity.py
tests/unit/test_semantic_ports_are_runtime_checkable.py
tests/unit/test_object_profiling_service.py
tests/unit/test_object_profiling_step.py
tests/unit/test_fused_clustering_k_selection.py
tests/unit/test_domain_discovery_service.py
tests/unit/test_enrichers.py
tests/unit/test_semantic_overlay_service.py
tests/unit/test_semantic_overlay_yaml_validation.py
tests/unit/test_compile_service.py
tests/unit/test_retrieval_service.py
tests/unit/test_domain_scoped_retriever.py
tests/unit/test_gateway_registries.py
tests/integration/test_migration_0005.py
tests/integration/test_enrichment_repository.py
tests/integration/test_domain_repository.py
tests/integration/test_metric_repository.py
tests/integration/test_openrouter_chat_provider.py
tests/integration/test_openrouter_embedding_provider.py
tests/integration/test_rerank_providers.py
tests/integration/test_fused_clustering_algorithm_repository.py
tests/integration/test_cluster_reader_repository.py
tests/integration/test_cli_semantic_overlay.py
tests/integration/test_comment_writer_repository.py
tests/integration/test_search_document_compiler.py
tests/integration/test_retriever_repositories.py
tests/integration/test_cli_graph_domains.py
tests/integration/test_cli_semantic_search.py
tests/integration/test_phase4_end_to_end.py
```

**Modified**

```
genql/domain/ports/semantic_catalog_reader.py   + read_columns, read_column_profiles
genql/repositories/semantic/semantic_catalog_reader_repository.py   + read_columns, read_column_profiles
genql/domain/errors.py                          + ChatProviderError, EmbeddingProviderError, RerankProviderError, EnrichmentError, DomainNamingError, OverlayError, CompileError, RetrievalError
genql/repositories/graph/registry.py            + fused entry usage documented (registration happens in the repository file itself)
genql/repositories/graph/__init__.py            + import FusedClusteringAlgorithm, Neo4jClusterReader for registration
genql/repositories/semantic/__init__.py         + import enricher/retriever repositories for registration
genql/core/settings.py                          + provider/model/clustering/retrieval settings (Task 11)
genql/composition_root.py                       + every new provider, service, and CLI wiring (Task 11)
genql/cli/commands/graph.py                     + `domains` command
genql/cli/main.py                               mounts the `semantic` sub-app
pyproject.toml                                  + pgvector (Task 2), httpx (Task 4), numpy + scikit-learn (Task 6)
.importlinter                                   + httpx to both forbidden-module lists (Task 4)
.env.example                                    + GENQL_OPENROUTER_API_KEY, GENQL_COHERE_API_KEY, model/provider defaults
tests/integration/conftest.py                   + nothing new required (existing fixtures cover Postgres/Neo4j); confirm CREATE EXTENSION lines still match Task 2's migration
tests/unit/test_ports_are_runtime_checkable.py  left alone — new ports get their own `test_semantic_ports_are_runtime_checkable.py` file to keep this one under the 250-line cap
tests/unit/test_composition_root.py             + assertions for every new container-level provider (Task 11)
```

---

## Task Sequence and Why

Tasks 1–3 lay the domain model and the plain Postgres side of the new schema — no external
provider, no Neo4j, nothing but entities, ports, a migration, and upsert repositories, mirroring
how Phase 3's Tasks 1–2 front-loaded the semantic-store shape before touching Neo4j. Task 4 adds the
LLM gateway (OpenRouter/Cohere over `httpx`) and its three registries — everything above it is pure
Postgres/pydantic and testable without a key; everything below it needs a `ChatProvider` or
`EmbeddingProvider` port satisfied, real or fake. Tasks 5–10 each add one vertical slice — profiling,
fused clustering, domain naming, overlay, compile, retrieval — following each port from Tasks 1–4
through to a repository, a service, and (where the spec calls for one) a CLI command, exactly the
shape Phase 3's Tasks 5–8 used. Task 11 is composition-root wiring, held back until everything it
wires exists, same as Phase 3's Task 9. Task 12 proves the whole chain end-to-end against real
infrastructure, same as Phase 3's Task 10.

---

### Task 1: Domain foundation

**Files:**
- Create: `genql/domain/entities/object_enrichment.py`, `genql/domain/entities/column_enrichment.py`, `genql/domain/entities/business_domain.py`, `genql/domain/entities/domain_member.py`, `genql/domain/entities/metric.py`, `genql/domain/entities/search_document.py`, `genql/domain/entities/enrichment_field.py`, `genql/domain/entities/semantic_overlay.py`, `genql/domain/ports/chat_provider.py`, `genql/domain/ports/embedding_provider.py`, `genql/domain/ports/rerank_provider.py`, `genql/domain/ports/enrichment_reader.py`, `genql/domain/ports/enrichment_writer.py`, `genql/domain/ports/domain_writer.py`, `genql/domain/ports/domain_namer.py`, `genql/domain/ports/metric_writer.py`, `genql/domain/ports/enricher.py`, `genql/domain/ports/search_document_writer.py`, `genql/domain/ports/comment_writer.py`, `genql/domain/ports/retriever.py`, `genql/domain/ports/cluster_reader.py`
- Modify: `genql/domain/ports/semantic_catalog_reader.py`, `genql/domain/errors.py`
- Test: `tests/unit/test_object_enrichment_entity.py`, `tests/unit/test_semantic_overlay_entity.py`, `tests/unit/test_enrichment_field_entity.py`, `tests/unit/test_semantic_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `Provenance` (Phase 3, `domain/value_objects/provenance.py`); `SchemaRef` (`domain/value_objects/schema_ref.py`); `Column`, `ColumnProfile`, `DatabaseObject`, `Constraint` (existing entities); `DiscoveryError`, `GenqlError` (`domain/errors.py`)
- Produces: every entity and port listed above, plus `ChatProviderError`, `EmbeddingProviderError`, `RerankProviderError`, `EnrichmentError`, `DomainNamingError`, `OverlayError`, `CompileError`, `RetrievalError` in `domain/errors.py`, and `SemanticCatalogReader.read_columns(ref) -> Sequence[Column]` / `.read_column_profiles(ref) -> Sequence[ColumnProfile]`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/test_object_enrichment_entity.py`:

```python
"""Frozen, and confidence is bounded to [0, 1] like every other confidence
field in the codebase."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.provenance import Provenance


def test_defaults_are_llm_provenance_and_full_confidence() -> None:
    enrichment = ObjectEnrichment(
        datasource_name="local", schema_name="tpcds", object_name="store_sales",
        description="Point-of-sale line items.",
    )

    assert enrichment.provenance == Provenance.LLM
    assert enrichment.confidence == 1.0
    assert enrichment.embedding is None
    assert enrichment.qualified_name == "local.tpcds.store_sales"


def test_confidence_above_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ObjectEnrichment(
            datasource_name="local", schema_name="tpcds", object_name="store_sales",
            description="x", confidence=1.5,
        )


def test_is_frozen() -> None:
    enrichment = ObjectEnrichment(
        datasource_name="local", schema_name="tpcds", object_name="store_sales", description="x",
    )
    with pytest.raises(ValidationError):
        enrichment.description = "y"  # type: ignore[misc]
```

Create `tests/unit/test_semantic_overlay_entity.py`:

```python
"""Validates the shape of one semantic/<datasource>.yaml file. Object keys
are fully-qualified "schema.object" strings; parsing them apart is the
overlay service's job, not this model's."""

from __future__ import annotations

from genql.domain.entities.semantic_overlay import (
    ColumnOverlay,
    JoinHintOverlay,
    MetricOverlay,
    ObjectOverlay,
    SemanticOverlay,
)


def test_round_trips_a_full_overlay() -> None:
    overlay = SemanticOverlay(
        datasource="local",
        objects={
            "tpcds.store_sales": ObjectOverlay(
                description="Point-of-sale line items for in-store purchases.",
                business_alias="store transactions",
                columns={
                    "ss_ext_sales_price": ColumnOverlay(
                        description="Extended sales price before discount.", unit="USD"
                    )
                },
            )
        },
        metrics=(
            MetricOverlay(
                name="net_sales", sql_expression="ss_ext_sales_price - ss_ext_discount_amt",
                grain="line_item", unit="USD",
            ),
        ),
        join_hints=(
            JoinHintOverlay(
                source_object="tpcds.store_sales", target_object="tpcds.customer",
                path=("tpcds.store_sales", "tpcds.customer"), weight=0.5,
            ),
        ),
    )

    assert overlay.objects["tpcds.store_sales"].columns["ss_ext_sales_price"].unit == "USD"
    assert overlay.metrics[0].name == "net_sales"
    assert overlay.join_hints[0].path == ("tpcds.store_sales", "tpcds.customer")


def test_objects_metrics_and_join_hints_default_empty() -> None:
    overlay = SemanticOverlay(datasource="local")

    assert overlay.objects == {}
    assert overlay.metrics == ()
    assert overlay.join_hints == ()
```

Create `tests/unit/test_enrichment_field_entity.py`:

```python
from __future__ import annotations

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.value_objects.provenance import Provenance


def test_kind_is_restricted_to_the_three_merge_time_fields() -> None:
    field = EnrichmentField(
        kind="description", qualified_name="local.tpcds.store_sales", value="x",
        provenance=Provenance.LLM,
    )

    assert field.kind == "description"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_object_enrichment_entity.py tests/unit/test_semantic_overlay_entity.py tests/unit/test_enrichment_field_entity.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the entities**

Create `genql/domain/entities/object_enrichment.py`:

```python
"""LLM-grounded (or YAML-overridden) description of one database object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.provenance import Provenance


class ObjectEnrichment(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    description: str
    business_alias: str | None = None
    provenance: Provenance = Provenance.LLM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    embedding: tuple[float, ...] | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}.{self.object_name}"
```

Create `genql/domain/entities/column_enrichment.py`:

```python
"""LLM-grounded (or YAML-overridden) description of one column."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.provenance import Provenance


class ColumnEnrichment(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    column_name: str
    description: str
    business_alias: str | None = None
    unit: str | None = None
    provenance: Provenance = Provenance.LLM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}.{self.object_name}.{self.column_name}"
```

Create `genql/domain/entities/business_domain.py`:

```python
"""A named business domain: one cluster of objects, given a name and a
description. Named BusinessDomain, not Domain — the latter collides with the
architecture's own domain/ layer name."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance


class BusinessDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    domain_id: int | None = None
    name: str
    description: str
    provenance: Provenance = Provenance.LLM
```

Create `genql/domain/entities/domain_member.py`:

```python
"""One object's membership in one business domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainMember(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_id: int
    datasource_name: str
    schema_name: str
    object_name: str
    membership_score: float = Field(default=1.0, ge=0.0, le=1.0)
```

Create `genql/domain/entities/metric.py`:

```python
"""A YAML-authored business metric: a named SQL expression at a stated
grain. Always provenance=YAML in Phase 4 — nothing else proposes a metric."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.provenance import Provenance


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    name: str
    sql_expression: str
    grain: str
    unit: str | None = None
    default_filters: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance = Provenance.YAML
```

Create `genql/domain/entities/search_document.py`:

```python
"""One compiled, retrievable document per object: BM25 text plus its
embedding. This embedding is computed over the fuller compiled text
(including the domain name) — a separate computation from
ObjectEnrichment.embedding, which exists earlier, before a domain name is
known."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    domain_name: str | None
    content: str
    embedding: tuple[float, ...]
```

Create `genql/domain/entities/enrichment_field.py`:

```python
"""The one shape description/alias/unit enrichment share: a single string
value on one object or column, competing between a discovered/LLM value and
a YAML override. Metric and join-hint enrichment do NOT share this shape
(see Non-goals in the spec) and are handled by their own dedicated code."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance

EnrichmentKind = Literal["description", "alias", "unit"]


class EnrichmentField(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EnrichmentKind
    qualified_name: str
    value: str
    provenance: Provenance
```

Create `genql/domain/entities/semantic_overlay.py`:

```python
"""Validated shape of one semantic/<datasource>.yaml file. Object keys in
`objects` are fully-qualified "schema.object" strings — parsing them apart
into a SchemaRef plus an object name is the overlay service's job, not this
model's, which stays a pure structural validator."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    business_alias: str | None = None
    unit: str | None = None


class ObjectOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    business_alias: str | None = None
    columns: dict[str, ColumnOverlay] = Field(default_factory=dict)


class MetricOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    sql_expression: str
    grain: str
    unit: str | None = None
    default_filters: dict[str, str] = Field(default_factory=dict)


class JoinHintOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_object: str
    target_object: str
    path: tuple[str, ...]
    weight: float = 1.0


class SemanticOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource: str
    objects: dict[str, ObjectOverlay] = Field(default_factory=dict)
    metrics: tuple[MetricOverlay, ...] = ()
    join_hints: tuple[JoinHintOverlay, ...] = ()
```

- [ ] **Step 4: Run to verify the entity tests pass**

Run: `uv run pytest tests/unit/test_object_enrichment_entity.py tests/unit/test_semantic_overlay_entity.py tests/unit/test_enrichment_field_entity.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing port test**

Create `tests/unit/test_semantic_ports_are_runtime_checkable.py`:

```python
"""A fake satisfying each protocol proves the corresponding service can be
tested without a database, an LLM, or a network call."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.domain_member import DomainMember
from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.cluster_reader import ClusterReader
from genql.domain.ports.comment_writer import CommentWriter
from genql.domain.ports.domain_namer import DomainNamer
from genql.domain.ports.domain_writer import DomainWriter
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.metric_writer import MetricWriter
from genql.domain.ports.rerank_provider import RerankProvider, RerankScore
from genql.domain.ports.retriever import Retriever, SearchResult
from genql.domain.ports.search_document_writer import SearchDocumentWriter
from genql.domain.value_objects.schema_ref import SchemaRef
from pydantic import BaseModel


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        return response_schema.model_validate({})


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.0,) for _ in texts]


class FakeRerankProvider:
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        return [RerankScore(index=i, score=1.0) for i in range(min(top_n, len(documents)))]


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return []

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        return []


class FakeEnrichmentWriter:
    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        return None

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        return len(enrichments)


class FakeDomainWriter:
    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        return domains

    def write_members(self, members: Sequence[DomainMember]) -> int:
        return len(members)


class FakeDomainNamer:
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        return []


class FakeMetricWriter:
    def write(self, metrics: Sequence[Metric]) -> int:
        return len(metrics)


class FakeEnricher:
    key = "description"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay or discovered


class FakeSearchDocumentWriter:
    def compile(self, datasource_name: str) -> int:
        return 0


class FakeCommentWriter:
    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        return None

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        return None


class FakeRetriever:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return []


class FakeClusterReader:
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        return {}


def test_a_plain_class_satisfies_each_new_port() -> None:
    assert isinstance(FakeChatProvider(), ChatProvider)
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)
    assert isinstance(FakeRerankProvider(), RerankProvider)
    assert isinstance(FakeEnrichmentReader(), EnrichmentReader)
    assert isinstance(FakeEnrichmentWriter(), EnrichmentWriter)
    assert isinstance(FakeDomainWriter(), DomainWriter)
    assert isinstance(FakeDomainNamer(), DomainNamer)
    assert isinstance(FakeMetricWriter(), MetricWriter)
    assert isinstance(FakeEnricher(), Enricher)
    assert isinstance(FakeSearchDocumentWriter(), SearchDocumentWriter)
    assert isinstance(FakeCommentWriter(), CommentWriter)
    assert isinstance(FakeRetriever(), Retriever)
    assert isinstance(FakeClusterReader(), ClusterReader)
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_semantic_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement the ports**

Create `genql/domain/ports/chat_provider.py`:

```python
"""One grounded LLM call, returning a validated Pydantic model rather than
prose to parse — a profiling or naming failure is a ValidationError the
caller catches, not a silent mis-parse."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class ChatProvider(Protocol):
    def complete(self, prompt: str, response_schema: type[T]) -> T: ...
```

Create `genql/domain/ports/embedding_provider.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]: ...
```

Create `genql/domain/ports/rerank_provider.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class RerankScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    score: float


@runtime_checkable
class RerankProvider(Protocol):
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]: ...
```

Create `genql/domain/ports/enrichment_reader.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class EnrichmentReader(Protocol):
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]: ...

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]: ...
```

Create `genql/domain/ports/enrichment_writer.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment


@runtime_checkable
class EnrichmentWriter(Protocol):
    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None: ...

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int: ...
```

Create `genql/domain/ports/domain_writer.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember


@runtime_checkable
class DomainWriter(Protocol):
    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]: ...

    def write_members(self, members: Sequence[DomainMember]) -> int: ...
```

Create `genql/domain/ports/domain_namer.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.object_enrichment import ObjectEnrichment


@runtime_checkable
class DomainNamer(Protocol):
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]: ...
```

Create `genql/domain/ports/metric_writer.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.metric import Metric


@runtime_checkable
class MetricWriter(Protocol):
    def write(self, metrics: Sequence[Metric]) -> int: ...
```

Create `genql/domain/ports/enricher.py`:

```python
"""Merge-time rule for one of description/alias/unit: given the current
discovered/LLM value and an optional YAML override, decide which value wins.
The default rule (an overlay always wins) is identical across all three
registered kinds; each still gets its own class so a future kind needing
different validation costs one new file, not a branch in an existing one."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from genql.domain.entities.enrichment_field import EnrichmentField


@runtime_checkable
class Enricher(Protocol):
    key: ClassVar[str]

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None: ...
```

Create `genql/domain/ports/search_document_writer.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SearchDocumentWriter(Protocol):
    def compile(self, datasource_name: str) -> int: ...
```

Create `genql/domain/ports/comment_writer.py`:

```python
"""Writes to the WAREHOUSE, not the semantic store — the one port in this
phase that touches a datasource other than GenQL's own. Off by default at
every call site."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class CommentWriter(Protocol):
    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None: ...

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None: ...
```

Create `genql/domain/ports/retriever.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    domain_name: str | None
    score: float


@runtime_checkable
class Retriever(Protocol):
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]: ...
```

Create `genql/domain/ports/cluster_reader.py`:

```python
"""Reads a clustering algorithm's node-property assignment back out of
Neo4j — the read side FusedClusteringAlgorithm's `detect` doesn't itself
provide, since ClusteringAlgorithm.detect returns only a count."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClusterReader(Protocol):
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]: ...
```

Extend `genql/domain/ports/semantic_catalog_reader.py` — add two methods to the existing `SemanticCatalogReader` Protocol:

```python
from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile

# ... inside the Protocol, alongside read_objects and read_constraints:
    def read_columns(self, ref: SchemaRef) -> Sequence[Column]: ...

    def read_column_profiles(self, ref: SchemaRef) -> Sequence[ColumnProfile]: ...
```

Extend `genql/domain/errors.py` — add at the end:

```python
class ChatProviderError(GenqlError):
    """A ChatProvider implementation could not complete a call."""


class EmbeddingProviderError(GenqlError):
    """An EmbeddingProvider implementation could not complete a call."""


class RerankProviderError(GenqlError):
    """A RerankProvider implementation could not complete a call."""


class EnrichmentError(DiscoveryError):
    """LLM object profiling or embedding could not complete."""


class DomainNamingError(DiscoveryError):
    """Fused clustering or LLM domain naming could not complete."""


class OverlayError(DiscoveryError):
    """semantic/<datasource>.yaml failed schema validation or named an unknown object."""


class CompileError(DiscoveryError):
    """genql_search_document could not be refreshed."""


class RetrievalError(GenqlError):
    """Hybrid retrieval or reranking could not complete. Runs online, not during discovery."""
```

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_semantic_ports_are_runtime_checkable.py -q`
Expected: PASS

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/domain tests/unit/test_object_enrichment_entity.py tests/unit/test_semantic_overlay_entity.py tests/unit/test_enrichment_field_entity.py tests/unit/test_semantic_ports_are_runtime_checkable.py
git commit -m "feat(domain): add Phase 4 entities, ports, and errors"
```

---

### Task 2: Migration 0005 and the SemanticCatalogReader read side

**Files:**
- Create: `migrations/versions/0005_semantic_store_and_retrieval.py`
- Modify: `genql/repositories/semantic/semantic_catalog_reader_repository.py`, `pyproject.toml`
- Test: `tests/integration/test_migration_0005.py`, `tests/integration/test_semantic_catalog_reader_repository.py` (extend the existing file)

**Interfaces:**
- Consumes: `Column`, `ColumnProfile` entities; `SchemaRef`; `SemanticCatalogReader` port (Task 1)
- Produces: six tables (`genql_object_enrichment`, `genql_column_enrichment`, `genql_domain`, `genql_domain_member`, `genql_metric`, `genql_search_document`) plus the `vector`/`pg_search` extensions and a BM25 + HNSW index; `PostgresSemanticCatalogReader.read_columns` / `.read_column_profiles`

- [ ] **Step 1: Add the pgvector dependency**

```bash
uv add pgvector
```

This adds `pgvector>=0.x` to `pyproject.toml`'s `[project.dependencies]`. `pgvector.sqlalchemy.Vector` is a SQLAlchemy Core column type whose bind/result processors handle the `vector` wire format directly — no change to `infrastructure/db/engine.py` is needed.

- [ ] **Step 2: Write the failing migration test**

Create `tests/integration/test_migration_0005.py`:

```python
"""Purely additive: six new tables, two extensions, one BM25 index, one HNSW
index. Downgrade drops the tables but never the extensions — another table
in the same database might still need them."""

from __future__ import annotations

from sqlalchemy import Engine, text
from alembic import command
from alembic.config import Config


def test_upgrade_creates_the_six_tables_and_both_indexes(
    engine: Engine, paradedb_dsn: str
) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'genql' AND table_name LIKE 'genql_%'"
                )
            ).scalars()
        )
        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'genql' AND tablename = 'genql_search_document'"
                )
            ).scalars()
        )

    assert {
        "genql_object_enrichment", "genql_column_enrichment", "genql_domain",
        "genql_domain_member", "genql_metric", "genql_search_document",
    } <= tables
    assert "genql_search_document_bm25" in indexes
    assert "genql_search_document_hnsw" in indexes


def test_downgrade_then_upgrade_is_clean(engine: Engine, paradedb_dsn: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "0004")
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('genql.genql_search_document') IS NOT NULL")
        ).scalar_one()
    assert exists
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0005.py -q` (against the VM per Global Constraints)
Expected: FAIL — table/index does not exist yet (migration `0005` not present)

- [ ] **Step 4: Write the migration**

Create `migrations/versions/0005_semantic_store_and_retrieval.py`:

```python
"""semantic store and retrieval

Revision ID: 0005
Revises: 0004

Six new tables, purely additive. `vector` and `pg_search` are created here
rather than assumed present — tests/integration/conftest.py has created them
ad hoc for every test run so far, but a real deployment applies this
migration once and should not depend on test fixtures to have extensions
ready. `genql_search_document`'s BM25 and HNSW indexes cannot be expressed
through SQLAlchemy's table DDL and are added with raw `op.execute`.

Two embeddings exist for a reason: `genql_object_enrichment.embedding` is
computed straight from the LLM profile, before a domain name exists (fused
clustering needs it to produce that name). `genql_search_document.embedding`
is computed later, over the fuller compiled text that includes the domain
name. `genql_column_enrichment` carries no embedding — column text is folded
into the parent object's search document instead of embedded a second time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    op.create_table(
        "genql_object_enrichment",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("business_alias", sa.Text),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("embedding", Vector(_EMBEDDING_DIM)),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name", "schema_name", "object_name", name="pk_genql_object_enrichment"
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_object_enrichment_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_column_enrichment",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("business_alias", sa.Text),
        sa.Column("unit", sa.Text),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name", "schema_name", "object_name", "column_name",
            name="pk_genql_column_enrichment",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_column_enrichment_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_domain",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_domain_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"], ["genql.genql_datasource.name"],
            name="fk_genql_domain_datasource", ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_domain_member",
        sa.Column("domain_id", sa.BigInteger, nullable=False),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("membership_score", sa.Float, nullable=False, server_default="1.0"),
        sa.PrimaryKeyConstraint(
            "domain_id", "datasource_name", "schema_name", "object_name",
            name="pk_genql_domain_member",
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["genql.genql_domain.id"],
            name="fk_genql_domain_member_domain", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_domain_member_schema", ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_metric",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("sql_expression", sa.Text, nullable=False),
        sa.Column("grain", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column("default_filters", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("provenance", sa.Text, nullable=False, server_default="yaml"),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_metric_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"], ["genql.genql_datasource.name"],
            name="fk_genql_metric_datasource", ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_search_document",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("domain_name", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "datasource_name", "schema_name", "object_name", name="uq_genql_search_document_identity"
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_search_document_schema", ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.execute("""
        CREATE INDEX genql_search_document_bm25
            ON genql.genql_search_document
            USING bm25 (id, content)
            WITH (key_field = 'id')
    """)
    op.execute("""
        CREATE INDEX genql_search_document_hnsw
            ON genql.genql_search_document
            USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genql.genql_search_document_hnsw")
    op.execute("DROP INDEX IF EXISTS genql.genql_search_document_bm25")
    op.drop_table("genql_search_document", schema="genql")
    op.drop_table("genql_metric", schema="genql")
    op.drop_table("genql_domain_member", schema="genql")
    op.drop_table("genql_domain", schema="genql")
    op.drop_table("genql_column_enrichment", schema="genql")
    op.drop_table("genql_object_enrichment", schema="genql")
    # Extensions are not dropped: another table in this database may still need them.
```

Note the `sa.dialects.postgresql.JSONB` reference requires `import sqlalchemy.dialects.postgresql` — add `from sqlalchemy.dialects.postgresql import JSONB` at the top instead and use `JSONB` directly; the inline form above is for readability in this plan only. Use the import form in the actual file.

- [ ] **Step 5: Run to verify the migration test passes**

Run: `uv run pytest tests/integration/test_migration_0005.py -q`
Expected: PASS

- [ ] **Step 6: Write the failing test for the extended reader**

Extend `tests/integration/test_semantic_catalog_reader_repository.py` (the file already exists from Phase 3 — add these two tests to it):

```python
def test_read_columns_returns_every_column_of_the_schema(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "reader_columns_test")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_column "
                "(datasource_name, schema_name, object_name, column_name, ordinal, data_type, "
                " is_nullable, is_primary_key) "
                "VALUES ('local', 'reader_columns_test', 'orders', 'id', 1, 'bigint', false, true)"
            )
        )

    columns = PostgresSemanticCatalogReader(migrated_engine).read_columns(
        SchemaRef(datasource_name="local", schema_name="reader_columns_test")
    )

    assert [c.column_name for c in columns] == ["id"]


def test_read_column_profiles_returns_every_profile_of_the_schema(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "reader_profiles_test")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_column_profile "
                "(datasource_name, schema_name, object_name, column_name, distinct_count, "
                " null_fraction, sample_values) "
                "VALUES ('local', 'reader_profiles_test', 'orders', 'status', 3, 0.0, "
                " ARRAY['OPEN', 'SHIPPED', 'CANCELLED'])"
            )
        )

    profiles = PostgresSemanticCatalogReader(migrated_engine).read_column_profiles(
        SchemaRef(datasource_name="local", schema_name="reader_profiles_test")
    )

    assert profiles[0].sample_values == ("OPEN", "SHIPPED", "CANCELLED")
```

(Add `from collections.abc import Callable` and `from genql.domain.value_objects.schema_ref import SchemaRef` to the file's imports if not already present from Phase 3.)

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/integration/test_semantic_catalog_reader_repository.py -q`
Expected: FAIL — `AttributeError: 'PostgresSemanticCatalogReader' object has no attribute 'read_columns'`

- [ ] **Step 8: Extend the port and the repository**

In `genql/domain/ports/semantic_catalog_reader.py`, add (Task 1 already wrote the stub signatures — this step is the reminder that the import lines below must exist at the top of the file):

```python
from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
```

In `genql/repositories/semantic/semantic_catalog_reader_repository.py`, add two `SELECT`s and two methods:

```python
from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile

_SELECT_COLUMNS = text("""
    SELECT datasource_name, schema_name, object_name, column_name, ordinal, data_type,
           is_nullable, is_primary_key
    FROM genql.genql_column
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
    ORDER BY object_name, ordinal
""")

_SELECT_COLUMN_PROFILES = text("""
    SELECT datasource_name, schema_name, object_name, column_name, distinct_count,
           null_fraction, sample_values
    FROM genql.genql_column_profile
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")


# ... inside PostgresSemanticCatalogReader, alongside read_objects and read_constraints:
    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_COLUMNS, ref.model_dump()).all()
        return [Column.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def read_column_profiles(self, ref: SchemaRef) -> Sequence[ColumnProfile]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_COLUMN_PROFILES, ref.model_dump()).all()
        return [ColumnProfile.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/integration/test_semantic_catalog_reader_repository.py -q`
Expected: PASS

- [ ] **Step 10: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add migrations/versions/0005_semantic_store_and_retrieval.py genql/repositories/semantic/semantic_catalog_reader_repository.py genql/domain/ports/semantic_catalog_reader.py pyproject.toml uv.lock tests/integration/test_migration_0005.py tests/integration/test_semantic_catalog_reader_repository.py
git commit -m "feat(semantic-store): add Phase 4 tables and extend the catalog reader"
```

---

### Task 3: Enrichment, domain, and metric repositories

**Files:**
- Create: `genql/repositories/semantic/enrichment_repository.py`, `genql/repositories/semantic/domain_repository.py`, `genql/repositories/semantic/metric_repository.py`
- Test: `tests/integration/test_enrichment_repository.py`, `tests/integration/test_domain_repository.py`, `tests/integration/test_metric_repository.py`

**Interfaces:**
- Consumes: `ObjectEnrichment`, `ColumnEnrichment`, `BusinessDomain`, `DomainMember`, `Metric` entities (Task 1); `EnrichmentReader`, `EnrichmentWriter`, `DomainWriter`, `MetricWriter` ports (Task 1)
- Produces: `PostgresEnrichmentRepository(engine)` implementing both `EnrichmentReader` and `EnrichmentWriter`; `PostgresDomainRepository(engine)` implementing `DomainWriter`; `PostgresMetricRepository(engine)` implementing `MetricWriter`

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_enrichment_repository.py`:

```python
"""One repository for both tables: object and column enrichment are always
read and written together for one object, same rule as every other
aggregate-scoped repository in this codebase."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.repositories.semantic.enrichment_repository import PostgresEnrichmentRepository


def test_write_then_read_object_enrichment(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "enrichment_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    enrichment = ObjectEnrichment(
        datasource_name="local", schema_name="enrichment_test", object_name="orders",
        description="Customer orders.", embedding=tuple(0.1 for _ in range(1536)),
    )

    repo.write_object_enrichment(enrichment)
    read_back = repo.read_object_enrichments("local")

    assert any(e.object_name == "orders" and e.description == "Customer orders." for e in read_back)


def test_writing_the_same_object_twice_upserts(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "enrichment_upsert_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    first = ObjectEnrichment(
        datasource_name="local", schema_name="enrichment_upsert_test", object_name="orders",
        description="v1",
    )
    repo.write_object_enrichment(first)

    repo.write_object_enrichment(ObjectEnrichment(**{**first.model_dump(), "description": "v2"}))

    read_back = [
        e for e in repo.read_object_enrichments("local") if e.schema_name == "enrichment_upsert_test"
    ]
    assert len(read_back) == 1
    assert read_back[0].description == "v2"


def test_write_then_read_column_enrichments(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    from genql.domain.value_objects.schema_ref import SchemaRef

    register_schema("local", "column_enrichment_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    column = ColumnEnrichment(
        datasource_name="local", schema_name="column_enrichment_test", object_name="orders",
        column_name="status", description="Order lifecycle state.", unit=None,
    )

    written = repo.write_column_enrichments([column])
    read_back = repo.read_column_enrichments(
        SchemaRef(datasource_name="local", schema_name="column_enrichment_test")
    )

    assert written == 1
    assert read_back[0].description == "Order lifecycle state."
```

Create `tests/integration/test_domain_repository.py`:

```python
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember
from genql.repositories.semantic.domain_repository import PostgresDomainRepository


def test_write_domains_returns_rows_with_ids_populated(migrated_engine: Engine) -> None:
    repo = PostgresDomainRepository(migrated_engine)
    domain = BusinessDomain(datasource_name="local", name="sales", description="Sales activity.")

    written = repo.write_domains([domain])

    assert written[0].domain_id is not None


def test_write_members_after_write_domains(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "domain_member_test")
    repo = PostgresDomainRepository(migrated_engine)
    domain = repo.write_domains(
        [BusinessDomain(datasource_name="local", name="sales_2", description="Sales activity.")]
    )[0]
    assert domain.domain_id is not None
    member = DomainMember(
        domain_id=domain.domain_id, datasource_name="local", schema_name="domain_member_test",
        object_name="orders",
    )

    count = repo.write_members([member])

    assert count == 1
```

Create `tests/integration/test_metric_repository.py`:

```python
from __future__ import annotations

from sqlalchemy import Engine

from genql.domain.entities.metric import Metric
from genql.repositories.semantic.metric_repository import PostgresMetricRepository


def test_write_upserts_by_name(migrated_engine: Engine) -> None:
    repo = PostgresMetricRepository(migrated_engine)
    metric = Metric(
        datasource_name="local", name="net_sales", sql_expression="a - b", grain="line_item",
    )

    written = repo.write([metric])
    rewritten = repo.write(
        [Metric(**{**metric.model_dump(), "sql_expression": "a - b - c"})]
    )

    assert written == 1
    assert rewritten == 1
```

- [ ] **Step 2: Run to verify all three fail**

Run: `uv run pytest tests/integration/test_enrichment_repository.py tests/integration/test_domain_repository.py tests/integration/test_metric_repository.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the repositories**

Create `genql/repositories/semantic/enrichment_repository.py`:

```python
"""Object and column enrichment, read and written together — one aggregate."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef

_SELECT_OBJECT_ENRICHMENTS = text("""
    SELECT datasource_name, schema_name, object_name, description, business_alias,
           provenance, confidence, embedding
    FROM genql.genql_object_enrichment
    WHERE datasource_name = :datasource_name
""")

_UPSERT_OBJECT_ENRICHMENT = text("""
    INSERT INTO genql.genql_object_enrichment
        (datasource_name, schema_name, object_name, description, business_alias, provenance,
         confidence, embedding)
    VALUES (:datasource_name, :schema_name, :object_name, :description, :business_alias,
            :provenance, :confidence, :embedding)
    ON CONFLICT ON CONSTRAINT pk_genql_object_enrichment DO UPDATE
        SET description = EXCLUDED.description,
            business_alias = EXCLUDED.business_alias,
            provenance = EXCLUDED.provenance,
            confidence = EXCLUDED.confidence,
            embedding = EXCLUDED.embedding,
            discovered_at = now()
""")

_SELECT_COLUMN_ENRICHMENTS = text("""
    SELECT datasource_name, schema_name, object_name, column_name, description, business_alias,
           unit, provenance, confidence
    FROM genql.genql_column_enrichment
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_UPSERT_COLUMN_ENRICHMENT = text("""
    INSERT INTO genql.genql_column_enrichment
        (datasource_name, schema_name, object_name, column_name, description, business_alias,
         unit, provenance, confidence)
    VALUES (:datasource_name, :schema_name, :object_name, :column_name, :description,
            :business_alias, :unit, :provenance, :confidence)
    ON CONFLICT ON CONSTRAINT pk_genql_column_enrichment DO UPDATE
        SET description = EXCLUDED.description,
            business_alias = EXCLUDED.business_alias,
            unit = EXCLUDED.unit,
            provenance = EXCLUDED.provenance,
            confidence = EXCLUDED.confidence,
            discovered_at = now()
""")


class PostgresEnrichmentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_OBJECT_ENRICHMENTS, {"datasource_name": datasource_name}
            ).all()
        return [
            ObjectEnrichment.model_validate(
                {**r._mapping, "embedding": tuple(r._mapping["embedding"] or ())  # noqa: SLF001
                    or None}
            )
            for r in rows
        ]

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_COLUMN_ENRICHMENTS, ref.model_dump()).all()
        return [ColumnEnrichment.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_OBJECT_ENRICHMENT, enrichment.model_dump(mode="json"))

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        if not enrichments:
            return 0
        rows = [e.model_dump(mode="json") for e in enrichments]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_COLUMN_ENRICHMENT, rows)
        return len(rows)
```

`embedding` needs a plain Python `list[float]` for `pgvector`'s bind side, not a tuple — `model_dump(mode="json")` already turns the tuple into a list, so the insert path needs no special handling. On the read side, `pgvector`'s SQLAlchemy type returns a `numpy.ndarray` (or `None`); `read_object_enrichments` converts it to `tuple[float, ...]` (or `None`) to match the frozen entity's type, which is what the slightly awkward `tuple(... or ()) or None` expression above does — read it as "empty-or-missing becomes `None`, otherwise a tuple of floats."

Create `genql/repositories/semantic/domain_repository.py`:

```python
"""Domains and their membership. write_domains upserts by (datasource_name,
name) and returns rows with `id` populated via RETURNING, since the caller's
BusinessDomain instances arrive with domain_id=None before the first write."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember

_UPSERT_DOMAIN = text("""
    INSERT INTO genql.genql_domain (datasource_name, name, description, provenance)
    VALUES (:datasource_name, :name, :description, :provenance)
    ON CONFLICT ON CONSTRAINT uq_genql_domain_identity DO UPDATE
        SET description = EXCLUDED.description,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
    RETURNING id
""")

_UPSERT_MEMBER = text("""
    INSERT INTO genql.genql_domain_member
        (domain_id, datasource_name, schema_name, object_name, membership_score)
    VALUES (:domain_id, :datasource_name, :schema_name, :object_name, :membership_score)
    ON CONFLICT ON CONSTRAINT pk_genql_domain_member DO UPDATE
        SET membership_score = EXCLUDED.membership_score
""")


class PostgresDomainRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        written: list[BusinessDomain] = []
        with self._engine.begin() as conn:
            for domain in domains:
                domain_id = conn.execute(
                    _UPSERT_DOMAIN,
                    {
                        "datasource_name": domain.datasource_name,
                        "name": domain.name,
                        "description": domain.description,
                        "provenance": domain.provenance.value,
                    },
                ).scalar_one()
                written.append(BusinessDomain(**{**domain.model_dump(), "domain_id": domain_id}))
        return written

    def write_members(self, members: Sequence[DomainMember]) -> int:
        if not members:
            return 0
        rows = [m.model_dump(mode="json") for m in members]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_MEMBER, rows)
        return len(rows)
```

Create `genql/repositories/semantic/metric_repository.py`:

```python
"""YAML-authored metrics, upserted by (datasource_name, name)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.metric import Metric

_UPSERT_METRIC = text("""
    INSERT INTO genql.genql_metric
        (datasource_name, name, sql_expression, grain, unit, default_filters, provenance)
    VALUES (:datasource_name, :name, :sql_expression, :grain, :unit,
            CAST(:default_filters AS JSONB), :provenance)
    ON CONFLICT ON CONSTRAINT uq_genql_metric_identity DO UPDATE
        SET sql_expression = EXCLUDED.sql_expression,
            grain = EXCLUDED.grain,
            unit = EXCLUDED.unit,
            default_filters = EXCLUDED.default_filters,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
""")


class PostgresMetricRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, metrics: Sequence[Metric]) -> int:
        if not metrics:
            return 0
        rows = [m.model_dump(mode="json") for m in metrics]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_METRIC, rows)
        return len(rows)
```

`default_filters` arrives from `model_dump(mode="json")` as a JSON-serialized-compatible dict; psycopg's default adapter sends a `dict` as a JSON string only when the column type is declared JSON/JSONB at the SQLAlchemy level, which raw `text()` does not know about — hence the explicit `CAST(:default_filters AS JSONB)`, with SQLAlchemy passing the dict through `json.dumps` automatically for parameters used in a JSONB cast under psycopg 3. If this cast fails locally, dump the dict to a JSON string in Python before binding (`json.dumps(m.default_filters)`) instead — either works, the cast is preferred because it keeps the entity model dict-typed.

- [ ] **Step 4: Run to verify all three pass**

Run: `uv run pytest tests/integration/test_enrichment_repository.py tests/integration/test_domain_repository.py tests/integration/test_metric_repository.py -q`
Expected: PASS

- [ ] **Step 5: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/repositories/semantic/enrichment_repository.py genql/repositories/semantic/domain_repository.py genql/repositories/semantic/metric_repository.py tests/integration/test_enrichment_repository.py tests/integration/test_domain_repository.py tests/integration/test_metric_repository.py
git commit -m "feat(semantic-store): add enrichment, domain, and metric repositories"
```

---

### Task 4: LLM gateway infrastructure — OpenRouter and Cohere

**Files:**
- Create: `genql/infrastructure/gateway/__init__.py`, `genql/infrastructure/gateway/openrouter_client.py`, `genql/infrastructure/gateway/cohere_client.py`, `genql/repositories/gateway/__init__.py`, `genql/repositories/gateway/registry.py`, `genql/repositories/gateway/chat_provider_repository.py`, `genql/repositories/gateway/embedding_provider_repository.py`, `genql/repositories/gateway/rerank_provider_repository.py`
- Modify: `pyproject.toml`, `.importlinter`
- Test: `tests/unit/test_gateway_registries.py`, `tests/integration/test_openrouter_chat_provider.py`, `tests/integration/test_openrouter_embedding_provider.py`, `tests/integration/test_rerank_providers.py`

**Interfaces:**
- Consumes: `ChatProvider`, `EmbeddingProvider`, `RerankProvider`, `RerankScore` ports (Task 1); `ChatProviderError`, `EmbeddingProviderError`, `RerankProviderError` (Task 1)
- Produces: `OpenRouterClient(api_key, timeout=30.0).post_json(path, payload) -> dict`; `CohereClient` (same shape); `CHAT_PROVIDERS`, `EMBEDDING_PROVIDERS`, `RERANK_PROVIDERS` registries; `OpenRouterChatProvider(client, model)`, `OpenRouterEmbeddingProvider(client, model)`, `OpenRouterRerankProvider(client, model)`, `CohereRerankProvider(client, model)`

- [ ] **Step 1: Add httpx and update import-linter**

```bash
uv add httpx
```

In `.importlinter`, add `httpx` to both `forbidden_modules` lists (`domain-is-pure` and `no-sql-in-services`), alongside the existing `sqlalchemy`/`psycopg`/`neo4j`/`graphdatascience` entries — a gateway call is a driver call for the purposes of this contract, same reasoning as every other forbidden module there.

- [ ] **Step 2: Write the failing registry test**

Create `tests/unit/test_gateway_registries.py`:

```python
"""The three gateway registries exist and are populated once the package is
imported — mirrors test_graph_registries.py."""

from __future__ import annotations

import genql.repositories.gateway  # noqa: F401 - registration side effect
from genql.repositories.gateway.registry import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    RERANK_PROVIDERS,
)


def test_the_three_registries_are_distinct_and_populated() -> None:
    assert CHAT_PROVIDERS.name == "chat_providers"
    assert EMBEDDING_PROVIDERS.name == "embedding_providers"
    assert RERANK_PROVIDERS.name == "rerank_providers"
    assert "openrouter" in CHAT_PROVIDERS.keys()
    assert "openrouter" in EMBEDDING_PROVIDERS.keys()
    assert {"openrouter", "cohere"} <= set(RERANK_PROVIDERS.keys())
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_gateway_registries.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement the infrastructure clients**

Create `genql/infrastructure/gateway/__init__.py` (empty — this package builds clients, it registers nothing).

Create `genql/infrastructure/gateway/openrouter_client.py`:

```python
"""Thin httpx wrapper for OpenRouter's chat, embeddings, and rerank
endpoints. No `openai` SDK: three JSON-over-HTTPS calls do not justify a
dependency that exists only to wrap them. Built here; called only from
`genql/repositories/gateway/`."""

from __future__ import annotations

from typing import Any

import httpx

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    """A request to OpenRouter failed or returned an unexpected shape."""


class OpenRouterClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request to {path} failed: {exc}") from exc
        result: dict[str, Any] = response.json()
        return result
```

Create `genql/infrastructure/gateway/cohere_client.py`:

```python
"""Thin httpx wrapper for Cohere's own rerank endpoint — the fallback
RerankProviderRegistry keeps registered from day one, not as a future
placeholder, in case OpenRouter ever stops carrying rerank-4-pro."""

from __future__ import annotations

from typing import Any

import httpx

_BASE_URL = "https://api.cohere.com/v1"


class CohereError(Exception):
    """A request to Cohere failed or returned an unexpected shape."""


class CohereClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CohereError(f"Cohere request to {path} failed: {exc}") from exc
        result: dict[str, Any] = response.json()
        return result
```

- [ ] **Step 5: Implement the registry and the provider repositories**

Create `genql/repositories/gateway/registry.py`:

```python
from __future__ import annotations

from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.registries.registry import Registry

CHAT_PROVIDERS: Registry[ChatProvider] = Registry("chat_providers")
EMBEDDING_PROVIDERS: Registry[EmbeddingProvider] = Registry("embedding_providers")
RERANK_PROVIDERS: Registry[RerankProvider] = Registry("rerank_providers")
```

Create `genql/repositories/gateway/chat_provider_repository.py`:

```python
"""OpenRouter chat completions, requesting a JSON-schema response shaped by
the caller's Pydantic model — a malformed reply becomes a ValidationError
here, not a silent mis-parse three layers up."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from genql.domain.errors import ChatProviderError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import CHAT_PROVIDERS

T = TypeVar("T", bound=BaseModel)


@CHAT_PROVIDERS.register("openrouter")
class OpenRouterChatProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                },
            },
        }
        try:
            body = self._client.post_json("/chat/completions", payload)
            content = body["choices"][0]["message"]["content"]
        except (OpenRouterError, KeyError, IndexError) as exc:
            raise ChatProviderError(f"OpenRouter chat completion failed: {exc}") from exc
        try:
            return response_schema.model_validate_json(content)
        except ValidationError as exc:
            raise ChatProviderError(
                f"OpenRouter response did not match {response_schema.__name__}: {exc}"
            ) from exc
```

Create `genql/repositories/gateway/embedding_provider_repository.py`:

```python
"""One request for the whole batch; vectors come back in input order."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import EmbeddingProviderError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import EMBEDDING_PROVIDERS


@EMBEDDING_PROVIDERS.register("openrouter")
class OpenRouterEmbeddingProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        try:
            body = self._client.post_json(
                "/embeddings", {"model": self._model, "input": list(texts)}
            )
            return [tuple(row["embedding"]) for row in body["data"]]
        except (OpenRouterError, KeyError) as exc:
            raise EmbeddingProviderError(f"OpenRouter embedding request failed: {exc}") from exc
```

Create `genql/repositories/gateway/rerank_provider_repository.py`:

```python
"""OpenRouterRerankProvider and CohereRerankProvider — both registered from
day one, per the parent spec's stated fallback."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import RerankProviderError
from genql.domain.ports.rerank_provider import RerankScore
from genql.infrastructure.gateway.cohere_client import CohereClient, CohereError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import RERANK_PROVIDERS


@RERANK_PROVIDERS.register("openrouter")
class OpenRouterRerankProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        try:
            body = self._client.post_json(
                "/rerank",
                {
                    "model": self._model, "query": query, "documents": list(documents),
                    "top_n": top_n,
                },
            )
            return [
                RerankScore(index=r["index"], score=r["relevance_score"]) for r in body["results"]
            ]
        except (OpenRouterError, KeyError) as exc:
            raise RerankProviderError(f"OpenRouter rerank request failed: {exc}") from exc


@RERANK_PROVIDERS.register("cohere")
class CohereRerankProvider:
    def __init__(self, client: CohereClient, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        try:
            body = self._client.post_json(
                "/rerank",
                {
                    "model": self._model, "query": query, "documents": list(documents),
                    "top_n": top_n,
                },
            )
            return [
                RerankScore(index=r["index"], score=r["relevance_score"]) for r in body["results"]
            ]
        except (CohereError, KeyError) as exc:
            raise RerankProviderError(f"Cohere rerank request failed: {exc}") from exc
```

Create `genql/repositories/gateway/__init__.py`:

```python
"""Registers every LLM-gateway implementation with its registry.

This is the one place that imports the provider modules purely for their
`@CHAT_PROVIDERS.register(...)` / `@EMBEDDING_PROVIDERS.register(...)` /
`@RERANK_PROVIDERS.register(...)` decorator side effect.
"""

from __future__ import annotations

from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.repositories.gateway.embedding_provider_repository import OpenRouterEmbeddingProvider
from genql.repositories.gateway.rerank_provider_repository import (
    CohereRerankProvider,
    OpenRouterRerankProvider,
)

__all__ = [
    "OpenRouterChatProvider", "OpenRouterEmbeddingProvider", "OpenRouterRerankProvider",
    "CohereRerankProvider",
]
```

- [ ] **Step 6: Run to verify the registry test passes**

Run: `uv run pytest tests/unit/test_gateway_registries.py -q`
Expected: PASS

- [ ] **Step 7: Write the gated real-provider integration tests**

Create `tests/integration/test_openrouter_chat_provider.py`:

```python
"""The only tests in this suite that cost money or need network access.
Skipped cleanly, with a printed reason, when no key is configured — that
skip is not a task failure."""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


class _Greeting(BaseModel):
    message: str


def test_complete_returns_a_validated_model() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterChatProvider(client=client, model="anthropic/claude-sonnet-5")

    result = provider.complete(
        "Reply with a JSON object with one field, `message`, containing the word hello.",
        _Greeting,
    )

    assert result.message
```

Create `tests/integration/test_openrouter_embedding_provider.py`:

```python
from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.embedding_provider_repository import OpenRouterEmbeddingProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


def test_embed_returns_one_vector_per_text() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterEmbeddingProvider(client=client, model="openai/text-embedding-3-small")

    vectors = provider.embed(["point-of-sale line items", "customer demographics"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1536
```

Create `tests/integration/test_rerank_providers.py`:

```python
from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.cohere_client import CohereClient
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.rerank_provider_repository import (
    CohereRerankProvider,
    OpenRouterRerankProvider,
)

_DOCS = ["a fact about apples", "a fact about sales tax", "a fact about oranges"]


@pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)
def test_openrouter_rerank_orders_the_relevant_document_first() -> None:
    client = OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"])
    provider = OpenRouterRerankProvider(client=client, model="cohere/rerank-4-pro")

    scores = provider.rerank("sales tax rate", _DOCS, top_n=3)

    assert scores[0].index == 1


@pytest.mark.skipif(
    not os.environ.get("GENQL_COHERE_API_KEY"), reason="GENQL_COHERE_API_KEY not set"
)
def test_cohere_rerank_orders_the_relevant_document_first() -> None:
    client = CohereClient(api_key=os.environ["GENQL_COHERE_API_KEY"])
    provider = CohereRerankProvider(client=client, model="rerank-v3.5")

    scores = provider.rerank("sales tax rate", _DOCS, top_n=3)

    assert scores[0].index == 1
```

- [ ] **Step 8: Run the gated tests (skip is expected without keys)**

Run: `uv run pytest tests/integration/test_openrouter_chat_provider.py tests/integration/test_openrouter_embedding_provider.py tests/integration/test_rerank_providers.py -q`
Expected: `4 skipped` in this environment (no `GENQL_OPENROUTER_API_KEY` or `GENQL_COHERE_API_KEY` set); `4 passed` wherever both are set

- [ ] **Step 9: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/infrastructure/gateway genql/repositories/gateway pyproject.toml uv.lock .importlinter tests/unit/test_gateway_registries.py tests/integration/test_openrouter_chat_provider.py tests/integration/test_openrouter_embedding_provider.py tests/integration/test_rerank_providers.py
git commit -m "feat(gateway): add OpenRouter and Cohere chat, embedding, and rerank providers"
```

---

### Task 5: Object profiling service and discovery step

**Files:**
- Create: `genql/services/semantic/__init__.py`, `genql/services/semantic/object_profiling_service.py`, `genql/discovery/steps/object_profiling_step.py`
- Test: `tests/unit/test_object_profiling_service.py`, `tests/unit/test_object_profiling_step.py`

**Interfaces:**
- Consumes: `SemanticCatalogReader` (extended, Task 2), `ChatProvider`, `EmbeddingProvider`, `EnrichmentWriter` ports (Task 1); `ObjectEnrichment`, `ColumnEnrichment` entities; `DiscoveryContext`, `StepResult` (existing `discovery_step` port)
- Produces: `ObjectProfilingReport(objects_profiled: int, columns_profiled: int)`; `ObjectProfilingService(reader, chat, embedder, writer).profile(ref: SchemaRef, sample_limit: int) -> ObjectProfilingReport`; `ObjectProfilingStep` registered as `"object_profiling"`

- [ ] **Step 1: Write the failing service test**

Create `tests/unit/test_object_profiling_service.py`:

```python
"""One grounded LLM call per object, carrying that object's columns,
foreign keys, and sample values — not one call per object plus one per
column. All four dependencies are ports, so no database, no LLM, and no
network is needed here."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.column import Column
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.object_profiling_service import ObjectProfilingService

T = TypeVar("T", bound=BaseModel)

REF = SchemaRef(datasource_name="local", schema_name="shop")
OBJECT = DatabaseObject(
    datasource_name="local", schema_name="shop", object_name="orders", object_type=ObjectType.TABLE
)
COLUMN = Column(
    datasource_name="local", schema_name="shop", object_name="orders", column_name="status",
    ordinal=1, data_type="text", is_nullable=False,
)


class FakeReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return [OBJECT]

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        return [COLUMN]

    def read_column_profiles(self, ref: SchemaRef) -> Sequence[ColumnProfile]:
        return [
            ColumnProfile(
                datasource_name="local", schema_name="shop", object_name="orders",
                column_name="status", sample_values=("OPEN", "SHIPPED"),
            )
        ]


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[T]) -> T:
        # Genuinely generic — validated against whatever schema the caller
        # passes, rather than hardcoding a return type the Protocol's
        # generic `type[T] -> T` signature couldn't otherwise be satisfied by.
        return response_schema.model_validate(
            {
                "description": "Customer orders.",
                "business_alias": "orders",
                "columns": [
                    {"column_name": "status", "description": "Order lifecycle state.", "unit": None}
                ],
            }
        )


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[ObjectEnrichment] = []
        self.columns: list[ColumnEnrichment] = []

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        self.objects.append(enrichment)

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        self.columns.extend(enrichments)
        return len(enrichments)


def test_profile_writes_one_object_enrichment_with_its_embedding_and_its_columns() -> None:
    writer = FakeWriter()
    service = ObjectProfilingService(
        FakeReader(), FakeChatProvider(), FakeEmbeddingProvider(), writer
    )

    report = service.profile(REF, sample_limit=5)

    assert report.objects_profiled == 1
    assert report.columns_profiled == 1
    assert writer.objects[0].description == "Customer orders."
    assert writer.objects[0].embedding == (0.1, 0.2)
    assert writer.columns[0].description == "Order lifecycle state."
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_object_profiling_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `genql/services/semantic/__init__.py` (empty).

Create `genql/services/semantic/object_profiling_service.py`:

```python
"""Grounds one schema's objects and columns in an LLM-generated description,
one call per object — the grounding context (columns, types, foreign keys,
sample values) is shared across that object's whole column list, so this
stays one call, not one call per object plus one per column."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.column import Column
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.errors import ChatProviderError, EmbeddingProviderError, EnrichmentError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.schema_ref import SchemaRef


class _ColumnProfileResponse(BaseModel):
    column_name: str
    description: str
    business_alias: str | None = None
    unit: str | None = None


class _ObjectProfileResponse(BaseModel):
    description: str
    business_alias: str | None = None
    columns: list[_ColumnProfileResponse]


class ObjectProfilingReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects_profiled: int
    columns_profiled: int


class ObjectProfilingService:
    def __init__(
        self,
        reader: SemanticCatalogReader,
        chat: ChatProvider,
        embedder: EmbeddingProvider,
        writer: EnrichmentWriter,
    ) -> None:
        self._reader = reader
        self._chat = chat
        self._embedder = embedder
        self._writer = writer

    def profile(self, ref: SchemaRef, sample_limit: int) -> ObjectProfilingReport:
        objects = self._reader.read_objects(ref)
        constraints = self._reader.read_constraints(ref)
        columns = self._reader.read_columns(ref)
        profiles = {p.column_name: p for p in self._reader.read_column_profiles(ref)}

        objects_profiled = 0
        columns_profiled = 0
        for obj in objects:
            object_columns = [c for c in columns if c.object_name == obj.object_name]
            object_constraints = [c for c in constraints if c.object_name == obj.object_name]
            prompt = self._build_prompt(obj, object_columns, object_constraints, profiles, sample_limit)
            try:
                response = self._chat.complete(prompt, _ObjectProfileResponse)
                embedding = self._embedder.embed([response.description])[0]
            except (ChatProviderError, EmbeddingProviderError) as exc:
                raise EnrichmentError(f"failed to profile {obj.qualified_name}: {exc}") from exc

            self._writer.write_object_enrichment(
                ObjectEnrichment(
                    datasource_name=obj.datasource_name, schema_name=obj.schema_name,
                    object_name=obj.object_name, description=response.description,
                    business_alias=response.business_alias, embedding=embedding,
                )
            )
            column_enrichments = [
                ColumnEnrichment(
                    datasource_name=obj.datasource_name, schema_name=obj.schema_name,
                    object_name=obj.object_name, column_name=col.column_name,
                    description=col.description, business_alias=col.business_alias, unit=col.unit,
                )
                for col in response.columns
            ]
            self._writer.write_column_enrichments(column_enrichments)
            objects_profiled += 1
            columns_profiled += len(column_enrichments)

        return ObjectProfilingReport(objects_profiled=objects_profiled, columns_profiled=columns_profiled)

    def _build_prompt(
        self,
        obj: DatabaseObject,
        object_columns: Sequence[Column],
        object_constraints: Sequence[Constraint],
        profiles: Mapping[str, ColumnProfile],
        sample_limit: int,
    ) -> str:
        column_lines = []
        for col in object_columns:
            profile = profiles.get(col.column_name)
            samples = list(profile.sample_values[:sample_limit]) if profile else []
            column_lines.append(f"- {col.column_name} ({col.data_type}); samples: {samples}")
        fk_lines = [
            f"- {', '.join(c.column_names)} -> {c.referenced_object_name}"
            for c in object_constraints
            if c.constraint_type == ConstraintType.FOREIGN_KEY
        ]
        return (
            f"Object: {obj.object_name} ({obj.object_type.value})\n"
            "Columns:\n" + "\n".join(column_lines) + "\n"
            "Foreign keys:\n" + "\n".join(fk_lines) + "\n"
            "Write a one-sentence plain-English description of this object, a short business "
            "alias, and for each column a one-sentence description with an optional unit. "
            "Ground every claim in the column names, types, and sample values given above — do "
            "not invent business meaning the data does not support."
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_object_profiling_service.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing step test**

Create `tests/unit/test_object_profiling_step.py`:

```python
from __future__ import annotations

from genql.discovery.steps.object_profiling_step import ObjectProfilingStep
from genql.domain.ports.discovery_step import DiscoveryContext
from genql.services.semantic.object_profiling_service import ObjectProfilingReport


class FakeService:
    def profile(self, ref: object, sample_limit: int) -> ObjectProfilingReport:
        return ObjectProfilingReport(objects_profiled=2, columns_profiled=9)


def test_run_reports_objects_and_columns_profiled() -> None:
    step = ObjectProfilingStep(FakeService())
    ctx = DiscoveryContext(datasource_name="local", schema_name="shop", sample_limit=5)

    result = step.run(ctx)

    assert result.succeeded
    assert result.records_written == 2
    assert "9 columns" in result.message
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_object_profiling_step.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement the step**

Create `genql/discovery/steps/object_profiling_step.py`:

```python
"""Sequenced after graph_projection: it needs nothing from the graph, but
running last among the per-schema steps means a profiling failure never
blocks Phase 3's steps from completing for that schema. Text embedding is
folded into ObjectProfilingService itself rather than a separate step —
splitting it out would mean re-reading a just-written description from
Postgres a moment after writing it, for no benefit."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.semantic.object_profiling_service import ObjectProfilingService


@DISCOVERY_STEPS.register("object_profiling")
class ObjectProfilingStep:
    name: ClassVar[str] = "object_profiling"

    def __init__(self, service: ObjectProfilingService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            report = self._service.profile(ctx.ref, ctx.sample_limit)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.objects_profiled,
            message=f"{report.objects_profiled} objects profiled, {report.columns_profiled} columns",
        )
```

Note for the implementing engineer, same shape as Phase 3's Task 9 ordering note: `DISCOVERY_STEPS.keys()` sorts alphabetically, and `"object_profiling"` sorts after `"graph_projection"` (`g` < `o`), so no explicit ordering override is needed here — alphabetical order already produces `catalog_scan`, `data_profiling`, `graph_projection`, `object_profiling`, which happens to be exactly the intended order.

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_object_profiling_step.py -q`
Expected: PASS

- [ ] **Step 9: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/services/semantic/__init__.py genql/services/semantic/object_profiling_service.py genql/discovery/steps/object_profiling_step.py tests/unit/test_object_profiling_service.py tests/unit/test_object_profiling_step.py
git commit -m "feat(semantic): add LLM object profiling service and discovery step"
```

---

### Task 6: Fused clustering and the cluster reader

**Files:**
- Create: `genql/repositories/graph/fused_clustering_algorithm_repository.py`, `genql/repositories/graph/cluster_reader_repository.py`
- Modify: `genql/repositories/graph/__init__.py`, `pyproject.toml`
- Test: `tests/unit/test_fused_clustering_k_selection.py`, `tests/integration/test_fused_clustering_algorithm_repository.py`, `tests/integration/test_cluster_reader_repository.py`

**Interfaces:**
- Consumes: `ClusteringAlgorithm` port (Phase 3), `ClusterReader` port (Task 1), `EnrichmentReader` port (Task 1), `CLUSTERING_ALGORITHMS` registry (Phase 3, `repositories/graph/registry.py`)
- Produces: `FusedClusteringAlgorithm(driver, enrichment_reader, k_min=2, k_max=20)` registered under `CLUSTERING_ALGORITHMS` as `"fused"`; `Neo4jClusterReader(driver)` implementing `ClusterReader`; module-level `_l2_normalize(vector) -> np.ndarray` and `_choose_k(vectors, k_min, k_max) -> tuple[int, np.ndarray]`

Runs in plain Python against vectors fetched into memory, not through GDS's own `kmeans` procedure — GDS has no silhouette-driven `k` search, and object counts at TPC-DS scale (dozens, not millions) make loading vectors into memory the cheap and simple path, the same reasoning `WeightedShortestPathJoinPathMiner`'s `_candidate_pairs` helper (Phase 3) already established for keeping graph-shaped logic testable as a plain function.

- [ ] **Step 1: Add numpy and scikit-learn**

```bash
uv add numpy scikit-learn
```

- [ ] **Step 2: Write the failing k-selection test**

Create `tests/unit/test_fused_clustering_k_selection.py`:

```python
"""_choose_k and _l2_normalize are plain functions — no Neo4j, no Postgres."""

from __future__ import annotations

import numpy as np

from genql.repositories.graph.fused_clustering_algorithm_repository import (
    _choose_k,
    _l2_normalize,
)


def test_l2_normalize_produces_unit_length_vectors() -> None:
    vector = np.array([3.0, 4.0])

    normalized = _l2_normalize(vector)

    assert np.isclose(np.linalg.norm(normalized), 1.0)


def test_l2_normalize_leaves_a_zero_vector_untouched() -> None:
    assert np.array_equal(_l2_normalize(np.zeros(3)), np.zeros(3))


def test_choose_k_finds_two_well_separated_clusters() -> None:
    cluster_a = np.random.default_rng(0).normal(loc=0.0, scale=0.1, size=(10, 4))
    cluster_b = np.random.default_rng(1).normal(loc=10.0, scale=0.1, size=(10, 4))
    vectors = np.concatenate([cluster_a, cluster_b])

    k, labels = _choose_k(vectors, k_min=2, k_max=5)

    assert k == 2
    assert len(set(labels[:10])) == 1
    assert len(set(labels[10:])) == 1
    assert labels[0] != labels[10]


def test_choose_k_falls_back_to_one_cluster_when_too_few_objects() -> None:
    vectors = np.array([[1.0, 2.0], [3.0, 4.0]])

    k, labels = _choose_k(vectors, k_min=2, k_max=20)

    assert k == 1
    assert set(labels) == {0}
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_fused_clustering_k_selection.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement fused clustering**

Create `genql/repositories/graph/fused_clustering_algorithm_repository.py`:

```python
"""FastRP structural embeddings (Neo4j, written by Phase 3's FastRpNodeEmbedder)
fused with LLM-description text embeddings (Postgres, written by
ObjectProfilingService) into business-domain clusters. Reads/writes plain
node properties via the Neo4j driver directly — not through
GraphCatalogSession's GDS graph catalog, which exists for GDS algorithms,
not for this Python-side k-means."""

from __future__ import annotations

import numpy as np
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from genql.domain.errors import DomainNamingError
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS

_FUSED_PROPERTY = "domain_cluster"
_READ_EMBEDDINGS = (
    "MATCH (o:Object {datasource_name: $datasource_name}) WHERE o.embedding IS NOT NULL "
    "RETURN o.qualified_name AS qualified_name, o.embedding AS embedding"
)
_WRITE_CLUSTERS = (
    "UNWIND $rows AS row MATCH (o:Object {qualified_name: row.qualified_name}) "
    f"SET o.{_FUSED_PROPERTY} = row.cluster_id"
)


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector if norm == 0 else vector / norm


def _choose_k(vectors: np.ndarray, k_min: int, k_max: int) -> tuple[int, np.ndarray]:
    n_samples = vectors.shape[0]
    upper = min(k_max, n_samples - 1)
    if upper < k_min:
        return 1, np.zeros(n_samples, dtype=int)
    best_k, best_score, best_labels = k_min, -1.0, np.zeros(n_samples, dtype=int)
    for k in range(k_min, upper + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(vectors)
        score = silhouette_score(vectors, labels)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels
    return best_k, best_labels


@CLUSTERING_ALGORITHMS.register("fused")
class FusedClusteringAlgorithm:
    def __init__(
        self, driver: Driver, enrichment_reader: EnrichmentReader, k_min: int = 2, k_max: int = 20
    ) -> None:
        self._driver = driver
        self._enrichment_reader = enrichment_reader
        self._k_min = k_min
        self._k_max = k_max

    def detect(self, datasource_name: str) -> int:
        try:
            with self._driver.session() as session:
                structural_rows = list(
                    session.run(_READ_EMBEDDINGS, datasource_name=datasource_name)
                )
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to read structural embeddings for {datasource_name!r}: {exc}"
            ) from exc

        structural = {
            r["qualified_name"]: np.array(r["embedding"], dtype=float) for r in structural_rows
        }
        textual = {
            e.qualified_name: np.array(e.embedding, dtype=float)
            for e in self._enrichment_reader.read_object_enrichments(datasource_name)
            if e.embedding is not None
        }
        shared = sorted(set(structural) & set(textual))
        if not shared:
            raise DomainNamingError(
                f"no object has both a structural and a text embedding for {datasource_name!r}; "
                "run graph analyze and discover (object_profiling) first"
            )

        fused = np.stack(
            [
                np.concatenate([_l2_normalize(structural[qn]), _l2_normalize(textual[qn])])
                for qn in shared
            ]
        )
        k, labels = _choose_k(fused, self._k_min, self._k_max)

        rows = [
            {"qualified_name": qn, "cluster_id": int(label)}
            for qn, label in zip(shared, labels, strict=True)
        ]
        try:
            with self._driver.session() as session:
                session.run(_WRITE_CLUSTERS, rows=rows)
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to write fused clusters for {datasource_name!r}: {exc}"
            ) from exc
        return k
```

Create `genql/repositories/graph/cluster_reader_repository.py`:

```python
"""Reads back whichever clustering algorithm's node-property assignment —
Leiden's community_id or fused clustering's domain_cluster — grouped by
cluster id. Not registry-based: it has one implementation and is wired
directly, the same treatment Neo4jGraphWriterRepository already gets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from genql.domain.errors import DomainNamingError

_READ_CLUSTERS = (
    "MATCH (o:Object {datasource_name: $datasource_name}) "
    "WHERE properties(o)[$property_name] IS NOT NULL "
    "RETURN o.qualified_name AS qualified_name, properties(o)[$property_name] AS cluster_id"
)


class Neo4jClusterReader:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        try:
            with self._driver.session() as session:
                rows = list(
                    session.run(
                        _READ_CLUSTERS, datasource_name=datasource_name, property_name=property_name
                    )
                )
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to read {property_name!r} clusters for {datasource_name!r}: {exc}"
            ) from exc
        clusters: dict[int, list[str]] = defaultdict(list)
        for row in rows:
            clusters[int(row["cluster_id"])].append(row["qualified_name"])
        return clusters
```

In `genql/repositories/graph/__init__.py`, add `FusedClusteringAlgorithm` to the imports and `__all__` (registration side effect — `Neo4jClusterReader` is not registry-based and does not need to be imported here).

- [ ] **Step 5: Run to verify the k-selection test passes**

Run: `uv run pytest tests/unit/test_fused_clustering_k_selection.py -q`
Expected: PASS

- [ ] **Step 6: Write the failing integration tests**

Create `tests/integration/test_fused_clustering_algorithm_repository.py`:

```python
"""Seeds two well-separated fake FastRP embeddings directly onto Neo4j nodes
and two matching text embeddings through a fake EnrichmentReader, then
asserts fused clustering finds two clusters and writes domain_cluster."""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.repositories.graph.fused_clustering_algorithm_repository import (
    FusedClusteringAlgorithm,
)


class FakeEnrichmentReader:
    def __init__(self, enrichments: Sequence[ObjectEnrichment]) -> None:
        self._enrichments = enrichments

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return self._enrichments

    def read_column_enrichments(self, ref: object) -> Sequence[object]:
        return []


def test_detect_finds_two_clusters_and_writes_domain_cluster(neo4j_uri: str) -> None:
    from neo4j import GraphDatabase

    driver: Driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", "genqlgenql"))
    ds = "fused_test"
    with driver.session() as session:
        session.run(
            "MERGE (a:Object {qualified_name: $qn, datasource_name: $ds}) "
            "SET a.embedding = $e",
            qn=f"{ds}.shop.a", ds=ds, e=[0.0] * 8,
        )
        session.run(
            "MERGE (b:Object {qualified_name: $qn, datasource_name: $ds}) "
            "SET b.embedding = $e",
            qn=f"{ds}.shop.b", ds=ds, e=[10.0] * 8,
        )
    enrichments = [
        ObjectEnrichment(
            datasource_name=ds, schema_name="shop", object_name="a", description="x",
            embedding=tuple([0.0] * 8),
        ),
        ObjectEnrichment(
            datasource_name=ds, schema_name="shop", object_name="b", description="y",
            embedding=tuple([10.0] * 8),
        ),
    ]
    algorithm = FusedClusteringAlgorithm(driver, FakeEnrichmentReader(enrichments), k_min=2, k_max=2)

    k = algorithm.detect(ds)

    assert k == 2
    with driver.session() as session:
        clusters = {
            r["qn"]: r["c"]
            for r in session.run(
                "MATCH (o:Object {datasource_name: $ds}) RETURN o.qualified_name AS qn, "
                "o.domain_cluster AS c",
                ds=ds,
            )
        }
    assert clusters[f"{ds}.shop.a"] != clusters[f"{ds}.shop.b"]
    driver.close()
```

Create `tests/integration/test_cluster_reader_repository.py`:

```python
from __future__ import annotations

from neo4j import Driver, GraphDatabase

from genql.repositories.graph.cluster_reader_repository import Neo4jClusterReader


def test_read_clusters_groups_qualified_names_by_cluster_id(neo4j_uri: str) -> None:
    driver: Driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", "genqlgenql"))
    ds = "cluster_reader_test"
    with driver.session() as session:
        session.run(
            "MERGE (a:Object {qualified_name: $qn, datasource_name: $ds, domain_cluster: 0})",
            qn=f"{ds}.shop.a", ds=ds,
        )
        session.run(
            "MERGE (b:Object {qualified_name: $qn, datasource_name: $ds, domain_cluster: 0})",
            qn=f"{ds}.shop.b", ds=ds,
        )

    clusters = Neo4jClusterReader(driver).read_clusters(ds, "domain_cluster")

    assert set(clusters[0]) == {f"{ds}.shop.a", f"{ds}.shop.b"}
    driver.close()
```

- [ ] **Step 7: Run to verify both pass (VM, with Neo4j provisioned per Global Constraints)**

Run: `uv run pytest tests/integration/test_fused_clustering_algorithm_repository.py tests/integration/test_cluster_reader_repository.py -q`
Expected: PASS

- [ ] **Step 8: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/repositories/graph/fused_clustering_algorithm_repository.py genql/repositories/graph/cluster_reader_repository.py genql/repositories/graph/__init__.py pyproject.toml uv.lock tests/unit/test_fused_clustering_k_selection.py tests/integration/test_fused_clustering_algorithm_repository.py tests/integration/test_cluster_reader_repository.py
git commit -m "feat(graph): add fused clustering and the cluster reader"
```

---

### Task 7: Domain naming service and `genql graph domains`

**Files:**
- Create: `genql/repositories/semantic/domain_namer_repository.py`, `genql/services/semantic/domain_discovery_service.py`
- Modify: `genql/cli/commands/graph.py`
- Test: `tests/unit/test_llm_domain_namer.py`, `tests/unit/test_domain_discovery_service.py`, `tests/integration/test_cli_graph_domains.py`

**Interfaces:**
- Consumes: `ChatProvider` (Task 4), `ClusteringAlgorithm` (Phase 3 port, Task 6's `fused` registration), `ClusterReader` (Task 6), `EnrichmentReader` (Task 3), `DomainWriter` (Task 3), `BusinessDomain`, `DomainMember`, `ObjectEnrichment`
- Produces: `LlmDomainNamer(chat)` implementing `DomainNamer` — returns one `BusinessDomain` per entry of its `clusters` argument, **in the same order `clusters` iterates**, which is the contract `DomainDiscoveryService` relies on to re-associate a written domain's new id with the cluster it came from; `DomainDiscoveryReport(domains: int, members: int)`; `DomainDiscoveryService(clustering, cluster_reader, enrichment_reader, namer, domain_writer).discover(datasource_name: str) -> DomainDiscoveryReport`; CLI command `genql graph domains --datasource NAME`

- [ ] **Step 1: Write the failing namer test**

Create `tests/unit/test_llm_domain_namer.py`:

```python
"""LlmDomainNamer consumes the ChatProvider port, so it is unit-testable
with a fake — unlike OpenRouterChatProvider itself, which IS that port's
implementation and is integration-tested against the real API instead."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.repositories.semantic.domain_namer_repository import LlmDomainNamer

T = TypeVar("T", bound=BaseModel)

MEMBER = ObjectEnrichment(
    datasource_name="local", schema_name="shop", object_name="orders",
    description="Customer orders.",
)


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[T]) -> T:
        return response_schema.model_validate({"name": "sales", "description": "Sales activity."})


def test_name_returns_one_domain_per_cluster_in_order() -> None:
    namer = LlmDomainNamer(FakeChatProvider())
    clusters: Mapping[int, Sequence[ObjectEnrichment]] = {0: [MEMBER], 1: [MEMBER]}

    domains = namer.name("local", clusters)

    assert len(domains) == 2
    assert domains[0].name == "sales"
    assert domains[0].datasource_name == "local"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_llm_domain_namer.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the namer**

Create `genql/repositories/semantic/domain_namer_repository.py`:

```python
"""One LLM call per cluster, naming it from its member objects' descriptions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.errors import ChatProviderError, DomainNamingError
from genql.domain.ports.chat_provider import ChatProvider


class _DomainNameResponse(BaseModel):
    name: str
    description: str


class LlmDomainNamer:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        domains: list[BusinessDomain] = []
        for cluster_id, members in clusters.items():
            member_lines = "\n".join(f"- {m.object_name}: {m.description}" for m in members)
            prompt = (
                "These database objects were clustered together by structural and semantic "
                "similarity:\n" + member_lines + "\n"
                "Give this cluster a two-to-three word business domain name and a one-sentence "
                "description grounded in what the member objects above actually are."
            )
            try:
                response = self._chat.complete(prompt, _DomainNameResponse)
            except ChatProviderError as exc:
                raise DomainNamingError(
                    f"failed to name cluster {cluster_id} for {datasource_name!r}: {exc}"
                ) from exc
            domains.append(
                BusinessDomain(
                    datasource_name=datasource_name, name=response.name,
                    description=response.description,
                )
            )
        return domains
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_llm_domain_namer.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing service test**

Create `tests/unit/test_domain_discovery_service.py`:

```python
"""DomainDiscoveryService: fused-cluster, read the assignment back, name
each cluster, write domains and their members. All five dependencies are
ports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.services.semantic.domain_discovery_service import DomainDiscoveryService

ENRICHMENT_A = ObjectEnrichment(
    datasource_name="local", schema_name="shop", object_name="a", description="x",
)
ENRICHMENT_B = ObjectEnrichment(
    datasource_name="local", schema_name="shop", object_name="b", description="y",
)


class FakeClustering:
    def detect(self, datasource_name: str) -> int:
        return 2


class FakeClusterReader:
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        return {0: ["local.shop.a"], 1: ["local.shop.b"]}


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return [ENRICHMENT_A, ENRICHMENT_B]

    def read_column_enrichments(self, ref: object) -> Sequence[object]:
        return []


class FakeNamer:
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        return [
            BusinessDomain(datasource_name=datasource_name, name=f"domain_{cid}", description="d")
            for cid in clusters
        ]


class FakeDomainWriter:
    def __init__(self) -> None:
        self.members: list[DomainMember] = []

    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        return [
            BusinessDomain(**{**d.model_dump(), "domain_id": i}) for i, d in enumerate(domains, 1)
        ]

    def write_members(self, members: Sequence[DomainMember]) -> int:
        self.members.extend(members)
        return len(members)


def test_discover_names_each_cluster_and_writes_its_members() -> None:
    writer = FakeDomainWriter()
    service = DomainDiscoveryService(
        FakeClustering(), FakeClusterReader(), FakeEnrichmentReader(), FakeNamer(), writer
    )

    report = service.discover("local")

    assert report.domains == 2
    assert report.members == 2
    member_by_object = {m.object_name: m.domain_id for m in writer.members}
    assert member_by_object["a"] == 1
    assert member_by_object["b"] == 2
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_domain_discovery_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement the service**

Create `genql/services/semantic/domain_discovery_service.py`:

```python
"""Orchestrates fused clustering, reading the assignment back out of Neo4j,
naming each cluster, and persisting domains and their members. `clustering`
is resolved to the `fused` ClusteringAlgorithm at the composition root — this
service does not know or care which algorithm it is, same rule
GraphAnalysisService already follows for `leiden`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.domain_member import DomainMember
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.cluster_reader import ClusterReader
from genql.domain.ports.domain_namer import DomainNamer
from genql.domain.ports.domain_writer import DomainWriter
from genql.domain.ports.enrichment_reader import EnrichmentReader

_FUSED_PROPERTY = "domain_cluster"


class DomainDiscoveryReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    domains: int
    members: int


class DomainDiscoveryService:
    def __init__(
        self,
        clustering: ClusteringAlgorithm,
        cluster_reader: ClusterReader,
        enrichment_reader: EnrichmentReader,
        namer: DomainNamer,
        domain_writer: DomainWriter,
    ) -> None:
        self._clustering = clustering
        self._cluster_reader = cluster_reader
        self._enrichment_reader = enrichment_reader
        self._namer = namer
        self._domain_writer = domain_writer

    def discover(self, datasource_name: str) -> DomainDiscoveryReport:
        self._clustering.detect(datasource_name)
        clusters_by_id = self._cluster_reader.read_clusters(datasource_name, _FUSED_PROPERTY)
        enrichment_by_qn = {
            e.qualified_name: e
            for e in self._enrichment_reader.read_object_enrichments(datasource_name)
        }

        cluster_ids = sorted(clusters_by_id)
        ordered_clusters = {
            cid: [
                enrichment_by_qn[qn] for qn in clusters_by_id[cid] if qn in enrichment_by_qn
            ]
            for cid in cluster_ids
        }
        named = self._namer.name(datasource_name, ordered_clusters)

        written = self._domain_writer.write_domains(named)
        members = [
            DomainMember(
                domain_id=domain.domain_id,  # type: ignore[arg-type]  # populated by write_domains
                datasource_name=datasource_name,
                schema_name=qn.split(".")[1],
                object_name=qn.split(".")[2],
            )
            for cluster_id, domain in zip(cluster_ids, written, strict=True)
            for qn in clusters_by_id[cluster_id]
        ]
        written_members = self._domain_writer.write_members(members)
        return DomainDiscoveryReport(domains=len(written), members=written_members)
```

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_domain_discovery_service.py -q`
Expected: PASS

- [ ] **Step 9: Write the failing CLI integration test**

Create `tests/integration/test_cli_graph_domains.py`:

```python
"""Needs graph analyze (structural embeddings) and discover with
object_profiling (text embeddings) to have already run — see Task 12 for the
full ordered chain. This test only checks the command exists and reports a
sane shape; it is expected to fail with a clear domain error, not a crash,
if run in isolation without those prerequisites."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_graph_domains_command_exists() -> None:
    result = runner.invoke(app, ["graph", "domains", "--help"])

    assert result.exit_code == 0
    assert "datasource" in result.stdout.lower()
```

- [ ] **Step 10: Run to verify it fails**

Run: `uv run pytest tests/integration/test_cli_graph_domains.py -q`
Expected: FAIL — no `domains` sub-command yet

- [ ] **Step 11: Implement the CLI command**

In `genql/cli/commands/graph.py`, add:

```python
@app.command("domains")
def domains(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Fuse structural and text embeddings into named business domains."""
    try:
        report = Container().domain_discovery_service().discover(datasource)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"{report.domains} domains, {report.members} members")
```

- [ ] **Step 12: Run to verify it passes**

Run: `uv run pytest tests/integration/test_cli_graph_domains.py -q`
Expected: PASS for the `--help` check now; the full data-dependent path is exercised in Task 12 once `domain_discovery_service` is wired in Task 11

- [ ] **Step 13: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/repositories/semantic/domain_namer_repository.py genql/services/semantic/domain_discovery_service.py genql/cli/commands/graph.py tests/unit/test_llm_domain_namer.py tests/unit/test_domain_discovery_service.py tests/integration/test_cli_graph_domains.py
git commit -m "feat(cli): add genql graph domains"
```

---

### Task 8: Enrichers, the semantic overlay service, and `genql semantic overlay`

**Files:**
- Create: `genql/repositories/semantic/registry.py`, `genql/repositories/semantic/enricher_repository.py`, `genql/services/semantic/semantic_overlay_service.py`, `genql/cli/commands/semantic.py`
- Modify: `genql/repositories/semantic/__init__.py`, `genql/cli/main.py`, `pyproject.toml`
- Test: `tests/unit/test_enrichers.py`, `tests/unit/test_semantic_overlay_service.py`, `tests/unit/test_semantic_overlay_yaml_validation.py`, `tests/integration/test_cli_semantic_overlay.py`

**Interfaces:**
- Consumes: `Enricher`, `EnrichmentField`, `EnrichmentReader`, `EnrichmentWriter`, `MetricWriter` ports; `JoinPathWriter` (Phase 3); `SemanticOverlay`/`ObjectOverlay`/`ColumnOverlay`/`MetricOverlay`/`JoinHintOverlay` entities (Task 1)
- Produces: `ENRICHERS`, `RETRIEVERS` registries (this task populates `ENRICHERS`; Task 10 populates `RETRIEVERS` in the same file); `DescriptionEnricher`, `AliasEnricher`, `UnitEnricher`; `OverlayReport(objects_updated, columns_updated, metrics_written, join_hints_written)`; `SemanticOverlayService(enrichment_reader, enrichment_writer, metric_writer, join_path_writer, enrichers: Sequence[Enricher]).apply(overlay: SemanticOverlay) -> OverlayReport`; CLI command `genql semantic overlay --datasource NAME`

- [ ] **Step 1: Add pyyaml**

```bash
uv add pyyaml
uv add --dev types-PyYAML
```

- [ ] **Step 2: Write the failing enricher tests**

Create `tests/unit/test_enrichers.py`:

```python
"""All three share one rule — an overlay value always wins — kept as
separate classes so a future kind needing different validation costs one
new file, not a branch in an existing one."""

from __future__ import annotations

import pytest

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.value_objects.provenance import Provenance
from genql.repositories.semantic.enricher_repository import (
    AliasEnricher,
    DescriptionEnricher,
    UnitEnricher,
)

DISCOVERED = EnrichmentField(
    kind="description", qualified_name="local.shop.orders", value="from LLM",
    provenance=Provenance.LLM,
)
OVERLAY = EnrichmentField(
    kind="description", qualified_name="local.shop.orders", value="from YAML",
    provenance=Provenance.YAML,
)


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_overlay_wins_when_present(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(DISCOVERED, OVERLAY) is OVERLAY


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_discovered_passes_through_when_no_overlay(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(DISCOVERED, None) is DISCOVERED


@pytest.mark.parametrize("enricher_cls", [DescriptionEnricher, AliasEnricher, UnitEnricher])
def test_none_when_neither_exists(enricher_cls: type) -> None:
    enricher = enricher_cls()

    assert enricher.merge(None, None) is None


def test_keys_are_distinct() -> None:
    assert {DescriptionEnricher.key, AliasEnricher.key, UnitEnricher.key} == {
        "description", "alias", "unit",
    }
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_enrichers.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement the registry and the enrichers**

Create `genql/repositories/semantic/registry.py`:

```python
"""ENRICHERS (this task) and RETRIEVERS (Task 10), colocated the way
repositories/graph/registry.py colocates its three graph-algorithm
registries."""

from __future__ import annotations

from genql.domain.ports.enricher import Enricher
from genql.domain.ports.retriever import Retriever
from genql.registries.registry import Registry

ENRICHERS: Registry[Enricher] = Registry("enrichers")
RETRIEVERS: Registry[Retriever] = Registry("retrievers")
```

Create `genql/repositories/semantic/enricher_repository.py`:

```python
"""The default merge rule — an overlay value always wins; absent an
overlay, the discovered value passes through unchanged — is identical
across all three registered kinds."""

from __future__ import annotations

from typing import ClassVar

from genql.domain.entities.enrichment_field import EnrichmentField
from genql.repositories.semantic.registry import ENRICHERS


@ENRICHERS.register("description")
class DescriptionEnricher:
    key: ClassVar[str] = "description"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered


@ENRICHERS.register("alias")
class AliasEnricher:
    key: ClassVar[str] = "alias"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered


@ENRICHERS.register("unit")
class UnitEnricher:
    key: ClassVar[str] = "unit"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay if overlay is not None else discovered
```

In `genql/repositories/semantic/__init__.py`, add:

```python
from genql.repositories.semantic.enricher_repository import (
    AliasEnricher,
    DescriptionEnricher,
    UnitEnricher,
)

__all__ = ["DescriptionEnricher", "AliasEnricher", "UnitEnricher"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/test_enrichers.py -q`
Expected: PASS

- [ ] **Step 6: Write the failing overlay-service test**

Create `tests/unit/test_semantic_overlay_service.py`:

```python
"""Overlay always wins on merge. An object entry with no prior profiling and
only a business_alias override (no description) writes nothing — an
ObjectEnrichment cannot exist without a description."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.entities.semantic_overlay import (
    ColumnOverlay,
    MetricOverlay,
    ObjectOverlay,
    SemanticOverlay,
)
from genql.repositories.semantic.enricher_repository import (
    AliasEnricher,
    DescriptionEnricher,
    UnitEnricher,
)
from genql.services.semantic.semantic_overlay_service import SemanticOverlayService

EXISTING = ObjectEnrichment(
    datasource_name="local", schema_name="shop", object_name="orders", description="from LLM",
)


class FakeEnrichmentReader:
    def __init__(self, objects: Sequence[ObjectEnrichment] = ()) -> None:
        self._objects = objects

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return self._objects

    def read_column_enrichments(self, ref: object) -> Sequence[ColumnEnrichment]:
        return []


class FakeEnrichmentWriter:
    def __init__(self) -> None:
        self.objects: list[ObjectEnrichment] = []
        self.columns: list[ColumnEnrichment] = []

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        self.objects.append(enrichment)

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        self.columns.extend(enrichments)
        return len(enrichments)


class FakeMetricWriter:
    def __init__(self) -> None:
        self.written: list[Metric] = []

    def write(self, metrics: Sequence[Metric]) -> int:
        self.written.extend(metrics)
        return len(metrics)


class FakeJoinPathWriter:
    def __init__(self) -> None:
        self.written: list[object] = []

    def write(self, paths: Sequence[object]) -> int:
        self.written.extend(paths)
        return len(paths)


def _service(objects: Sequence[ObjectEnrichment] = ()) -> tuple[SemanticOverlayService, FakeEnrichmentWriter, FakeMetricWriter, FakeJoinPathWriter]:
    writer = FakeEnrichmentWriter()
    metrics = FakeMetricWriter()
    join_paths = FakeJoinPathWriter()
    service = SemanticOverlayService(
        FakeEnrichmentReader(objects), writer, metrics, join_paths,
        [DescriptionEnricher(), AliasEnricher(), UnitEnricher()],
    )
    return service, writer, metrics, join_paths


def test_overlay_description_overrides_the_llm_value() -> None:
    service, writer, _, _ = _service([EXISTING])
    overlay = SemanticOverlay(
        datasource="local",
        objects={"shop.orders": ObjectOverlay(description="from YAML")},
    )

    report = service.apply(overlay)

    assert report.objects_updated == 1
    assert writer.objects[0].description == "from YAML"


def test_alias_only_overlay_on_an_unprofiled_object_writes_nothing() -> None:
    service, writer, _, _ = _service([])
    overlay = SemanticOverlay(
        datasource="local",
        objects={"shop.orders": ObjectOverlay(business_alias="orders desk")},
    )

    report = service.apply(overlay)

    assert report.objects_updated == 0
    assert writer.objects == []


def test_column_overlay_overrides_unit() -> None:
    service, writer, _, _ = _service([EXISTING])
    overlay = SemanticOverlay(
        datasource="local",
        objects={
            "shop.orders": ObjectOverlay(
                columns={"total": ColumnOverlay(description="Order total.", unit="USD")}
            )
        },
    )

    service.apply(overlay)

    assert writer.columns[0].unit == "USD"
    assert writer.columns[0].description == "Order total."


def test_metrics_are_written_as_is() -> None:
    service, _, metrics, _ = _service([])
    overlay = SemanticOverlay(
        datasource="local",
        metrics=(
            MetricOverlay(name="net_sales", sql_expression="a - b", grain="line_item"),
        ),
    )

    report = service.apply(overlay)

    assert report.metrics_written == 1
    assert metrics.written[0].name == "net_sales"
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/unit/test_semantic_overlay_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 8: Implement the service**

Create `genql/services/semantic/semantic_overlay_service.py`:

```python
"""Merges semantic/<datasource>.yaml over discovered/LLM enrichment. Overlay
always wins, via each field kind's registered Enricher — going through the
registry rather than an inline `if overlay is not None` keeps the merge rule
swappable per kind later without touching this service.

Metrics have no merge step: nothing else proposes a metric, so they are
always YAML-authored and simply upserted. Join hints become JoinPath rows
with provenance=YAML, written through the existing JoinPathWriter — a YAML
join hint is not a new concept, it is another path with a different
provenance."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.enrichment_field import EnrichmentField, EnrichmentKind
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.metric_writer import MetricWriter
from genql.domain.value_objects.provenance import Provenance


class OverlayReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects_updated: int
    columns_updated: int
    metrics_written: int
    join_hints_written: int


class SemanticOverlayService:
    def __init__(
        self,
        enrichment_reader: EnrichmentReader,
        enrichment_writer: EnrichmentWriter,
        metric_writer: MetricWriter,
        join_path_writer: JoinPathWriter,
        enrichers: list[Enricher],
    ) -> None:
        self._reader = enrichment_reader
        self._writer = enrichment_writer
        self._metric_writer = metric_writer
        self._join_path_writer = join_path_writer
        self._enrichers = {e.key: e for e in enrichers}

    def apply(self, overlay: SemanticOverlay) -> OverlayReport:
        existing_objects = {
            (e.schema_name, e.object_name): e
            for e in self._reader.read_object_enrichments(overlay.datasource)
        }
        # Loaded once per schema on first use, not once per object — most
        # overlays touch several objects in the same schema, and re-reading
        # the same schema's columns for every one of them would be wasted
        # round trips for no different result.
        existing_columns_by_schema: dict[str, dict[tuple[str, str], ColumnEnrichment]] = {}

        objects_updated = 0
        columns_updated = 0
        for qualified_key, object_overlay in overlay.objects.items():
            schema_name, object_name = qualified_key.split(".", 1)
            qn = f"{overlay.datasource}.{schema_name}.{object_name}"
            current = existing_objects.get((schema_name, object_name))

            description = self._merge(
                "description", qn, current.description if current else None,
                current.provenance if current else None, object_overlay.description,
            )
            alias = self._merge(
                "alias", qn, current.business_alias if current else None,
                current.provenance if current else None, object_overlay.business_alias,
            )
            if description is not None:
                self._writer.write_object_enrichment(
                    ObjectEnrichment(
                        datasource_name=overlay.datasource, schema_name=schema_name,
                        object_name=object_name, description=description.value,
                        business_alias=alias.value if alias else None,
                        provenance=description.provenance,
                        confidence=current.confidence if current else 1.0,
                        embedding=current.embedding if current else None,
                    )
                )
                objects_updated += 1

            if schema_name not in existing_columns_by_schema:
                existing_columns_by_schema[schema_name] = {
                    (ce.object_name, ce.column_name): ce
                    for ce in self._reader.read_column_enrichments(
                        SchemaRef(datasource_name=overlay.datasource, schema_name=schema_name)
                    )
                }
            existing_columns = existing_columns_by_schema[schema_name]

            column_enrichments: list[ColumnEnrichment] = []
            for column_name, column_overlay in object_overlay.columns.items():
                col_qn = f"{qn}.{column_name}"
                existing_col = existing_columns.get((object_name, column_name))
                col_description = self._merge(
                    "description", col_qn, existing_col.description if existing_col else None,
                    existing_col.provenance if existing_col else None, column_overlay.description,
                )
                col_unit = self._merge(
                    "unit", col_qn, existing_col.unit if existing_col else None,
                    existing_col.provenance if existing_col else None, column_overlay.unit,
                )
                col_alias = self._merge(
                    "alias", col_qn, existing_col.business_alias if existing_col else None,
                    existing_col.provenance if existing_col else None,
                    column_overlay.business_alias,
                )
                if col_description is not None:
                    column_enrichments.append(
                        ColumnEnrichment(
                            datasource_name=overlay.datasource, schema_name=schema_name,
                            object_name=object_name, column_name=column_name,
                            description=col_description.value,
                            business_alias=col_alias.value if col_alias else None,
                            unit=col_unit.value if col_unit else None,
                            provenance=col_description.provenance,
                        )
                    )
            if column_enrichments:
                columns_updated += self._writer.write_column_enrichments(column_enrichments)

        metrics = [
            Metric(
                datasource_name=overlay.datasource, name=m.name, sql_expression=m.sql_expression,
                grain=m.grain, unit=m.unit, default_filters=m.default_filters,
            )
            for m in overlay.metrics
        ]
        metrics_written = self._metric_writer.write(metrics) if metrics else 0

        join_hints = [
            JoinPath(
                datasource_name=overlay.datasource,
                schema_name=h.source_object.split(".", 1)[0],
                source_object=h.source_object.split(".", 1)[1],
                target_object=h.target_object.split(".", 1)[1],
                path=tuple(p.split(".", 1)[1] for p in h.path),
                weight=h.weight,
                provenance=Provenance.YAML,
            )
            for h in overlay.join_hints
        ]
        join_hints_written = self._join_path_writer.write(join_hints) if join_hints else 0

        return OverlayReport(
            objects_updated=objects_updated, columns_updated=columns_updated,
            metrics_written=metrics_written, join_hints_written=join_hints_written,
        )

    def _merge(
        self, kind: EnrichmentKind, qualified_name: str, discovered_value: str | None,
        discovered_provenance: Provenance | None, overlay_value: str | None,
    ) -> EnrichmentField | None:
        discovered = (
            EnrichmentField(
                kind=kind, qualified_name=qualified_name, value=discovered_value,
                provenance=discovered_provenance or Provenance.LLM,
            )
            if discovered_value is not None
            else None
        )
        overlay = (
            EnrichmentField(
                kind=kind, qualified_name=qualified_name, value=overlay_value,
                provenance=Provenance.YAML,
            )
            if overlay_value is not None
            else None
        )
        return self._enrichers[kind].merge(discovered, overlay)
```

Join hints assume `source_object`/`target_object`/every entry of `path` share one schema — the same single-schema scoping `JoinPath` (Phase 3) already assumes. A cross-schema join hint is out of scope here for the same reason cross-schema graphs are a Phase 3 non-goal.

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/unit/test_semantic_overlay_service.py -q`
Expected: PASS

- [ ] **Step 10: Write the failing YAML-validation test**

Create `tests/unit/test_semantic_overlay_yaml_validation.py`:

```python
"""A malformed semantic/<datasource>.yaml fails validation wholesale before
any row is written — proven here at the parsing boundary the CLI command
uses, without needing a real file or a database."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from genql.domain.entities.semantic_overlay import SemanticOverlay

VALID_YAML = """
datasource: local
objects:
  "tpcds.store_sales":
    description: "Point-of-sale line items."
    columns:
      ss_ext_sales_price:
        unit: USD
metrics:
  - name: net_sales
    sql_expression: "ss_ext_sales_price - ss_ext_discount_amt"
    grain: line_item
"""

INVALID_YAML = """
datasource: local
metrics:
  - name: net_sales
    grain: line_item
"""  # missing required sql_expression


def test_valid_yaml_parses_into_a_semantic_overlay() -> None:
    overlay = SemanticOverlay.model_validate(yaml.safe_load(VALID_YAML))

    assert overlay.objects["tpcds.store_sales"].columns["ss_ext_sales_price"].unit == "USD"


def test_invalid_yaml_raises_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        SemanticOverlay.model_validate(yaml.safe_load(INVALID_YAML))
```

- [ ] **Step 11: Run to verify it passes**

Run: `uv run pytest tests/unit/test_semantic_overlay_yaml_validation.py -q`
Expected: PASS (no implementation change needed — `SemanticOverlay`'s own Pydantic validation already provides this; this step exists to prove it before the CLI command relies on it)

- [ ] **Step 12: Write the failing CLI integration test**

Create `tests/integration/test_cli_semantic_overlay.py`:

```python
"""No semantic/<datasource>.yaml present is a no-op, not an error — not
every datasource needs authored overrides."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_overlay_with_no_file_present_is_a_clean_no_op(tmp_path: object) -> None:
    result = runner.invoke(app, ["semantic", "overlay", "--datasource", "nonexistent_ds_xyz"])

    assert result.exit_code == 0
    assert "no overlay file" in result.stdout.lower()
```

- [ ] **Step 13: Run to verify it fails**

Run: `uv run pytest tests/integration/test_cli_semantic_overlay.py -q`
Expected: FAIL — no `semantic` sub-command yet

- [ ] **Step 14: Implement the CLI**

Create `genql/cli/commands/semantic.py` (this task adds only the `overlay` command; Tasks 9 and 10 add `compile` and `search` to the same file):

```python
"""`genql semantic` — merge YAML overrides, compile the search index, and
query it. Domain errors are caught here and turned into a message plus exit
code 1, same rule as every other command."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from genql.composition_root import Container
from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.errors import GenqlError

app = typer.Typer(help="Merge YAML overrides, compile, and search the semantic store")


@app.command("overlay")
def overlay(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Validate and merge semantic/<datasource>.yaml over discovered/LLM enrichment."""
    path = Path("semantic") / f"{datasource}.yaml"
    if not path.exists():
        typer.echo(f"no overlay file at {path}; nothing to apply")
        return
    try:
        parsed = SemanticOverlay.model_validate(yaml.safe_load(path.read_text()))
    except ValidationError as exc:
        typer.echo(f"{path} failed validation:\n{exc}")
        raise typer.Exit(code=1) from exc
    try:
        report = Container().semantic_overlay_service().apply(parsed)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{report.objects_updated} objects, {report.columns_updated} columns, "
        f"{report.metrics_written} metrics, {report.join_hints_written} join hints"
    )
```

In `genql/cli/main.py`, add the import and mount:

```python
from genql.cli.commands import semantic as semantic_commands
```

```python
app.add_typer(semantic_commands.app, name="semantic")
```

- [ ] **Step 15: Run to verify it passes**

Run: `uv run pytest tests/integration/test_cli_semantic_overlay.py -q`
Expected: PASS

- [ ] **Step 16: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/repositories/semantic/registry.py genql/repositories/semantic/enricher_repository.py genql/repositories/semantic/__init__.py genql/services/semantic/semantic_overlay_service.py genql/cli/commands/semantic.py genql/cli/main.py pyproject.toml uv.lock tests/unit/test_enrichers.py tests/unit/test_semantic_overlay_service.py tests/unit/test_semantic_overlay_yaml_validation.py tests/integration/test_cli_semantic_overlay.py
git commit -m "feat(cli): add genql semantic overlay"
```

---

### Task 9: Comment write-back, the search document compiler, and `genql semantic compile`

**Files:**
- Create: `genql/domain/ports/comment_writer_factory.py`, `genql/infrastructure/catalog/comment_writer_factory.py`, `genql/repositories/warehouse/comment_writer_repository.py`, `genql/repositories/semantic/search_document_repository.py`, `genql/services/semantic/compile_service.py`
- Modify: `genql/cli/commands/semantic.py`
- Test: `tests/unit/test_compile_service.py`, `tests/integration/test_comment_writer_repository.py`, `tests/integration/test_search_document_compiler.py`

**Interfaces:**
- Consumes: `CommentWriter`, `SearchDocumentWriter`, `EnrichmentReader`, `EmbeddingProvider` ports; `DatasourceRepository` (Phase 2.5); `SchemaRef`
- Produces: `CommentWriterFactory` port (new — not anticipated in Task 1, added here once the exact need is concrete, the same way Phase 3's plan discovered exact port needs task by task); `CommentWriterFactoryImpl(provider).for_datasource(datasource) -> PostgresCommentWriter`; `PostgresCommentWriter(engine)` implementing `CommentWriter`; `SearchDocumentCompiler(engine, embedder)` implementing `SearchDocumentWriter`; `CompileReport(documents: int, comments_written: int)`; `CompileService(search_document_writer, enrichment_reader, comment_writer_factory, datasource_repository).compile(datasource_name, write_back=False) -> CompileReport`; CLI command `genql semantic compile --datasource NAME [--write-back]`

- [ ] **Step 1: Write the failing service test**

Create `tests/unit/test_compile_service.py`:

```python
"""write_back=False never touches the CommentWriterFactory — proving that is
the whole point of the flag defaulting off."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.compile_service import CompileService

OBJECT_ENRICHMENT = ObjectEnrichment(
    datasource_name="local", schema_name="shop", object_name="orders", description="x",
)


class FakeSearchDocumentWriter:
    def compile(self, datasource_name: str) -> int:
        return 3


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return [OBJECT_ENRICHMENT]

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        return []


class FakeCommentWriter:
    def __init__(self) -> None:
        self.object_comments: list[str] = []

    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        self.object_comments.append(object_name)

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        return None


class FakeCommentWriterFactory:
    def __init__(self) -> None:
        self.writer = FakeCommentWriter()
        self.calls = 0

    def for_datasource(self, datasource: Datasource) -> FakeCommentWriter:
        self.calls += 1
        return self.writer


class FakeDatasourceRepository:
    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")


def test_compile_without_write_back_never_touches_the_comment_factory() -> None:
    factory = FakeCommentWriterFactory()
    service = CompileService(
        FakeSearchDocumentWriter(), FakeEnrichmentReader(), factory, FakeDatasourceRepository()
    )

    report = service.compile("local", write_back=False)

    assert report.documents == 3
    assert report.comments_written == 0
    assert factory.calls == 0


def test_compile_with_write_back_writes_one_comment_per_object() -> None:
    factory = FakeCommentWriterFactory()
    service = CompileService(
        FakeSearchDocumentWriter(), FakeEnrichmentReader(), factory, FakeDatasourceRepository()
    )

    report = service.compile("local", write_back=True)

    assert report.comments_written == 1
    assert factory.writer.object_comments == ["orders"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_compile_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Add the CommentWriterFactory port**

Create `genql/domain/ports/comment_writer_factory.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.comment_writer import CommentWriter


@runtime_checkable
class CommentWriterFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> CommentWriter: ...
```

- [ ] **Step 4: Implement the service**

Create `genql/services/semantic/compile_service.py`:

```python
"""Builds genql_search_document for a whole datasource, then optionally
writes descriptions back to the warehouse as COMMENT ON. write_back stays
off by default — this is the one path in this phase that writes to a
datasource other than GenQL's own."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.comment_writer_factory import CommentWriterFactory
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.search_document_writer import SearchDocumentWriter
from genql.domain.value_objects.schema_ref import SchemaRef


class CompileReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    comments_written: int


class CompileService:
    def __init__(
        self,
        search_document_writer: SearchDocumentWriter,
        enrichment_reader: EnrichmentReader,
        comment_writer_factory: CommentWriterFactory,
        datasource_repository: DatasourceRepository,
    ) -> None:
        self._writer = search_document_writer
        self._enrichment_reader = enrichment_reader
        self._comment_writer_factory = comment_writer_factory
        self._datasource_repository = datasource_repository

    def compile(self, datasource_name: str, write_back: bool = False) -> CompileReport:
        documents = self._writer.compile(datasource_name)
        comments_written = 0
        if write_back:
            datasource = self._datasource_repository.get(datasource_name)
            comment_writer = self._comment_writer_factory.for_datasource(datasource)
            object_enrichments = self._enrichment_reader.read_object_enrichments(datasource_name)
            for enrichment in object_enrichments:
                ref = SchemaRef(
                    datasource_name=datasource_name, schema_name=enrichment.schema_name
                )
                comment_writer.write_object_comment(
                    ref, enrichment.object_name, enrichment.description
                )
                comments_written += 1
            for schema_name in {e.schema_name for e in object_enrichments}:
                ref = SchemaRef(datasource_name=datasource_name, schema_name=schema_name)
                for col in self._enrichment_reader.read_column_enrichments(ref):
                    comment_writer.write_column_comment(
                        ref, col.object_name, col.column_name, col.description
                    )
                    comments_written += 1
        return CompileReport(documents=documents, comments_written=comments_written)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/test_compile_service.py -q`
Expected: PASS

- [ ] **Step 6: Write the failing comment-writer integration test**

Create `tests/integration/test_comment_writer_repository.py`:

```python
"""Writes against a real table so identifier quoting is exercised for real,
not just asserted about."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.warehouse.comment_writer_repository import PostgresCommentWriter


def test_write_object_comment_lands_on_the_table(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "comment_test")
    with migrated_engine.begin() as conn:
        conn.execute(text('CREATE SCHEMA IF NOT EXISTS comment_test'))
        conn.execute(text("CREATE TABLE IF NOT EXISTS comment_test.orders (id int)"))
    writer = PostgresCommentWriter(migrated_engine)
    ref = SchemaRef(datasource_name="local", schema_name="comment_test")

    writer.write_object_comment(ref, "orders", "Customer orders.")

    with migrated_engine.connect() as conn:
        comment = conn.execute(
            text("SELECT obj_description('comment_test.orders'::regclass)")
        ).scalar_one()
    assert comment == "Customer orders."
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/integration/test_comment_writer_repository.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 8: Implement the comment writer and its factory**

Create `genql/repositories/warehouse/comment_writer_repository.py`:

```python
"""Writes COMMENT ON TABLE / COMMENT ON COLUMN against the WAREHOUSE engine
— not the semantic store. `COMMENT ON` has no parameterized-identifier
form, so schema/object/column names are quoted through SQLAlchemy's own
IdentifierPreparer (which doubles embedded quote characters, the standard
SQL escaping rule) rather than interpolated raw; only the comment TEXT
itself is a bind parameter."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.errors import CompileError
from genql.domain.value_objects.schema_ref import SchemaRef


class PostgresCommentWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _quote(self, *parts: str) -> str:
        preparer = self._engine.dialect.identifier_preparer
        return ".".join(preparer.quote(p) for p in parts)

    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        target = self._quote(ref.schema_name, object_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(text(f"COMMENT ON TABLE {target} IS :comment"), {"comment": comment})
        except SQLAlchemyError as exc:
            raise CompileError(f"failed to write comment on {target}: {exc}") from exc

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        target = self._quote(ref.schema_name, object_name, column_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(text(f"COMMENT ON COLUMN {target} IS :comment"), {"comment": comment})
        except SQLAlchemyError as exc:
            raise CompileError(f"failed to write comment on {target}: {exc}") from exc
```

Create `genql/infrastructure/catalog/comment_writer_factory.py`:

```python
"""Binds a CommentWriter to one datasource's warehouse engine — mirrors
CatalogReaderFactoryImpl exactly."""

from __future__ import annotations

from genql.domain.entities.datasource import Datasource
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.warehouse.comment_writer_repository import PostgresCommentWriter


class CommentWriterFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider) -> None:
        self._provider = provider

    def for_datasource(self, datasource: Datasource) -> PostgresCommentWriter:
        engine = self._provider.engine_for(datasource)
        return PostgresCommentWriter(engine)
```

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/integration/test_comment_writer_repository.py -q`
Expected: PASS

- [ ] **Step 10: Write the failing search-document-compiler integration test**

Create `tests/integration/test_search_document_compiler.py`:

```python
"""Uses a fake EmbeddingProvider — this test proves the SQL and the content
assembly, not embedding quality, which the gated OpenRouter tests already
cover."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import Engine, text

from genql.repositories.semantic.search_document_repository import SearchDocumentCompiler


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [tuple([0.0] * 1536) for _ in texts]


def test_compile_writes_one_document_per_object(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "compile_test")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object (datasource_name, schema_name, object_name, "
                "object_type) VALUES ('local', 'compile_test', 'orders', 'table')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO genql.genql_object_enrichment "
                "(datasource_name, schema_name, object_name, description) "
                "VALUES ('local', 'compile_test', 'orders', 'Customer orders.')"
            )
        )

    written = SearchDocumentCompiler(migrated_engine, FakeEmbeddingProvider()).compile("local")

    assert written >= 1
    with migrated_engine.connect() as conn:
        content = conn.execute(
            text(
                "SELECT content FROM genql.genql_search_document "
                "WHERE datasource_name = 'local' AND schema_name = 'compile_test' "
                "AND object_name = 'orders'"
            )
        ).scalar_one()
    assert "Customer orders." in content
```

- [ ] **Step 11: Run to verify it fails**

Run: `uv run pytest tests/integration/test_search_document_compiler.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 12: Implement the compiler**

Create `genql/repositories/semantic/search_document_repository.py`:

```python
"""Builds one genql_search_document row per object: name, type, description,
alias, domain name, and each column's name, description, unit, and sample
values — the exact field list the parent spec names for the BM25 text.
Embeds the assembled text and upserts."""

from __future__ import annotations

from sqlalchemy import Engine, text

from genql.domain.errors import CompileError, EmbeddingProviderError
from genql.domain.ports.embedding_provider import EmbeddingProvider

_SELECT_OBJECTS = text("""
    SELECT o.schema_name, o.object_name, o.object_type, oe.description, oe.business_alias,
           d.name AS domain_name
    FROM genql.genql_object o
    JOIN genql.genql_schema s
        ON s.datasource_name = o.datasource_name AND s.schema_name = o.schema_name
    LEFT JOIN genql.genql_object_enrichment oe
        ON oe.datasource_name = o.datasource_name AND oe.schema_name = o.schema_name
        AND oe.object_name = o.object_name
    LEFT JOIN genql.genql_domain_member dm
        ON dm.datasource_name = o.datasource_name AND dm.schema_name = o.schema_name
        AND dm.object_name = o.object_name
    LEFT JOIN genql.genql_domain d ON d.id = dm.domain_id
    WHERE o.datasource_name = :datasource_name AND s.enabled
""")

_SELECT_COLUMNS = text("""
    SELECT c.schema_name, c.object_name, c.column_name, ce.description, ce.unit,
           cp.sample_values
    FROM genql.genql_column c
    LEFT JOIN genql.genql_column_enrichment ce
        ON ce.datasource_name = c.datasource_name AND ce.schema_name = c.schema_name
        AND ce.object_name = c.object_name AND ce.column_name = c.column_name
    LEFT JOIN genql.genql_column_profile cp
        ON cp.datasource_name = c.datasource_name AND cp.schema_name = c.schema_name
        AND cp.object_name = c.object_name AND cp.column_name = c.column_name
    WHERE c.datasource_name = :datasource_name
""")

_UPSERT_DOCUMENT = text("""
    INSERT INTO genql.genql_search_document
        (datasource_name, schema_name, object_name, domain_name, content, embedding)
    VALUES (:datasource_name, :schema_name, :object_name, :domain_name, :content, :embedding)
    ON CONFLICT ON CONSTRAINT uq_genql_search_document_identity DO UPDATE
        SET domain_name = EXCLUDED.domain_name,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            updated_at = now()
""")


class SearchDocumentCompiler:
    def __init__(self, engine: Engine, embedder: EmbeddingProvider) -> None:
        self._engine = engine
        self._embedder = embedder

    def compile(self, datasource_name: str) -> int:
        with self._engine.connect() as conn:
            object_rows = conn.execute(_SELECT_OBJECTS, {"datasource_name": datasource_name}).all()
            column_rows = conn.execute(_SELECT_COLUMNS, {"datasource_name": datasource_name}).all()
        if not object_rows:
            return 0

        columns_by_object: dict[tuple[str, str], list] = {}
        for row in column_rows:
            columns_by_object.setdefault((row.schema_name, row.object_name), []).append(row)

        contents: list[str] = []
        keys: list[tuple[str, str, str | None]] = []
        for row in object_rows:
            column_lines = [
                f"{col.column_name}: {col.description or ''} "
                f"(unit: {col.unit or 'n/a'}; samples: {list(col.sample_values or [])})"
                for col in columns_by_object.get((row.schema_name, row.object_name), [])
            ]
            contents.append(
                f"{row.object_name} ({row.object_type}) in domain {row.domain_name or 'unassigned'}. "
                f"{row.description or ''} Also known as: {row.business_alias or 'n/a'}. "
                f"Columns: {'; '.join(column_lines)}"
            )
            keys.append((row.schema_name, row.object_name, row.domain_name))

        try:
            embeddings = self._embedder.embed(contents)
        except EmbeddingProviderError as exc:
            raise CompileError(
                f"failed to embed search documents for {datasource_name!r}: {exc}"
            ) from exc

        rows = [
            {
                "datasource_name": datasource_name, "schema_name": schema_name,
                "object_name": object_name, "domain_name": domain_name, "content": content,
                "embedding": list(embedding),
            }
            for (schema_name, object_name, domain_name), content, embedding in zip(
                keys, contents, embeddings, strict=True
            )
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_DOCUMENT, rows)
        return len(rows)
```

- [ ] **Step 13: Run to verify it passes**

Run: `uv run pytest tests/integration/test_search_document_compiler.py -q`
Expected: PASS

- [ ] **Step 14: Add the CLI command**

In `genql/cli/commands/semantic.py`, add:

```python
@app.command("compile")
def compile_command(
    datasource: str = typer.Option(..., "--datasource"),
    write_back: bool = typer.Option(False, "--write-back", help="Also COMMENT ON the warehouse"),
) -> None:
    """Build genql_search_document; optionally write descriptions back to the warehouse."""
    try:
        report = Container().compile_service().compile(datasource, write_back=write_back)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"{report.documents} documents compiled, {report.comments_written} comments written")
```

- [ ] **Step 15: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/domain/ports/comment_writer_factory.py genql/infrastructure/catalog/comment_writer_factory.py genql/repositories/warehouse/comment_writer_repository.py genql/repositories/semantic/search_document_repository.py genql/services/semantic/compile_service.py genql/cli/commands/semantic.py tests/unit/test_compile_service.py tests/integration/test_comment_writer_repository.py tests/integration/test_search_document_compiler.py
git commit -m "feat(cli): add genql semantic compile"
```

---

### Task 10: Retrievers, the retrieval service, and `genql semantic search`

**Files:**
- Create: `genql/repositories/semantic/bm25_retriever_repository.py`, `genql/repositories/semantic/dense_retriever_repository.py`, `genql/repositories/semantic/hybrid_rrf_retriever_repository.py`, `genql/repositories/semantic/domain_scoped_retriever_repository.py`, `genql/services/semantic/retrieval_service.py`
- Modify: `genql/repositories/semantic/__init__.py`, `genql/cli/commands/semantic.py`
- Test: `tests/unit/test_retrieval_service.py`, `tests/unit/test_domain_scoped_retriever.py`, `tests/integration/test_retriever_repositories.py`, `tests/integration/test_cli_semantic_search.py`

**Interfaces:**
- Consumes: `Retriever`, `SearchResult`, `RerankProvider`, `EmbeddingProvider` ports; `RETRIEVERS` registry (Task 8)
- Produces: `Bm25Retriever(engine)`, `DenseRetriever(engine)`, `HybridRrfRetriever(engine, rrf_k=60)` registered under `RETRIEVERS` as `"bm25"`, `"dense"`, `"hybrid_rrf"`; `DomainScopedRetriever(inner: Retriever)` registered as `"domain_scoped"`; `RetrievalService(embedder, retriever, rerank).search(datasource_name, query, top_k, domain_id=None) -> Sequence[SearchResult]`; CLI command `genql semantic search --datasource NAME QUESTION [--top-k N] [--domain-id N]`

All three concrete retrievers accept the same optional `domain_id` filter via one static SQL clause — `AND (:domain_id::bigint IS NULL OR (schema_name, object_name) IN (SELECT schema_name, object_name FROM genql.genql_domain_member WHERE domain_id = :domain_id))` — rather than branching to build two SQL strings; the NULL check makes one query serve both the scoped and unscoped case.

- [ ] **Step 1: Write the failing service and decorator tests**

Create `tests/unit/test_retrieval_service.py`:

```python
"""Embeds once, retrieves through whichever Retriever is injected, reranks
unless reranking is disabled by configuration (rerank=None)."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.ports.rerank_provider import RerankScore
from genql.domain.ports.retriever import SearchResult
from genql.services.semantic.retrieval_service import RetrievalService

RESULTS = [
    SearchResult(datasource_name="local", schema_name="shop", object_name="a", domain_name=None, score=1.0),
    SearchResult(datasource_name="local", schema_name="shop", object_name="b", domain_name=None, score=0.5),
]


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeRetriever:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return RESULTS


class FakeRerankProvider:
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        return [RerankScore(index=1, score=0.9), RerankScore(index=0, score=0.1)]


def test_search_without_rerank_returns_the_retriever_order() -> None:
    service = RetrievalService(FakeEmbeddingProvider(), FakeRetriever(), rerank=None)

    results = service.search("local", "how many orders", top_k=10)

    assert [r.object_name for r in results] == ["a", "b"]


def test_search_with_rerank_reorders_by_rerank_score() -> None:
    service = RetrievalService(FakeEmbeddingProvider(), FakeRetriever(), FakeRerankProvider())

    results = service.search("local", "how many orders", top_k=10)

    assert [r.object_name for r in results] == ["b", "a"]
```

Create `tests/unit/test_domain_scoped_retriever.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.errors import RetrievalError
from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.domain_scoped_retriever_repository import DomainScopedRetriever

RESULT = SearchResult(
    datasource_name="local", schema_name="shop", object_name="a", domain_name="sales", score=1.0
)


class FakeInner:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        assert domain_id is not None
        return [RESULT]


def test_requires_a_domain_id() -> None:
    retriever = DomainScopedRetriever(FakeInner())

    with pytest.raises(RetrievalError):
        retriever.search("local", "q", (0.1,), 10, domain_id=None)


def test_forwards_to_the_inner_retriever_when_domain_id_is_given() -> None:
    retriever = DomainScopedRetriever(FakeInner())

    results = retriever.search("local", "q", (0.1,), 10, domain_id=7)

    assert results == [RESULT]
```

- [ ] **Step 2: Run to verify both fail**

Run: `uv run pytest tests/unit/test_retrieval_service.py tests/unit/test_domain_scoped_retriever.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service and the decorator**

Create `genql/services/semantic/retrieval_service.py`:

```python
"""Embeds the question once, retrieves through whichever Retriever key
Settings.retriever names, and reranks unless reranking is disabled — a
config-only toggle, per the parent spec's stated reason for giving rerank
its own port."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import EmbeddingProviderError, RerankProviderError, RetrievalError
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.rerank_provider import RerankProvider
from genql.domain.ports.retriever import Retriever, SearchResult


class RetrievalService:
    def __init__(
        self, embedder: EmbeddingProvider, retriever: Retriever, rerank: RerankProvider | None
    ) -> None:
        self._embedder = embedder
        self._retriever = retriever
        self._rerank = rerank

    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        try:
            query_embedding = self._embedder.embed([query])[0]
        except EmbeddingProviderError as exc:
            raise RetrievalError(f"failed to embed query: {exc}") from exc

        results = self._retriever.search(datasource_name, query, query_embedding, top_k, domain_id)
        if self._rerank is None or not results:
            return results

        documents = [f"{r.schema_name}.{r.object_name} (domain: {r.domain_name})" for r in results]
        try:
            scores = self._rerank.rerank(query, documents, top_n=len(results))
        except RerankProviderError as exc:
            raise RetrievalError(f"failed to rerank results: {exc}") from exc
        return [results[s.index] for s in sorted(scores, key=lambda s: s.score, reverse=True)]
```

Create `genql/repositories/semantic/domain_scoped_retriever_repository.py`:

```python
"""Wraps another Retriever and requires domain_id — for the online
pipeline's future 'domain already resolved, now search only inside it'
case. Refusing to silently no-op on a missing domain_id is the point of
giving this its own type rather than treating domain scoping as just
another optional filter everywhere."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import RetrievalError
from genql.domain.ports.retriever import Retriever, SearchResult
from genql.repositories.semantic.registry import RETRIEVERS


@RETRIEVERS.register("domain_scoped")
class DomainScopedRetriever:
    def __init__(self, inner: Retriever) -> None:
        self._inner = inner

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        if domain_id is None:
            raise RetrievalError("domain_scoped retrieval requires a domain_id")
        return self._inner.search(datasource_name, query, query_embedding, top_k, domain_id)
```

- [ ] **Step 4: Run to verify both pass**

Run: `uv run pytest tests/unit/test_retrieval_service.py tests/unit/test_domain_scoped_retriever.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing retriever-repository integration tests**

Create `tests/integration/test_retriever_repositories.py`:

```python
"""Seeds documents engineered to favor one signal over the other — a
distinctive keyword with a nearly-orthogonal embedding on one row, a
matching embedding with unrelated text on another — and asserts hybrid
ranking differs from either single-signal ranking alone."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.repositories.semantic.bm25_retriever_repository import Bm25Retriever
from genql.repositories.semantic.dense_retriever_repository import DenseRetriever
from genql.repositories.semantic.hybrid_rrf_retriever_repository import HybridRrfRetriever


def _seed(engine: Engine, datasource_name: str) -> None:
    keyword_embedding = [0.0] * 1536
    vector_embedding = [1.0] + [0.0] * 1535
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_search_document "
                "(datasource_name, schema_name, object_name, content, embedding) VALUES "
                "(:ds, 'shop', 'keyword_match', 'zorblatt unique keyword content', "
                " CAST(:e1 AS vector)), "
                "(:ds, 'shop', 'vector_match', 'completely unrelated generic text', "
                " CAST(:e2 AS vector))"
            ),
            {"ds": datasource_name, "e1": str(keyword_embedding), "e2": str(vector_embedding)},
        )


def test_bm25_and_dense_disagree_and_hybrid_blends_them(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "shop")
    ds = "retriever_test"
    register_schema(ds, "shop")
    _seed(migrated_engine, ds)
    query_embedding = [1.0] + [0.0] * 1535

    bm25_top = Bm25Retriever(migrated_engine).search(
        ds, "zorblatt", query_embedding, top_k=2
    )[0]
    dense_top = DenseRetriever(migrated_engine).search(
        ds, "zorblatt", query_embedding, top_k=2
    )[0]
    hybrid = HybridRrfRetriever(migrated_engine).search(ds, "zorblatt", query_embedding, top_k=2)

    assert bm25_top.object_name == "keyword_match"
    assert dense_top.object_name == "vector_match"
    assert {r.object_name for r in hybrid} == {"keyword_match", "vector_match"}
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/integration/test_retriever_repositories.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement the three concrete retrievers**

Create `genql/repositories/semantic/bm25_retriever_repository.py`:

```python
"""pg_search BM25 ranking over genql_search_document.content."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    SELECT datasource_name, schema_name, object_name, domain_name, paradedb.score(id) AS score
    FROM genql.genql_search_document
    WHERE datasource_name = :datasource_name AND content @@@ :query
      AND (:domain_id::bigint IS NULL OR (schema_name, object_name) IN (
            SELECT schema_name, object_name FROM genql.genql_domain_member
            WHERE domain_id = :domain_id
          ))
    ORDER BY score DESC
    LIMIT :top_k
""")


@RETRIEVERS.register("bm25")
class Bm25Retriever:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "datasource_name": datasource_name, "query": query, "top_k": top_k,
                    "domain_id": domain_id,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

Create `genql/repositories/semantic/dense_retriever_repository.py`:

```python
"""pgvector cosine-distance ranking, converted to a similarity score
(1 - distance) so higher is better everywhere, matching Bm25Retriever's
scoring direction."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    SELECT datasource_name, schema_name, object_name, domain_name,
           1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
    FROM genql.genql_search_document
    WHERE datasource_name = :datasource_name
      AND (:domain_id::bigint IS NULL OR (schema_name, object_name) IN (
            SELECT schema_name, object_name FROM genql.genql_domain_member
            WHERE domain_id = :domain_id
          ))
    ORDER BY embedding <=> CAST(:query_embedding AS vector)
    LIMIT :top_k
""")


@RETRIEVERS.register("dense")
class DenseRetriever:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "datasource_name": datasource_name, "query_embedding": str(list(query_embedding)),
                    "top_k": top_k, "domain_id": domain_id,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

Create `genql/repositories/semantic/hybrid_rrf_retriever_repository.py`:

```python
"""The parent spec's 'single SQL statement': two ranked CTEs, one BM25, one
vector-distance, combined by reciprocal rank fusion — fusion happens in the
database, not by round-tripping two result sets through Python."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    WITH bm25_ranked AS (
        SELECT id, datasource_name, schema_name, object_name, domain_name,
               ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rank
        FROM genql.genql_search_document
        WHERE datasource_name = :datasource_name AND content @@@ :query
    ),
    dense_ranked AS (
        SELECT id, datasource_name, schema_name, object_name, domain_name,
               ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_embedding AS vector)) AS rank
        FROM genql.genql_search_document
        WHERE datasource_name = :datasource_name
    )
    SELECT
        COALESCE(b.datasource_name, d.datasource_name) AS datasource_name,
        COALESCE(b.schema_name, d.schema_name) AS schema_name,
        COALESCE(b.object_name, d.object_name) AS object_name,
        COALESCE(b.domain_name, d.domain_name) AS domain_name,
        (COALESCE(1.0 / (:rrf_k + b.rank), 0) + COALESCE(1.0 / (:rrf_k + d.rank), 0)) AS score
    FROM bm25_ranked b
    FULL OUTER JOIN dense_ranked d ON b.id = d.id
    WHERE (:domain_id::bigint IS NULL OR (COALESCE(b.schema_name, d.schema_name),
           COALESCE(b.object_name, d.object_name)) IN (
        SELECT schema_name, object_name FROM genql.genql_domain_member WHERE domain_id = :domain_id
    ))
    ORDER BY score DESC
    LIMIT :top_k
""")


@RETRIEVERS.register("hybrid_rrf")
class HybridRrfRetriever:
    def __init__(self, engine: Engine, rrf_k: int = 60) -> None:
        self._engine = engine
        self._rrf_k = rrf_k

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "datasource_name": datasource_name, "query": query,
                    "query_embedding": str(list(query_embedding)), "top_k": top_k,
                    "domain_id": domain_id, "rrf_k": self._rrf_k,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

In `genql/repositories/semantic/__init__.py`, extend the imports to also register the four retrievers:

```python
from genql.repositories.semantic.bm25_retriever_repository import Bm25Retriever
from genql.repositories.semantic.dense_retriever_repository import DenseRetriever
from genql.repositories.semantic.domain_scoped_retriever_repository import DomainScopedRetriever
from genql.repositories.semantic.hybrid_rrf_retriever_repository import HybridRrfRetriever
```

(add each new name to `__all__` alongside the enrichers already imported there from Task 8)

The implementing engineer should verify the exact `paradedb.score()` and `@@@` call shape against the ParadeDB version pinned in `docker/compose.yaml` (0.25.6) before trusting this SQL verbatim — `pg_search`'s query syntax has changed across versions, and Step 6's integration test is what actually proves it, not this plan.

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/integration/test_retriever_repositories.py -q`
Expected: PASS

- [ ] **Step 9: Write the failing CLI integration test**

Create `tests/integration/test_cli_semantic_search.py`:

```python
from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_search_command_exists() -> None:
    result = runner.invoke(app, ["semantic", "search", "--help"])

    assert result.exit_code == 0
    assert "top-k" in result.stdout.lower()
```

- [ ] **Step 10: Run to verify it fails**

Run: `uv run pytest tests/integration/test_cli_semantic_search.py -q`
Expected: FAIL — no `search` sub-command yet

- [ ] **Step 11: Implement the CLI command**

In `genql/cli/commands/semantic.py`, add:

```python
@app.command("search")
def search(
    datasource: str = typer.Option(..., "--datasource"),
    question: str = typer.Argument(...),
    top_k: int = typer.Option(10, "--top-k"),
    domain_id: int | None = typer.Option(None, "--domain-id"),
) -> None:
    """Hybrid retrieval plus reranking — the first command that answers
    something resembling the product question."""
    try:
        results = Container().retrieval_service().search(datasource, question, top_k, domain_id)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    for r in results:
        typer.echo(f"{r.schema_name}.{r.object_name}  domain={r.domain_name}  score={r.score:.4f}")
```

- [ ] **Step 12: Run to verify it passes**

Run: `uv run pytest tests/integration/test_cli_semantic_search.py -q`
Expected: PASS

- [ ] **Step 13: Local checks and commit**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`

```bash
git add genql/repositories/semantic/bm25_retriever_repository.py genql/repositories/semantic/dense_retriever_repository.py genql/repositories/semantic/hybrid_rrf_retriever_repository.py genql/repositories/semantic/domain_scoped_retriever_repository.py genql/repositories/semantic/__init__.py genql/services/semantic/retrieval_service.py genql/cli/commands/semantic.py tests/unit/test_retrieval_service.py tests/unit/test_domain_scoped_retriever.py tests/integration/test_retriever_repositories.py tests/integration/test_cli_semantic_search.py
git commit -m "feat(cli): add genql semantic search"
```

---

### Task 11: Composition root wiring

**Files:**
- Modify: `genql/core/settings.py`, `genql/composition_root.py`, `tests/unit/test_composition_root.py`

**Interfaces:**
- Consumes: everything from Tasks 1–10
- Produces: every new `Settings` field below; `Container.openrouter_client`, `.cohere_client`, `.chat_provider`, `.embedding_provider`, `.rerank_provider`, `.enrichment_repository`, `.domain_repository`, `.metric_repository`, `.object_profiling_service`, `.cluster_reader`, `.domain_clustering_algorithm`, `.domain_namer`, `.domain_discovery_service`, `.semantic_overlay_service`, `.comment_writer_factory`, `.search_document_compiler`, `.compile_service`, `.retriever`, `.retrieval_service`

- [ ] **Step 1: Write the failing composition-root assertions**

In `tests/unit/test_composition_root.py`, extend the `container` fixture:

```python
    monkeypatch.setenv("GENQL_OPENROUTER_API_KEY", "test-key")
```

and add:

```python
def test_the_runner_includes_object_profiling(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "object_profiling" in step_names


def test_the_container_builds_a_chat_provider(container: Container) -> None:
    assert hasattr(container.chat_provider(), "complete")


def test_the_container_builds_an_embedding_provider(container: Container) -> None:
    assert hasattr(container.embedding_provider(), "embed")


def test_the_container_builds_a_rerank_provider_when_enabled(container: Container) -> None:
    assert hasattr(container.rerank_provider(), "rerank")


def test_the_container_builds_an_object_profiling_service(container: Container) -> None:
    assert hasattr(container.object_profiling_service(), "profile")


def test_the_container_builds_a_domain_discovery_service(container: Container) -> None:
    assert hasattr(container.domain_discovery_service(), "discover")


def test_the_container_builds_a_semantic_overlay_service(container: Container) -> None:
    assert hasattr(container.semantic_overlay_service(), "apply")


def test_the_container_builds_a_compile_service(container: Container) -> None:
    assert hasattr(container.compile_service(), "compile")


def test_the_container_builds_a_retrieval_service(container: Container) -> None:
    assert hasattr(container.retrieval_service(), "search")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL — `AttributeError: 'Container' object has no attribute 'chat_provider'`

- [ ] **Step 3: Add the new Settings fields**

In `genql/core/settings.py`, add to the `Settings` class:

```python
    openrouter_api_key: str = ""
    cohere_api_key: str | None = None
    chat_provider: str = "openrouter"
    embedding_provider: str = "openrouter"
    rerank_provider: str = "openrouter"
    rerank_enabled: bool = True
    chat_model: str = "anthropic/claude-sonnet-5"
    embedding_model: str = "openai/text-embedding-3-small"
    rerank_model: str = "cohere/rerank-4-pro"
    domain_clustering_algorithm: str = "fused"
    domain_cluster_k_min: int = 2
    domain_cluster_k_max: int = 20
    retriever: str = "hybrid_rrf"
    rrf_k: int = 60
    search_top_k: int = 10
```

`openrouter_api_key` defaults to `""` rather than being required — the parent spec's own correctness principle (§1: "with every LLM provider unreachable, retrieval and schema linking still function") means building `Settings`/`Container` must not hard-fail just because no key is configured yet. A missing key surfaces as a real `httpx` failure translated to `ChatProviderError`/`EmbeddingProviderError`/`RerankProviderError` at first actual call, not at process start — the same "fails at first use, not at construction" shape `MissingDatasourceSecretError` already uses for a datasource's DSN.

- [ ] **Step 4: Wire the container**

In `genql/composition_root.py`, add to the imports:

```python
import genql.repositories.gateway  # noqa: F401 - registration side effect
import genql.repositories.semantic  # noqa: F401 - registration side effect
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.rerank_provider import RerankProvider
from genql.domain.ports.retriever import Retriever
from genql.infrastructure.catalog.comment_writer_factory import CommentWriterFactoryImpl
from genql.infrastructure.gateway.cohere_client import CohereClient
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.registry import (
    CHAT_PROVIDERS,
    EMBEDDING_PROVIDERS,
    RERANK_PROVIDERS,
)
from genql.repositories.graph.cluster_reader_repository import Neo4jClusterReader
from genql.repositories.semantic.domain_namer_repository import LlmDomainNamer
from genql.repositories.semantic.domain_repository import PostgresDomainRepository
from genql.repositories.semantic.enrichment_repository import PostgresEnrichmentRepository
from genql.repositories.semantic.metric_repository import PostgresMetricRepository
from genql.repositories.semantic.registry import ENRICHERS, RETRIEVERS
from genql.repositories.semantic.search_document_repository import SearchDocumentCompiler
from genql.services.semantic.compile_service import CompileService
from genql.services.semantic.domain_discovery_service import DomainDiscoveryService
from genql.services.semantic.object_profiling_service import ObjectProfilingService
from genql.services.semantic.retrieval_service import RetrievalService
from genql.services.semantic.semantic_overlay_service import SemanticOverlayService
```

Five module-level builder functions, next to the existing `_build_clustering_algorithm` and friends:

```python
def _build_chat_provider(key: str, openrouter_client: OpenRouterClient, model: str) -> ChatProvider:
    return CHAT_PROVIDERS.create(key, client=openrouter_client, model=model)


def _build_embedding_provider(
    key: str, openrouter_client: OpenRouterClient, model: str
) -> EmbeddingProvider:
    return EMBEDDING_PROVIDERS.create(key, client=openrouter_client, model=model)


def _build_rerank_provider(
    key: str,
    enabled: bool,
    openrouter_client: OpenRouterClient,
    cohere_client: CohereClient,
    model: str,
) -> RerankProvider | None:
    if not enabled:
        return None
    client = openrouter_client if key == "openrouter" else cohere_client
    return RERANK_PROVIDERS.create(key, client=client, model=model)


def _build_domain_clustering_algorithm(
    key: str, driver: object, enrichment_reader: EnrichmentReader, k_min: int, k_max: int
) -> object:
    return CLUSTERING_ALGORITHMS.create(
        key, driver=driver, enrichment_reader=enrichment_reader, k_min=k_min, k_max=k_max
    )


def _build_retriever(key: str, engine: object, rrf_k: int) -> Retriever:
    if key == "hybrid_rrf":
        return RETRIEVERS.create(key, engine=engine, rrf_k=rrf_k)
    if key == "domain_scoped":
        inner = RETRIEVERS.create("hybrid_rrf", engine=engine, rrf_k=rrf_k)
        return RETRIEVERS.create(key, inner=inner)
    return RETRIEVERS.create(key, engine=engine)


def _build_enrichers() -> list[Enricher]:
    return [ENRICHERS.create(key) for key in ENRICHERS.keys()]
```

(`driver: object` and `engine: object` above match the loose typing `_build_join_path_miner` already uses for `driver` in this file — narrow to `neo4j.Driver` / `sqlalchemy.Engine` if the implementing engineer prefers stricter local typing; `mypy --strict` will not object either way since `providers.Singleton` erases these to `Any` at the call site regardless.)

Inside `Container`, add:

```python
    openrouter_client = providers.Singleton(
        OpenRouterClient, api_key=settings.provided.openrouter_api_key
    )
    cohere_client = providers.Singleton(CohereClient, api_key=settings.provided.cohere_api_key)

    chat_provider = providers.Singleton(
        _build_chat_provider,
        key=settings.provided.chat_provider,
        openrouter_client=openrouter_client,
        model=settings.provided.chat_model,
    )
    embedding_provider = providers.Singleton(
        _build_embedding_provider,
        key=settings.provided.embedding_provider,
        openrouter_client=openrouter_client,
        model=settings.provided.embedding_model,
    )
    rerank_provider = providers.Singleton(
        _build_rerank_provider,
        key=settings.provided.rerank_provider,
        enabled=settings.provided.rerank_enabled,
        openrouter_client=openrouter_client,
        cohere_client=cohere_client,
        model=settings.provided.rerank_model,
    )

    enrichment_repository = providers.Singleton(PostgresEnrichmentRepository, engine=semantic_engine)
    domain_repository = providers.Singleton(PostgresDomainRepository, engine=semantic_engine)
    metric_repository = providers.Singleton(PostgresMetricRepository, engine=semantic_engine)

    object_profiling_service = providers.Factory(
        ObjectProfilingService,
        reader=semantic_catalog_reader,
        chat=chat_provider,
        embedder=embedding_provider,
        writer=enrichment_repository,
    )

    cluster_reader = providers.Singleton(Neo4jClusterReader, driver=neo4j_driver)
    domain_clustering_algorithm = providers.Singleton(
        _build_domain_clustering_algorithm,
        key=settings.provided.domain_clustering_algorithm,
        driver=neo4j_driver,
        enrichment_reader=enrichment_repository,
        k_min=settings.provided.domain_cluster_k_min,
        k_max=settings.provided.domain_cluster_k_max,
    )
    domain_namer = providers.Singleton(LlmDomainNamer, chat=chat_provider)
    domain_discovery_service = providers.Singleton(
        DomainDiscoveryService,
        clustering=domain_clustering_algorithm,
        cluster_reader=cluster_reader,
        enrichment_reader=enrichment_repository,
        namer=domain_namer,
        domain_writer=domain_repository,
    )

    semantic_overlay_service = providers.Singleton(
        SemanticOverlayService,
        enrichment_reader=enrichment_repository,
        enrichment_writer=enrichment_repository,
        metric_writer=metric_repository,
        join_path_writer=join_path_writer,
        enrichers=providers.Factory(_build_enrichers),
    )

    comment_writer_factory = providers.Singleton(CommentWriterFactoryImpl, provider=engine_provider)
    search_document_compiler = providers.Singleton(
        SearchDocumentCompiler, engine=semantic_engine, embedder=embedding_provider
    )
    compile_service = providers.Singleton(
        CompileService,
        search_document_writer=search_document_compiler,
        enrichment_reader=enrichment_repository,
        comment_writer_factory=comment_writer_factory,
        datasource_repository=datasource_repository,
    )

    retriever = providers.Singleton(
        _build_retriever, key=settings.provided.retriever, engine=semantic_engine,
        rrf_k=settings.provided.rrf_k,
    )
    retrieval_service = providers.Singleton(
        RetrievalService, embedder=embedding_provider, retriever=retriever, rerank=rerank_provider
    )
```

Add the new discovery step to the service-provider map:

```python
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": catalog_scan_service,
        "graph_projection": graph_projection_service,
        "data_profiling": profiling_service,
        "object_profiling": object_profiling_service,
    }
```

(`"object_profiling"` sorts after `"graph_projection"` alphabetically — see Task 5's note — so the alphabetical order `_step_providers_in_registered_order` already produces via `DISCOVERY_STEPS.keys()` remains the intended order with no further change needed.)

- [ ] **Step 5: Run to verify the composition-root tests pass**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS

- [ ] **Step 6: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — this is the run that catches the deliberate stray import planted in Step 4; fix it here if it is still present

- [ ] **Step 7: Commit**

```bash
git add genql/core/settings.py genql/composition_root.py tests/unit/test_composition_root.py
git commit -m "feat(composition-root): wire Phase 4 providers, services, and settings"
```

---

### Task 12: Prove it end-to-end against real infrastructure

**Files:**
- Test: `tests/integration/test_phase4_end_to_end.py`

**Interfaces:**
- Consumes: the full CLI surface from Tasks 1–11

**Prerequisites for this task specifically** (beyond the shared Global Constraints): Neo4j provisioned on the VM (it is not, as of this plan's writing — see Global Constraints); `alembic upgrade head` run against the VM's `genql` schema (it is currently behind — no `genql_join_path` table exists there yet, meaning Phase 3's own migration hasn't landed on this VM either); and `GENQL_OPENROUTER_API_KEY` set (it is not set anywhere as of this plan's writing). This test is written now and is expected to skip cleanly wherever that key is absent — do not treat the skip as this task failing.

- [ ] **Step 1: Write the end-to-end test**

Create `tests/integration/test_phase4_end_to_end.py`:

```python
"""genql discover -> graph analyze -> graph domains -> semantic overlay ->
semantic compile -> semantic search against local.tpcds. Skipped cleanly
without an OpenRouter key — nearly every step here needs one."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

runner = CliRunner()


def test_full_chain_answers_a_tpcds_question() -> None:
    discover = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert discover.exit_code == 0, discover.stdout

    analyze = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])
    assert analyze.exit_code == 0, analyze.stdout

    domains = runner.invoke(app, ["graph", "domains", "--datasource", "local"])
    assert domains.exit_code == 0, domains.stdout
    assert "0 domains" not in domains.stdout

    overlay = runner.invoke(app, ["semantic", "overlay", "--datasource", "local"])
    assert overlay.exit_code == 0, overlay.stdout

    compile_result = runner.invoke(app, ["semantic", "compile", "--datasource", "local"])
    assert compile_result.exit_code == 0, compile_result.stdout
    assert "0 documents" not in compile_result.stdout

    search = runner.invoke(
        app, ["semantic", "search", "--datasource", "local", "total sales by store"]
    )
    assert search.exit_code == 0, search.stdout
    assert search.stdout.strip() != ""
```

- [ ] **Step 2: Run it (VM, with Neo4j provisioned, migrations at head, and an OpenRouter key set)**

Run: `uv run pytest tests/integration/test_phase4_end_to_end.py -v`
Expected: PASS with all six commands succeeding in order, `graph domains` reporting more than zero domains, `semantic compile` reporting more than zero documents, and `semantic search` printing at least one ranked result. If `GENQL_OPENROUTER_API_KEY` is unset in the environment running this, expect a clean skip instead — report that outcome exactly, not as a task failure.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_phase4_end_to_end.py
git commit -m "test(semantic): prove discover through search against the real TPC-DS graph"
```

---

## Done When

- `genql discover` runs `object_profiling` after `graph_projection` for every schema, writing `genql_object_enrichment` and `genql_column_enrichment` rows grounded in sampled values.
- `genql graph domains --datasource X` fuses FastRP and text embeddings, names each cluster via LLM, and writes `genql_domain` / `genql_domain_member`.
- `genql semantic overlay --datasource X` validates and merges `semantic/<X>.yaml`, with YAML always winning over discovered/LLM values.
- `genql semantic compile --datasource X` builds `genql_search_document` with a working `pg_search` BM25 index and a `pgvector` HNSW index; `--write-back` optionally writes `COMMENT ON` to the warehouse and is off by default.
- `genql semantic search --datasource X "<question>"` returns ranked, reranked results end to end.
- `ChatProviderRegistry`, `EmbeddingProviderRegistry`, and `RerankProviderRegistry` each carry a working `openrouter` implementation; `RerankProviderRegistry` also carries a working `cohere` implementation.
- `RetrieverRegistry` carries working `bm25`, `dense`, `hybrid_rrf`, and `domain_scoped` implementations.
- `ClusteringRegistry` carries a working `fused` implementation alongside Phase 3's `leiden`.
- The full local unit suite is green; every integration test is written and, wherever the VM (with Neo4j provisioned) and an OpenRouter key are reachable, green; `mypy --strict`, `ruff check`, `ruff format --check`, and `lint-imports` all pass.
- Task 12's end-to-end test passes against `local.tpcds` on a fully-provisioned VM.

---

## Deliberately Not Done

- **Query-log mining and the synthetic ambiguity log** (parent spec steps 10–11). Neither has a consumer before Phase 6.
- **`genql_rule`** (fiscal calendar, default filters, freshness cutoffs, policy constraints). Same reasoning — the Phase 6 ambiguity gate is its first reader.
- **Domain scoping as an online pipeline stage.** `domain_scoped` exists and is proven from the CLI; wiring an actual "resolve the question to a domain" stage in front of it is Phase 5/6 work.
- **`vcr`-recorded LLM integration tests.** Real-provider tests are gated on an API key and skip cleanly without one; recording is deferred until Phase 5+ generates enough call volume to justify a fixture library.
- **Real SQL-parse validation of YAML metric expressions.** `sqlglot` is not a dependency yet; `Metric.sql_expression` gets only a non-empty-string check in `SemanticOverlayService`, upgraded once Phase 5 makes `sqlglot` a genuine dependency.
- **Incremental re-profiling.** `ObjectProfilingService` re-profiles every object on every run. `provenance`/`discovered_at` make a "skip already-profiled objects" flag possible later; nothing in this phase needs it yet.
- **A real `semantic/local.yaml` for TPC-DS.** The spec's example YAML is illustrative. Authoring an actual overlay for the TPC-DS or Olist warehouse is a content task, not an implementation task, and is left for whenever the business-knowledge layer is actually being populated.

