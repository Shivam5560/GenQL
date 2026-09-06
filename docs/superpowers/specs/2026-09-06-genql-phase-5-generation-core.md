# GenQL Phase 5 — Generation Core

## 1. Purpose

The parent spec's phasing (§18) names Phase 5 "Generation core — planning, candidate generation,
static validation, guardrails, guarded execution. First end-to-end answers." This phase turns
GenQL from a discovery/retrieval system into one that answers an analytical question with real,
safely-executed SQL against a real warehouse — the first point at which the project produces an
actual answer rather than metadata about one.

**Scope, decided explicitly against the parent spec's richer online pipeline (§9) to keep this
phase a thin, provable slice:**

- **Single candidate, no critique, no probing, no selection.** The parent spec's stages 9–11
  (critique, ambiguity probing, candidate selection) require data-driven disagreement resolution
  across *multiple* candidates and belong to Phase 6 ("Ambiguity machinery") in full, alongside the
  ambiguity gate that would motivate generating more than one candidate in the first place.
  Generating a second candidate with nothing that consumes the disagreement between them is dead
  work, so Phase 5 generates exactly one NL plan and one SQL candidate per question.
- **No intent classification (stage 1).** Every question passed to `genql query` is assumed to be
  `analytical_sql`. Routing non-SQL or follow-up questions away from the pipeline is deferred to
  whichever phase first has a caller that sends one.
- **LangGraph now, without its Phase 6 machinery.** The parent spec's §13 ties LangGraph's
  `PostgresSaver`, per-thread advisory locks, and `interrupt()` specifically to multi-turn
  clarification, which does not exist yet. Phase 5 still wires a real `StateGraph` — so Phase 6
  extends an existing graph rather than introducing one — but with no checkpointer and no
  interrupts: each invocation is a single, stateless run from question to answer.
- **No natural-language answer synthesis.** The parent spec's §9 stage 14 ("Response") bundles an
  NL answer with SQL, plan, and provenance. Phase 5 proves the harder half — correct, safely
  executed SQL — and returns the validated SQL plus the executed rows. Turning rows into prose is
  a separate, independently gradeable concern deferred to a later phase.
- **Schema linking is in scope.** It is not named in either Phase 5 or Phase 6's one-line summary
  in §18, but planning and candidate generation have nothing solid to ground SQL against without
  first binding retrieved objects/columns/metrics to concrete identifiers, so it is built now as
  the first stage of this phase's graph.

**What Phase 5 does not touch:** the ambiguity gate, domain-scoping *policy* (domain resolution
itself already exists from Phase 3/4 and is reused, not rebuilt), rewrite/optimization (§11,
Phase 7), the API/SSE layer (Phase 8), and anything involving conversation state across turns.

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/schema_link.py
@dataclass(frozen=True)
class SchemaLink:
    """One retrieval hit bound to a concrete SQL identifier."""
    object_qualified_name: str  # datasource.schema.object
    column_names: tuple[str, ...]
    join_paths: tuple[str, ...]  # qualified_name pairs, from genql_join_path
    metric_names: tuple[str, ...]
    domain_id: str | None

# domain/entities/query_plan.py
@dataclass(frozen=True)
class QueryPlan:
    """The NL plan produced before any SQL — what candidate generation and
    static validation both check their output against."""
    question: str
    plan_text: str
    referenced_objects: tuple[str, ...]

# domain/entities/sql_candidate.py
@dataclass(frozen=True)
class SqlCandidate:
    sql: str
    plan: QueryPlan

# domain/entities/guardrail_violation.py
@dataclass(frozen=True)
class GuardrailViolation:
    rule_name: str
    message: str
    repairable: bool  # e.g. "missing LIMIT" is repairable; "contains DELETE" is not

# domain/entities/execution_result.py
@dataclass(frozen=True)
class ExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    row_count: int
    truncated: bool
```

New ports (`genql/domain/ports/`), all `@runtime_checkable` `Protocol`s per the existing pattern:

```python
# domain/ports/schema_linker.py
class SchemaLinker(Protocol):
    def link(self, question: str, datasource: str, domain_id: str | None) -> tuple[SchemaLink, ...]: ...

# domain/ports/planner.py
class Planner(Protocol):
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan: ...

# domain/ports/candidate_generator.py
class CandidateGenerator(Protocol):
    def generate(self, plan: QueryPlan, links: tuple[SchemaLink, ...]) -> SqlCandidate: ...

# domain/ports/guardrail.py
class Guardrail(Protocol):
    """One registered rule. `check` returns violations found; `repair` is only
    called for violations this rule itself reported as repairable."""
    name: str
    def check(self, sql: str) -> tuple[GuardrailViolation, ...]: ...
    def repair(self, sql: str, violation: GuardrailViolation) -> str: ...

# domain/ports/query_executor.py
class QueryExecutor(Protocol):
    def execute(self, sql: str, row_cap: int) -> ExecutionResult: ...
