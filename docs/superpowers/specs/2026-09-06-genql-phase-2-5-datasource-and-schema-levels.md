# GenQL Phase 2.5 — Datasource and Schema Levels

**Status:** design approved, pending implementation plan
**Date:** 2026-09-06
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md`

---

## 1. Purpose

Phase 2 built discovery against exactly one warehouse. `Settings.warehouse_dsn` names a single
database, `DiscoveryContext` carries a single `schema_name`, and every catalog row is keyed on
`(schema_name, object_name)`. Nothing in the system can express *which database* a table came
from.

Phase 2.5 inserts the two levels that were missing — **datasource** above schema, and **schema**
as a registered first-class object rather than a string passed on the command line — so GenQL can
ingest *n* schemas across *n* databases and address a subset of them as the scope of a query.

This lands before Phase 3 deliberately. The Neo4j projection keys its nodes on object identity; if
identity is still `(schema, object)` when the graph is built, the single-datasource assumption is
baked into the graph, the community detection, and every downstream artifact that references a
node key.

### Goals

- Every catalog and profile row is attributable to a specific datasource and schema.
- Datasources and schemas are registered, listed, enabled, and removed through the CLI.
- Discovery runs over a resolved scope of `(datasource, schema)` pairs rather than one schema.
- Warehouse credentials never enter the semantic store.
- The dialect axis exists as a registry seam, with Postgres as its one implementation.
- Existing discovered data survives the migration.

### Non-goals

- **Cross-datasource query federation.** A query targets exactly one datasource and may join
  freely across that datasource's schemas, which PostgreSQL does natively. Planning across
  datasources needs a distributed plan representation, per-source result materialisation, and its
  own cost model. It is a separate subsystem and is not built here.
- **LLM-driven scope routing.** The `ScopeResolver` port and its registry exist so Phase 5 can
  register a router as one file. Only deterministic resolvers are implemented now.
- **A second dialect implementation.** `dialect` is carried, validated against a registry, and
  used to select the catalog reader. Postgres is the only registered dialect.
- **Per-datasource enrichment policy.** Enrichment does not exist yet; it will inherit the scope
  model when it arrives in Phase 4.

---

## 2. Identity model

Identity becomes a three-level natural key: `datasource → schema → object → column`.

Surrogate ids were rejected. They would either place database primary keys inside frozen domain
entities — violating the rule that `domain/` performs no I/O and knows nothing of persistence — or
force every repository to translate name↔id on both directions of every call. At the scale in
question (tens of tables per schema, single-digit datasources) the normalisation buys nothing that
pays for that cost.

`Datasource.name` is therefore a `TEXT` primary key, `genql_schema` is keyed on
`(datasource_name, schema_name)`, and the four existing catalog tables carry both columns with a
composite foreign key to `genql_schema` declared `ON DELETE CASCADE`. Removing a datasource
removes its schemas, and removing a schema removes its objects, columns, constraints, and
profiles, without any application-level cleanup code.

---

## 3. Semantic store changes

### 3.1 New tables

```sql
genql.genql_datasource (
    name            TEXT PRIMARY KEY,
    dialect         TEXT        NOT NULL,
    dsn_env_var     TEXT        NOT NULL,
    description     TEXT,
    enabled         BOOLEAN     NOT NULL DEFAULT true,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now()
)

