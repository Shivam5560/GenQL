# GenQL — Enterprise NL2SQL with Semantic Enrichment

**Status:** design approved, pending implementation plan
**Date:** 2026-09-05

---

## 1. Purpose

GenQL is an enterprise natural-language-to-SQL system built on the premise that production
NL2SQL fails on *business meaning*, not SQL syntax. Its central architectural commitment is that
semantic enrichment is **shared infrastructure consumed by every pipeline stage**, not prompt glue
assembled per request.

The system is split into an **offline enrichment path** and an **online execution path**, joined by
a **semantic store**. The offline path may improve continuously without making the serving path
brittle; the serving path reads only compiled artifacts. The correctness test for this separation:
*with every LLM provider unreachable, retrieval and schema linking still function.*

### Goals

- Resolve ambiguous business intent before generating SQL, using discovered and authored semantics.
- Discover schema meaning automatically from catalog, data, structure, and query behaviour.
- Generate dialect-correct SQL, validate it statically and against live data, and repair it.
- Rewrite correct SQL into *efficiently executable* SQL, and learn which rewrites help.
- Ask a clarifying question when uncertainty is genuinely high, rather than guessing.
- Remain extensible along every axis without modification to existing call sites.

### Non-goals

- Public leaderboard evaluation. Spider 2.0, BIRD, and Archer are not run. A small golden set and
  an ablation harness substitute for benchmark chasing.
- Local model serving or fine-tuning. The development machine is an 8 GB M1.
- A React frontend in the initial phases. Deferred until the engine and SSE contract are stable.
- Write operations against the target warehouse. GenQL is strictly read-only.

---

## 2. Research basis

The design derives from four Oracle publications and current benchmark literature. Full extracted
sources are retained in the session research digest.

**"OCI NL2SQL: Building an Enterprise-Ready NL2SQL System with Semantic Enrichment"** (2026-03-27)
establishes the offline/online split, the semantic store, and enrichment at three levels — schema
(descriptions, example values, join keys, units, aliases), organizational (metric definitions,
glossary, fiscal calendars, territory mappings, default filters, policy constraints), and
behavioural (mined query logs). It names four failure classes GenQL must address directly:
ambiguous intent; business knowledge absent from the schema; physical modelling variation
(`revenue + currency_code` versus materialized `revenue_usd`; refunds as negative facts versus
adjustment rows); and context sensitivity (current date, freshness, identity, fiscal calendar,
locale).

**SOMA-SQL** (2026-04-23), Oracle's Spider 2.0-Lite leader at 72.02% EX@1, supplies the online
algorithm: offline synthetic ambiguity-aware query logs retrieved as few-shot context; structured
planning producing multiple candidate SQLs representing alternative interpretations; a critique
phase emitting a structured defect report before execution; and **ambiguity-driven probing** —
diffing candidates, mapping differences to intent/schema/value dimensions, and issuing targeted
probe queries whose results decide between interpretations. The probing step is the distinguishing
idea: peers such as CHASE-SQL and XiYan-SQL select candidates with a learned selector, whereas
probing lets the data arbitrate.

**Schema Discovery Agent** (2026-07-06) supplies the offline pipeline: catalog scan, per-column
value profiling, FK/dependency graph construction, Louvain community detection, LLM object
profiling grounded on sampled values, embedding, K-Means, cluster merge at cosine 0.75, LLM domain
naming, and write-back of mappings and `COMMENT ON` statements. Reported throughput: 380 objects
and 4,200 columns in roughly 142 seconds, yielding domain-scoped retrieval that reduces 380
candidate tables to 28–42.

**"Best practices to improve NL2SQL accuracy with Select AI"** (2026-06-22) supplies governance:
comments, annotations, and constraints as explicit prompt-context controls; object allowlists with
enforcement that generated SQL touches only permitted objects; and a feedback vector index in which
corrected SQL is retrieved by similarity as a hint. It also warns that agent memory and trace
stores living outside the database become ungoverned **shadow data repositories** — a constraint
GenQL honours by keeping conversation checkpoints, traces, and feedback in its own Postgres.

GenQL departs from the sources in two deliberate places. Oracle used Louvain; GenQL uses **Leiden**,
which corrects Louvain's known production of internally disconnected communities. Oracle merged
structural and semantic clusters post-hoc at a hand-tuned cosine threshold; GenQL additionally
computes **graph-topology-aware embeddings (FastRP)** so structural signal participates in the
clustering itself rather than only in a merge rule.

---

## 3. Architecture

