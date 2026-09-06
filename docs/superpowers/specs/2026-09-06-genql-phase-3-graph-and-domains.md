# GenQL Phase 3 — Graph and Domains

**Status:** design approved, pending implementation plan
**Date:** 2026-09-06
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

---

## 1. Purpose

Phases 1–2.5 built structural discovery: objects, columns, constraints, and profiles land in the
semantic store, keyed on `datasource.schema.object[.column]`. Nothing yet turns the foreign-key
graph implicit in `genql_constraint` into something GenQL can reason over topologically — which
objects cluster together, which pairs of tables actually join, and how "far" one object is from
another.

Phase 3 projects that structure into Neo4j and runs graph algorithms over it: community detection
(Leiden) finds object clusters from FK topology alone, node embeddings (FastRP) turn that topology
into vectors later phases can combine with text, and join-path mining finds the FK route between
any two objects so query generation never has to guess a join.

### Goals

- Every discovered object and its FK relationships are projected into Neo4j, scoped by datasource.
- Leiden communities and FastRP embeddings are computed per datasource and written back onto nodes.
- Every pair of FK-reachable objects has a mined shortest join path, persisted to Postgres so
  retrieval and generation never touch Neo4j on the query path.
- The projection is derived and rebuildable from Postgres alone, at any time, without re-running
  discovery against the warehouse.

### Non-goals

- **Fused clustering and domain naming** (spec pipeline steps 7–8). Both consume text embeddings,
  which Phase 4 produces. Clustering on FastRP alone and calling it a domain would be a different,
  weaker feature wearing the same name — it is not built here.