genql.genql_schema (
    datasource_name     TEXT NOT NULL REFERENCES genql.genql_datasource(name) ON DELETE CASCADE,
    schema_name         TEXT NOT NULL,
    description         TEXT,
    enabled             BOOLEAN NOT NULL DEFAULT true,
    last_discovered_at  TIMESTAMPTZ,
    PRIMARY KEY (datasource_name, schema_name)
)
```

`dsn_env_var` holds the *name* of an environment variable, never a connection string. The DSN is
read from the process environment at connect time. This keeps warehouse credentials out of the
semantic store, consistent with the parent spec's position on shadow data repositories, and means
a dump of the semantic store is safe to hand to someone.

`dialect` is a free-text registry key rather than an enum. An enum would have to be edited to add
a dialect, which is exactly the modification the registry design exists to avoid.

### 3.2 Changed tables

`genql_object`, `genql_column`, `genql_constraint`, and `genql_column_profile` each gain
`datasource_name TEXT NOT NULL`. Their `uq_genql_*_identity` unique constraints are rebuilt to
include it, and each gains a composite foreign key `(datasource_name, schema_name)` referencing
`genql_schema` with `ON DELETE CASCADE`.

### 3.3 Migration 0003, non-destructive

The existing rows describe a real warehouse and re-discovery is not free, so the migration
backfills rather than truncating:

1. Create `genql_datasource` and `genql_schema`.
2. Insert the datasource `('local', 'postgres', 'GENQL_WAREHOUSE_DSN')` — the database Phase 2
   was pointed at.
3. Add `datasource_name` to the four catalog tables with `SERVER DEFAULT 'local'`, so existing
   rows are backfilled by the DDL itself.
4. Populate `genql_schema` from `SELECT DISTINCT schema_name FROM genql_object`, attributed to
   `local`.
5. Drop the server default, swap the unique constraints, and add the composite foreign keys.

`downgrade()` reverses each step. After upgrade, the `tpcds` objects discovered in Phase 2 are
addressable as `local.tpcds` and nothing has been lost.

---

## 4. Domain

### 4.1 New entities and value objects

| File | Type | Contents |
|---|---|---|
| `domain/entities/datasource.py` | `Datasource` | `name`, `dialect`, `dsn_env_var`, `description`, `enabled` |
| `domain/entities/schema_registration.py` | `SchemaRegistration` | `datasource_name`, `schema_name`, `description`, `enabled`, `last_discovered_at` |
| `domain/value_objects/schema_ref.py` | `SchemaRef` | `datasource_name`, `schema_name`; `qualified_name` property |
| `domain/value_objects/query_scope.py` | `QueryScope` | `datasource_name`, `schema_names: tuple[str, ...]`; `refs()` yields `SchemaRef` |

All frozen Pydantic v2 models, consistent with the existing entities.

`QueryScope` names one datasource and one or more of its schemas. That shape *is* the federation
decision, expressed as a type: a scope spanning two datasources is unrepresentable, so no
downstream stage can accidentally assume it works.

### 4.2 Changed entities

`DatabaseObject`, `Column`, `Constraint`, and `ColumnProfile` each gain `datasource_name: str`.
Their `qualified_name` properties extend to `datasource.schema.object[.column]`.

### 4.3 New ports

```python
# domain/ports/datasource_repository.py
class DatasourceRepository(Protocol):
    def add(self, datasource: Datasource) -> None: ...
    def get(self, name: str) -> Datasource: ...
    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]: ...
    def remove(self, name: str) -> None: ...

# domain/ports/schema_registration_repository.py
class SchemaRegistrationRepository(Protocol):
    def add(self, registration: SchemaRegistration) -> None: ...
    def list_for_datasource(self, datasource_name: str, enabled_only: bool = False) -> Sequence[SchemaRegistration]: ...
    def remove(self, ref: SchemaRef) -> None: ...
    def mark_discovered(self, ref: SchemaRef) -> None: ...

# domain/ports/catalog_reader_factory.py
class CatalogReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> CatalogReader: ...

# domain/ports/profile_reader_factory.py
class ProfileReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> ProfileReader: ...

# domain/ports/scope_resolver.py
class ScopeResolver(Protocol):
    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope: ...