```
OFFLINE — Discovery Pipeline                  ONLINE — Query Pipeline (LangGraph StateGraph)
────────────────────────────                  ─────────────────────────────────────────────
 1  catalog scan                               1  intent classification
 2  data profiling                             2  ambiguity gate ──interrupt()──▶ clarify
 3  graph projection → Neo4j                   3  domain scoping
 4  Leiden communities + FastRP                4  hybrid retrieval (BM25 ⊕ dense, RRF)
 5  LLM object profiling                       5  schema linking
 6  text embeddings                            6  natural-language planning
 7  fused clustering                           7  N candidate SQL generation
 8  domain naming                              8  static validation (sqlglot)
 9  join-path mining                           9  critique → structured defect report
10  query-log mining                          10  ambiguity probing
11  synthetic ambiguity log                   11  candidate selection
12  YAML overlay merge                        12  guarded execution
13  compile + COMMENT ON write-back           13  rewrite / optimize
                    │                         14  response + provenance + feedback
                    └────▶  SEMANTIC STORE  ◀──────────┘
                    ParadeDB/Postgres (system of record) + Neo4j (derived projection)
```

The offline path is a linear, resumable, registry-driven runner with per-step SSE progress.
LangGraph is deliberately *not* used there: the path has no branching, no interrupts, and no
conversational state, and a plain runner gives better resume semantics.

The online path is a LangGraph `StateGraph` because it requires conditional routing, replanning on
failure, human interrupts for clarification, and durable multi-turn state.

---

## 4. Layered architecture

Dependency flows in exactly one direction. This is the project's primary structural constraint.

```
   api/            controllers — HTTP and SSE transport only. DTO in, DTO out. No logic.
     ↓
   services/       orchestration and business rules. Depends on ports, never on adapters.
     ↓
   domain/         entities, value objects, ports (Protocols), errors. No I/O. Imports nothing.
     ↑
   repositories/   ALL SQL. Returns domain models, never rows or cursors.
   infrastructure/ adapters implementing domain ports.
```

**Rules**

1. `domain/` imports no other GenQL package and performs no I/O.
2. `services/` imports `domain/` only. It may not import `psycopg`, `sqlalchemy`, `neo4j`, any
   HTTP client, or any `repositories`/`infrastructure` module. It receives dependencies as
   `Protocol`-typed ports through constructor injection.
3. **No SQL is written or executed outside `repositories/`.** Services that need data call a
   repository port. This is non-negotiable and mechanically enforced.
4. `api/` contains controllers that translate DTO ↔ domain and delegate to a service. Controllers
   contain no branching business logic.
5. `infrastructure/` and `repositories/` may import third-party libraries freely; they implement
   ports declared in `domain/ports/`.
6. Construction happens only in `composition_root.py`. No module instantiates its own dependencies.

**Enforcement.** These rules are checked in CI by `import-linter` layered and forbidden contracts,
so a violation fails the build rather than surviving review. Additional gates: `ruff` (lint and
format), `mypy --strict`, and a pre-commit hook capping files at 250 lines to sustain
single-responsibility decomposition. One class per file; one action per file.

**Dependency injection** uses `dependency-injector` with declarative containers, singleton and
factory providers, configuration injection, and FastAPI wiring.

---

## 5. Registries

Extension along any axis is *registration*, never modification. A generic `Registry[T]` provides
decorator-based registration plus entry-point discovery for out-of-tree plugins. Each registry is
keyed by name and typed against a `Protocol` declared in `domain/ports/`.

| Registry | Port | Initial implementations |
|---|---|---|
| `DialectRegistry` | `SqlDialect` | postgres (snowflake, bigquery, oracle later) |
| `ChatProviderRegistry` | `ChatProvider` | openrouter |
| `EmbeddingProviderRegistry` | `EmbeddingProvider` | openrouter |
| `RerankProviderRegistry` | `RerankProvider` | openrouter, cohere |
| `RetrieverRegistry` | `Retriever` | bm25, dense, hybrid_rrf, domain_scoped |
| `DiscoveryStepRegistry` | `DiscoveryStep` | the thirteen offline steps |
| `PipelineStageRegistry` | `PipelineStage` | the fourteen online stages |
| `EnricherRegistry` | `Enricher` | description, alias, unit, metric, join_hint |
| `GuardrailRegistry` | `Guardrail` | statement_kind, object_allowlist, forbidden_function, limit_injection |
| `RewriteRuleRegistry` | `RewriteRule` | predicate_pushdown, redundant_join_elimination, cte_materialization, projection_pruning |
| `ProbeStrategyRegistry` | `ProbeStrategy` | intent, schema, value |
| `ClusteringRegistry` | `ClusteringAlgorithm` | leiden, louvain, kmeans, fused |
| `TracerRegistry` | `TracerPort` | structlog (phoenix later) |

Adding a SQL dialect, an LLM gateway, a guardrail, or a rewrite rule is one new file plus one
decorator. No existing file changes.

---

## 6. Technology stack