- **Query-log-weighted join paths.** Frequency-weighted edges (spec step 9's stated intent) need a
  query log, which does not exist before Phase 5/6. Paths are mined on the FK graph with uniform
  edge weight instead; the weight *source* is a registry seam so Phase 6 can register a
  query-frequency-weighted strategy with no call-site change.
- **View-dependency edges.** The parent spec lists these alongside FK edges, but no catalog reader
  in this codebase reads `pg_depend`/`information_schema.view_table_usage` yet — that is a
  warehouse-reading capability this phase does not add. Only FK edges are projected.
- **Cross-datasource graphs.** One Neo4j graph exists per datasource, matching Phase 2.5's ruling
  that FK edges cannot cross a database boundary.
- **Neo4j multi-database separation.** Neo4j 5 Community Edition supports one database; datasources
  are separated by a `datasource_name` node property and Cypher-side filtering, not by database.

---

## 2. Graph model

Every projected node is one `DatabaseObject`, labeled `:Object`, keyed on its existing
`qualified_name` (`datasource.schema.object`) rather than a composite key: Neo4j 5 Community
Edition only supports a uniqueness constraint on a single property, not the composite node-key
constraints Enterprise Edition offers. `qualified_name` is already computed on the entity, so this
costs nothing.

```
(:Object {qualified_name, datasource_name, schema_name, object_name, object_type, row_estimate,
          community_id, embedding})
```

`community_id` and `embedding` start absent and are populated by the Leiden and FastRP steps
respectively; they are never written by projection itself.

Every `FOREIGN_KEY` constraint becomes one directed edge from the constrained object to the object
it references:

```
(:Object)-[:REFERENCES {constraint_name, column_names, referenced_column_names}]->(:Object)
```

`PRIMARY_KEY` and `UNIQUE` constraints project nothing — they carry no relationship meaning.

A GDS algorithm needs an in-memory graph scoped to one datasource. Since nodes are not separated by
database, each analysis run projects a **named, Cypher-filtered GDS graph** —
`gds.graph.project.cypher` selecting only `:Object` nodes and `:REFERENCES` edges whose
`datasource_name` matches — under a name derived from the datasource (`graph_<datasource_name>`),
and always drops it in a `finally` block so a crashed run cannot leave a stale entry in the GDS
graph catalog to collide with the next one.

---

## 3. Semantic store changes

### 3.1 New table

```sql
genql.genql_join_path (
    datasource_name         TEXT NOT NULL,
    schema_name             TEXT NOT NULL,
    source_object           TEXT NOT NULL,
    target_object           TEXT NOT NULL,
    path                    TEXT[]      NOT NULL,
    weight                  DOUBLE PRECISION NOT NULL,
    provenance              TEXT        NOT NULL DEFAULT 'discovered',
    discovered_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (datasource_name, schema_name, source_object, target_object),
    FOREIGN KEY (datasource_name, schema_name)
        REFERENCES genql.genql_schema (datasource_name, schema_name) ON DELETE CASCADE
)
```

`path` is the full object sequence from source to target inclusive, in join order. Removing a
schema cascades to its mined paths, the same rule Phase 2.5 established for every catalog table.

This is the one table this phase adds from the parent spec's enrichment layer
(`genql_object_enrichment`, `genql_domain`, `genql_metric`, etc. all wait on Phase 4's LLM steps).

### 3.2 Migration 0004

Purely additive — one `CREATE TABLE`, no existing table changes, no backfill. `downgrade()` drops
it.

### 3.3 Community and embedding storage

`community_id` and `embedding` are **not** duplicated into Postgres. They live only as Neo4j node
properties, consistent with "the projection is derived... may be dropped and rebuilt at any time."
Phase 4's fused clustering reads FastRP vectors directly out of Neo4j when it needs them; nothing
downstream in this phase needs them out of the graph.

---

## 4. Domain

### 4.1 New value objects and entities

| File | Type | Contents |
|---|---|---|
| `domain/value_objects/provenance.py` | `Provenance` (`StrEnum`) | `DISCOVERED`, `LLM`, `YAML` — the vocabulary the parent spec assigns to every enrichment-layer row, introduced here since `genql_join_path` is the first such table built |
| `domain/entities/join_path.py` | `JoinPath` | `datasource_name`, `schema_name`, `source_object`, `target_object`, `path: tuple[str, ...]`, `weight: float`, `provenance: Provenance = Provenance.DISCOVERED` |

Both frozen Pydantic v2 models, consistent with existing entities.

### 4.2 New ports

```python
# domain/ports/semantic_catalog_reader.py
class SemanticCatalogReader(Protocol):
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]: ...
    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]: ...

# domain/ports/graph_writer.py
class GraphWriter(Protocol):
    def write_objects(self, objects: Sequence[DatabaseObject]) -> int: ...
    def write_edges(self, constraints: Sequence[Constraint]) -> int: ...

# domain/ports/clustering_algorithm.py
class ClusteringAlgorithm(Protocol):
    def detect(self, datasource_name: str) -> int: ...  # returns communities found

# domain/ports/node_embedder.py
class NodeEmbedder(Protocol):
    def embed(self, datasource_name: str) -> int: ...  # returns nodes embedded

# domain/ports/join_path_miner.py
class JoinPathMiner(Protocol):
    def mine(self, datasource_name: str) -> Sequence[JoinPath]: ...

# domain/ports/join_path_writer.py
class JoinPathWriter(Protocol):
    def write(self, paths: Sequence[JoinPath]) -> int: ...
```

`SemanticCatalogReader` is the missing read side of `CatalogWriter` — nothing before this phase
reads catalog rows back out of the semantic store. It is what lets graph projection run from
Postgres alone, independent of a live discovery run against the warehouse, which is what makes
`graph rebuild` (section 9) possible.

`ClusteringAlgorithm` and `NodeEmbedder` take a datasource name rather than a `QueryScope`: Leiden
and FastRP run once over a datasource's whole graph, not per schema — schemas are a projection-time
concept, not an analysis-time one.

### 4.3 New errors

`GraphProjectionError` and `GraphAnalysisError`, both under `DiscoveryError` (projection is a
discovery-pipeline concern; analysis is triggered separately but fails the same way — a typed error
a caller can catch without inspecting a message string).

---

## 5. Registries

Three new registries, following the existing `DISCOVERY_STEPS` / `CATALOG_READERS` pattern —
module-level `Registry[T]` plus a package `__init__` importing implementations for their decorator
side effect. All three live in `repositories/graph/registry.py`, keyed by algorithm name.

| Registry | Port | Registered now |
|---|---|---|
| `CLUSTERING_ALGORITHMS` | `ClusteringAlgorithm` | `leiden` |
| `NODE_EMBEDDERS` | `NodeEmbedder` | `fastrp` |
| `JOIN_PATH_STRATEGIES` | `JoinPathMiner` | `weighted_shortest_path` |

`CLUSTERING_ALGORITHMS` is the parent spec's already-named `ClusteringRegistry`; `louvain` (named
alongside `leiden` in the parent spec, kept for comparison) may be added later as one file with no
call-site change. `kmeans` and `fused` wait on Phase 4's text embeddings. Phase 6 adds a
`query_weighted_shortest_path` entry to `JOIN_PATH_STRATEGIES` the same way, once a query log
exists to weight edges from.

`Settings` gains `clustering_algorithm: str = "leiden"`, `node_embedding_algorithm: str = "fastrp"`,
and `join_path_strategy: str = "weighted_shortest_path"`, resolved at the composition root — the
same pattern `scope_resolver` already establishes.

---

## 6. Infrastructure

**`Neo4jDriverProvider`** (`infrastructure/graph/neo4j_driver_provider.py`) wraps
`neo4j.GraphDatabase.driver(uri, auth=(user, password))` as a process-lifetime singleton, built
from `Settings.neo4j_uri/neo4j_user/neo4j_password` at the composition root — the same shape as
`DatasourceEngineProvider`, minus the per-datasource dimension, since one Neo4j instance serves
every datasource.

**`GdsClientProvider`** (`infrastructure/graph/gds_client_provider.py`) wraps
`graphdatascience.GraphDataScience`, constructed from the same driver settings. GDS operations
(`gds.graph.project.cypher`, `gds.leiden.write`, `gds.fastRP.write`, `gds.shortestPath.dijkstra`)
are called only from `repositories/graph/`, never from `services/`.

**`GraphCatalogSession`** (`infrastructure/graph/graph_catalog_session.py`) is a small context
manager: given a datasource name, it projects the named Cypher-filtered GDS graph on `__enter__`
and drops it on `__exit__` regardless of outcome. Every repository under `repositories/graph/` that
runs a GDS algorithm uses it, so "always drop the projection" is enforced in one place instead of
copy-pasted into three repositories.

---

## 7. Repositories

All new, none change existing repositories.

**`repositories/semantic/semantic_catalog_reader_repository.py`** — `PostgresSemanticCatalogReader`
implements `SemanticCatalogReader`: `SELECT` from `genql_object`/`genql_constraint` filtered on
`(datasource_name, schema_name)`.

**`repositories/semantic/join_path_writer_repository.py`** — `PostgresJoinPathWriterRepository`
implements `JoinPathWriter`: idempotent upsert into `genql_join_path`, same
`ON CONFLICT ... DO UPDATE` shape `PostgresCatalogWriterRepository` already uses.

**`repositories/graph/graph_writer_repository.py`** — `Neo4jGraphWriterRepository` implements
`GraphWriter`. `write_objects` runs one `UNWIND $rows AS row MERGE (o:Object {qualified_name:
row.qualified_name}) SET o += row` per batch; `write_edges` `MATCH`es source and target by
`qualified_name` and `MERGE`s the `:REFERENCES` relationship, so re-running projection for an
already-projected schema changes nothing.

**`repositories/graph/clustering_algorithm_repository.py`** — `LeidenClusteringAlgorithm` opens a
`GraphCatalogSession`, runs `gds.leiden.write(graph, writeProperty="community_id")`, and returns the
community count from the algorithm's own result row.

**`repositories/graph/node_embedder_repository.py`** — `FastRpNodeEmbedder` opens a
`GraphCatalogSession`, runs `gds.fastRP.write(graph, writeProperty="embedding",
embeddingDimension=128)`, and returns the node count.

**`repositories/graph/join_path_miner_repository.py`** — `WeightedShortestPathJoinPathMiner` opens
a `GraphCatalogSession`, enumerates object pairs that are reachable but not directly
FK-connected, and runs `gds.shortestPath.dijkstra` between each pair with uniform relationship
weight 1.0, keeping only paths within a configurable hop limit (`Settings.max_join_path_hops = 4`)
to bound the pair count on wide schemas. Each result becomes one `JoinPath` with
`provenance=DISCOVERED`.

---

## 8. Services

**`GraphProjectionService`** (`services/graph/graph_projection_service.py`) — takes a
`SemanticCatalogReader` and a `GraphWriter`. `project(ref: SchemaRef) -> GraphProjectionReport`
reads that schema's objects and FK constraints back from Postgres and writes them into Neo4j.
Exactly the `CatalogScanService` shape: read via one port, write via another, return a typed
report. Unit-testable against fakes with no database and no Neo4j.

**`GraphAnalysisService`** (`services/graph/graph_analysis_service.py`) — takes a
`ClusteringAlgorithm`, a `NodeEmbedder`, a `JoinPathMiner`, and a `JoinPathWriter`.
`analyze(datasource_name: str) -> GraphAnalysisReport` runs clustering, then embedding, then join-
path mining and persists the mined paths, returning counts of each. The three algorithm ports are
resolved from their registries at the composition root using the `Settings` keys from section 5,
so swapping `leiden` for `louvain` is a config change, not a code change.

---

## 9. Discovery and CLI

**`GraphProjectionStep`** (`discovery/steps/graph_projection_step.py`) is a normal `DiscoveryStep`,
registered in `DISCOVERY_STEPS` as `"graph_projection"`, sequenced immediately after
`catalog_scan` — it needs that schema's objects and constraints already committed to Postgres, and
gains nothing from waiting for `data_profiling`. It calls `GraphProjectionService.project(ctx.ref)`.
Like every step, a `DiscoveryError` becomes a failed `StepResult` rather than aborting the run.

```
genql graph analyze --datasource local
genql graph rebuild --datasource local
```

Both are Typer commands under `cli/commands/graph.py`. `analyze` resolves the datasource, then
calls `GraphAnalysisService.analyze`. `rebuild` re-runs `GraphProjectionService.project` for every
enabled `SchemaRegistration` under that datasource — reading only from Postgres, never touching the
warehouse — which is the concrete implementation of "rebuild is a single idempotent command"
mentioned as the parent spec's mitigation for projection drift.

---

## 10. Configuration

`Settings` gains `clustering_algorithm: str = "leiden"`, `node_embedding_algorithm: str = "fastrp"`,
`join_path_strategy: str = "weighted_shortest_path"`, and `max_join_path_hops: int = 4`. The three
existing `neo4j_*` fields are unchanged — they were added in Phase 1 in anticipation of this phase
and need no adjustment.

---

## 11. Testing

**Unit** — `GraphProjectionService` and `GraphAnalysisService` against fake ports, no database and
no Neo4j; `GraphProjectionStep`; the three new registries; `Settings` default resolution.

**Integration (VM compose stack, testcontainers)** — `Neo4jGraphWriterRepository` idempotency
(projecting the same schema twice leaves the same node and edge count); `LeidenClusteringAlgorithm`
and `FastRpNodeEmbedder` against a real Neo4j with GDS, asserting `community_id` and `embedding`
land on nodes; `WeightedShortestPathJoinPathMiner` against the TPC-DS FK graph, asserting a known
multi-hop path (e.g. `store_sales` → `date_dim` via a non-adjacent dimension) is found;
`PostgresJoinPathWriterRepository` and `PostgresSemanticCatalogReader` against real Postgres;
migration 0004 upgrade/downgrade.

**End-to-end** — `genql discover` followed by `genql graph analyze` against `local.tpcds` produces
at least one Leiden community, an embedding on every projected node, and at least one row in
`genql_join_path`.

---

## 12. Consequences for later phases

**Phase 4 (semantic store and retrieval)** reads FastRP embeddings directly from Neo4j to
concatenate with text embeddings for fused clustering, and joins against `genql_join_path` when
building `genql_search_document` so retrieval can bias toward validated join paths without a graph
round-trip at query time.

**Phase 6 (ambiguity machinery / query log)** registers a `query_weighted_shortest_path` entry in
`JOIN_PATH_STRATEGIES`, built from `pg_stat_statements` join frequency, and switches
`Settings.join_path_strategy` to it. No call site changes; `genql graph analyze` re-mines with the
new weights on the next run.

---

## 13. Risks

**Neo4j Community Edition has no composite node-key constraint.** Mitigation: nodes are keyed on
the single `qualified_name` property, which already exists on `DatabaseObject`, and carries a
standard Community-compatible uniqueness constraint.

**Join-path combinatorial blowup on wide schemas.** Mining every reachable pair is quadratic in
object count. Mitigation: `Settings.max_join_path_hops` bounds the search, and only pairs without a
direct FK edge are mined — direct edges need no mined path.

**GDS graph-catalog collisions.** A crashed analysis run could leave a named graph projection
behind to collide with the next run. Mitigation: `GraphCatalogSession` drops the projection in a
`finally` block, and projection names are derived from the datasource name, so two datasources can
never collide with each other either.

**Projection/source drift.** A derived store can fall behind Postgres. Mitigation: `genql graph
rebuild` is idempotent and reads only from Postgres, so drift is always one command away from
resolved, matching the parent spec's stated mitigation for this exact risk.
