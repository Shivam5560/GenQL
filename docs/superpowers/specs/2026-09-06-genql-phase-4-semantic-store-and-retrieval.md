# GenQL Phase 4 — Semantic Store and Retrieval

**Status:** design approved, pending implementation plan
**Date:** 2026-09-06
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

---

## 1. Purpose

Phases 1–3 built structural discovery and graph topology: objects, columns, constraints, and
profiles land in the semantic store; foreign keys are projected into Neo4j; Leiden communities,
FastRP embeddings, and mined join paths exist per datasource. None of it is *meaning* yet. A column
named `TYPE` with sample values `[CREDIT, DEBIT, TRANSFER]` is still just a column.

Phase 4 grounds every object and column in an LLM-generated description, embeds that description,
fuses the embedding with FastRP's structural signal to name business domains, lets a human override
any of it from YAML, and compiles the result into one retrievable document per object. It ends with
`genql semantic search`, a command that takes a natural-language question and returns ranked,
reranked candidate objects — the first point at which GenQL answers something resembling the actual
product question, even though no SQL is generated yet.

### Goals

- Every object and column carries an LLM-grounded description, with provenance and confidence.
- Text embeddings exist per object, fused with FastRP embeddings into business-named domains.
- A human can override any discovered or LLM-generated field from `semantic/*.yaml`, and YAML
  always wins on merge — conflicts are reported, not silently resolved.
- `genql_search_document` exists per object, indexed for both BM25 (`pg_search`) and vector
  similarity (`pgvector` HNSW), and hybrid retrieval with reranking runs as a single command.
- `COMMENT ON` write-back to the warehouse exists but stays off by default.

### Non-goals

- **Query-log mining** (parent spec step 10) and the **synthetic ambiguity log** (step 11). Neither
  has a consumer before Phase 6's ambiguity gate and critique loop; building them now produces
  tables and code nothing reads. `JOIN_PATH_STRATEGIES` keeps the registry seam Phase 3 already
  left for a query-frequency-weighted strategy.
- **`genql_rule`** (fiscal calendar, default filters, freshness cutoffs, policy constraints). Same
  reasoning: the ambiguity gate that reads rules doesn't exist until Phase 6.
- **Domain scoping as an online pipeline stage.** This phase builds the `domain_scoped` retriever as
  a composable primitive and proves it works from the CLI; wiring it behind an actual "resolve the
  question to a domain" stage is Phase 5/6's online-pipeline work.
- **`vcr`-recorded LLM integration tests.** Not in the repo today. Unit tests use fakes (no
  network); a small number of real-provider integration tests gate on an API key being present and
  skip cleanly otherwise. Recording real calls is better justified once Phase 5+ generates enough
  call volume to make a fixture library worth maintaining.
- **Full five-kind `EnricherRegistry`.** The parent spec's registry table lists `description`,
  `alias`, `unit`, `metric`, `join_hint`. Only the first three share one shape — a single string
  value on one object or column, competing between a discovered/LLM value and a YAML override — and
  that shared shape is exactly what makes a registry seam worth having. `metric` rows are always
  YAML-authored in this phase (nothing else proposes a metric to override), so there is no merge
  conflict to adjudicate — the overlay step validates and upserts them directly. A YAML `join_hint`
  is not a new concept at all: it is another `JoinPath` row with `provenance=YAML`, written through
  the `JoinPathWriter` port Phase 3 already built. Forcing both into the same `Enricher` protocol as
  `description`/`alias`/`unit` would mean inventing a lossy generic value type to paper over
  genuinely different shapes — a false abstraction, not a real seam.

---

## 2. Semantic store schema

### 2.1 New tables