| Concern | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.12 via `uv` | 3.13 retains data-ecosystem gaps; `uv` already present |
| Database | **ParadeDB 0.25.6 on PostgreSQL 18** | `pg_search` gives BM25 over Tantivy natively; pgvector alongside. Hybrid retrieval with RRF is a single SQL statement. PG18 adds async I/O and btree skip scan |
| Driver | psycopg 3, SQLAlchemy 2.0 Core, Alembic | Core rather than ORM for query-path control; confined to `repositories/` |
| Graph | Neo4j + Graph Data Science, via `neo4j` and `graphdatascience` | Leiden, FastRP, node similarity, weighted shortest path. A **derived projection**, rebuildable from Postgres |
| SQL intelligence | **sqlglot** | Parse, transpile across 30+ dialects, `qualify` normalization, `annotate_types`, column lineage, AST visitors for guardrails and rewrites |
| LLM gateway | **OpenRouter** | Chat, embeddings, and rerank behind one key with no infrastructure to manage. LiteLLM and Bifrost are self-hosted and therefore excluded; Portkey is mid-acquisition by Palo Alto Networks; Helicone is in maintenance |
| Embeddings | `text-embedding-3-small` | Via gateway |
| Rerank | `rerank-v4.0-pro` | Via gateway if carried, otherwise Cohere direct through `RerankProviderRegistry` |
| Orchestration | **LangGraph 1.2 `StateGraph`** | Conditional routing, `interrupt()` for clarification, `PostgresSaver` checkpoints |
| API | FastAPI, uvicorn, `sse-starlette` | Per-stage SSE streaming is a first-class requirement |
| DTOs and config | Pydantic v2, pydantic-settings | Typed stage contracts and structured LLM outputs |
| DI | `dependency-injector` | Declarative containers with FastAPI wiring |
| Observability | `structlog` now; Phoenix later behind `TracerPort` | Traces persisted to Postgres, not an external store |
| Testing | pytest, pytest-asyncio, testcontainers, hypothesis, vcr | Real ParadeDB and Neo4j; recorded LLM calls |
| Enforcement | import-linter, ruff, mypy strict, 250-line file cap | |
| Local infra | Docker Compose: paradedb, neo4j, api | ~2 GB total, fits 8 GB |

**LangGraph and the layering.** Graph nodes are thin adapters: each resolves a service from the
container and calls one method. Business logic never lives in a node. LangGraph owns control flow
only — edges, conditional routing, interrupts, checkpointing. Services remain unit-testable with no
graph present; the graph is tested for routing alone.

**Concurrency.** LangGraph checkpoints are not distributed-lock-safe; concurrent resumes of one
`thread_id` are uncoordinated. GenQL takes a Postgres advisory lock keyed on the thread for the
duration of a turn.

---

## 7. Semantic store schema

All tables live in a `genql` schema inside the same ParadeDB instance as the target warehouse
during development, and in a dedicated database in deployment. Alembic manages migrations for
these tables only; GenQL never migrates the warehouse.

**Catalog layer** (raw discovery)
`genql_object`, `genql_column`, `genql_column_profile`, `genql_constraint`.
Profiles carry distinct count, null fraction, min/max, up to five sample values, and an inferred
semantic type. Sample values are what let a column named `TYPE` with values
`[CREDIT, DEBIT, TRANSFER]` be understood as a payment transaction type.

**Enrichment layer** (generated, then overridden)
`genql_object_enrichment`, `genql_column_enrichment`, `genql_domain`, `genql_domain_member`,
`genql_join_path`, `genql_metric`, `genql_rule`.
Every enrichment row carries `provenance` (`discovered` | `llm` | `yaml`) and `confidence`. A YAML
overlay row always wins on merge. `genql_metric` holds metric name, SQL expression, grain, unit,
and default filters. `genql_rule` holds fiscal calendar rules, default filters, freshness cutoffs,
and policy constraints.

**Behavioural layer**
`genql_query_log`, `genql_query_feature`, `genql_example`, `genql_ambiguity_case`.
Query features are extracted with sqlglot: tables touched, join pairs, predicates, aggregate
functions, and time grain. `genql_example` distinguishes `real`, `synthetic`, and
`ambiguity_variant` examples. `genql_ambiguity_case` stores the SOMA-SQL clarification cases —
dimension, options, resolution, and explanation.

**Retrieval layer**
`genql_search_document` is a materialized denormalization of objects, columns, domains, and metrics
carrying a text field with a `pg_search` BM25 index and a `vector` column with an HNSW index.
Hybrid retrieval reads this one table.

**Feedback and runtime**
`genql_feedback` (question, generated SQL, corrected SQL, verdict, guidance), `genql_trace`
(session, stage, latency, tokens, cost), and the LangGraph `PostgresSaver` checkpoint tables.

---

## 8. Offline discovery pipeline