```

`Planner` and `CandidateGenerator` both take the existing `ChatProvider` port as a constructor
dependency — `ChatProvider.complete(prompt, response_schema)` already returns a validated Pydantic
model, which is exactly the shape a structured NL-plan-then-SQL call needs. No new LLM port is
introduced.

`SchemaLinker`'s implementation is not a new LLM call: it composes the existing
`RetrievalService.search` (Phase 4) with the existing `SemanticCatalogReader` (join paths, column
names) to resolve retrieval hits into concrete identifiers — deterministic composition, not
generation, so no `ChatProvider` dependency here.

---

## 3. Registries

```python
# repositories/guardrails/registry.py
GUARDRAILS = Registry[Guardrail]()
```

Five registered implementations, one file each, mirroring the `EnricherRegistry` pattern from
Phase 4 (one new file + one registration line adds a rule; nothing else changes):

| Registration key | File | Rule (parent spec §12) |
|---|---|---|
| `statement_kind` | `statement_kind_guardrail.py` | Only `SELECT`/`WITH` (via `sqlglot` parse); anything else is unrepairable |
| `object_allowlist` | `object_allowlist_guardrail.py` | Every table/view referenced must exist in the semantic store for this datasource; unrepairable |
| `forbidden_function` | `forbidden_function_guardrail.py` | Rejects `pg_sleep`, `COPY`, `dblink`, `pg_read_file`, large-object functions; unrepairable |
| `limit_injection` | `limit_injection_guardrail.py` | Missing `LIMIT` is repairable — injects `Settings.query_row_cap` |
| `statement_timeout` | `statement_timeout_guardrail.py` | Not a SQL-text check; asserts the executor will apply `Settings.query_statement_timeout_ms` — included in the registry for uniformity of the "did every guardrail pass" report even though it has nothing to repair |

`StaticValidationService.validate(candidate)` runs every registered guardrail via `sqlglot.parse`
+ `qualify` first (parent spec §9 stage 8), then each `Guardrail.check`, then attempts
`repair` exactly once per repairable violation before re-checking; an unrepairable violation, or a
repairable one that still fails after one repair pass, raises `GuardrailViolation` and the graph's
conditional edge routes back to `candidate_generation` for a single retry (§4) before hard-failing.

---

## 4. Infrastructure — read-only execution path

No read-only Postgres role exists yet (confirmed against `data/seed_tpcds.py`,
`data/seed_pagila.sh`, and `docker/compose.yaml` — every existing connection uses the admin role).
New Alembic migration `0006_readonly_role.py`:

```sql
CREATE ROLE genql_readonly LOGIN PASSWORD :readonly_password;
GRANT CONNECT ON DATABASE genql TO genql_readonly;
GRANT USAGE ON SCHEMA tpcds, pagila TO genql_readonly;  -- per-datasource schemas, dynamic per warehouse
GRANT SELECT ON ALL TABLES IN SCHEMA tpcds, pagila TO genql_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA tpcds, pagila GRANT SELECT ON TABLES TO genql_readonly;
```

The password is read from a new `Settings.readonly_db_password` (env-backed, never hardcoded);
downgrade drops the role. `genql/infrastructure/db/engine_provider.py`'s existing per-datasource
engine cache gets a second binding keyed `("readonly", datasource)`, built from the same DSN with
the role swapped — `GuardedExecutionService` resolves only through this binding, so the admin
engine is structurally unreachable from the execution path, not just unused by convention.

---

## 5. Repositories

```python
# repositories/query/query_executor_repository.py
class ReadOnlyQueryExecutorRepository:
    """The only place in this phase that touches a database driver."""
    def __init__(self, readonly_engine_provider: EngineProvider) -> None: ...
    def execute(self, sql: str, row_cap: int) -> ExecutionResult: ...