```sql
-- extensions, created here rather than assumed present
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

genql.genql_object_enrichment (
    datasource_name   TEXT NOT NULL,
    schema_name       TEXT NOT NULL,
    object_name       TEXT NOT NULL,
    description       TEXT NOT NULL,
    business_alias    TEXT,
    provenance        TEXT NOT NULL DEFAULT 'llm',
    confidence        DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    embedding         VECTOR(1536),
    discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (datasource_name, schema_name, object_name),
    FOREIGN KEY (datasource_name, schema_name)
        REFERENCES genql.genql_schema (datasource_name, schema_name) ON DELETE CASCADE
)

genql.genql_column_enrichment (
    datasource_name   TEXT NOT NULL,
    schema_name       TEXT NOT NULL,
    object_name       TEXT NOT NULL,
    column_name       TEXT NOT NULL,
    description       TEXT NOT NULL,
    business_alias    TEXT,
    unit              TEXT,
    provenance        TEXT NOT NULL DEFAULT 'llm',
    confidence        DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (datasource_name, schema_name, object_name, column_name),
    FOREIGN KEY (datasource_name, schema_name)
        REFERENCES genql.genql_schema (datasource_name, schema_name) ON DELETE CASCADE
)

genql.genql_domain (
    id                BIGSERIAL PRIMARY KEY,
    datasource_name   TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL,
    provenance        TEXT NOT NULL DEFAULT 'llm',
    discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (datasource_name, name)
)

genql.genql_domain_member (
    domain_id         BIGINT NOT NULL REFERENCES genql.genql_domain (id) ON DELETE CASCADE,
    datasource_name   TEXT NOT NULL,
    schema_name       TEXT NOT NULL,
    object_name       TEXT NOT NULL,
    membership_score  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    PRIMARY KEY (domain_id, datasource_name, schema_name, object_name),
    FOREIGN KEY (datasource_name, schema_name)
        REFERENCES genql.genql_schema (datasource_name, schema_name) ON DELETE CASCADE
)

genql.genql_metric (
    id                BIGSERIAL PRIMARY KEY,
    datasource_name   TEXT NOT NULL,
    name              TEXT NOT NULL,
    sql_expression    TEXT NOT NULL,
    grain             TEXT NOT NULL,
    unit              TEXT,
    default_filters   JSONB NOT NULL DEFAULT '{}',
    provenance        TEXT NOT NULL DEFAULT 'yaml',
    discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (datasource_name, name)
)

genql.genql_search_document (
    id                BIGSERIAL PRIMARY KEY,
    datasource_name   TEXT NOT NULL,
    schema_name       TEXT NOT NULL,
    object_name       TEXT NOT NULL,
    domain_name       TEXT,
    content           TEXT NOT NULL,
    embedding         VECTOR(1536) NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (datasource_name, schema_name, object_name)
)
```

Two embeddings exist for a reason, not by accident: `genql_object_enrichment.embedding` is computed
straight from the LLM profile (step 6) *before* a domain name exists, because fused clustering
(step 7) needs it to produce that domain name in the first place. `genql_search_document.embedding`
is computed later, over the fuller compiled text that includes the domain name once known. They are
almost always similar vectors and never the same computation.

`genql_column_enrichment` carries no embedding — column text is folded into the parent object's
`genql_search_document.content` rather than embedded a second time, matching the parent spec's
description of one BM25/HNSW-indexed row "per object."

### 2.2 Migration 0005

One migration, purely additive: the two `CREATE EXTENSION IF NOT EXISTS` statements, six
`CREATE TABLE`s, then two indexes that cannot be expressed through SQLAlchemy's table DDL and are
added with `op.execute`:

```sql
CREATE INDEX genql_search_document_bm25
    ON genql.genql_search_document
    USING bm25 (id, content)
    WITH (key_field = 'id');

CREATE INDEX genql_search_document_hnsw
    ON genql.genql_search_document
    USING hnsw (embedding vector_cosine_ops);
```