Thirteen registered steps. Each declares its inputs and outputs, is individually resumable, and
emits SSE progress. Steps 5, 8, and 11 are the only ones requiring an LLM.

1. **Catalog scan** — `information_schema` and `pg_catalog` for tables, views, materialized views,
   columns, types, primary keys, foreign keys, and view dependencies.
2. **Data profiling** — per column: distinct count, null fraction, min/max, up to five sample
   values, and inferred semantic type. Sampled with `TABLESAMPLE` on large tables.
3. **Graph projection** — objects as nodes, foreign keys and view dependencies as edges, written to
   Neo4j. The projection is derived and may be dropped and rebuilt at any time.
4. **Leiden communities and FastRP embeddings** — Neo4j GDS. Leiden supersedes the Louvain step in
   the source pipeline. FastRP produces topology-aware node embeddings.
5. **LLM object profiling** — prompt carries object name, type, columns with types, foreign keys,
   and the sampled values from step 2. Produces plain-English table and column descriptions,
   business aliases, and units. Grounding on sampled values is what prevents description
   hallucination.
6. **Text embeddings** — profiles embedded with `text-embedding-3-small`, stored in pgvector.
7. **Fused clustering** — text embeddings concatenated with FastRP embeddings, clustered with
   *k* chosen by silhouette score. Structural signal participates in clustering rather than only
   in a post-hoc merge. Louvain and pure K-Means remain available through `ClusteringRegistry` for
   comparison.
8. **Domain naming** — LLM assigns a two-to-three word business domain name per cluster from the
   member objects and their profiles.
9. **Join-path mining** — weighted shortest paths in Neo4j between frequently co-queried object
   pairs. Edge weights derive from query-log join frequency, so mined paths reflect how analysts
   actually join rather than only what the FK graph permits. Each candidate path is validated by
   executing a `LIMIT 1` probe before being persisted.
10. **Query-log mining** — `pg_stat_statements` plus any imported corpus, normalized and parsed
    with sqlglot into join pairs, predicates, aggregate functions, and time grains.
11. **Synthetic ambiguity log** — LLM generates question/SQL pairs aligned to the schema, then
    produces deliberate variants along intent, schema, and value dimensions, each converted into a
    clarification case with options, resolution, and explanation.
12. **YAML overlay merge** — `semantic/*.yaml` is validated against a Pydantic schema and merged
    over generated enrichment. Overlay always wins; conflicts are reported, not silently resolved.
13. **Compile and write-back** — refresh `genql_search_document` with BM25 and HNSW indexes, then
    optionally emit `COMMENT ON TABLE` and `COMMENT ON COLUMN` back to the warehouse so the
    database documents itself for every other tool. Write-back is off by default and requires an
    explicit flag, since it is the only step that writes anywhere.

---

## 9. Online query pipeline

Fourteen registered stages, wired as a LangGraph `StateGraph`.

1. **Intent classification** — `analytical_sql`, `metadata_question`, `followup`, or `non_sql`.
   Routes away from SQL generation when SQL is not the answer.
2. **Ambiguity gate** — scores specification completeness across entity, metric, time range, grain,
   filter, and comparison baseline. Below threshold, raises `interrupt()` with one targeted
   question rather than a generic request for clarification. Above threshold, proceeds with
   best-supported defaults drawn from `genql_rule` and records which defaults were applied.
3. **Domain scoping** — resolves the question to one or two business domains, reducing the
   candidate object set by roughly an order of magnitude before any retrieval.
4. **Hybrid retrieval** — a single SQL statement over `genql_search_document` combining
   `pg_search` BM25 with pgvector cosine distance, fused by reciprocal rank, then reranked with
   `rerank-v4.0-pro`. Returns objects, columns, metrics, and validated join paths.
5. **Schema linking** — binds entities, metrics, filters, and time expressions to specific columns
   using aliases, synonyms, metric definitions, and value profiles. Value profiles allow a filter
   on "active customers" to be checked against actual distinct values before it reaches SQL.
   Emits a compact, high-confidence schema context.
6. **Natural-language planning** — produces an explicit NL plan before any SQL, the technique
   behind Oracle's Archer result. The plan is inspectable and is what the critique stage checks the
   SQL against.
7. **Candidate generation** — N candidates representing genuinely different interpretations, using
   divide-and-conquer decomposition, execution-plan-oriented chain of thought, and few-shot
   examples retrieved from `genql_example` and `genql_ambiguity_case`.
8. **Static validation** — sqlglot parse, `qualify`, and the full `GuardrailRegistry`. Candidates
   that fail unrepairably are dropped; repairable ones are corrected and re-checked.
9. **Critique** — combines database signals (column existence, type compatibility, join validity,
   grain consistency) with LLM review against the NL plan, emitting a structured defect report
   rather than prose. The report drives correction *before* anything executes.