```

The two factory ports are the one genuinely new architectural seam. `CatalogScanService` needs a
reader bound to a *particular* datasource, but a service may never see an `Engine`, a DSN, or a
dialect. The factory is the port that lets it ask for one by handing over a `Datasource` entity it
loaded through another port.

### 4.4 Changed ports

`CatalogReader`'s three methods take a `SchemaRef` instead of `schema: str`, so the reader can
stamp `datasource_name` onto the entities it returns. `ProfileReader.profile_column` is unchanged:
a `Column` already carries its full identity. The two writer ports are unchanged in signature —
the entities they receive now carry the extra key.

### 4.5 New errors

`UnknownDatasourceError`, `DuplicateDatasourceError`, `MissingDatasourceSecretError`,
`UnknownSchemaRegistrationError`, and `AmbiguousScopeError`, all under the existing `GenqlError`
hierarchy so callers keep routing on type.

---

## 5. Registries

Two new registries, both following the `DISCOVERY_STEPS` pattern of a module-level `Registry[T]`
plus a package `__init__` that imports implementations for their decorator side effect.

| Registry | Location | Keyed on | Registered now |
|---|---|---|---|
| `CATALOG_READERS` | `repositories/warehouse/registry.py` | dialect | `postgres` |
| `PROFILE_READERS` | `repositories/warehouse/registry.py` | dialect | `postgres` |
| `SCOPE_RESOLVERS` | `services/scope/registry.py` | resolver name | `explicit`, `default` |

Registering a dialect is one file and one decorator; nothing in `services/`, `discovery/`, or the
CLI changes.

---

## 6. Infrastructure

`DatasourceEngineProvider` (`infrastructure/db/engine_provider.py`) maps a `Datasource` to a
pooled SQLAlchemy `Engine`, caching one engine per datasource name for the process lifetime. It
receives the environment as an injected `Mapping[str, str]` — `os.environ` in production, a plain
dict in tests — so nothing in the test suite mutates process state. A `dsn_env_var` that is absent
or empty raises `MissingDatasourceSecretError` rather than surfacing as a driver error later.

`CatalogReaderFactoryImpl` and `ProfileReaderFactoryImpl` (`infrastructure/catalog/`) implement
the two factory ports: resolve the engine from the provider, look the repository class up in the
dialect registry, and construct it. Both are thin — engine resolution plus a registry lookup.

---

## 7. Services

**`DatasourceService`** registers, lists, and removes datasources. Registration validates that the
dialect is a registered key and that the named environment variable resolves, so a
misconfiguration fails at `datasource add` rather than during the first discovery run.

**`SchemaRegistrationService`** registers, lists, and removes schemas, and verifies at
registration time that the schema actually exists in the target datasource by reading its catalog
through the factory.

**Scope resolvers** (`services/scope/`):

- `ExplicitScopeResolver` — a datasource name and schema names were given; validates both exist
  and are enabled, and returns the `QueryScope`.
- `DefaultScopeResolver` — nothing was given; if exactly one datasource is enabled it returns that
  datasource with all of its enabled schemas, otherwise it raises `AmbiguousScopeError` naming the
  candidates. Filling in only the schemas when the datasource is given follows the same rule.

**`CatalogScanService`** and **`ProfilingService`** change shape: each now takes a
`DatasourceRepository` and the relevant factory, and its entry point takes a `SchemaRef`. Each
loads the `Datasource`, asks the factory for a reader bound to it, and proceeds exactly as before.
Both remain unit-testable against fakes with no database present.

---

## 8. Discovery

`DiscoveryContext` gains `datasource_name` and a `ref` property returning the `SchemaRef`. Both
existing steps pass `ctx.ref` to their service instead of `ctx.schema_name`.

`DiscoveryRunner.run()` is unchanged — it still executes the step sequence for one
`(datasource, schema)` pair with `start_from` resume semantics. It gains
`run_scope(scope, sample_limit, start_from)`, which builds a context per `SchemaRef` in the scope
and returns results grouped by ref. Putting the loop in the runner rather than the CLI keeps the
controller free of orchestration, and leaves the per-pair resume behaviour untouched.

A schema whose run completes successfully has `last_discovered_at` stamped through
`SchemaRegistrationRepository.mark_discovered`.

---

## 9. CLI

```
genql datasource add --name local --dialect postgres --dsn-env GENQL_WAREHOUSE_DSN [--description TEXT]
genql datasource list
genql datasource remove --name local