`downgrade()` drops the two indexes, then the six tables in dependency order, then does not drop the
extensions (another table added later in the same database might still need them; extension removal
is an operator decision, not a migration's).

---

## 3. Domain

### 3.1 New value objects and entities

| File | Type | Notes |
|---|---|---|
| `domain/entities/object_enrichment.py` | `ObjectEnrichment` | `datasource_name`, `schema_name`, `object_name`, `description`, `business_alias: str \| None`, `provenance: Provenance = LLM`, `confidence: float = 1.0`, `embedding: tuple[float, ...] \| None = None` |
| `domain/entities/column_enrichment.py` | `ColumnEnrichment` | same shape, column-scoped, plus `unit: str \| None` |
| `domain/entities/business_domain.py` | `BusinessDomain` | `datasource_name`, `domain_id: int \| None = None`, `name`, `description`, `provenance: Provenance = LLM`. Named `BusinessDomain`, not `Domain` — the latter collides with the architecture's own `domain/` layer name and would be confusing in every import line |
| `domain/entities/domain_member.py` | `DomainMember` | `domain_id`, `datasource_name`, `schema_name`, `object_name`, `membership_score: float = 1.0` |
| `domain/entities/metric.py` | `Metric` | `datasource_name`, `name`, `sql_expression`, `grain`, `unit: str \| None`, `default_filters: dict[str, str] = {}`, `provenance: Provenance = YAML` |
| `domain/entities/search_document.py` | `SearchDocument` | `datasource_name`, `schema_name`, `object_name`, `domain_name: str \| None`, `content`, `embedding: tuple[float, ...]` |
| `domain/entities/enrichment_field.py` | `EnrichmentField` | `kind: Literal["description","alias","unit"]`, `qualified_name` (object's or column's), `value: str`, `provenance: Provenance` — the uniform shape the three merge-time enrichers share |
| `domain/entities/semantic_overlay.py` | `SemanticOverlay`, `ObjectOverlay`, `ColumnOverlay`, `MetricOverlay`, `JoinHintOverlay` | validated shape of one `semantic/<datasource>.yaml` file (§8.3) |

All frozen Pydantic v2 models, consistent with existing entities. `ObjectEnrichment`,
`ColumnEnrichment`, `BusinessDomain`, and `Metric` all carry `Provenance` from Phase 3 — no new
provenance vocabulary needed, confirming the value object was named generically for exactly this
reuse.

### 3.2 New ports

```python
# domain/ports/chat_provider.py
class ChatProvider(Protocol):
    def complete(self, prompt: str, response_schema: type[T]) -> T: ...  # T bound to BaseModel

# domain/ports/embedding_provider.py
class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]: ...

# domain/ports/rerank_provider.py
class RerankScore(BaseModel):
    index: int
    score: float

class RerankProvider(Protocol):
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]: ...

# domain/ports/enrichment_reader.py
class EnrichmentReader(Protocol):
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]: ...
    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]: ...

# domain/ports/enrichment_writer.py
class EnrichmentWriter(Protocol):
    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None: ...
    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int: ...

# domain/ports/domain_writer.py
class DomainWriter(Protocol):
    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]: ...
    def write_members(self, members: Sequence[DomainMember]) -> int: ...

# domain/ports/domain_namer.py
class DomainNamer(Protocol):
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]: ...

# domain/ports/metric_writer.py
class MetricWriter(Protocol):
    def write(self, metrics: Sequence[Metric]) -> int: ...

# domain/ports/enricher.py
class Enricher(Protocol):
    key: ClassVar[str]
    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None: ...

# domain/ports/search_document_writer.py
class SearchDocumentWriter(Protocol):
    def compile(self, datasource_name: str) -> int: ...  # returns documents written

# domain/ports/comment_writer.py
class CommentWriter(Protocol):
    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None: ...
    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None: ...

# domain/ports/retriever.py
class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    datasource_name: str
    schema_name: str
    object_name: str
    domain_name: str | None
    score: float

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

`ChatProvider.complete` takes a Pydantic response model so every LLM call in this phase — object
profiling, domain naming — returns a typed, validated object rather than prose to parse. This is
what makes grounding failures a Pydantic `ValidationError` the caller can catch, not a silent
mis-parse.

`Retriever.search` takes a pre-computed `query_embedding` rather than embedding the query itself:
embedding is `EmbeddingProvider`'s job, called once by `RetrievalService`, so a `BM25 only`
configuration never pays for an embedding call it doesn't use.

### 3.3 New errors

```python
class EnrichmentError(DiscoveryError):
    """LLM object profiling or embedding could not complete."""

class DomainNamingError(DiscoveryError):
    """Fused clustering or LLM domain naming could not complete."""

class OverlayError(DiscoveryError):
    """semantic/<datasource>.yaml failed schema validation or referenced an unknown object."""

class CompileError(DiscoveryError):
    """genql_search_document could not be refreshed."""

class RetrievalError(GenqlError):
    """Hybrid retrieval or reranking could not complete. Not a DiscoveryError — this runs online."""
```

`OverlayError` carries the offending file path and the Pydantic validation errors so `genql semantic
overlay` can print exactly which YAML entry is wrong, matching how `UnknownDiscoveryStepError`
already reports "available" options rather than a bare exception message.

---

## 4. Registries

| Registry | Port | Registered now |
|---|---|---|
| `CHAT_PROVIDERS` | `ChatProvider` | `openrouter` |
| `EMBEDDING_PROVIDERS` | `EmbeddingProvider` | `openrouter` |
| `RERANK_PROVIDERS` | `RerankProvider` | `openrouter`, `cohere` |
| `ENRICHERS` | `Enricher` | `description`, `alias`, `unit` |
| `RETRIEVERS` | `Retriever` | `bm25`, `dense`, `hybrid_rrf`, `domain_scoped` |

`CLUSTERING_ALGORITHMS` (Phase 3, `repositories/graph/registry.py`) gains a fourth entry, `fused`,
implementing the same `ClusteringAlgorithm` protocol as `leiden`. `Registry[T].create(key, **kwargs)`
forwards whatever kwargs the caller passes for that specific key — it does not require every
registered class to share one constructor signature — so `FusedClusteringAlgorithm.__init__(self,
gds_provider, enrichment_reader)` coexists with `LeidenClusteringAlgorithm.__init__(self,
gds_provider)` in the same dict without either seeing the other's dependency. The composition root
gets a second builder function, `_build_domain_clustering_algorithm`, for the `fused` path, resolved
from a new `Settings.domain_clustering_algorithm: str = "fused"` — a second, independent setting
from `clustering_algorithm`, because `genql graph analyze` and `genql graph domains` run different
algorithms for different purposes and must be swappable independently.

`DomainNamer` is not registry-backed. Exactly one strategy exists (LLM-grounded naming from cluster
membership), and `ChatProviderRegistry` already makes the model underneath it swappable — a second
registry over a single implementation is indirection with no seam it earns.

`Settings` gains `chat_provider: str = "openrouter"`, `embedding_provider: str = "openrouter"`,
`rerank_provider: str = "openrouter"`, and `domain_clustering_algorithm: str = "fused"`, resolved at
the composition root exactly like `clustering_algorithm` already is.

---

## 5. Infrastructure

**`infrastructure/gateway/openrouter_client.py`** — a thin `httpx.Client` wrapper carrying the base
URL, API key, and a `post_json` helper with typed error translation (`OpenRouterError` → caught and
re-raised as the calling repository's domain error, same rule `CatalogAccessError` already follows
for `psycopg` exceptions). No `openai` SDK: OpenRouter's chat, embeddings, and (per the parent spec's
resolved risk) rerank surfaces are all plain JSON-over-HTTPS, and a dependency that exists only to
wrap three `POST` calls is not worth taking.

**`infrastructure/gateway/cohere_client.py`** — the same shape, pointed at Cohere's own `/v1/rerank`,
kept behind the `RerankProviderRegistry` seam the parent spec explicitly calls out as an escape
hatch if OpenRouter ever stops carrying `rerank-4-pro`.

**`infrastructure/catalog/comment_writer.py`** — `PostgresCommentWriter` runs `COMMENT ON TABLE` /
`COMMENT ON COLUMN` against the *warehouse* engine resolved from `DatasourceEngineProvider`, not the
semantic store engine. This is the one piece of infrastructure in this phase that writes to a
datasource other than GenQL's own — the reason write-back defaults off.

No new Neo4j infrastructure. Fused clustering reuses `GdsClientProvider` and `GraphCatalogSession`
from Phase 3 unchanged — it needs the same named, datasource-scoped graph projection, just with an
extra node property before clustering.

---

## 6. Repositories

**`repositories/gateway/chat_provider_repository.py`** — `OpenRouterChatProvider` posts a
chat-completion request with a JSON-schema response format derived from the caller's Pydantic model
(`model_json_schema()`), then validates the response body against that same model before returning
it, translating a validation failure into `EnrichmentError`.

**`repositories/gateway/embedding_provider_repository.py`** — `OpenRouterEmbeddingProvider` batches
texts into one embeddings request (OpenRouter's endpoint accepts a list) and returns vectors in
input order.

**`repositories/gateway/rerank_provider_repository.py`** — `OpenRouterRerankProvider` and
`CohereRerankProvider`, both implementing `RerankProvider.rerank`, differing only in endpoint shape.

**`repositories/semantic/enrichment_repository.py`** — `PostgresEnrichmentRepository` implements
both `EnrichmentReader` and `EnrichmentWriter` (one repository, one aggregate — `genql_object_
enrichment` and `genql_column_enrichment` are always read and written together for one object).
Writes are the same `ON CONFLICT ... DO UPDATE` upsert shape `PostgresCatalogWriterRepository`
already established, keyed on the enrichment tables' primary keys — re-running `object_profiling`
for an already-profiled object updates it rather than duplicating it.

**`repositories/semantic/domain_repository.py`** — `PostgresDomainRepository` implements
`DomainWriter`: upserts `genql_domain` by `(datasource_name, name)`, returning rows with `id`
populated (`RETURNING id`) so `write_members` can key off the id `write_domains` just assigned in the
same call.

**`repositories/semantic/metric_repository.py`** — `PostgresMetricRepository` implements
`MetricWriter`, same upsert shape keyed on `(datasource_name, name)`.

**`repositories/graph/fused_clustering_algorithm_repository.py`** — `FusedClusteringAlgorithm`
implements `ClusteringAlgorithm.detect`. Reads every object's FastRP `embedding` node property out
of Neo4j (already written by Phase 3's `FastRpNodeEmbedder`) and every object's text `embedding` out
of `EnrichmentReader.read_object_enrichments`, joined on `qualified_name`. Each 128-dim structural
vector and each 1536-dim text vector is L2-normalized independently before concatenation, so neither
block dominates the clustering purely because it has more dimensions or a larger natural scale — an
unnormalized concatenation would let the higher-magnitude block decide every cluster. `scikit-learn`
`KMeans` runs once per candidate `k` in `[Settings.domain_cluster_k_min,
Settings.domain_cluster_k_max]`, and the `k` with the best silhouette score is kept, matching the
parent spec's "k chosen by silhouette score" verbatim — GDS's own `kmeans` procedure has no
silhouette-driven search, which is why this runs in Python against vectors fetched into memory
rather than inside Neo4j. The winning assignment is written back onto Neo4j nodes as `domain_
cluster` (a different property from Leiden's `community_id`, since the two clusterings answer
different questions and a rebuild of one must not silently overwrite the other), and `detect`
returns the chosen `k`.

**`repositories/semantic/domain_namer_repository.py`** — `LlmDomainNamer` implements `DomainNamer`.
For each cluster, prompts `ChatProvider` with the member objects' names, types, and LLM-generated
descriptions, requesting a two-to-three-word business domain name and one-sentence description as a
structured `BusinessDomain`-shaped response.

**`repositories/semantic/enricher_repository.py`** — `DescriptionEnricher`, `AliasEnricher`,
`UnitEnricher`, one small class each, all sharing the same default rule ("an overlay value always
wins; absent an overlay, the discovered value passes through unchanged") and registered under
`ENRICHERS`. Three classes rather than one parameterized class because a future enricher — say, a
`synonym` kind — may need validation logic none of these three share, and the registry's whole
premise is that adding it costs one file, not a branch inside an existing one.

**`repositories/semantic/search_document_repository.py`** — `SearchDocumentCompiler` implements
`SearchDocumentWriter.compile`: for every object in the datasource, assembles `content` from the
object's name, type, description, alias, domain name, each column's name/description/unit, and up to
five sample values per column (from Phase 2's `genql_column_profile`) — the exact field list the
parent spec names for the BM25 text — embeds it, and upserts one `genql_search_document` row keyed
on `(datasource_name, schema_name, object_name)`.

**`repositories/semantic/bm25_retriever_repository.py`**, **`dense_retriever_repository.py`**,
**`hybrid_rrf_retriever_repository.py`** — three `Retriever` implementations over
`genql_search_document`. `Bm25Retriever` orders by `pg_search`'s `paradedb.score()`; `DenseRetriever`
orders by pgvector cosine distance; `HybridRrfRetriever` is the parent spec's "single SQL statement"
— one query with two ranked CTEs (BM25 rank, vector-distance rank) combined by reciprocal rank
fusion (`1 / (Settings.rrf_k + rank)` summed per document, `Settings.rrf_k = 60`, the standard
default from the RRF literature), so fusion happens in the database, not by round-tripping two
result sets through Python.

**`repositories/semantic/domain_scoped_retriever_repository.py`** — `DomainScopedRetriever`
implements `Retriever` by wrapping another `Retriever` instance (constructor-injected) and requiring
`domain_id` to be non-`None`, raising `RetrievalError` otherwise — it exists specifically for the
online pipeline's future "domain already resolved, now search only inside it" case, and refusing to
silently no-op when that precondition is missing is the point of giving it its own type.

---

## 7. Services

**`ObjectProfilingService`** (`services/semantic/object_profiling_service.py`) — takes a
`SemanticCatalogReader` (extended, see below), a `ChatProvider`, an `EmbeddingProvider`, and an
`EnrichmentWriter`. For one schema: reads objects, columns, and column profiles; for each object,
issues one grounded `ChatProvider.complete` call carrying the object's name, type, its columns with
types, its foreign keys, and up to `Settings.profile_sample_limit` sample values per column —
grounding is what the parent spec's Risk #1 says prevents description hallucination — producing an
`ObjectEnrichment` plus one `ColumnEnrichment` per column in a single structured response; embeds the
object description; writes both through `EnrichmentWriter`. One LLM call per object, not one per
object plus one per column, keeping cost aligned with the parent spec's cost model (§20: output
tokens are the expensive side, and grounding context is shared across an object's whole column list).

`SemanticCatalogReader` (Phase 3) gains `read_columns(ref) -> Sequence[Column]` and
`read_column_profiles(ref) -> Sequence[ColumnProfile]` — an incremental extension of an existing
port, not a new one, since profiling genuinely is "read structural metadata back out of the semantic
store," the port's existing job description.

**`DomainDiscoveryService`** (`services/semantic/domain_discovery_service.py`) — takes the `fused`
`ClusteringAlgorithm`, an `EnrichmentReader`, a `DomainNamer`, and a `DomainWriter`. `discover
(datasource_name) -> DomainDiscoveryReport`: runs fused clustering, reads back which objects landed
in which cluster (via the Neo4j `domain_cluster` property, read through a small `GraphCatalogSession`
query — no new port needed, this reuses the existing GDS driver plumbing), asks `DomainNamer` to name
each cluster, and writes the resulting domains and memberships. Mirrors `GraphAnalysisService`'s
shape exactly: resolve algorithms from the composition root, orchestrate, return a typed report.

**`SemanticOverlayService`** (`services/semantic/semantic_overlay_service.py`) — takes an
`EnrichmentReader`, an `EnrichmentWriter`, a `MetricWriter`, a `JoinPathWriter` (Phase 3, reused
as-is), and the three registered `Enricher`s. `apply(overlay: SemanticOverlay) -> OverlayReport`:
for every object/column entry in the overlay, reads the current discovered/LLM `EnrichmentField` for
each of `description`/`alias`/`unit`, runs it through the matching `ENRICHERS` entry alongside the
overlay's value, and writes back whichever value wins — always the overlay's, by the registered
merge rule, but going through the registry rather than an `if overlay is not None` inline keeps the
rule swappable per field kind later without touching this service. Metrics are validated (non-empty
`sql_expression`; real SQL-parse validation is explicitly deferred to Phase 5, where `sqlglot` is a
genuine dependency already — adding it two phases early for one weak check is not worth it) and
written via `MetricWriter`. Join hints become `JoinPath` rows with `provenance=YAML`, written via
the existing `JoinPathWriter`.

**`CompileService`** (`services/semantic/compile_service.py`) — takes a `SearchDocumentWriter` and,
only when `write_back=True` is passed, a `CommentWriter` plus a read of the just-compiled enrichment
rows. `compile(datasource_name, write_back=False) -> CompileReport`. Write-back loops the compiled
descriptions out to `COMMENT ON`; the default path never touches the warehouse at all.

**`RetrievalService`** (`services/semantic/retrieval_service.py`) — takes an `EmbeddingProvider`, a
resolved `Retriever` (whichever key `Settings.retriever` names), and a `RerankProvider`.
`search(datasource_name, query, top_k, domain_id=None) -> Sequence[SearchResult]`: embeds the query
once, calls the retriever, and if `Settings.rerank_enabled` reranks the retriever's document content
against the original query, reordering results by the returned scores. Reranking is skippable by
configuration alone — the parent spec's stated reason for giving it its own port.

---

## 8. Discovery, semantic overlay, and CLI

### 8.1 New discovery steps

**`ObjectProfilingStep`** (`discovery/steps/object_profiling_step.py`), registered as
`"object_profiling"`, sequenced after `graph_projection` — it needs nothing from the graph, but
running last among the per-schema steps means a failure here never blocks Phase 3's steps from
completing for that schema. Calls `ObjectProfilingService`.

Text embedding is folded into `ObjectProfilingService` itself (§7) rather than a separate discovery
step: the parent spec lists "text embeddings" as step 6 and "LLM object profiling" as step 5, but
splitting them into two steps would mean re-reading every object's just-written description from
Postgres a moment after writing it, for no benefit — embedding the description the service already
holds in memory is strictly simpler and costs nothing the two-step version would have saved.

### 8.2 Datasource-wide domain and semantic commands

Fused clustering, domain naming, YAML overlay, and compile are **not** discovery steps, for the same
reason Phase 3's clustering/embedding/join-path-mining aren't: all four are whole-datasource
operations that must run after every enabled schema has already been discovered and profiled, not
once per schema.

```
genql graph domains --datasource local
genql semantic overlay --datasource local
genql semantic compile --datasource local [--write-back]
genql semantic search --datasource local "<question>" [--top-k 10]
```

`graph domains` calls `DomainDiscoveryService.discover` and must run after `genql graph analyze`
(documented, not enforced — the same precedent `genql graph rebuild` already sets by depending on a
prior `genql discover`). `semantic overlay` loads and validates `semantic/<datasource>.yaml` (§8.3)
and calls `SemanticOverlayService.apply`; running it with no such file present is a no-op, not an
error, since not every datasource needs authored overrides. `semantic compile` calls
`CompileService.compile`, `--write-back` threading `write_back=True` through. `semantic search` is
the phase's end-to-end proof: it calls `RetrievalService.search` and prints ranked object names,
domains, and scores — the first command in GenQL that answers something resembling the product
question.

### 8.3 `semantic/<datasource>.yaml` shape

```yaml
datasource: local
objects:
  "tpcds.store_sales":
    description: "Point-of-sale line items for in-store purchases."
    business_alias: "store transactions"
    columns:
      ss_ext_sales_price:
        description: "Extended sales price before discount."
        unit: USD
metrics:
  - name: net_sales
    sql_expression: "ss_ext_sales_price - ss_ext_discount_amt"
    grain: line_item
    unit: USD
    default_filters: {}
join_hints:
  - source_object: "tpcds.store_sales"
    target_object: "tpcds.customer"
    path: ["tpcds.store_sales", "tpcds.customer"]
    weight: 0.5
```

One file per datasource — `semantic/<datasource_name>.yaml` — validated wholesale against
`SemanticOverlay` (a Pydantic model) before any row is written, so a typo anywhere in the file fails
the whole `overlay` run with a pointed error rather than partially applying. Object keys are fully
qualified (`"schema.object"`) to avoid a nested-mapping ambiguity about which schema an entry
belongs to.

---

## 9. Configuration

`Settings` gains:

```python
openrouter_api_key: str
cohere_api_key: str | None = None
chat_provider: str = "openrouter"
embedding_provider: str = "openrouter"
rerank_provider: str = "openrouter"
chat_model: str = "anthropic/claude-sonnet-5"
embedding_model: str = "openai/text-embedding-3-small"
embedding_dimension: int = 1536
rerank_model: str = "cohere/rerank-4-pro"
rerank_enabled: bool = True
domain_clustering_algorithm: str = "fused"
domain_cluster_k_min: int = 2
domain_cluster_k_max: int = 20
retriever: str = "hybrid_rrf"
rrf_k: int = 60
search_top_k: int = 10
```

Per the parent spec's §21 ("model choice is configuration, not architecture"), `chat_model` is a
plain string passed to whichever `ChatProvider` is resolved — nothing in this phase's code names a
model. `cohere_api_key` is optional because the default `rerank_provider` is `openrouter`, which
carries `rerank-4-pro` without a separate Cohere account; it becomes required only if `rerank_
provider` is switched to `cohere`, and that failure surfaces as a clear `MissingDatasourceSecret`-
shaped error at first use, not at process start.

---

## 10. Testing

**Unit** — `ObjectProfilingService`, `DomainDiscoveryService`, `SemanticOverlayService`,
`CompileService`, and `RetrievalService` against fake `ChatProvider`/`EmbeddingProvider`/
`RerankProvider`/repository ports — no database, no network, matching the existing strategy exactly.
Fakes return deterministic canned responses, so these tests assert orchestration (which port was
called with what, in what order, how a `ValidationError` becomes an `EnrichmentError`) rather than
model quality. The three `Enricher`s; `SemanticOverlay` YAML validation, including a deliberately
malformed fixture; the `fused` clustering registry entry resolves; `Settings` default resolution.

**Integration (testcontainers)** — migration 0005 upgrade/downgrade; `PostgresEnrichmentRepository`,
`PostgresDomainRepository`, `PostgresMetricRepository` against real Postgres; `SearchDocumentCompiler`
against a real ParadeDB, asserting the BM25 index and HNSW index both exist and both return results
for a seeded row; `Bm25Retriever`/`DenseRetriever`/`HybridRrfRetriever` against a small seeded
`genql_search_document` table, asserting hybrid ranking differs from either single-signal ranking on
a query engineered to favor one signal over the other; `FusedClusteringAlgorithm` against real Neo4j
+ GDS with a small fixture graph carrying both `embedding` and text-embedding-shaped node data,
asserting a chosen `k` and a `domain_cluster` property landing on every node.

**Real-provider integration (gated)** — one `OpenRouterChatProvider` call, one
`OpenRouterEmbeddingProvider` call, one rerank call against each of `openrouter` and `cohere`, each
skipped with a clear reason when its API key environment variable is unset. These are the only tests
in the suite that cost money or require network access, and they stay few by design.

**End-to-end** — `genql discover` → `genql graph analyze` → `genql graph domains` → `genql semantic
overlay` → `genql semantic compile` → `genql semantic search "<TPC-DS question>"` against
`local.tpcds` produces at least one non-empty result with a populated domain name, proving the whole
chain from raw catalog to a ranked answer to a text query.

---

## 11. Consequences for later phases

**Phase 5 (generation core)** reads `genql_search_document` through `RetrievalService` for schema
linking and few-shot context, and is where `sqlglot` first becomes a real dependency — at which
point `Metric.sql_expression` validation in `SemanticOverlayService` should be upgraded from a
non-empty-string check to an actual parse, closing the gap this phase deliberately leaves open.

**Phase 6 (ambiguity machinery)** adds `genql_rule`, `genql_query_log`/`genql_query_feature`, and the
synthetic ambiguity log this phase explicitly deferred; registers a query-frequency-weighted
`JOIN_PATH_STRATEGIES` entry per Phase 3's already-left seam; and is where `domain_scoped` first gets
a real caller — the online pipeline's domain-scoping stage, once it exists, resolves a domain id and
passes it straight through to `DomainScopedRetriever`.

**Phase 8 (API and evaluation)** exposes `RetrievalService.search` over SSE and is where the golden
set runner first has something to measure against — retrieval recall/precision on the curated
question set, independent of SQL generation quality.

---

## 12. Risks

**LLM-hallucinated descriptions poison everything downstream.** This is the parent spec's Risk #1,
restated because Phase 4 is where it first bites. Mitigation unchanged from the parent spec:
grounding on sampled values, `confidence` and `provenance` on every row, and YAML override always
available and always winning.

**Fused clustering quality depends on embedding scale normalization.** An unnormalized concatenation
of a 128-dim structural vector and a 1536-dim text vector lets whichever has larger natural magnitude
dominate every cluster, silently. Mitigation: L2-normalize each block independently before
concatenation (§6), and the end-to-end test (§10) asserts a non-trivial `domain_cluster` spread
rather than every object landing in one cluster, which is what an unnormalized fusion tends to
produce.

**OpenRouter rerank availability.** The parent spec already flags this as a resolved-but-watched
risk. Mitigation unchanged: `RerankProviderRegistry` carries a working `cohere` direct
implementation from day one, not as a future placeholder, so the fallback is one config change
(`Settings.rerank_provider = "cohere"` plus `cohere_api_key`), not a code change made under pressure
later.

**`genql_search_document` drift from its sources.** Enrichment, domain membership, and join paths
can all change after a compile without anyone re-running `semantic compile`. Mitigation: compile is
a single idempotent command over the current state of all its sources, the same shape as `genql
graph rebuild`'s answer to projection drift — staleness is always one command away from resolved,
never silently accumulating.

**Cost of profiling a wide schema.** One `ChatProvider.complete` call per object means TPC-DS's ~25
objects are cheap, but a schema with thousands of objects is not. Mitigation: `provenance` and
`discovered_at` make incremental re-profiling possible in principle (skip objects already profiled
unless forced) — not built in this phase, since nothing yet needs it, but the schema does not block
adding it later as one new CLI flag.