10. **Ambiguity probing** — diffs surviving candidates, maps each difference to an intent, schema,
    or value dimension, generates targeted probe SQL, executes it under a strict budget, and
    converts outcomes into explicit resolution decisions. This is where the data, not a model,
    settles the interpretation.
11. **Candidate selection** — selects the final SQL from probe-resolved evidence, falling back to
    ranked critique scores when probes are inconclusive.
12. **Guarded execution** — read-only role, `statement_timeout`, row cap, injected `LIMIT`.
13. **Rewrite and optimize** — see section 11.
14. **Response** — answer, the SQL, the NL plan, the applied defaults, provenance for every
    semantic element used, an optional visualization spec, and a feedback handle.

Failure at any stage returns a typed error, allowing the graph to replan, repair, or escalate to a
clarifying question rather than collapsing.

---

## 10. Retrieval design

ParadeDB collapses what would otherwise be two systems. `genql_search_document` carries a BM25
index built by `pg_search` over enriched text (object name, description, aliases, column names,
column descriptions, synonyms, sample values, domain name) and an HNSW pgvector index over its
embedding. A single statement in `SearchDocumentRepository` performs both retrievals, fuses them
by reciprocal rank, filters by scoped domain, and returns ranked candidates. No Elasticsearch, no
Python-side merge, no second store to keep consistent.

Reranking is a separate port so that model choice, or removal of reranking entirely, changes one
registration.

---

## 11. Optimizer and rewrite

Correct SQL that cannot execute affordably is not correct enough. The optimizer operates in three
phases and learns from outcomes.

**Pre-execution, static.** `RewriteRuleRegistry` rules over the sqlglot AST: predicate pushdown,
redundant join elimination proven by foreign-key analysis, projection pruning, `SELECT *`
expansion, CTE materialization or inlining, and mandatory `LIMIT` injection. Every rule is
semantics-preserving and is verified by a property test asserting result equivalence on the golden
set.

**Pre-execution, cost-gated.** `EXPLAIN (FORMAT JSON)` without `ANALYZE` yields an estimated cost.
Queries exceeding the configured budget are rewritten or decomposed before running; queries that
remain over budget after rewriting return an explanation and a suggested narrowing rather than
executing.

**Post-execution, learned.** `EXPLAIN (ANALYZE, BUFFERS)` actuals and `pg_stat_statements` are
recorded against the rewrite rules applied, so the system accumulates evidence about which rewrites
help on this warehouse. Repeated sequential scans on filtered columns produce **index
recommendations reported to the operator** — GenQL never creates an index itself.

---

## 12. Safety and governance

Generated SQL must clear the `GuardrailRegistry` before execution:

- Statement kind restricted to `SELECT` and `WITH`. No DDL, DML, or DCL.
- Object allowlist enforced against the semantic store, mirroring `enforce_object_list`.
- Forbidden functions and constructs: `pg_sleep`, `COPY`, `dblink`, `pg_read_file`, large object
  functions, and any function performing I/O.
- Mandatory `LIMIT` injection and enforced `statement_timeout`.
- Execution under a dedicated read-only role; row-level security on the warehouse continues to
  apply and is never bypassed.
- Probe queries carry a separate, stricter timeout and row budget.

Conversation checkpoints, traces, feedback, and the semantic store all live in GenQL's own
Postgres. Nothing about a user's data or questions accumulates in an ungoverned external store.

---

## 13. Multi-turn interaction

Each turn updates **structured state**, not appended chat text. Turn state carries resolved
entities, the candidate metric, accepted defaults, user scope, rejected interpretations, and the
current domain scope. A clarification such as "I mean OCI revenue in North America, compared with
the same month last year" narrows retrieval, tightens schema linking, and prunes candidate
branching on the next turn, rather than merely adding context to a prompt.

State persists through LangGraph `PostgresSaver`, guarded by a per-thread Postgres advisory lock.
Clarification is raised through `interrupt()`, so a paused turn resumes exactly where it stopped.

---

## 14. Data acquisition

Four layers, only the first of which is downloadable. That asymmetry is precisely the gap the
research describes, and BEAVER exists to document it.

**Layer 1 — the warehouse.** Primary: **TPC-DS at scale factor 1** (~1 GB), generated with DuckDB's
`tpcds` extension and loaded into ParadeDB with `COPY`. Chosen for three properties: a 24-table
snowflake schema with a real fiscal date dimension and multi-channel facts; deliberately cryptic
column names (`ss_ext_sales_price`, `d_moy`, `cd_demo_sk`) that give schema discovery genuine work;
and 99 official analytical query templates that seed the query log. Secondary: **Olist Brazilian
E-Commerce** (9 tables, real transactional data, some Portuguese column names — a strong ambiguity
test). Development fixture: **Pagila**, small enough for a fast test loop.