genql schema add --datasource local --schema tpcds [--description TEXT]
genql schema list [--datasource local]
genql schema remove --datasource local --schema tpcds

genql discover [--datasource NAME] [--schema NAME ...] [--start-from STEP]
genql steps
```

`datasource` and `schema` are Typer sub-applications, one command per file under `cli/commands/`
to stay inside the 250-line cap and the one-action-per-file rule. `discover` resolves its
arguments through a `ScopeResolver` — explicit when flags are given, default when they are not —
and hands the resulting `QueryScope` to `run_scope`.

---

## 10. Configuration

`Settings.warehouse_dsn` is removed. It described a single warehouse, which is precisely the
assumption being deleted; the value survives as the environment variable that the `local`
datasource points at. `Settings.semantic_dsn` is unchanged — GenQL's own store is genuinely
singular. `Settings.default_datasource: str | None` is added for `DefaultScopeResolver` to consult
before falling back to the sole-enabled-datasource rule.

---

## 11. Testing

**Unit** — both scope resolvers including the ambiguous and disabled paths; `DatasourceService`
validation; `SchemaRegistrationService`; the two factories against fake registries and providers;
`DatasourceEngineProvider` env resolution and caching against an injected dict;
`DiscoveryRunner.run_scope`; both steps; the updated `CatalogScanService` and `ProfilingService`
against fakes.

**Integration (VM compose stack)** — migration 0003 upgrade and downgrade with explicit backfill
assertions on pre-existing rows; cascade behaviour when a datasource is removed; the datasource
and schema-registration repositories; the catalog reader stamping `datasource_name` correctly.

**Contract** — the existing import-linter contracts must pass unchanged. That they do, with a new
cross-layer seam added, is the evidence that the factory-port design respects the layering.

**Multi-datasource proof.** Asserting that *n* databases work is not the same as showing it, so a
second database `genql_wh2` is created on the VM's ParadeDB instance and seeded with **Pagila**,
registered as the datasource `wh2` against `GENQL_WH2_DSN`. This gives a genuine three-way test —
`local.tpcds`, `local.shop`, `wh2.pagila` — covering *n* schemas within a datasource and *n*
datasources at once. It also discharges the `UNVERIFIED` marker on the Pagila seed in
`data/README.md`, which has never been executed for want of a local `psql`; running it through
`docker exec` on the VM removes that obstacle.

---

## 12. Consequences for later phases

**Phase 3 (graph projection)** keys Neo4j nodes on `datasource.schema.object` and projects one
graph per datasource, since FK edges cannot cross a database boundary. Leiden communities and
FastRP embeddings are therefore computed per datasource, which is correct rather than merely
convenient.

**Phase 4 (retrieval)** carries `datasource_name` and `schema_name` on `genql_search_document` and
filters on the resolved scope before BM25 and vector search run, narrowing the candidate set
before retrieval instead of after.

**Phase 5 (query pipeline)** registers an LLM-backed `ScopeResolver` alongside the deterministic
pair and picks the datasource from the question. No call site changes.

---

## 13. Risks

**Migration on a populated store.** 0003 rewrites unique constraints on four tables holding real
discovered data. Mitigation: the backfill is driven by a server default rather than an
`UPDATE`, `downgrade()` is implemented and tested, and the integration test asserts on rows that
existed before the upgrade.

**Env-var indirection is a second place to look.** A datasource row is useless without its
variable set. Mitigation: `datasource add` resolves the variable eagerly and refuses to register
a datasource whose secret is missing, so the failure surfaces at registration.

**Engine cache lifetime.** One pooled engine per datasource is held for the process lifetime.
This is right for a CLI and for a long-lived API process, but a datasource removed and re-added
with a different DSN inside one process would serve a stale engine. Mitigation: the provider
invalidates its cache entry on removal, and the CLI is process-per-invocation regardless.