```

Sets `SET LOCAL statement_timeout` inside the same transaction as the query (per-call, not a
connection-level default) so the timeout can vary between guarded execution and any future probe
execution (Phase 6) without a second connection pool.

---

## 6. Services

All five live under `genql/services/query/`, each constructor-injected with ports only —
no service imports a repository, a driver, or LangGraph:

- `SchemaLinkingService` — wraps `RetrievalService.search` + `SemanticCatalogReader`, returns
  `SchemaLink` tuples, raises `SchemaLinkingError` on zero results.
- `PlanningService` — one `ChatProvider.complete` call producing `QueryPlan`, grounded on the
  schema links; raises `PlanningError` on a `ValidationError` from the provider.
- `CandidateGenerationService` — one `ChatProvider.complete` call producing `SqlCandidate` from
  the plan + links; raises `GenerationError` likewise.
- `StaticValidationService` — runs `GUARDRAILS` as described in §3; raises `GuardrailViolation`.
- `GuardedExecutionService` — calls `QueryExecutor.execute` with `Settings.query_row_cap`; raises
  `ExecutionError` translating driver-level failures (timeout, permission denied) into one typed
  error, matching the existing `CatalogReader` error-translation pattern from Phase 1–2.

---

## 7. Controller: LangGraph graph and CLI

`genql/api/query_graph.py` — the only file in this phase that imports `langgraph`:

```python
class QueryState(TypedDict):
    question: str
    datasource: str
    domain_id: str | None
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    candidate: SqlCandidate | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
```

Five nodes (`schema_linking`, `planning`, `candidate_generation`, `static_validation`,
`guarded_execution`), each a one-line adapter: read the fields it needs off `QueryState`, call its
service, write the result back. A single conditional edge out of `static_validation`: on success
→ `guarded_execution`; on a repairable-but-still-failing violation with `retry_count == 0` → back
to `candidate_generation` with `retry_count` incremented; otherwise → raise (the graph does not
catch and re-wrap; the CLI layer does).

`genql/cli/commands/query.py`:

```
genql query "<question>" --datasource X [--domain Y]
```

Prints the resolved `QueryPlan.plan_text`, the final validated SQL, and the executed rows
(truncated notice if `ExecutionResult.truncated`). Any typed error from the graph is caught here
and printed as a clean one-line failure, not a traceback — matching `genql discover`'s existing
CLI error-handling convention.

---

## 8. Configuration

`Settings` gains:

```python
query_row_cap: int = 1000
query_statement_timeout_ms: int = 30_000
readonly_db_password: str
```

`chat_model` (already added in Phase 4) is reused unchanged for both `PlanningService` and
`CandidateGenerationService` — no new model-selection surface, per the parent spec's §21 stance
that model choice is configuration, not architecture.

---

## 9. Testing

**Unit** — `SchemaLinkingService`, `PlanningService`, `CandidateGenerationService` against fake
`RetrievalService`/`ChatProvider` — no network. Each of the five `Guardrail` implementations gets
its own focused test table (a candidate containing `pg_sleep` is rejected and unrepairable; a
candidate missing `LIMIT` is repaired and re-passes; a `DELETE` statement is rejected by
`statement_kind`). `StaticValidationService` gets one integration-shaped unit test asserting the
registry runs in a stable order and that a repair loop terminates after exactly one retry.
`QueryState`/graph wiring: a unit test using a fake node set asserts the conditional edge routes
correctly on both the pass and single-retry paths without needing a real `ChatProvider`.

**Integration (testcontainers)** — migration `0006` upgrade/downgrade, asserting `genql_readonly`
can `SELECT` from a seeded table and cannot `INSERT`/`DELETE`/`DROP`; `ReadOnlyQueryExecutorRepository`
against real Postgres, asserting `statement_timeout` actually aborts a deliberately slow query and
that the row cap actually truncates a result set larger than it.

**Real-provider integration (gated)** — one real `PlanningService.plan` and one real
`CandidateGenerationService.generate` call against a real TPC-DS question, skipped cleanly without
`GENQL_OPENROUTER_API_KEY`, matching Phase 4's convention exactly.

**End-to-end** — `genql query "<TPC-DS question>" --datasource local.tpcds` produces a validated
`SELECT` statement and at least one executed row, proving the full chain from a natural-language
question to a real, safely-executed answer for the first time in the project.

---

## 10. Consequences for later phases

**Phase 6 (ambiguity machinery)** adds the ambiguity gate before `schema_linking`, upgrades
`candidate_generation` to produce N candidates once critique/probing exist to consume the
disagreement between them, and wraps this phase's stateless `StateGraph` with `PostgresSaver`,
per-thread advisory locks, and `interrupt()` for real multi-turn state — the graph structure this
phase builds is extended, not replaced.

**Phase 7 (optimizer)** inserts a rewrite/cost-gating stage between `static_validation` and
`guarded_execution`; the guardrail registry's `LimitInjectionGuardrail` and the executor's row cap
stay as the safety floor underneath whatever the optimizer decides.

**A later answer-synthesis phase** adds an NL-response stage after `guarded_execution` that turns
`ExecutionResult` into prose — deliberately left undesigned here since nothing yet needs it.

---

## 11. Risks

**Single-candidate generation has no self-correction beyond one guardrail-repair retry.** Without
critique or probing, a plausible-but-wrong SQL candidate that clears every guardrail (guardrails
check safety, not correctness) executes and returns wrong rows with no signal that anything was
wrong. Mitigation: this is exactly the gap Phase 6 exists to close; Phase 5's end-to-end test
targets TPC-DS questions specific enough that a wrong-but-safe candidate is unlikely, not
impossible — accuracy measurement is explicitly out of scope until Phase 8's golden-set runner.

**A hand-provisioned read-only role is easy to get wrong once.** A missing `GRANT` on a
newly-added schema silently breaks discovery of new datasources' guarded execution rather than
failing loudly at provisioning time. Mitigation: the migration's `ALTER DEFAULT PRIVILEGES` clause
covers tables created after the grant, and the integration test in §9 asserts the negative case
(write attempts fail) as a first-class check, not just the positive case.

**LangGraph now, without its main payoff yet.** Phase 5 pays LangGraph's dependency and API-surface
cost without using checkpointing or interrupts — the two features that justify choosing it over a
plain function pipeline. Mitigation: this is a deliberate bet, made explicitly (not by default) so
that Phase 6 extends one graph instead of migrating a plain pipeline into one under more time
pressure; if Phase 6 is meaningfully delayed, this cost should be revisited rather than carried
silently.