**Layer 2 — business knowledge.** Authored, not downloaded. `semantic/*.yaml` carries metric
definitions, fiscal calendar, synonyms, default filters, and policy rules. For TPC-DS retail this
is realistic to write: net versus gross sales, returns handling, promotion lift, channel
definitions.

**Layer 3 — query logs.** Three sources: the 99 TPC-DS templates parameterized into thousands of
variants; `pg_stat_statements` captured from GenQL's own running system; and LLM-synthesized
ambiguity-aware pairs per step 11.

**Layer 4 — golden set.** Thirty to fifty hand-curated question/expected-result pairs over TPC-DS
and Olist, weighted toward the four failure classes, stored as YAML fixtures.

---

## 15. Evaluation

No public benchmarks. Two mechanisms substitute.

**Golden set runner** executes the curated questions and compares **execution results** with
order-insensitive set equality, never SQL string matching. Runs in seconds and costs cents with
recorded LLM calls; costs a few dollars live.

**Ablation harness** replays the golden set with enrichment layers disabled independently — no
descriptions, no domains, no join paths, no query log, no probing. This is the only mechanism that
demonstrates whether the semantic store earns its latency, which is the system's entire thesis. It
runs on demand, not per commit.

---

## 16. Repository structure

```
genql/
  domain/
    entities/            one entity per file
    value_objects/
    ports/               Protocol definitions, one port per file
    errors/
  services/              one service per file, ports only
  repositories/          all SQL, one repository per aggregate
  infrastructure/
    paradedb/  neo4j/  gateway/  sqlglot/  embedding/  rerank/  tracing/
  registries/            generic Registry[T] plus one module per axis
  discovery/steps/       one file per offline step
  pipeline/stages/       one file per online stage
  graphs/                StateGraph definitions and thin node adapters
  api/
    controllers/  dtos/  sse/  deps.py
  composition_root.py
semantic/                user-authored YAML overlays
data/                    seed scripts: tpcds, olist, pagila
docker/                  compose, ParadeDB and Neo4j configuration
tests/                   unit, integration, property, golden
docs/superpowers/specs/
```

---

## 17. Testing strategy

- **Unit** — services tested against in-memory fake repositories. No database, no network. This is
  possible only because services depend on ports, and is the practical payoff of the layering.
- **Integration** — repositories tested against real ParadeDB and Neo4j via testcontainers.
- **Property** — hypothesis asserts that anything the generator emits parses in sqlglot and clears
  every guardrail, and that each rewrite rule preserves results on the golden set.
- **Contract** — import-linter contracts verified in CI as tests, so the layering cannot erode.
- **Golden** — execution-result comparison as described in section 15.
- **LLM calls** recorded once and replayed, so the suite is deterministic and free.

---

## 18. Phasing

Each phase ends with something runnable and tested.

1. **Foundation** — uv project, layered skeleton, `Registry[T]`, composition root,
   import-linter contracts, Docker Compose with ParadeDB and Neo4j, Alembic baseline.
2. **Warehouse and catalog** — TPC-DS and Pagila seeds; catalog scan and data profiling steps;
   catalog repositories; CLI to run and inspect discovery.
3. **Graph and domains** — Neo4j projection, Leiden, FastRP, fused clustering, domain naming,
   join-path mining.
4. **Semantic store and retrieval** — enrichment steps, YAML overlay, compile step,
   `genql_search_document` with BM25 and HNSW, hybrid retrieval with reranking.
5. **Generation core** — planning, candidate generation, static validation, guardrails, guarded
   execution. First end-to-end answers.
6. **Ambiguity machinery** — critique, probing, selection, synthetic ambiguity log, the LangGraph
   graph with the clarification interrupt and multi-turn state.
7. **Optimizer** — rewrite rules, cost gating, EXPLAIN feedback loop, index recommendations.
8. **API and evaluation** — FastAPI controllers, SSE streaming, golden set runner, ablation
   harness.
9. **Frontend** — deferred until the SSE contract is stable.

---

## 19. Risks

**Discovery quality bounds everything.** If step 5 produces poor descriptions, every downstream
stage degrades. Mitigation: descriptions are grounded on sampled values, carry confidence and
provenance, and are overridable from YAML.

**Probing cost.** Probe queries execute against the warehouse and add latency. Mitigation: probing
is gated on candidates actually disagreeing, runs under a strict budget, and is individually
ablatable so its value is measurable.

**Neo4j projection drift.** A derived store can fall behind its source. Mitigation: rebuild is a
single idempotent command, the projection holds no authoritative data, and a checksum comparison
against Postgres detects drift.

**Rerank model availability.** Resolved — `cohere/rerank-4-pro` is carried by OpenRouter, so
chat, embeddings, and rerank all run through one key. `RerankProviderRegistry` retains the option
of binding Cohere directly if that changes.

**TPC-DS is synthetic.** Its data distributions are cleaner than production. Mitigation: Olist
provides genuinely messy real-world data as a second warehouse.

---

## 20. Cost model and cost policy

Prices are Anthropic first-party rates (Opus 5 $5/$25, Sonnet 5 $2/$10, Haiku 4.5 $1/$5 per MTok),
`text-embedding-3-small` at $0.02/MTok, `cohere/rerank-4-pro` at $0.0025 per search, plus
OpenRouter's 5.5% platform fee. OpenRouter passes Anthropic `cache_control` through at 0.1x input
for reads, with sticky provider routing to keep entries warm. It requires **explicit per-block
breakpoints** — top-level automatic caching is not available through the gateway, so cache
placement is an explicit responsibility of the prompt-assembly layer.

### Three constraints that shape the design

**Cache namespaces are model-scoped.** A prompt cache entry belongs to one model. A pipeline that
routes Haiku for gating, Sonnet for generation, and Opus for reasoning therefore needs *three*
copies of the schema prefix and pays three cache writes, and no stage benefits from another
stage's write. A single-model pipeline pays one. This is the single largest cost factor in the
design and it is architectural, not a tuning parameter.

**Output tokens cost five times input.** A natural-language plan is roughly 500 tokens, a
generated SQL statement roughly 900, a structured critique report roughly 500. Estimating these
generously is the fastest way to overstate cost by a factor of two.

**Stage activation must be demand-driven.** Critique, multi-candidate generation, and probing exist
to resolve disagreement. When the ambiguity gate scores a question as well-specified and the first
candidate clears static validation, there is nothing to critique and nothing to probe. Running the
full pipeline unconditionally spends the ambiguity budget on questions that carry no ambiguity.

### Routing policy

One model — **Sonnet 5** — serves the whole pipeline, with `output_config.effort` varied per stage
rather than the model swapped. This keeps a single cache namespace. Two exceptions, both of which
cost no namespace:

- The merged gate runs on **Haiku 4.5** because it does not read the schema prefix at all.
- **Opus 5** is an *escalation*, not a tier: it is invoked only when the gate scores a question as
  genuinely hard or when critique fails to resolve after one repair round. It pays its own cache
  write, amortized over the escalated minority.

This ordering follows Anthropic's own guidance — measure the most capable model at lower effort
before building a multi-model cascade, because lower effort on current models frequently matches
prior-generation performance at high effort, and a cascade forfeits cache reuse across its members.

Candidate diversity is preserved while halving the call count: diversity in multi-candidate
text-to-SQL comes from *different generator prompts* (divide-and-conquer decomposition versus
execution-plan chain of thought), not from resampling one prompt. Two generator calls returning two
structured variants each yield four candidates through two calls.

Selection and rewriting are **deterministic by default**. When probing resolves every contested
dimension, selection is a lookup rather than a judgement. Rewrite rules are sqlglot AST transforms
gated on `EXPLAIN` cost; an LLM is invoked only to decompose a query that remains over budget.

### Per-query cost

| Path | When it runs | Cost |
|---|---|---|
| Semantic cache hit | question matches a validated prior question | **$0.0001** |
| Simple | well-specified question, first candidate validates | **$0.046** |
| Hard | contested dimensions — 4 candidates, critique, probing | **$0.137** |
| Opus escalation | genuinely hard or unresolved after repair | **$0.174** |

Simple-path breakdown: merged gate $0.0045, schema linking $0.0110, plan and generate $0.0156,
response $0.0086, amortized prefix write $0.0010, embedding and rerank $0.0025.

### Blended cost

| Query mix | Expected cost |
|---|---|
| No semantic result cache (worst case) | $0.075 |
| 25% cache hits (pessimistic) | $0.054 |
| 40% cache hits (expected) | **$0.044** |

The **$0.046 simple path is measured from token accounting and does not depend on the cache-hit
assumption**. The blended figure does; 40% is plausible for enterprise analytics, where dashboard
refreshes and recurring questions repeat heavily, but it is an assumption until measured. The
golden-set runner reports realized cost per query alongside accuracy so the assumption is checked
rather than trusted.

### Semantic store build

| | Cost |
|---|---|
| Full build via OpenRouter | $3.90 |
| Full build via Anthropic Batch API (registered as a second `ChatProvider`, −50%) | **$1.85** |
| Incremental rediscovery, ~10% of objects changed | **$0.18** |

Offline work is latency-insensitive and therefore batchable. Registering an `anthropic_batch`
`ChatProvider` alongside OpenRouter is one file and one decorator — the first real payoff of the
registry design.

### Cost as a measured property

Every stage records tokens and cost to `genql_trace`, so cost per query is a reported metric rather
than an estimate. The ablation harness reports accuracy *and* cost per configuration, which makes
the candidate count, the probing threshold, and the Opus escalation threshold tunable against
evidence instead of intuition.

---

## 21. Model selection policy

Model choice is **configuration, not architecture**. `ChatProviderRegistry` binds a model per
stage from YAML, so nothing below changes a line of pipeline code, and the ablation harness settles
it empirically once there is something to run.

### Evidence

An independent 2026 panel evaluated 36 models on 759 BIRD-SQL questions, zero-shot, temperature 0,
with the domain hint withheld and database identification left to the model:

| Model | Strict | Gold-clean | Adjudicated |
|---|---|---|---|
| gemini-3-flash-preview | 0.551 | **0.677** | 0.759 |
| gemini-3.1-pro-preview | 0.536 | 0.669 | 0.751 |
| claude-fable-5 | 0.531 | 0.655 | 0.803 |
| claude-opus-5 | 0.523 | 0.643 | **0.824** |
| qwen3.6-27b | 0.471 | 0.590 | — |
| claude-opus-4.8 | 0.445 | 0.549 | 0.765 |
| gpt-5.6-sol | 0.438 | 0.545 | 0.785 |
| kimi-k3 | 0.391 | 0.482 | 0.772 |
| claude-sonnet-5 | 0.311 | — | 0.710 |

Three findings drive the policy.

**Cheap does not mean worse at SQL.** `gemini-3-flash-preview`, at $0.50/$3.00 per MTok, is the
panel's best SQL writer — ahead of every frontier model on gold-clean accuracy. Price and
SQL quality are not correlated in this panel.

**Routing and SQL writing are independent skills.** `kimi-k3` routes at 0.832 while writing
gold-clean SQL at 0.482; `gemini-3-flash-preview` routes at 0.753 and writes at 0.677. GenQL
separates routing (the gate and domain scoping) from writing (candidate generation) into distinct
stages, so each can take the model that is good at that skill instead of compromising on one model
for both. This is an empirical argument for the modular pipeline.

**DeepSeek is the wrong choice for generation specifically.** The panel notes `qwen3.6-27b`
outperforming every OpenAI, Kimi, and DeepSeek entry in its tier. DeepSeek V4 Flash is excellent
value for routing and formatting; it is not the model to write the SQL.

### Policy

| Stage | Model | Reason |
|---|---|---|
| Merged gate, domain scoping | DeepSeek V4 Flash ($0.05/$0.10) | Routing is the easier skill and cheap models do it well |
| Schema linking | DeepSeek V4 Flash | Retrieval-adjacent; the semantic store carries the difficulty |
| Candidate generation | **gemini-3-flash-preview** | Best gold-clean SQL in the panel, at Flash pricing |
| Critique, probe design | gemini-3-flash-preview, escalating to Opus 5 | Opus 5 leads adjudicated accuracy at 0.824 |
| Response | DeepSeek V4 Flash | Formatting |

### Resulting cost

| Configuration | Simple | Hard | Blended |
|---|---|---|---|
| All Sonnet 5 (previous policy) | $0.046 | $0.137 | $0.043 |
| **Split policy above** | **$0.012** | **$0.057** | **$0.015** |
| Split policy, 8 candidates on the hard path | $0.012 | $0.081 | $0.019 |
| All DeepSeek V4 Flash (not recommended) | $0.005 | $0.008 | $0.003 |

Semantic store build falls to **$1.41**, or $0.67 batched.

Two consequences. First, at these prices **prompt caching stops being load-bearing** — DeepSeek V4
Flash uncached input at $0.05/MTok is four times cheaper than Sonnet 5's *cached* read at
$0.20/MTok — so the single-namespace constraint in section 20 relaxes and models may be mixed
per stage freely. Second, Cohere rerank at $0.0025 per search becomes a large share of a simple
query; if it does not earn its place in ablation, dropping it is the next saving.

The generation stage being 40x cheaper also makes **more candidates affordable**, which is the
CHASE-SQL and SOMA-SQL thesis directly: test-time compute substitutes for model size. Eight
candidates plus probing on a Flash model costs less than four candidates on Sonnet 5. Whether that
trade improves accuracy is exactly what the ablation harness measures.

### Caveat on the evidence

The panel flagged **236 of 759 BIRD golds (31.1%) as broken**, corroborating published findings on
pervasive annotation errors in text-to-SQL benchmarks. Grading used LLM juries rather than
independent human annotators, with no repeat measurement. Treat the ordering as directional and
small deltas as noise. Most importantly, these numbers measure models **without semantic
enrichment** — the domain hint was deliberately withheld. GenQL's entire premise is that enrichment
supplies precisely that missing context, so the spread inside this pipeline should be narrower than
the panel suggests. The golden set on our own warehouse is the measurement that decides.
