# GenQL Phase 5: Generation Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a natural-language question into an NL plan, one SQL candidate grounded on Phase 4's retrieval, a statically-validated statement that has cleared five registered guardrails, and real rows read back through a dedicated read-only Postgres role — the first end-to-end answer GenQL produces.

**Architecture:** Five ports (`SchemaLinker`, `Planner`, `CandidateGenerator`, `Guardrail`, `QueryExecutor`) and five services under `genql/services/query/` implement one stage each. `SchemaLinkingService` composes Phase 4's `RetrievalService` with `SemanticCatalogReader`, a new `JoinPathReader`, and a new `MetricReader` to bind retrieval hits to concrete identifiers — deterministic, no LLM. `PlanningService` and `CandidateGenerationService` each make exactly one `ChatProvider.complete` call. `StaticValidationService` resolves the five `GUARDRAILS`-registered rules through a `GuardrailFactory` (per-datasource, because the object allowlist is per-datasource), runs them in priority order over a `sqlglot`-parsed statement, repairs each repairable violation exactly once, and qualifies last. `GuardedExecutionService` resolves a `QueryExecutor` bound to a `genql_readonly` engine that the migration provisions, so the admin engine is structurally unreachable from the execution path. A real LangGraph `StateGraph` in `genql/api/` wires the five stages with one conditional edge allowing a single regeneration retry; `genql query` is the thin CLI controller over it.

**Tech Stack:** Python 3.12 (uv), `sqlglot` (new — parse, qualify, guardrail AST checks, LIMIT injection), `langgraph` (new — stateless `StateGraph`, no checkpointer, no interrupts), ParadeDB 0.25.6 on PostgreSQL 18 (reused), OpenRouter over `httpx` via Phase 4's `ChatProvider` (reused), SQLAlchemy 2.0 Core, Alembic, Pydantic v2, pydantic-settings, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-06-genql-phase-5-generation-core.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md` (§9 online pipeline, §12 safety and governance, §18 phasing, §21 model selection)

## Global Constraints

- Python 3.12 exactly, managed by `uv`. Run everything through `uv run`.
- **No SQL string, SQLAlchemy Core construct, psycopg call, `httpx` call, Cypher string, or GDS client call may appear outside `genql/repositories/`.** Enforced by import-linter: `genql.services` may not import `genql.repositories`, `genql.infrastructure`, `sqlalchemy`, `psycopg`, `neo4j`, `graphdatascience`, or `httpx`. `genql/infrastructure/` may import `sqlalchemy` to build an engine, never to run a query.
- `sqlglot` is **not** added to either import-linter forbidden list. It is a pure parser — no I/O, no driver, no network — so `StaticValidationService` may import it directly. `langgraph` is likewise unrestricted but by convention appears in exactly one place: `genql/api/query_graph.py`.
- `genql/domain/` imports no other `genql` package and performs no I/O.
- The `layers` contract already declares `genql.api > genql.services > genql.domain`. `genql/api/` may import `genql.services` and `genql.domain`; it may not import `genql.repositories` or `genql.infrastructure`. `genql/composition/` and `genql/cli/` are outside the layers contract and may import anything.
- Every file ≤ 250 lines (pre-commit hook `scripts/check_file_length.py`, `LIMIT = 250`). One class per file. One action per file.
- `uv run mypy genql` (strict) must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass. `uv run lint-imports` must pass.
- All entities and value objects are **frozen Pydantic v2 models** (`model_config = ConfigDict(frozen=True)`), not stdlib dataclasses. The spec's §2 code blocks are written as `@dataclass(frozen=True)` for brevity; the repository convention established in Phases 1–4 is Pydantic, and this plan follows the repository.
- All ports are `@runtime_checkable` `Protocol`s. Protocols carrying non-method members (`Guardrail.name`, `Guardrail.priority`) support `isinstance()` but not `issubclass()` — port tests use `isinstance`.
- Every typed failure inherits `GenqlError` from `genql/domain/errors.py`. The CLI catches `GenqlError` and prints one line plus exit code 1; it never shows a traceback.
- Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`). Commit at the end of every task.
- **Execution note for whoever runs this plan under subagent-driven-development:** the user's standing preference is to group sequentially-dependent tasks into one dispatch, parallelize genuinely independent tasks, commit at batch boundaries, and run one review at the very end. See "Execution Batches" below for the intended grouping.
- Docker (ParadeDB) runs on the Debian VM (`ssh genql-vm`, 100.99.72.99). Export before running integration tests:

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_TEST_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_URI=bolt://100.99.72.99:7687
  export GENQL_NEO4J_USER=neo4j
  export GENQL_NEO4J_PASSWORD=genqlgenql
  export GENQL_READONLY_DB_PASSWORD=genql_readonly_dev
  ```

  `GENQL_READONLY_DB_PASSWORD` is new in this phase and migration `0006` refuses to run without it (Task 2). Real-provider tests (Tasks 8, 9, 13) additionally need `GENQL_OPENROUTER_API_KEY`, which as of this plan's writing exists nowhere locally or on the VM — those tests are written to skip cleanly and **a clean skip is not a task failure**.
- **This plan may be executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit suite (`tests/unit/`) must be run and must pass there. Integration tests are written, committed, and left for a VM-connected run; report "unit green, integration written-but-unrun" exactly as Phases 2.5, 3, and 4 did.
- The baseline before Task 1 is the full Phase 4 suite green. Never leave a task boundary with a red unit suite.

---

## Deviations From the Spec (decided here, deliberately)

Each of these is a place where the spec's literal text is internally inconsistent, conflicts with an established repository convention, or would produce provably dead code. Implement the plan's version, not the spec's.

1. **`GuardrailViolation` is an entity, not an exception.** §2 defines it as a frozen record; §3 and §6 say `StaticValidationService` "raises `GuardrailViolation`". A frozen record cannot be raised. Resolution: `GuardrailViolation` stays a frozen Pydantic entity, and `StaticValidationError(QueryError)` is raised carrying `violations: tuple[GuardrailViolation, ...]`.
2. **`SchemaLink.domain_id` is `int | None`, not `str | None`.** `genql_domain.id` is `BigInteger` and `Retriever.search(domain_id: int | None)` is already `int` throughout Phase 4. `str` would be the only string domain id in the codebase.
3. **`CandidateGenerator.generate` takes the violations from the previous attempt.** The spec's conditional edge routes back to `candidate_generation` for one retry, but with `generate(plan, links)` the retry receives identical inputs and must produce an identical candidate — the retry edge would be provably dead. The port becomes `generate(plan, links, violations: tuple[GuardrailViolation, ...] = ()) -> SqlCandidate`.
4. **`QueryState` carries `violations: tuple[GuardrailViolation, ...]` instead of nothing.** Same reason as (3): the router needs the failure to decide, and the regeneration node needs it to do better.
5. **`Guardrail` gains `priority: int`.** With registry-key ordering alone the rules run alphabetically, so `object_allowlist` would reject a `DELETE` before `statement_kind` could — and §9's test explicitly requires "a `DELETE` statement is rejected by `statement_kind`". `priority` keeps the ordering declarative and open/closed: a new rule is still one file plus one decorator.
6. **`qualify` runs last, not first.** §3 says "`sqlglot.parse` + `qualify` first, then each `Guardrail.check`". `sqlglot.optimizer.qualify.qualify` raises on a non-`SELECT`, which would turn the clean `statement_kind` violation into an opaque optimizer error — exactly the case the rule exists to report. Order becomes: `parse_one` → guardrails in priority order → `qualify` on the repaired statement.
7. **Migration `0006` grants `pg_read_all_data` rather than per-schema `GRANT SELECT` + `ALTER DEFAULT PRIVILEGES`.** The spec's §11 names "a missing `GRANT` on a newly-added schema" as this phase's second risk; `pg_read_all_data` (PostgreSQL 14+, and this stack is 18) confers SELECT on every table plus USAGE on every schema, present and future, so the risk class disappears rather than being mitigated. §9's negative assertions (`INSERT`/`DELETE`/`DROP` denied) are unchanged and still the first-class check.
8. **`Settings.readonly_db_password` defaults to `""`, not required.** A required field breaks `Settings()` construction in `migrations/env.py` and in every existing container test. The house pattern for a required-at-use-time secret is `openrouter_api_key: str = ""` plus a typed error at the point of use; this follows it with `MissingReadonlySecretError`.
9. **The CLI option is `--domain-id INTEGER`, not `--domain`.** Matches `genql semantic search --domain-id` from Phase 4 and (2) above.
10. **`SchemaLinker.link` takes `datasource_name`, not `datasource`.** Every other signature in the codebase uses `datasource_name` for the string and `datasource` for the `Datasource` entity.

---

## File Structure

**Created**

```
genql/domain/entities/schema_link.py                  SchemaLink
genql/domain/entities/query_plan.py                   QueryPlan
genql/domain/entities/sql_candidate.py                SqlCandidate
genql/domain/entities/guardrail_violation.py          GuardrailViolation
genql/domain/entities/execution_result.py             ExecutionResult
genql/domain/value_objects/guardrail_config.py        GuardrailConfig
genql/domain/ports/schema_linker.py                   SchemaLinker
genql/domain/ports/planner.py                         Planner
genql/domain/ports/candidate_generator.py             CandidateGenerator
genql/domain/ports/guardrail.py                       Guardrail
genql/domain/ports/guardrail_factory.py               GuardrailFactory
genql/domain/ports/query_executor.py                  QueryExecutor
genql/domain/ports/query_executor_factory.py          QueryExecutorFactory
genql/domain/ports/join_path_reader.py                JoinPathReader
genql/domain/ports/metric_reader.py                   MetricReader
genql/domain/ports/object_name_reader.py              ObjectNameReader
migrations/versions/0006_readonly_role.py             genql_readonly role, pg_read_all_data
genql/repositories/query/__init__.py                  package marker
genql/repositories/query/query_executor_repository.py ReadOnlyQueryExecutorRepository
genql/repositories/query/object_name_repository.py    PostgresObjectNameReader
genql/repositories/semantic/join_path_reader_repository.py  PostgresJoinPathReader
genql/repositories/guardrails/__init__.py             imports the five rules for registration
genql/repositories/guardrails/registry.py             GUARDRAILS
genql/repositories/guardrails/statement_kind_guardrail.py      StatementKindGuardrail
genql/repositories/guardrails/forbidden_function_guardrail.py  ForbiddenFunctionGuardrail
genql/repositories/guardrails/object_allowlist_guardrail.py    ObjectAllowlistGuardrail
genql/repositories/guardrails/limit_injection_guardrail.py     LimitInjectionGuardrail
genql/repositories/guardrails/statement_timeout_guardrail.py   StatementTimeoutGuardrail
genql/infrastructure/query/__init__.py                package marker
genql/infrastructure/query/guardrail_factory.py       GuardrailFactoryImpl
genql/infrastructure/query/query_executor_factory.py  QueryExecutorFactoryImpl
genql/services/query/__init__.py                      package marker
genql/services/query/schema_linking_service.py        SchemaLinkingService
genql/services/query/planning_service.py              PlanningService, PlanResponse
genql/services/query/candidate_generation_service.py  CandidateGenerationService, SqlResponse
genql/services/query/static_validation_service.py     StaticValidationService
genql/services/query/guarded_execution_service.py     GuardedExecutionService
genql/api/query_state.py                              QueryState, initial_state
genql/api/query_nodes.py                              five node adapters
genql/api/query_graph.py                              build_query_graph, route_after_validation
genql/cli/commands/query.py                           `genql query`
genql/composition/query_container.py                  QueryContainer
tests/unit/test_query_entities.py
tests/unit/test_query_ports_are_runtime_checkable.py
tests/unit/test_statement_kind_guardrail.py
tests/unit/test_forbidden_function_guardrail.py
tests/unit/test_object_allowlist_guardrail.py
tests/unit/test_limit_injection_guardrail.py
tests/unit/test_statement_timeout_guardrail.py
tests/unit/test_guardrail_factory.py
tests/unit/test_static_validation_service.py
tests/unit/test_schema_linking_service.py
tests/unit/test_planning_service.py
tests/unit/test_candidate_generation_service.py
tests/unit/test_guarded_execution_service.py
tests/unit/test_query_nodes.py
tests/unit/test_query_graph.py
tests/integration/test_migration_0006.py
tests/integration/test_query_executor_repository.py
tests/integration/test_query_read_repositories.py
tests/integration/test_planning_service_real_provider.py
tests/integration/test_candidate_generation_service_real_provider.py
tests/integration/test_phase5_end_to_end.py
```

**Modified**

```
genql/domain/errors.py                      + QueryError, SchemaLinkingError, PlanningError,
                                              GenerationError, StaticValidationError,
                                              ExecutionError, MissingReadonlySecretError
genql/domain/ports/metric_writer.py         unchanged — MetricReader is a separate port file
genql/repositories/semantic/metric_repository.py  + read_metrics
genql/repositories/semantic/__init__.py     + PostgresJoinPathReader
genql/infrastructure/db/engine_provider.py  + readonly_engine_for, two-part cache key
genql/core/settings.py                      + query_row_cap, query_statement_timeout_ms,
                                              readonly_db_password
genql/composition/core_container.py         engine_provider gains readonly_password
genql/composition_root.py                   Container now inherits QueryContainer
genql/cli/main.py                           + the top-level `query` command
pyproject.toml                              + sqlglot, langgraph (Task 2)
.env.example                                + GENQL_READONLY_DB_PASSWORD, query caps
tests/integration/conftest.py               sets GENQL_READONLY_DB_PASSWORD before upgrade;
                                              adds a `readonly_engine` fixture
tests/unit/test_engine_provider.py          + readonly-binding tests
tests/unit/test_composition_root.py         + GENQL_READONLY_DB_PASSWORD env, new providers
```

**Not modified, deliberately:** `.importlinter` (no new forbidden module — see Global Constraints), `docker/compose.yaml` (no new service), `tests/unit/test_semantic_ports_are_runtime_checkable.py` (Phase 5's ports get their own file, keeping both under 250 lines).

---

## Task Sequence and Why

Task 1 is pure declaration — entities, a value object, ten ports, seven errors — so every later task can be written against fixed names without waiting on infrastructure, exactly as Phase 4's Task 1 did. Task 2 pays the two new dependencies and provisions the read-only execution path (migration + engine binding + settings) because Task 3's executor integration test cannot run without the role existing. Task 3 adds every repository this phase needs, all four of them read-or-execute only. Tasks 4 and 5 add the five guardrail rules, split so each is a reviewable unit on its own; Task 5 extends the package `__init__` Task 4 creates, so they run in that order rather than in parallel. Task 6 is the factory plus the service that consumes the registry, and is the first place the rules run together. Tasks 7–10 are the four remaining vertical slices — linking, planning, generation, execution — each depending only on Task 1 (and, for Task 10, Task 3), so all four are parallelizable. Task 11 assembles the LangGraph graph and the CLI over everything above. Task 12 is composition-root wiring, held until everything it wires exists, the same place Phases 3 and 4 put it. Task 13 proves the chain end-to-end against real infrastructure.

## Execution Batches

| Batch | Tasks | Parallelizable? |
|---|---|---|
| 1 | 1 | — |
| 2 | 2 → 3 | No (3 needs 2's role) |
| 3 | 4 → 5 | No (5 extends the package `__init__` 4 creates) |
| 4 | 6 | — |
| 5 | 7, 8, 9, 10 | Yes |
| 6 | 11 | — |
| 7 | 12 → 13 | No (13 needs the wired CLI) |

---

### Task 1: Domain foundation — entities, ports, typed errors

**Files:**
- Create: `genql/domain/entities/schema_link.py`, `genql/domain/entities/query_plan.py`, `genql/domain/entities/sql_candidate.py`, `genql/domain/entities/guardrail_violation.py`, `genql/domain/entities/execution_result.py`, `genql/domain/value_objects/guardrail_config.py`, `genql/domain/ports/schema_linker.py`, `genql/domain/ports/planner.py`, `genql/domain/ports/candidate_generator.py`, `genql/domain/ports/guardrail.py`, `genql/domain/ports/guardrail_factory.py`, `genql/domain/ports/query_executor.py`, `genql/domain/ports/query_executor_factory.py`, `genql/domain/ports/join_path_reader.py`, `genql/domain/ports/metric_reader.py`, `genql/domain/ports/object_name_reader.py`
- Modify: `genql/domain/errors.py`
- Test: `tests/unit/test_query_entities.py`, `tests/unit/test_query_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `genql.domain.entities.join_path.JoinPath`, `genql.domain.entities.metric.Metric`, `genql.domain.entities.datasource.Datasource`, `genql.domain.errors.GenqlError` (all existing)
- Produces: entities `SchemaLink`, `QueryPlan`, `SqlCandidate`, `GuardrailViolation`, `ExecutionResult`; value object `GuardrailConfig`; ports `SchemaLinker.link(question, datasource_name, domain_id) -> tuple[SchemaLink, ...]`, `Planner.plan(question, links) -> QueryPlan`, `CandidateGenerator.generate(plan, links, violations=()) -> SqlCandidate`, `Guardrail.name/priority/check(sql)/repair(sql, violation)`, `GuardrailFactory.for_datasource(datasource_name) -> Sequence[Guardrail]`, `QueryExecutor.execute(sql, row_cap) -> ExecutionResult`, `QueryExecutorFactory.for_datasource(datasource) -> QueryExecutor`, `JoinPathReader.read_join_paths(datasource_name, object_names) -> Sequence[JoinPath]`, `MetricReader.read_metrics(datasource_name) -> Sequence[Metric]`, `ObjectNameReader.read_object_names(datasource_name) -> frozenset[str]`; errors `QueryError`, `SchemaLinkingError`, `PlanningError`, `GenerationError`, `StaticValidationError`, `ExecutionError`, `MissingReadonlySecretError`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/test_query_entities.py`:

```python
"""Every Phase 5 entity is frozen: the graph passes them between nodes, and a
node mutating a neighbour's value in place would be invisible in a test."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.value_objects.guardrail_config import GuardrailConfig

PLAN = QueryPlan(
    question="how many stores are there",
    plan_text="count rows in tpcds.store",
    referenced_objects=("local.tpcds.store",),
)


def test_schema_link_defaults_every_collection_to_empty() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    assert link.column_names == ()
    assert link.join_paths == ()
    assert link.metric_names == ()
    assert link.domain_id is None


def test_schema_link_exposes_the_bare_object_name() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    assert link.schema_qualified_name == "tpcds.store"


def test_schema_link_is_frozen() -> None:
    link = SchemaLink(object_qualified_name="local.tpcds.store")

    with pytest.raises(ValidationError):
        link.object_qualified_name = "other"


def test_query_plan_coerces_referenced_objects_to_a_tuple() -> None:
    plan = QueryPlan(question="q", plan_text="p", referenced_objects=["a", "b"])

    assert plan.referenced_objects == ("a", "b")


def test_sql_candidate_carries_the_plan_it_was_generated_from() -> None:
    candidate = SqlCandidate(sql="SELECT 1", plan=PLAN)

    assert candidate.plan.question == "how many stores are there"


def test_guardrail_violation_defaults_to_unrepairable() -> None:
    violation = GuardrailViolation(rule_name="statement_kind", message="DELETE is not allowed")

    assert violation.repairable is False


def test_execution_result_is_frozen_and_keeps_row_order() -> None:
    result = ExecutionResult(
        columns=("n",), rows=((1,), (2,)), row_count=2, truncated=False
    )

    assert result.rows == ((1,), (2,))
    with pytest.raises(ValidationError):
        result.truncated = True


def test_guardrail_config_holds_an_immutable_allowlist() -> None:
    config = GuardrailConfig(
        row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset({"tpcds.store"})
    )

    assert "tpcds.store" in config.allowed_objects
    assert isinstance(config.allowed_objects, frozenset)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.schema_link'`

- [ ] **Step 3: Create the entities and the value object**

Create `genql/domain/entities/schema_link.py`:

```python
"""One retrieval hit bound to concrete SQL identifiers.

This is the whole output of schema linking: an object the retriever found,
plus the columns, mined join paths, and metrics that are actually usable
against it. Everything here is a name a generated statement may legally
mention, which is why the guardrails and the planner both read it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_qualified_name: str
    column_names: tuple[str, ...] = ()
    join_paths: tuple[str, ...] = ()
    metric_names: tuple[str, ...] = ()
    domain_id: int | None = None

    @property
    def schema_qualified_name(self) -> str:
        """`schema.object` — what appears in SQL, without the datasource prefix."""
        return self.object_qualified_name.split(".", 1)[1]
```

Create `genql/domain/entities/query_plan.py`:

```python
"""The natural-language plan produced before any SQL exists.

The parent spec's §9 stage 6 is the technique behind Oracle's Archer result:
an inspectable plan that later stages check the SQL against. Phase 5 has no
critique stage yet, so the plan's immediate job is grounding — it names the
objects the candidate is allowed to be about.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    plan_text: str
    referenced_objects: tuple[str, ...]
```

Create `genql/domain/entities/sql_candidate.py`:

```python
"""One generated statement, carrying the plan it came from.

Phase 5 generates exactly one candidate per question. The plan travels with
it so a later phase's critique stage can diff SQL against plan without
re-threading both through every signature.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.query_plan import QueryPlan


class SqlCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    plan: QueryPlan
```

Create `genql/domain/entities/guardrail_violation.py`:

```python
"""One rule's complaint about one statement.

`repairable` is the rule's own claim about its own violation, which is what
lets StaticValidationService attempt a repair without knowing anything about
the rule that reported it. Default False: a new rule is unrepairable until it
says otherwise.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GuardrailViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_name: str
    message: str
    repairable: bool = False
```

Create `genql/domain/entities/execution_result.py`:

```python
"""Rows read back from a guarded execution.

`truncated` is set by the executor when the warehouse returned more rows than
the row cap allowed, so the CLI can say so rather than silently presenting a
partial answer as a whole one.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    truncated: bool
```

Create `genql/domain/value_objects/guardrail_config.py`:

```python
"""Everything any guardrail needs, in one immutable bundle.

Every rule takes exactly this one constructor argument, which is what lets
GUARDRAILS.create(key, config=config) build all of them uniformly. A rule that
needs nothing from it (statement_kind) still accepts it, so adding a rule that
needs a new field is a change to this value object plus one new file — never a
change to how the factory constructs rules.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GuardrailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_cap: int
    statement_timeout_ms: int
    allowed_objects: frozenset[str]
```

- [ ] **Step 4: Run to verify the entity tests pass**

Run: `uv run pytest tests/unit/test_query_entities.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing port test**

Create `tests/unit/test_query_ports_are_runtime_checkable.py`:

```python
"""A plain class satisfying each port proves every Phase 5 service can be
tested without a database, an LLM, or a network call. Guardrail and
GuardrailFactory carry non-method members, so these are isinstance checks —
issubclass is not defined for data protocols."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.candidate_generator import CandidateGenerator
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.guardrail_factory import GuardrailFactory
from genql.domain.ports.join_path_reader import JoinPathReader
from genql.domain.ports.metric_reader import MetricReader
from genql.domain.ports.object_name_reader import ObjectNameReader
from genql.domain.ports.planner import Planner
from genql.domain.ports.query_executor import QueryExecutor
from genql.domain.ports.query_executor_factory import QueryExecutorFactory
from genql.domain.ports.schema_linker import SchemaLinker

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())


class FakeSchemaLinker:
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        return ()


class FakePlanner:
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        return PLAN


class FakeCandidateGenerator:
    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        return SqlCandidate(sql="SELECT 1", plan=plan)


class FakeGuardrail:
    name = "fake"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return sql


class FakeGuardrailFactory:
    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return [FakeGuardrail()]


class FakeQueryExecutor:
    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        return ExecutionResult(columns=(), rows=(), row_count=0, truncated=False)


class FakeQueryExecutorFactory:
    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        return FakeQueryExecutor()


class FakeJoinPathReader:
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return []


class FakeMetricReader:
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        return []


class FakeObjectNameReader:
    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        return frozenset()


def test_a_plain_class_satisfies_each_phase_5_port() -> None:
    assert isinstance(FakeSchemaLinker(), SchemaLinker)
    assert isinstance(FakePlanner(), Planner)
    assert isinstance(FakeCandidateGenerator(), CandidateGenerator)
    assert isinstance(FakeGuardrail(), Guardrail)
    assert isinstance(FakeGuardrailFactory(), GuardrailFactory)
    assert isinstance(FakeQueryExecutor(), QueryExecutor)
    assert isinstance(FakeQueryExecutorFactory(), QueryExecutorFactory)
    assert isinstance(FakeJoinPathReader(), JoinPathReader)
    assert isinstance(FakeMetricReader(), MetricReader)
    assert isinstance(FakeObjectNameReader(), ObjectNameReader)
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.schema_linker'`

- [ ] **Step 7: Create the ten ports**

Create `genql/domain/ports/schema_linker.py`:

```python
"""Binds a question to concrete identifiers.

Deliberately not an LLM port: the implementation composes Phase 4's retrieval
with the semantic store's own columns, join paths, and metrics. The parent
spec's correctness test for the offline/online split — retrieval and schema
linking still work with every LLM provider unreachable — holds only if this
stage never calls a model.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.schema_link import SchemaLink


@runtime_checkable
class SchemaLinker(Protocol):
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]: ...
```

Create `genql/domain/ports/planner.py`:

```python
"""Produces the natural-language plan, grounded on schema links."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink


@runtime_checkable
class Planner(Protocol):
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan: ...
```

Create `genql/domain/ports/candidate_generator.py`:

```python
"""Produces one SQL candidate from a plan and its schema links.

`violations` is empty on the first attempt and carries the previous attempt's
guardrail failures on the graph's single retry. Without it the retry would be
handed identical inputs and would have no reason to produce different SQL.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class CandidateGenerator(Protocol):
    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate: ...
```

Create `genql/domain/ports/guardrail.py`:

```python
"""One registered safety rule.

`check` returns the violations it found; `repair` is only ever called for a
violation this same rule reported as repairable, so an unrepairable rule's
`repair` may raise rather than pretend.

`priority` orders the rules deterministically at the factory. It exists
because alphabetical registry order would run the object allowlist before the
statement-kind check, and a DELETE deserves to be rejected for being a DELETE.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.guardrail_violation import GuardrailViolation


@runtime_checkable
class Guardrail(Protocol):
    name: str
    priority: int

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]: ...

    def repair(self, sql: str, violation: GuardrailViolation) -> str: ...
```

Create `genql/domain/ports/guardrail_factory.py`:

```python
"""Builds the full, priority-ordered rule set for one datasource.

Per-datasource rather than a process-wide singleton because one rule — the
object allowlist — is only meaningful against a particular datasource's
catalog. Mirrors CatalogReaderFactory and CommentWriterFactory exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.ports.guardrail import Guardrail


@runtime_checkable
class GuardrailFactory(Protocol):
    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]: ...
```

Create `genql/domain/ports/query_executor.py`:

```python
"""Runs one validated statement under a row cap and returns its rows."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.execution_result import ExecutionResult


@runtime_checkable
class QueryExecutor(Protocol):
    def execute(self, sql: str, row_cap: int) -> ExecutionResult: ...
```

Create `genql/domain/ports/query_executor_factory.py`:

```python
"""Binds a QueryExecutor to one datasource's read-only engine.

The only implementation resolves the read-only binding, never the admin one,
which is what makes the admin engine structurally unreachable from the
execution path rather than merely unused by convention.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.query_executor import QueryExecutor


@runtime_checkable
class QueryExecutorFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> QueryExecutor: ...
```

Create `genql/domain/ports/join_path_reader.py`:

```python
"""The read side of JoinPathWriter — Phase 3 mined paths, Phase 5 reads them.

Filtered by object name rather than returning a whole datasource's paths:
schema linking only ever wants the paths touching the objects retrieval
actually returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathReader(Protocol):
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]: ...
```

Create `genql/domain/ports/metric_reader.py`:

```python
"""The read side of MetricWriter — Phase 4's YAML overlay authored them,
schema linking surfaces them so a plan can name a metric rather than
re-deriving its expression."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.metric import Metric


@runtime_checkable
class MetricReader(Protocol):
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]: ...
```

Create `genql/domain/ports/object_name_reader.py`:

```python
"""Every `schema.object` the semantic store knows for one datasource.

Datasource-wide, unlike SemanticCatalogReader's per-SchemaRef reads: the
object allowlist has to reject a table in *any* unregistered schema, so it
cannot be built one schema at a time.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectNameReader(Protocol):
    def read_object_names(self, datasource_name: str) -> frozenset[str]: ...
```

- [ ] **Step 8: Run to verify the port test passes**

Run: `uv run pytest tests/unit/test_query_ports_are_runtime_checkable.py -q`
Expected: PASS

- [ ] **Step 9: Add the typed errors**

Append to `genql/domain/errors.py`:

```python
class MissingReadonlySecretError(DatasourceError):
    """GENQL_READONLY_DB_PASSWORD is unset, so no read-only engine can be built.

    Separate from MissingDatasourceSecretError: that one means a datasource's
    own DSN variable is missing, this one means the process-wide read-only
    role password is, and the fix is different in each case.
    """

    def __init__(self, datasource_name: str) -> None:
        super().__init__(
            f"no read-only engine can be built for datasource {datasource_name!r}: "
            "GENQL_READONLY_DB_PASSWORD is unset or empty"
        )
        self.datasource_name = datasource_name


class QueryError(GenqlError):
    """The online query pipeline could not produce an answer.

    Runs online, not during discovery, so it hangs off GenqlError rather than
    DiscoveryError — same placement rule RetrievalError follows.
    """


class SchemaLinkingError(QueryError):
    """Retrieval returned nothing usable for this question."""


class PlanningError(QueryError):
    """The planner could not produce a valid QueryPlan."""


class GenerationError(QueryError):
    """The candidate generator could not produce a valid SqlCandidate."""


class StaticValidationError(QueryError):
    """A candidate failed one or more guardrails and could not be repaired.

    Carries the violations rather than only a message so the graph's retry
    edge can hand them back to candidate generation as feedback.
    """

    def __init__(self, violations: tuple[GuardrailViolation, ...]) -> None:
        detail = "; ".join(f"{v.rule_name}: {v.message}" for v in violations) or "no detail"
        super().__init__(f"static validation failed: {detail}")
        self.violations = violations


class ExecutionError(QueryError):
    """Guarded execution failed — timeout, permission denied, or a bad statement."""
```

Add the import at the top of `genql/domain/errors.py`, immediately after `from __future__ import annotations`:

```python
from genql.domain.entities.guardrail_violation import GuardrailViolation
```

(`genql.domain.errors` importing `genql.domain.entities` stays inside the domain package, so the `domain-is-pure` contract is unaffected.)

- [ ] **Step 10: Verify the new errors import cleanly and the full unit suite is green**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 11: Commit**

```bash
git add genql/domain/entities/schema_link.py genql/domain/entities/query_plan.py \
  genql/domain/entities/sql_candidate.py genql/domain/entities/guardrail_violation.py \
  genql/domain/entities/execution_result.py genql/domain/value_objects/guardrail_config.py \
  genql/domain/ports/schema_linker.py genql/domain/ports/planner.py \
  genql/domain/ports/candidate_generator.py genql/domain/ports/guardrail.py \
  genql/domain/ports/guardrail_factory.py genql/domain/ports/query_executor.py \
  genql/domain/ports/query_executor_factory.py genql/domain/ports/join_path_reader.py \
  genql/domain/ports/metric_reader.py genql/domain/ports/object_name_reader.py \
  genql/domain/errors.py tests/unit/test_query_entities.py \
  tests/unit/test_query_ports_are_runtime_checkable.py
git commit -m "feat(domain): add Phase 5 generation entities, ports, and typed errors"
```

---

### Task 2: Dependencies, settings, migration `0006`, and the read-only engine binding

**Files:**
- Create: `migrations/versions/0006_readonly_role.py`, `tests/integration/test_migration_0006.py`
- Modify: `pyproject.toml`, `genql/core/settings.py`, `genql/infrastructure/db/engine_provider.py`, `genql/composition/core_container.py`, `tests/integration/conftest.py`, `.env.example`
- Test: `tests/unit/test_engine_provider.py`, `tests/integration/test_migration_0006.py`

**Interfaces:**
- Consumes: `MissingReadonlySecretError` (Task 1), existing `DatasourceEngineProvider`, existing `Datasource`
- Produces: `sqlglot` and `langgraph` as project dependencies; `Settings.query_row_cap: int = 1000`, `Settings.query_statement_timeout_ms: int = 30_000`, `Settings.readonly_db_password: str = ""`; `DatasourceEngineProvider(env, engine_factory=create_engine_from_dsn, readonly_role="genql_readonly", readonly_password="")` with `readonly_engine_for(datasource) -> Engine`; migration revision `"0006"` creating role `genql_readonly`; integration fixture `readonly_engine`

- [ ] **Step 1: Add the two new dependencies**

Both are genuinely absent from `pyproject.toml` as of this plan's writing (checked: `dependencies` lists alembic, dependency-injector, graphdatascience, httpx, neo4j, numpy, pgvector, psycopg, pydantic, pydantic-settings, pyyaml, scikit-learn, sqlalchemy, structlog, typer — neither `sqlglot` nor `langgraph` appears).

Run:

```bash
uv add sqlglot langgraph
```

Expected: `pyproject.toml` gains `"langgraph>=..."` and `"sqlglot>=..."` in `dependencies`, and `uv.lock` updates.

- [ ] **Step 2: Verify both import and that mypy is still clean**

Run: `uv run python -c "import sqlglot, langgraph; print(sqlglot.__version__)" && uv run mypy genql`
Expected: a version number printed, then `Success: no issues found`.

If mypy reports `Cannot find implementation or library stub for module named "langgraph..."`, add this block to `pyproject.toml` immediately after the existing `[[tool.mypy.overrides]]` for `sklearn` — and only if it actually reports that:

```toml
# LangGraph ships no py.typed marker on some releases.
[[tool.mypy.overrides]]
module = ["langgraph.*"]
ignore_missing_imports = true
```

- [ ] **Step 3: Add the three settings**

Modify `genql/core/settings.py` — append to the `Settings` class body, after `search_top_k`:

```python
    query_row_cap: int = 1000
    query_statement_timeout_ms: int = 30_000
    # Empty by default rather than required: `migrations/env.py` and every
    # container unit test construct Settings() without it, and the house
    # pattern for a required-at-use-time secret is exactly openrouter_api_key's
    # — default empty, typed error at the point of use.
    readonly_db_password: str = ""
```

- [ ] **Step 4: Write the failing read-only engine tests**

Append to `tests/unit/test_engine_provider.py`:

```python
def test_the_readonly_engine_swaps_the_role_and_password_into_the_dsn() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )

    engine = provider.readonly_engine_for(DS)

    assert engine.dsn == "postgresql+psycopg://genql_readonly:s3cret@host:5433/genql"  # type: ignore[attr-defined]


def test_the_readonly_engine_is_cached_separately_from_the_admin_engine() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )

    admin = provider.engine_for(DS)
    readonly = provider.readonly_engine_for(DS)

    assert admin is not readonly
    assert provider.readonly_engine_for(DS) is readonly


def test_a_missing_readonly_password_raises_a_typed_error() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"})

    with pytest.raises(MissingReadonlySecretError, match="wh2"):
        provider.readonly_engine_for(DS)


def test_invalidate_drops_both_bindings() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )
    admin = provider.engine_for(DS)
    readonly = provider.readonly_engine_for(DS)

    provider.invalidate("wh2")

    assert provider.engine_for(DS) is not admin
    assert provider.readonly_engine_for(DS) is not readonly
```

And extend the import at the top of the same file:

```python
from genql.domain.errors import MissingDatasourceSecretError, MissingReadonlySecretError
```

- [ ] **Step 5: Run to verify the new tests fail**

Run: `uv run pytest tests/unit/test_engine_provider.py -q`
Expected: FAIL — `AttributeError: 'DatasourceEngineProvider' object has no attribute 'readonly_engine_for'`

- [ ] **Step 6: Add the read-only binding to the engine provider**

Replace the whole body of `genql/infrastructure/db/engine_provider.py`:

```python
"""Maps a Datasource to a pooled Engine, one per datasource name and role.

The environment is injected rather than read from `os.environ` directly, so
unit tests describe a datasource whose secret is missing without mutating
process state.

Two bindings exist per datasource, keyed ("admin", name) and
("readonly", name). Only `readonly_engine_for` is reachable from the guarded
execution path, so the admin engine is structurally out of reach there rather
than merely unused by convention. Both are cached for the process lifetime,
which is right for a CLI invocation and for a long-lived API process;
`invalidate` drops both so removing a datasource cannot leave a stale
connection behind inside one process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, MissingReadonlySecretError
from genql.infrastructure.db.engine import create_engine_from_dsn

READONLY_ROLE = "genql_readonly"

_ADMIN = "admin"
_READONLY = "readonly"


class DatasourceEngineProvider:
    def __init__(
        self,
        env: Mapping[str, str],
        engine_factory: Callable[[str], Engine] = create_engine_from_dsn,
        readonly_role: str = READONLY_ROLE,
        readonly_password: str = "",
    ) -> None:
        self._env = env
        self._engine_factory = engine_factory
        self._readonly_role = readonly_role
        self._readonly_password = readonly_password
        self._engines: dict[tuple[str, str], Engine] = {}

    def engine_for(self, datasource: Datasource) -> Engine:
        return self._cached(_ADMIN, datasource, self._dsn_for(datasource))

    def readonly_engine_for(self, datasource: Datasource) -> Engine:
        if not self._readonly_password.strip():
            raise MissingReadonlySecretError(datasource.name)
        url = make_url(self._dsn_for(datasource)).set(
            username=self._readonly_role, password=self._readonly_password
        )
        return self._cached(_READONLY, datasource, url.render_as_string(hide_password=False))

    def invalidate(self, name: str) -> None:
        self._engines.pop((_ADMIN, name), None)
        self._engines.pop((_READONLY, name), None)

    def _cached(self, role: str, datasource: Datasource, dsn: str) -> Engine:
        key = (role, datasource.name)
        cached = self._engines.get(key)
        if cached is not None:
            return cached
        engine = self._engine_factory(dsn)
        self._engines[key] = engine
        return engine

    def _dsn_for(self, datasource: Datasource) -> str:
        dsn = self._env.get(datasource.dsn_env_var, "").strip()
        if not dsn:
            raise MissingDatasourceSecretError(datasource.name, datasource.dsn_env_var)
        return dsn
```

- [ ] **Step 7: Run to verify the engine-provider tests pass**

Run: `uv run pytest tests/unit/test_engine_provider.py -q`
Expected: PASS (9 tests — the 5 pre-existing ones still green)

- [ ] **Step 8: Pass the read-only password through the composition root**

Modify `genql/composition/core_container.py`, replacing the `engine_provider` provider:

```python
    engine_provider = providers.Singleton(
        DatasourceEngineProvider,
        env=os.environ,
        readonly_password=settings.provided.readonly_db_password,
    )
```

- [ ] **Step 9: Write the failing migration test**

Create `tests/integration/test_migration_0006.py`:

```python
"""The negative assertions are the point. A read-only role that can SELECT is
easy to get right by accident; one that genuinely cannot INSERT, DELETE, or
DROP is what the guarded execution path depends on."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from genql.infrastructure.db.engine import create_engine_from_dsn


@pytest.fixture()
def readonly_engine(migrated_engine: Engine, paradedb_dsn: str) -> Engine:
    url = make_url(paradedb_dsn).set(
        username="genql_readonly", password=os.environ["GENQL_READONLY_DB_PASSWORD"]
    )
    return create_engine_from_dsn(url.render_as_string(hide_password=False))


def test_the_role_exists_after_upgrade(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genql_readonly')")
        ).scalar_one()

    assert exists is True


@pytest.mark.skipif_no_tpcds
def test_the_role_can_select_from_a_seeded_table(readonly_engine: Engine) -> None:
    with readonly_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM tpcds.store")).scalar_one()

    assert count >= 0


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_insert(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"), readonly_engine.begin() as conn:
        conn.execute(text("INSERT INTO tpcds.store (s_store_sk) VALUES (-1)"))


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_delete(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"), readonly_engine.begin() as conn:
        conn.execute(text("DELETE FROM tpcds.store"))


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_drop(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="must be owner"), readonly_engine.begin() as conn:
        conn.execute(text("DROP TABLE tpcds.store"))


def test_the_role_can_read_a_table_created_after_the_grant(
    migrated_engine: Engine, readonly_engine: Engine
) -> None:
    """pg_read_all_data covers objects created later, which per-schema GRANTs do not."""
    with migrated_engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS public.after_the_grant (n int)"))
        conn.execute(text("INSERT INTO public.after_the_grant (n) VALUES (7)"))
    try:
        with readonly_engine.connect() as conn:
            value = conn.execute(text("SELECT n FROM public.after_the_grant")).scalar_one()
        assert value == 7
    finally:
        with migrated_engine.begin() as conn:
            conn.execute(text("DROP TABLE public.after_the_grant"))
```

- [ ] **Step 10: Run to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0006.py -q`
Expected: FAIL — `test_the_role_exists_after_upgrade` asserts `False`, because revision `0006` does not exist yet. (If the VM is unreachable, this step is deferred with the rest of the integration suite.)

- [ ] **Step 11: Write the migration**

Create `migrations/versions/0006_readonly_role.py`:

```python
"""read-only execution role

Revision ID: 0006
Revises: 0005

Creates the login role guarded execution connects as. `pg_read_all_data`
(PostgreSQL 14+) is granted rather than a per-schema `GRANT SELECT` plus
`ALTER DEFAULT PRIVILEGES`: the predefined role confers SELECT on every table
and USAGE on every schema, including ones created after this migration ran,
which removes the "a newly-added schema silently has no grant" failure mode
instead of merely narrowing it. No write privilege of any kind is granted, so
the role stays read-only by construction.

The password comes from GENQL_READONLY_DB_PASSWORD and is never hardcoded.
DDL cannot be parameterized, so the value is validated against a strict
character class before it is interpolated — a password that would need
escaping is rejected rather than escaped.
"""

from __future__ import annotations

import re

from alembic import op
from sqlalchemy import text

from genql.core.settings import Settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ROLE = "genql_readonly"
_SAFE_PASSWORD = re.compile(r"^[A-Za-z0-9_.:@+~-]{8,128}$")


def _password() -> str:
    password = Settings().readonly_db_password.strip()
    if not password:
        raise RuntimeError(
            "GENQL_READONLY_DB_PASSWORD is unset. Migration 0006 provisions the "
            f"{ROLE!r} login role and refuses to invent a password for it."
        )
    if not _SAFE_PASSWORD.match(password):
        raise RuntimeError(
            "GENQL_READONLY_DB_PASSWORD must be 8-128 characters from "
            "[A-Za-z0-9_.:@+~-]; DDL cannot be parameterized and this "
            "migration rejects rather than escapes."
        )
    return password


def upgrade() -> None:
    password = _password()
    database = op.get_bind().execute(text("SELECT current_database()")).scalar_one()
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                EXECUTE 'CREATE ROLE {ROLE} LOGIN PASSWORD ''{password}''';
            ELSE
                EXECUTE 'ALTER ROLE {ROLE} LOGIN PASSWORD ''{password}''';
            END IF;
        END $$;
    """)
    op.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {ROLE}')
    op.execute(f"GRANT pg_read_all_data TO {ROLE}")


def downgrade() -> None:
    database = op.get_bind().execute(text("SELECT current_database()")).scalar_one()
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                EXECUTE 'REVOKE pg_read_all_data FROM {ROLE}';
                EXECUTE 'REVOKE CONNECT ON DATABASE "{database}" FROM {ROLE}';
                EXECUTE 'DROP OWNED BY {ROLE}';
                EXECUTE 'DROP ROLE {ROLE}';
            END IF;
        END $$;
    """)
```

- [ ] **Step 12: Make the password available to the migration in tests**

Modify `tests/integration/conftest.py` — in the `migrated_engine` fixture, set the variable before `command.upgrade` so a sandbox or CI run without a `.env` file still provisions the role:

```python
@pytest.fixture(scope="session")
def migrated_engine(engine: Engine, paradedb_dsn: str) -> Engine:
    # Migration 0006 refuses to invent a password for genql_readonly. Tests
    # supply a known one so the read-only fixtures below can connect as it.
    os.environ.setdefault("GENQL_READONLY_DB_PASSWORD", "genql_readonly_dev")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")
    return engine
```

- [ ] **Step 13: Run the migration test to verify it passes**

Run: `uv run pytest tests/integration/test_migration_0006.py tests/integration/test_migrations.py -q`
Expected: PASS — the role exists, SELECT works, INSERT/DELETE/DROP are refused, and a table created after the grant is still readable. Where `tpcds` is not seeded the three write-denial tests skip cleanly. If the VM is unreachable, record "written, unrun".

- [ ] **Step 14: Verify downgrade drops the role**

Run: `uv run alembic downgrade 0005 && uv run psql "$GENQL_TEST_DSN" -c "SELECT count(*) FROM pg_roles WHERE rolname='genql_readonly'" && uv run alembic upgrade head`
Expected: `0` between the two alembic calls, and `head` restored afterwards. If `psql` is unavailable, substitute `uv run python -c "from sqlalchemy import create_engine, text; import os; e=create_engine(os.environ['GENQL_TEST_DSN']); print(e.connect().execute(text(\"SELECT count(*) FROM pg_roles WHERE rolname='genql_readonly'\")).scalar_one())"`.

- [ ] **Step 15: Document the new environment variable**

Append to `.env.example`:

```
# Password for the genql_readonly login role that migration 0006 provisions.
# Guarded execution connects as this role; nothing else may.
GENQL_READONLY_DB_PASSWORD=genql_readonly_dev
GENQL_QUERY_ROW_CAP=1000
GENQL_QUERY_STATEMENT_TIMEOUT_MS=30000
```

- [ ] **Step 16: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 17: Commit**

```bash
git add pyproject.toml uv.lock genql/core/settings.py genql/infrastructure/db/engine_provider.py \
  genql/composition/core_container.py migrations/versions/0006_readonly_role.py \
  tests/integration/conftest.py tests/integration/test_migration_0006.py \
  tests/unit/test_engine_provider.py .env.example
git commit -m "feat(db): provision the genql_readonly role and its engine binding"
```

---

### Task 3: Query repositories — join paths, object names, and the read-only executor

**Files:**
- Create: `genql/repositories/query/__init__.py`, `genql/repositories/query/object_name_repository.py`, `genql/repositories/query/query_executor_repository.py`, `genql/repositories/semantic/join_path_reader_repository.py`, `tests/integration/test_query_read_repositories.py`, `tests/integration/test_query_executor_repository.py`
- Modify: `genql/repositories/semantic/metric_repository.py`, `genql/repositories/semantic/__init__.py`
- Test: `tests/integration/test_query_read_repositories.py`, `tests/integration/test_query_executor_repository.py`

**Interfaces:**
- Consumes: `JoinPathReader`, `MetricReader`, `ObjectNameReader`, `QueryExecutor` ports and `ExecutionResult`, `ExecutionError` (Task 1); `DatasourceEngineProvider.readonly_engine_for` (Task 2)
- Produces: `PostgresJoinPathReader(engine).read_join_paths(datasource_name, object_names) -> Sequence[JoinPath]`; `PostgresObjectNameReader(engine).read_object_names(datasource_name) -> frozenset[str]`; `PostgresMetricRepository.read_metrics(datasource_name) -> Sequence[Metric]` added to the existing class; `ReadOnlyQueryExecutorRepository(engine, statement_timeout_ms).execute(sql, row_cap) -> ExecutionResult`

- [ ] **Step 1: Write the failing read-repository integration test**

Create `tests/integration/test_query_read_repositories.py`:

```python
"""The three read sides schema linking needs. All are plain SELECTs against
tables Phases 2.5-4 already created, so the only thing worth asserting is the
shape they hand back and the filtering they apply."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.domain.entities.metric import Metric
from genql.repositories.query.object_name_repository import PostgresObjectNameReader
from genql.repositories.semantic.join_path_reader_repository import PostgresJoinPathReader
from genql.repositories.semantic.metric_repository import PostgresMetricRepository

DS = "query_reads_test"


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object "
                "(datasource_name, schema_name, object_name, object_type) VALUES "
                "(:ds, 'shop', 'orders', 'table'), (:ds, 'shop', 'customers', 'table') "
                "ON CONFLICT DO NOTHING"
            ),
            {"ds": DS},
        )
        conn.execute(
            text(
                "INSERT INTO genql.genql_join_path "
                "(datasource_name, schema_name, source_object, target_object, path, weight) "
                "VALUES (:ds, 'shop', 'orders', 'customers', ARRAY['orders','customers'], 1.0) "
                "ON CONFLICT ON CONSTRAINT pk_genql_join_path DO NOTHING"
            ),
            {"ds": DS},
        )


def test_object_names_come_back_schema_qualified_and_lowercased(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    _seed(migrated_engine)

    names = PostgresObjectNameReader(migrated_engine).read_object_names(DS)

    assert "shop.orders" in names
    assert "shop.customers" in names


def test_join_paths_are_filtered_to_the_objects_asked_for(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    _seed(migrated_engine)
    reader = PostgresJoinPathReader(migrated_engine)

    matched = reader.read_join_paths(DS, ["orders"])
    unmatched = reader.read_join_paths(DS, ["nothing_here"])

    assert [p.target_object for p in matched] == ["customers"]
    assert list(unmatched) == []


def test_an_empty_object_name_list_reads_nothing(migrated_engine: Engine) -> None:
    assert list(PostgresJoinPathReader(migrated_engine).read_join_paths(DS, [])) == []


def test_metrics_round_trip_through_the_same_repository(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    repository = PostgresMetricRepository(migrated_engine)
    repository.write(
        [Metric(datasource_name=DS, name="net_revenue", sql_expression="sum(o.total)", grain="day")]
    )

    metrics = repository.read_metrics(DS)

    assert [m.name for m in metrics] == ["net_revenue"]
    assert metrics[0].sql_expression == "sum(o.total)"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_query_read_repositories.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.query'`

- [ ] **Step 3: Implement the three read sides**

Create `genql/repositories/query/__init__.py`:

```python
"""Repositories the online query pipeline reads and executes through.

Separate from `repositories/semantic/` because nothing here writes: this
package holds the read side of the store and the one component that touches a
warehouse driver at query time.
"""
```

Create `genql/repositories/query/object_name_repository.py`:

```python
"""Every `schema.object` one datasource has in the semantic store.

Lowercased on the way out because the only consumer is the object allowlist,
which compares against identifiers sqlglot has normalized — comparing raw
catalog casing against normalized SQL would reject valid statements.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

_SELECT_OBJECT_NAMES = text("""
    SELECT schema_name, object_name
    FROM genql.genql_object
    WHERE datasource_name = :datasource_name
""")


class PostgresObjectNameReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_OBJECT_NAMES, {"datasource_name": datasource_name}
            ).all()
        return frozenset(f"{r.schema_name}.{r.object_name}".lower() for r in rows)
```

Create `genql/repositories/semantic/join_path_reader_repository.py`:

```python
"""The read side of Phase 3's mined join paths.

Lives beside PostgresJoinPathWriterRepository rather than in
repositories/query/ because it reads the table that package's sibling writes,
and splitting a table's reader from its writer across packages makes both
harder to keep in step.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.join_path import JoinPath

_SELECT_JOIN_PATHS = text("""
    SELECT datasource_name, schema_name, source_object, target_object, path, weight, provenance
    FROM genql.genql_join_path
    WHERE datasource_name = :datasource_name
      AND (source_object = ANY(:object_names) OR target_object = ANY(:object_names))
    ORDER BY weight DESC, source_object, target_object
""")


class PostgresJoinPathReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        if not object_names:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_JOIN_PATHS,
                {"datasource_name": datasource_name, "object_names": list(object_names)},
            ).all()
        return [JoinPath.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

Add `read_metrics` to `genql/repositories/semantic/metric_repository.py` — a new module-level statement above the class:

```python
_SELECT_METRICS = text("""
    SELECT datasource_name, name, sql_expression, grain, unit, default_filters, provenance
    FROM genql.genql_metric
    WHERE datasource_name = :datasource_name
    ORDER BY name
""")
```

and a new method on `PostgresMetricRepository`, after `write`:

```python
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_METRICS, {"datasource_name": datasource_name}
            ).all()
        return [Metric.model_validate(r._mapping) for r in rows]  # noqa: SLF001
```

Also update the class docstring's first line to `"""YAML-authored metrics, upserted by (datasource_name, name) and read back by datasource."""`.

Register the new reader for import convenience in `genql/repositories/semantic/__init__.py`:

```python
from genql.repositories.semantic.join_path_reader_repository import PostgresJoinPathReader
```

and add `"PostgresJoinPathReader"` to `__all__`.

- [ ] **Step 4: Run to verify the read tests pass**

Run: `uv run pytest tests/integration/test_query_read_repositories.py -q`
Expected: PASS (4 tests). If the VM is unreachable, record "written, unrun".

- [ ] **Step 5: Write the failing executor integration test**

Create `tests/integration/test_query_executor_repository.py`:

```python
"""The two safety properties that only a real database can prove: the
statement timeout actually aborts a slow query, and the row cap actually
truncates a result set larger than itself."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from genql.domain.errors import ExecutionError
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.repositories.query.query_executor_repository import ReadOnlyQueryExecutorRepository


@pytest.fixture()
def readonly_engine(migrated_engine: Engine, paradedb_dsn: str) -> Engine:
    url = make_url(paradedb_dsn).set(
        username="genql_readonly", password=os.environ["GENQL_READONLY_DB_PASSWORD"]
    )
    return create_engine_from_dsn(url.render_as_string(hide_password=False))


def test_rows_and_columns_come_back_in_order(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT 1 AS a, 2 AS b", row_cap=10)

    assert result.columns == ("a", "b")
    assert result.rows == ((1, 2),)
    assert result.row_count == 1
    assert result.truncated is False


def test_the_row_cap_truncates_and_says_so(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT n FROM generate_series(1, 50) AS n", row_cap=5)

    assert result.row_count == 5
    assert result.truncated is True
    assert result.rows[0] == (1,)


def test_an_exactly_full_result_is_not_reported_as_truncated(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT n FROM generate_series(1, 5) AS n", row_cap=5)

    assert result.row_count == 5
    assert result.truncated is False


def test_the_statement_timeout_aborts_a_slow_query(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=250)

    with pytest.raises(ExecutionError, match="timeout|canceling"):
        executor.execute("SELECT pg_sleep(5)", row_cap=10)


def test_a_write_attempt_is_translated_to_a_typed_error(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    with pytest.raises(ExecutionError):
        executor.execute("CREATE TABLE should_not_exist (n int)", row_cap=10)
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/integration/test_query_executor_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.query.query_executor_repository'`

- [ ] **Step 7: Implement the executor repository**

Create `genql/repositories/query/query_executor_repository.py`:

```python
"""The only place in Phase 5 that touches a database driver.

`SET LOCAL statement_timeout` is issued inside the same transaction as the
query rather than as a connection-level default, so a future probe execution
(Phase 6) can carry a stricter budget without a second connection pool.

One extra row beyond the cap is fetched and thrown away: that is how the
result knows it was truncated without counting the whole set, and it is why
`LIMIT` injection is a guardrail rather than this repository's job — the cap
here is the floor underneath whatever LIMIT the statement already carries.

Driver failures are translated here, not in the service, for the same reason
CatalogReader translates its own: a service that cannot import sqlalchemy
cannot catch a DBAPIError.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import ExecutionError


class ReadOnlyQueryExecutorRepository:
    def __init__(self, engine: Engine, statement_timeout_ms: int) -> None:
        self._engine = engine
        self._statement_timeout_ms = statement_timeout_ms

    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        try:
            with self._engine.begin() as conn:
                # statement_timeout is a GUC, not a bindable value; the int
                # cast is what makes the interpolation safe.
                conn.execute(text(f"SET LOCAL statement_timeout = {int(self._statement_timeout_ms)}"))
                cursor = conn.execute(text(sql))
                columns = tuple(str(key) for key in cursor.keys())
                fetched = cursor.fetchmany(row_cap + 1)
        except SQLAlchemyError as exc:
            raise ExecutionError(f"failed to execute the validated statement: {exc}") from exc

        kept = fetched[:row_cap]
        return ExecutionResult(
            columns=columns,
            rows=tuple(tuple(row) for row in kept),
            row_count=len(kept),
            truncated=len(fetched) > row_cap,
        )
```

- [ ] **Step 8: Run to verify the executor tests pass**

Run: `uv run pytest tests/integration/test_query_executor_repository.py -q`
Expected: PASS (5 tests). If the VM is unreachable, record "written, unrun".

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/repositories/query genql/repositories/semantic/join_path_reader_repository.py \
  genql/repositories/semantic/metric_repository.py genql/repositories/semantic/__init__.py \
  tests/integration/test_query_read_repositories.py \
  tests/integration/test_query_executor_repository.py
git commit -m "feat(repositories): add query read sides and the read-only executor"
```

---

### Task 4: The guardrail registry, `statement_kind`, and `forbidden_function`

**Files:**
- Create: `genql/repositories/guardrails/__init__.py`, `genql/repositories/guardrails/registry.py`, `genql/repositories/guardrails/statement_kind_guardrail.py`, `genql/repositories/guardrails/forbidden_function_guardrail.py`
- Test: `tests/unit/test_statement_kind_guardrail.py`, `tests/unit/test_forbidden_function_guardrail.py`

**Interfaces:**
- Consumes: `Guardrail` port, `GuardrailViolation`, `GuardrailConfig`, `StaticValidationError` (Task 1); `Registry` from `genql/registries/registry.py`; `sqlglot` (Task 2)
- Produces: `GUARDRAILS: Registry[Guardrail]` in `genql/repositories/guardrails/registry.py`; `StatementKindGuardrail(config)` registered as `"statement_kind"` with `priority = 10`; `ForbiddenFunctionGuardrail(config)` registered as `"forbidden_function"` with `priority = 20`. Every rule's constructor signature is `__init__(self, config: GuardrailConfig) -> None` — the factory in Task 6 depends on that being uniform.

- [ ] **Step 1: Write the failing `statement_kind` tests**

Create `tests/unit/test_statement_kind_guardrail.py`:

```python
"""Parent spec §12: statement kind restricted to SELECT and WITH. No DDL, DML,
or DCL — and nothing here is repairable, because rewriting a DELETE into a
SELECT would be guessing at intent, not repairing a defect."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> StatementKindGuardrail:
    return StatementKindGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT s.name FROM shop.store AS s WHERE s.id = 1 LIMIT 10",
        "WITH t AS (SELECT 1 AS n) SELECT n FROM t",
        "SELECT 1 UNION ALL SELECT 2",
        "(SELECT 1)",
    ],
)
def test_select_and_with_statements_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM shop.store",
        "INSERT INTO shop.store (id) VALUES (1)",
        "UPDATE shop.store SET id = 2",
        "DROP TABLE shop.store",
        "CREATE TABLE t (n int)",
        "GRANT SELECT ON shop.store TO someone",
        "COPY shop.store FROM '/etc/passwd'",
    ],
)
def test_every_other_statement_kind_is_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "statement_kind"
    assert violations[0].repairable is False


def test_unparseable_sql_is_reported_here_rather_than_crashing() -> None:
    violations = _rule().check("SELECT FROM WHERE ((")

    assert len(violations) == 1
    assert "parse" in violations[0].message.lower()
    assert violations[0].repairable is False


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("DELETE FROM shop.store")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("DELETE FROM shop.store", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "statement_kind"
    assert _rule().priority == 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_statement_kind_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.guardrails'`

- [ ] **Step 3: Create the package, the registry, and the `statement_kind` rule**

Create `genql/repositories/guardrails/__init__.py`:

```python
"""The registered guardrail rules.

Importing this package is what populates GUARDRAILS: each module below
decorates its class into the registry. Adding a rule is one new file plus one
import line here — no factory, service, or call site changes.
"""

from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail

__all__ = [
    "ForbiddenFunctionGuardrail",
    "StatementKindGuardrail",
]
```

Create `genql/repositories/guardrails/registry.py`:

```python
"""The guardrail registry, keyed by rule name.

Mirrors the EnricherRegistry pattern from Phase 4: one file plus one
decorator adds a rule. Rules are ordered by their declared `priority`, not by
registry key, so registration order and alphabetical key order are both
irrelevant to correctness.
"""

from __future__ import annotations

from genql.domain.ports.guardrail import Guardrail
from genql.registries.registry import Registry

GUARDRAILS: Registry[Guardrail] = Registry("guardrails")
```

Create `genql/repositories/guardrails/statement_kind_guardrail.py`:

```python
"""Only SELECT and WITH survive. Runs first (priority 10) so a DELETE is
rejected for being a DELETE rather than for happening to name a table the
allowlist has never heard of.

Parse failures are reported here too: this is the first rule to touch the
statement, so a candidate that is not SQL at all gets one clean violation
instead of five confused ones.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS

_ALLOWED = (exp.Select, exp.Union, exp.Subquery)


@GUARDRAILS.register("statement_kind")
class StatementKindGuardrail:
    name = "statement_kind"
    priority = 10

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError as exc:
            return (
                GuardrailViolation(
                    rule_name=self.name, message=f"could not parse the candidate: {exc}"
                ),
            )
        if isinstance(expression, _ALLOWED):
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    f"{type(expression).__name__.upper()} is not permitted; "
                    "only SELECT and WITH statements may be executed"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))
```

- [ ] **Step 4: Run to verify the `statement_kind` tests pass**

Run: `uv run pytest tests/unit/test_statement_kind_guardrail.py -q`
Expected: PASS (15 tests across the parametrizations)

- [ ] **Step 5: Write the failing `forbidden_function` tests**

Create `tests/unit/test_forbidden_function_guardrail.py`:

```python
"""Parent spec §12: pg_sleep, dblink, pg_read_file, large-object functions,
and anything else performing I/O. COPY is not listed here on purpose — it is a
statement kind, and statement_kind already rejects it with a better message."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> ForbiddenFunctionGuardrail:
    return ForbiddenFunctionGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(5)",
        "SELECT PG_SLEEP(5)",
        "SELECT * FROM dblink('dbname=x', 'SELECT 1') AS t(n int)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT n FROM t WHERE n = (SELECT pg_sleep(1))",
    ],
)
def test_forbidden_functions_are_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "forbidden_function"
    assert violations[0].repairable is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM shop.store",
        "SELECT sum(o.total) FROM shop.orders AS o",
        "SELECT date_trunc('day', o.created_at) FROM shop.orders AS o",
    ],
)
def test_ordinary_functions_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


def test_the_message_names_the_offending_function() -> None:
    violations = _rule().check("SELECT pg_sleep(5)")

    assert "pg_sleep" in violations[0].message


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("SELECT pg_sleep(5)")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("SELECT pg_sleep(5)", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "forbidden_function"
    assert _rule().priority == 20
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_forbidden_function_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.guardrails.forbidden_function_guardrail'`

- [ ] **Step 7: Implement the `forbidden_function` rule**

Create `genql/repositories/guardrails/forbidden_function_guardrail.py`:

```python
"""Rejects functions that read files, sleep, open connections, or touch large
objects. An allowlist of permitted functions would be the stronger design and
is deliberately not what this is: the warehouse's own function set is open,
and blocking the named I/O escape hatches is what the parent spec §12 asks
for. Phase 7's optimizer is the natural place to revisit that trade.

Names are matched against the parsed AST rather than the SQL text so that
`/* pg_sleep */` in a comment and a column literally named `pg_sleep_seconds`
do not trip the rule.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS

FORBIDDEN = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "lo_get",
        "lo_put",
        "query_to_xml",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
    }
)


def _function_names(expression: exp.Expression) -> set[str]:
    names = {str(node.this).lower() for node in expression.find_all(exp.Anonymous)}
    for node in expression.find_all(exp.Func):
        if not isinstance(node, exp.Anonymous):
            names.add(node.sql_name().lower())
    return names


@GUARDRAILS.register("forbidden_function")
class ForbiddenFunctionGuardrail:
    name = "forbidden_function"
    priority = 20

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures and has already
            # reported this one with a better message.
            return ()
        offenders = sorted(_function_names(expression) & FORBIDDEN)
        if not offenders:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=f"forbidden function(s) called: {', '.join(offenders)}",
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))
```

- [ ] **Step 8: Run to verify the `forbidden_function` tests pass**

Run: `uv run pytest tests/unit/test_forbidden_function_guardrail.py -q`
Expected: PASS

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/repositories/guardrails tests/unit/test_statement_kind_guardrail.py \
  tests/unit/test_forbidden_function_guardrail.py
git commit -m "feat(guardrails): add the registry, statement_kind, and forbidden_function"
```

---

### Task 5: `object_allowlist`, `limit_injection`, and `statement_timeout`

**Files:**
- Create: `genql/repositories/guardrails/object_allowlist_guardrail.py`, `genql/repositories/guardrails/limit_injection_guardrail.py`, `genql/repositories/guardrails/statement_timeout_guardrail.py`
- Modify: `genql/repositories/guardrails/__init__.py`
- Test: `tests/unit/test_object_allowlist_guardrail.py`, `tests/unit/test_limit_injection_guardrail.py`, `tests/unit/test_statement_timeout_guardrail.py`

**Interfaces:**
- Consumes: `GUARDRAILS` registry and the `GuardrailConfig`/`GuardrailViolation`/`StaticValidationError` names from Tasks 1 and 4
- Produces: `ObjectAllowlistGuardrail(config)` as `"object_allowlist"`, `priority = 30`, unrepairable; `LimitInjectionGuardrail(config)` as `"limit_injection"`, `priority = 40`, **repairable** — `repair` returns the statement with `LIMIT config.row_cap` applied; `StatementTimeoutGuardrail(config)` as `"statement_timeout"`, `priority = 50`, reports only a misconfigured timeout

- [ ] **Step 1: Write the failing `object_allowlist` tests**

Create `tests/unit/test_object_allowlist_guardrail.py`:

```python
"""Parent spec §12: object allowlist enforced against the semantic store. A
table GenQL has never catalogued is not a table this statement may read, which
is what stops a hallucinated join from reaching the warehouse at all."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.object_allowlist_guardrail import ObjectAllowlistGuardrail

CONFIG = GuardrailConfig(
    row_cap=1000,
    statement_timeout_ms=30_000,
    allowed_objects=frozenset({"shop.orders", "shop.customers"}),
)


def _rule() -> ObjectAllowlistGuardrail:
    return ObjectAllowlistGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM shop.orders",
        "SELECT * FROM SHOP.ORDERS",
        "SELECT o.id FROM shop.orders AS o JOIN shop.customers AS c ON c.id = o.customer_id",
        "SELECT * FROM orders",
    ],
)
def test_catalogued_objects_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


def test_a_cte_name_is_not_treated_as_a_table() -> None:
    sql = "WITH recent AS (SELECT * FROM shop.orders) SELECT * FROM recent"

    assert _rule().check(sql) == ()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM shop.secrets",
        "SELECT * FROM pg_catalog.pg_authid",
        "SELECT o.id FROM shop.orders AS o JOIN other.thing AS t ON t.id = o.id",
    ],
)
def test_uncatalogued_objects_are_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "object_allowlist"
    assert violations[0].repairable is False


def test_the_message_names_every_offending_object() -> None:
    violations = _rule().check("SELECT * FROM shop.secrets, other.thing")

    assert "shop.secrets" in violations[0].message
    assert "other.thing" in violations[0].message


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("SELECT * FROM shop.secrets")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("SELECT * FROM shop.secrets", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "object_allowlist"
    assert _rule().priority == 30
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_object_allowlist_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `object_allowlist`**

Create `genql/repositories/guardrails/object_allowlist_guardrail.py`:

```python
"""Every table and view the statement reads must be in the semantic store.

An unqualified table name is matched against the bare object name in the
allowlist rather than rejected: candidate generation is prompted with
`schema.object` names, but sqlglot's rendering of a single-schema query can
drop the qualifier, and rejecting that would fail valid SQL for a formatting
reason. A name that matches nothing at all — qualified or not — is a
hallucinated object and is refused.

CTE names are collected first and excluded: `WITH recent AS (...) SELECT FROM
recent` reads no table called `recent`.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("object_allowlist")
class ObjectAllowlistGuardrail:
    name = "object_allowlist"
    priority = 30

    def __init__(self, config: GuardrailConfig) -> None:
        self._allowed = config.allowed_objects
        self._bare = {name.split(".", 1)[-1] for name in config.allowed_objects}

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            return ()

        cte_names = {str(cte.alias_or_name).lower() for cte in expression.find_all(exp.CTE)}
        offenders = sorted(
            {
                referenced
                for referenced in self._referenced_objects(expression)
                if referenced not in cte_names and not self._is_allowed(referenced)
            }
        )
        if not offenders:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    f"object(s) not in the semantic store for this datasource: "
                    f"{', '.join(offenders)}"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))

    @staticmethod
    def _referenced_objects(expression: exp.Expression) -> set[str]:
        names: set[str] = set()
        for table in expression.find_all(exp.Table):
            schema_name = str(table.db).lower()
            object_name = str(table.name).lower()
            names.add(f"{schema_name}.{object_name}" if schema_name else object_name)
        return names

    def _is_allowed(self, referenced: str) -> bool:
        if "." in referenced:
            return referenced in self._allowed
        return referenced in self._bare
```

- [ ] **Step 4: Run to verify the `object_allowlist` tests pass**

Run: `uv run pytest tests/unit/test_object_allowlist_guardrail.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing `limit_injection` tests**

Create `tests/unit/test_limit_injection_guardrail.py`:

```python
"""Parent spec §12: mandatory LIMIT injection. The only repairable rule in the
registry — a missing LIMIT is a defect with exactly one correct fix, unlike
every other violation, which needs different SQL rather than more SQL."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.limit_injection_guardrail import LimitInjectionGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> LimitInjectionGuardrail:
    return LimitInjectionGuardrail(CONFIG)


def test_a_statement_with_a_limit_passes() -> None:
    assert _rule().check("SELECT id FROM shop.orders LIMIT 10") == ()


def test_a_missing_limit_is_a_repairable_violation() -> None:
    violations = _rule().check("SELECT id FROM shop.orders")

    assert len(violations) == 1
    assert violations[0].rule_name == "limit_injection"
    assert violations[0].repairable is True


def test_repair_injects_the_configured_row_cap_and_the_result_re_passes() -> None:
    rule = _rule()
    violation = rule.check("SELECT id FROM shop.orders")[0]

    repaired = rule.repair("SELECT id FROM shop.orders", violation)

    assert "LIMIT 1000" in repaired.upper()
    assert rule.check(repaired) == ()


def test_repair_leaves_the_projection_and_predicate_intact() -> None:
    rule = _rule()
    sql = "SELECT o.id FROM shop.orders AS o WHERE o.total > 5"
    violation = rule.check(sql)[0]

    repaired = rule.repair(sql, violation)

    assert "o.total > 5" in repaired
    assert "o.id" in repaired


def test_a_union_without_a_limit_is_repaired_too() -> None:
    rule = _rule()
    sql = "SELECT 1 UNION ALL SELECT 2"
    violation = rule.check(sql)[0]

    assert rule.check(rule.repair(sql, violation)) == ()


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "limit_injection"
    assert _rule().priority == 40
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_limit_injection_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement `limit_injection`**

Create `genql/repositories/guardrails/limit_injection_guardrail.py`:

```python
"""Injects the configured row cap when the statement has no LIMIT of its own.

Only the outermost statement is checked. A LIMIT inside a subquery bounds that
subquery, not the result set the caller receives, so treating it as sufficient
would defeat the cap. An existing outer LIMIT is left alone even when it is
larger than the cap: the executor's own row cap is the floor underneath it, so
the statement never returns more than the cap regardless.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("limit_injection")
class LimitInjectionGuardrail:
    name = "limit_injection"
    priority = 40

    def __init__(self, config: GuardrailConfig) -> None:
        self._row_cap = config.row_cap

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        expression = self._parse(sql)
        if expression is None or expression.args.get("limit") is not None:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=f"no LIMIT on the outermost statement; {self._row_cap} will be injected",
                repairable=True,
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        expression = self._parse(sql)
        if expression is None:
            return sql
        return expression.limit(self._row_cap).sql(dialect="postgres")

    @staticmethod
    def _parse(sql: str) -> exp.Expression | None:
        try:
            return sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures.
            return None
```

- [ ] **Step 8: Run to verify the `limit_injection` tests pass**

Run: `uv run pytest tests/unit/test_limit_injection_guardrail.py -q`
Expected: PASS

- [ ] **Step 9: Write the failing `statement_timeout` tests**

Create `tests/unit/test_statement_timeout_guardrail.py`:

```python
"""Not a SQL-text check. It exists so "did every guardrail pass" is one
uniform report over one registry rather than four registered rules plus a
special case, and so a timeout misconfigured to zero fails loudly at
validation instead of silently letting a runaway query through."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.statement_timeout_guardrail import StatementTimeoutGuardrail


def _rule(statement_timeout_ms: int) -> StatementTimeoutGuardrail:
    return StatementTimeoutGuardrail(
        GuardrailConfig(
            row_cap=1000,
            statement_timeout_ms=statement_timeout_ms,
            allowed_objects=frozenset(),
        )
    )


def test_a_configured_timeout_passes_any_statement() -> None:
    assert _rule(30_000).check("SELECT id FROM shop.orders") == ()
    assert _rule(30_000).check("this is not sql at all") == ()


def test_a_zero_timeout_is_an_unrepairable_violation() -> None:
    violations = _rule(0).check("SELECT 1")

    assert len(violations) == 1
    assert violations[0].rule_name == "statement_timeout"
    assert violations[0].repairable is False


def test_a_negative_timeout_is_an_unrepairable_violation() -> None:
    assert _rule(-1).check("SELECT 1")[0].repairable is False


def test_repair_returns_the_statement_unchanged_because_sql_is_not_the_problem() -> None:
    rule = _rule(0)
    violation = rule.check("SELECT 1")[0]

    assert rule.repair("SELECT 1", violation) == "SELECT 1"


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule(30_000).name == "statement_timeout"
    assert _rule(30_000).priority == 50
```

- [ ] **Step 10: Run to verify it fails**

Run: `uv run pytest tests/unit/test_statement_timeout_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 11: Implement `statement_timeout` and register all three**

Create `genql/repositories/guardrails/statement_timeout_guardrail.py`:

```python
"""Asserts the executor will actually apply a statement timeout.

The timeout itself is applied by ReadOnlyQueryExecutorRepository via
SET LOCAL, not here — a SQL-text rule cannot enforce a runtime setting. What
this rule contributes is that the setting is present and positive before
anything executes, reported through the same registry and the same
GuardrailViolation type as every other rule.
"""

from __future__ import annotations

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("statement_timeout")
class StatementTimeoutGuardrail:
    name = "statement_timeout"
    priority = 50

    def __init__(self, config: GuardrailConfig) -> None:
        self._statement_timeout_ms = config.statement_timeout_ms

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        if self._statement_timeout_ms > 0:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    "query_statement_timeout_ms must be greater than zero; "
                    f"it is {self._statement_timeout_ms}"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        # Nothing about the SQL is wrong; the configuration is. Returning it
        # unchanged keeps the Guardrail contract total without pretending.
        return sql
```

Replace `genql/repositories/guardrails/__init__.py` with all five imports:

```python
"""The registered guardrail rules.

Importing this package is what populates GUARDRAILS: each module below
decorates its class into the registry. Adding a rule is one new file plus one
import line here — no factory, service, or call site changes.
"""

from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail
from genql.repositories.guardrails.limit_injection_guardrail import LimitInjectionGuardrail
from genql.repositories.guardrails.object_allowlist_guardrail import ObjectAllowlistGuardrail
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail
from genql.repositories.guardrails.statement_timeout_guardrail import StatementTimeoutGuardrail

__all__ = [
    "ForbiddenFunctionGuardrail",
    "LimitInjectionGuardrail",
    "ObjectAllowlistGuardrail",
    "StatementKindGuardrail",
    "StatementTimeoutGuardrail",
]
```

- [ ] **Step 12: Run to verify all five rules register and pass**

Run: `uv run pytest tests/unit/test_statement_timeout_guardrail.py tests/unit/test_object_allowlist_guardrail.py tests/unit/test_limit_injection_guardrail.py -q && uv run python -c "import genql.repositories.guardrails; from genql.repositories.guardrails.registry import GUARDRAILS; print(GUARDRAILS.keys())"`
Expected: PASS, then `['forbidden_function', 'limit_injection', 'object_allowlist', 'statement_kind', 'statement_timeout']`

- [ ] **Step 13: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 14: Commit**

```bash
git add genql/repositories/guardrails tests/unit/test_object_allowlist_guardrail.py \
  tests/unit/test_limit_injection_guardrail.py tests/unit/test_statement_timeout_guardrail.py
git commit -m "feat(guardrails): add object_allowlist, limit_injection, and statement_timeout"
```

---

### Task 6: `GuardrailFactory` and `StaticValidationService`

**Files:**
- Create: `genql/infrastructure/query/__init__.py`, `genql/infrastructure/query/guardrail_factory.py`, `genql/services/query/__init__.py`, `genql/services/query/static_validation_service.py`
- Test: `tests/unit/test_guardrail_factory.py`, `tests/unit/test_static_validation_service.py`

**Interfaces:**
- Consumes: `GUARDRAILS` (Task 4), all five rules (Tasks 4–5), `GuardrailFactory`/`Guardrail`/`ObjectNameReader` ports, `GuardrailConfig`, `SqlCandidate`, `StaticValidationError` (Task 1)
- Produces: `GuardrailFactoryImpl(objects: ObjectNameReader, row_cap: int, statement_timeout_ms: int).for_datasource(datasource_name) -> Sequence[Guardrail]`, priority-ordered; `StaticValidationService(guardrails: GuardrailFactory).validate(candidate: SqlCandidate, datasource_name: str) -> str` returning the qualified, repaired SQL

- [ ] **Step 1: Write the failing factory test**

Create `tests/unit/test_guardrail_factory.py`:

```python
"""The factory is what makes "one file plus one decorator" true: it never
names a rule class, and it orders by the rule's own declared priority rather
than by registry key, so the ordering survives a rule being renamed."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl


class FakeObjectNameReader:
    def __init__(self, names: frozenset[str]) -> None:
        self.calls: list[str] = []
        self._names = names

    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        self.calls.append(datasource_name)
        return self._names


def _factory(names: frozenset[str] = frozenset({"shop.orders"})) -> GuardrailFactoryImpl:
    return GuardrailFactoryImpl(
        objects=FakeObjectNameReader(names), row_cap=1000, statement_timeout_ms=30_000
    )


def test_every_registered_rule_is_built() -> None:
    rules = _factory().for_datasource("local")

    assert len(rules) == 5


def test_rules_come_back_in_priority_order_not_alphabetical_order() -> None:
    rules = _factory().for_datasource("local")

    assert [rule.name for rule in rules] == [
        "statement_kind",
        "forbidden_function",
        "object_allowlist",
        "limit_injection",
        "statement_timeout",
    ]


def test_the_allowlist_is_read_for_the_datasource_asked_for() -> None:
    reader = FakeObjectNameReader(frozenset({"shop.orders"}))
    factory = GuardrailFactoryImpl(objects=reader, row_cap=1000, statement_timeout_ms=30_000)

    factory.for_datasource("warehouse_two")

    assert reader.calls == ["warehouse_two"]


def test_the_allowlist_actually_reaches_the_object_allowlist_rule() -> None:
    rules = {rule.name: rule for rule in _factory(frozenset({"shop.orders"})).for_datasource("local")}

    assert rules["object_allowlist"].check("SELECT * FROM shop.orders") == ()
    assert rules["object_allowlist"].check("SELECT * FROM shop.secrets") != ()


def test_the_row_cap_reaches_the_limit_injection_rule() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(frozenset()), row_cap=7, statement_timeout_ms=30_000
    )
    rules = {rule.name: rule for rule in factory.for_datasource("local")}
    violation = rules["limit_injection"].check("SELECT 1")[0]

    assert "LIMIT 7" in rules["limit_injection"].repair("SELECT 1", violation).upper()


def test_a_config_built_by_the_factory_carries_all_three_inputs() -> None:
    config = GuardrailConfig(
        row_cap=7, statement_timeout_ms=1, allowed_objects=frozenset({"shop.orders"})
    )

    assert config.row_cap == 7
    assert config.statement_timeout_ms == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_guardrail_factory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.query'`

- [ ] **Step 3: Implement the factory**

Create `genql/infrastructure/query/__init__.py`:

```python
"""Per-datasource assembly for the online query path.

Same role as `infrastructure/catalog/`: it knows which registry key to
resolve for a given datasource and hands the service a ready object, so no
service ever imports a registry.
"""
```

Create `genql/infrastructure/query/guardrail_factory.py`:

```python
"""Builds the priority-ordered rule set for one datasource.

Importing `genql.repositories.guardrails` is what populates GUARDRAILS: the
package imports each rule module for its registration decorator. Nothing here
names a rule class, so adding a rule is one file plus one decorator plus one
import line in that package — never an edit here.

The object allowlist is read once per call rather than cached: `genql discover`
adds objects between invocations, and a validation that trusts a stale
allowlist would reject freshly-catalogued tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import genql.repositories.guardrails  # noqa: F401 - registration side effect
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.object_name_reader import ObjectNameReader
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


class GuardrailFactoryImpl:
    def __init__(
        self, objects: ObjectNameReader, row_cap: int, statement_timeout_ms: int
    ) -> None:
        self._objects = objects
        self._row_cap = row_cap
        self._statement_timeout_ms = statement_timeout_ms

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        config = GuardrailConfig(
            row_cap=self._row_cap,
            statement_timeout_ms=self._statement_timeout_ms,
            allowed_objects=self._objects.read_object_names(datasource_name),
        )
        rules = [
            GUARDRAILS.create(key, config=config)
            for key in GUARDRAILS.keys()  # noqa: SIM118 - Registry, not a dict
        ]
        return sorted(rules, key=lambda rule: (rule.priority, rule.name))
```

- [ ] **Step 4: Run to verify the factory tests pass**

Run: `uv run pytest tests/unit/test_guardrail_factory.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Write the failing service test**

Create `tests/unit/test_static_validation_service.py`:

```python
"""The service knows nothing about any individual rule: it asks the factory
for them, runs them in the order given, and gives each repairable violation
exactly one chance. The termination test is the important one — a rule whose
repair does not actually fix anything must not loop."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl
from genql.services.query.static_validation_service import StaticValidationService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))


def _candidate(sql: str) -> SqlCandidate:
    return SqlCandidate(sql=sql, plan=PLAN)


class RecordingRule:
    name = "recording"
    priority = 10

    def __init__(self) -> None:
        self.checked: list[str] = []

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        self.checked.append(sql)
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise AssertionError("repair must not be called for a clean statement")


class UnrepairableRule:
    name = "unrepairable"
    priority = 20

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name=self.name, message="nope", repairable=False),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise AssertionError("repair must not be called for an unrepairable violation")


class UselessRepairRule:
    """Reports a repairable violation whose repair changes nothing."""

    name = "useless_repair"
    priority = 30

    def __init__(self) -> None:
        self.repairs = 0

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name=self.name, message="still bad", repairable=True),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        self.repairs += 1
        return sql


class SuffixRepairRule:
    name = "suffix_repair"
    priority = 40

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        if sql.endswith("LIMIT 5"):
            return ()
        return (GuardrailViolation(rule_name=self.name, message="needs a cap", repairable=True),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return f"{sql} LIMIT 5"


class FixedFactory:
    def __init__(self, rules: Sequence[Guardrail]) -> None:
        self._rules = rules

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return self._rules


class FakeObjectNameReader:
    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        return frozenset({"shop.orders"})


def test_a_clean_candidate_comes_back_qualified() -> None:
    rule = RecordingRule()
    service = StaticValidationService(FixedFactory([rule]))

    validated = service.validate(_candidate("SELECT o.id FROM shop.orders AS o LIMIT 5"), "local")

    assert "shop.orders" in validated
    assert rule.checked == ["SELECT o.id FROM shop.orders AS o LIMIT 5"]


def test_an_unrepairable_violation_raises_and_carries_the_violation() -> None:
    service = StaticValidationService(FixedFactory([UnrepairableRule()]))

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("SELECT 1 LIMIT 1"), "local")

    assert caught.value.violations[0].rule_name == "unrepairable"


def test_a_repair_is_attempted_exactly_once_and_then_the_loop_stops() -> None:
    rule = UselessRepairRule()
    service = StaticValidationService(FixedFactory([rule]))

    with pytest.raises(StaticValidationError):
        service.validate(_candidate("SELECT 1 LIMIT 1"), "local")

    assert rule.repairs == 1


def test_a_successful_repair_is_carried_into_the_returned_sql() -> None:
    service = StaticValidationService(FixedFactory([SuffixRepairRule()]))

    validated = service.validate(_candidate("SELECT 1"), "local")

    assert "LIMIT 5" in validated.upper()


def test_unparseable_sql_raises_rather_than_reaching_qualify() -> None:
    service = StaticValidationService(FixedFactory([]))

    with pytest.raises(StaticValidationError):
        service.validate(_candidate("SELECT FROM WHERE (("), "local")


def test_the_real_registry_rejects_a_delete_via_statement_kind() -> None:
    """§9's stated case: the rule that reports a DELETE must be statement_kind,
    which is only true because the factory orders by priority."""
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("DELETE FROM shop.orders"), "local")

    assert caught.value.violations[0].rule_name == "statement_kind"


def test_the_real_registry_rejects_pg_sleep_unrepairably() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("SELECT pg_sleep(5) LIMIT 1"), "local")

    assert caught.value.violations[0].rule_name == "forbidden_function"
    assert caught.value.violations[0].repairable is False


def test_the_real_registry_repairs_a_missing_limit_and_the_candidate_passes() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    validated = service.validate(_candidate("SELECT o.id FROM shop.orders AS o"), "local")

    assert "LIMIT 1000" in validated.upper()
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_static_validation_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query'`

- [ ] **Step 7: Implement the service**

Create `genql/services/query/__init__.py`:

```python
"""The five online-pipeline stages, one service per file.

Every service here is constructor-injected with ports only. None of them
imports a repository, a driver, or LangGraph — which is what lets the whole
pipeline be exercised in unit tests with fakes and no infrastructure at all.
"""
```

Create `genql/services/query/static_validation_service.py`:

```python
"""Runs every registered guardrail, repairs what is repairable, qualifies last.

Order matters and is not the spec's literal order. `qualify` raises on a
non-SELECT, so qualifying first would turn a clean `statement_kind` violation
("DELETE is not permitted") into an opaque optimizer error from the one rule
whose entire purpose is to report exactly that. The statement is therefore
parsed, run past every rule in priority order, and only then qualified.

Each repairable violation gets exactly one repair attempt, after which the
rule re-checks its own work. A rule whose repair does not actually fix
anything fails on the re-check instead of looping — which is the property the
graph's single-retry edge depends on to terminate.

`sqlglot` is a pure parser: no I/O, no driver, no network. Importing it here
does not breach the no-database-in-services rule, and it is deliberately not
added to either import-linter forbidden list.
"""

from __future__ import annotations

import sqlglot
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.guardrail_factory import GuardrailFactory


class StaticValidationService:
    def __init__(self, guardrails: GuardrailFactory) -> None:
        self._guardrails = guardrails

    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        sql = candidate.sql
        for rule in self._guardrails.for_datasource(datasource_name):
            sql = self._apply(rule, sql)
        return self._qualify(sql)

    @staticmethod
    def _apply(rule: Guardrail, sql: str) -> str:
        violations = rule.check(sql)
        if not violations:
            return sql

        unrepairable = tuple(v for v in violations if not v.repairable)
        if unrepairable:
            raise StaticValidationError(unrepairable)

        for violation in violations:
            sql = rule.repair(sql, violation)

        remaining = rule.check(sql)
        if remaining:
            raise StaticValidationError(remaining)
        return sql

    @staticmethod
    def _qualify(sql: str) -> str:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
            # qualify_columns needs a real column schema to be meaningful and
            # would reject valid SQL without one; qualifying tables is the part
            # that matters here. identify=False keeps the output readable
            # instead of quoting every identifier.
            qualified = qualify(
                expression,
                dialect="postgres",
                qualify_columns=False,
                validate_qualify_columns=False,
                identify=False,
            )
        except (ParseError, OptimizeError) as exc:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="qualify",
                        message=f"the statement could not be parsed or qualified: {exc}",
                    ),
                )
            ) from exc
        return str(qualified.sql(dialect="postgres"))
```

- [ ] **Step 8: Run to verify the service tests pass**

Run: `uv run pytest tests/unit/test_static_validation_service.py -q`
Expected: PASS (8 tests)

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — `lint-imports` in particular confirms `genql.services.query` importing `sqlglot` breaches no contract

- [ ] **Step 10: Commit**

```bash
git add genql/infrastructure/query genql/services/query/__init__.py \
  genql/services/query/static_validation_service.py tests/unit/test_guardrail_factory.py \
  tests/unit/test_static_validation_service.py
git commit -m "feat(query): resolve guardrails per datasource and validate statically"
```

---

### Task 7: `SchemaLinkingService`

**Files:**
- Create: `genql/services/query/schema_linking_service.py`
- Test: `tests/unit/test_schema_linking_service.py`

**Interfaces:**
- Consumes: `SchemaLink`, `SchemaLinkingError`, `JoinPathReader`, `MetricReader` (Task 1); Phase 4's `RetrievalService(embedder, retriever, rerank).search(datasource_name, query, top_k, domain_id)`; Phase 2.5's `SemanticCatalogReader.read_columns(ref)` and `SchemaRef(datasource_name, schema_name)`
- Produces: `SchemaLinkingService(retrieval, reader, join_paths, metrics, top_k).link(question, datasource_name, domain_id=None) -> tuple[SchemaLink, ...]` — satisfies the `SchemaLinker` port

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_schema_linking_service.py`:

```python
"""Schema linking is deterministic composition, not generation: retrieval says
which objects, the semantic store says which columns, which mined join paths,
and which metrics. No ChatProvider appears anywhere in this test, which is the
parent spec's stated correctness test for the offline/online split."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.column import Column
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.errors import SchemaLinkingError
from genql.domain.ports.retriever import SearchResult
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.query.schema_linking_service import SchemaLinkingService
from genql.services.semantic.retrieval_service import RetrievalService

RESULTS = [
    SearchResult(
        datasource_name="local",
        schema_name="shop",
        object_name="orders",
        domain_name="sales",
        score=1.0,
    ),
    SearchResult(
        datasource_name="local",
        schema_name="shop",
        object_name="customers",
        domain_name="sales",
        score=0.5,
    ),
]


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeRetriever:
    def __init__(self, results: Sequence[SearchResult]) -> None:
        self._results = results

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return self._results


class FakeSemanticCatalogReader:
    def __init__(self) -> None:
        self.refs: list[SchemaRef] = []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        self.refs.append(ref)
        return [
            Column(
                datasource_name="local",
                schema_name="shop",
                object_name="orders",
                column_name="total",
                ordinal=1,
                data_type="numeric",
                is_nullable=False,
            ),
            Column(
                datasource_name="local",
                schema_name="shop",
                object_name="customers",
                column_name="email",
                ordinal=1,
                data_type="text",
                is_nullable=True,
            ),
        ]


class FakeJoinPathReader:
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return [
            JoinPath(
                datasource_name="local",
                schema_name="shop",
                source_object="orders",
                target_object="customers",
                path=("orders", "customers"),
                weight=1.0,
            )
        ]


class FakeMetricReader:
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        return [
            Metric(
                datasource_name="local",
                name="net_revenue",
                sql_expression="sum(orders.total)",
                grain="day",
            ),
            Metric(
                datasource_name="local",
                name="stock_on_hand",
                sql_expression="sum(inventory.qty)",
                grain="day",
            ),
        ]


def _service(
    results: Sequence[SearchResult] = RESULTS,
    reader: FakeSemanticCatalogReader | None = None,
) -> SchemaLinkingService:
    return SchemaLinkingService(
        retrieval=RetrievalService(FakeEmbeddingProvider(), FakeRetriever(results), rerank=None),
        reader=reader or FakeSemanticCatalogReader(),
        join_paths=FakeJoinPathReader(),
        metrics=FakeMetricReader(),
        top_k=10,
    )


def test_one_link_is_produced_per_retrieved_object() -> None:
    links = _service().link("revenue by customer", "local")

    assert [link.object_qualified_name for link in links] == [
        "local.shop.orders",
        "local.shop.customers",
    ]


def test_columns_are_bound_to_the_object_they_belong_to() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].column_names == ("total",)
    assert links[1].column_names == ("email",)


def test_join_paths_are_bound_to_both_ends() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].join_paths == ("orders->customers",)
    assert links[1].join_paths == ("orders->customers",)


def test_a_metric_is_bound_to_the_object_its_expression_names() -> None:
    links = _service().link("revenue by customer", "local")

    assert links[0].metric_names == ("net_revenue",)
    assert links[1].metric_names == ()


def test_each_schema_is_read_once_however_many_objects_it_contributed() -> None:
    reader = FakeSemanticCatalogReader()

    _service(reader=reader).link("revenue by customer", "local")

    assert reader.refs == [SchemaRef(datasource_name="local", schema_name="shop")]


def test_zero_retrieval_results_is_a_typed_failure() -> None:
    with pytest.raises(SchemaLinkingError, match="revenue by customer"):
        _service(results=[]).link("revenue by customer", "local")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_schema_linking_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.schema_linking_service'`

- [ ] **Step 3: Implement the service**

Create `genql/services/query/schema_linking_service.py`:

```python
"""Binds retrieval hits to concrete SQL identifiers.

The parent spec's §9 stage 5. Deliberately free of any LLM call: retrieval
decides which objects, and the semantic store supplies everything else, so
this stage keeps working with every model provider unreachable.

A metric is bound to an object when the metric's SQL expression names that
object. It is a substring match on a normalized name rather than a parse:
`Metric.sql_expression` is a fragment authored in YAML (`sum(orders.total)`),
not a whole statement, so there is nothing for sqlglot to parse reliably.

Columns are read once per distinct schema rather than once per object: a
question that retrieves eight objects from one schema is one read, not eight.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import RetrievalError, SchemaLinkingError
from genql.domain.ports.join_path_reader import JoinPathReader
from genql.domain.ports.metric_reader import MetricReader
from genql.domain.ports.retriever import SearchResult
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.retrieval_service import RetrievalService


class SchemaLinkingService:
    def __init__(
        self,
        retrieval: RetrievalService,
        reader: SemanticCatalogReader,
        join_paths: JoinPathReader,
        metrics: MetricReader,
        top_k: int,
    ) -> None:
        self._retrieval = retrieval
        self._reader = reader
        self._join_paths = join_paths
        self._metrics = metrics
        self._top_k = top_k

    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        try:
            results = self._retrieval.search(datasource_name, question, self._top_k, domain_id)
        except RetrievalError as exc:
            raise SchemaLinkingError(f"retrieval failed for {question!r}: {exc}") from exc
        if not results:
            raise SchemaLinkingError(
                f"no catalogued object matched {question!r} in datasource {datasource_name!r}"
            )

        object_names = [r.object_name for r in results]
        paths = self._join_paths.read_join_paths(datasource_name, object_names)
        metrics = self._metrics.read_metrics(datasource_name)
        columns_by_object = self._columns_by_object(datasource_name, results)

        return tuple(
            SchemaLink(
                object_qualified_name=f"{datasource_name}.{r.schema_name}.{r.object_name}",
                column_names=tuple(columns_by_object.get(r.object_name, ())),
                join_paths=tuple(
                    f"{p.source_object}->{p.target_object}"
                    for p in paths
                    if r.object_name in (p.source_object, p.target_object)
                ),
                metric_names=tuple(
                    m.name
                    for m in metrics
                    if r.object_name.lower() in m.sql_expression.lower()
                ),
                domain_id=None,
            )
            for r in results
        )

    def _columns_by_object(
        self, datasource_name: str, results: Sequence[SearchResult]
    ) -> dict[str, list[str]]:
        schema_names = sorted({r.schema_name for r in results})
        columns_by_object: dict[str, list[str]] = {}
        for schema_name in schema_names:
            ref = SchemaRef(datasource_name=datasource_name, schema_name=schema_name)
            for column in self._reader.read_columns(ref):
                columns_by_object.setdefault(column.object_name, []).append(column.column_name)
        return columns_by_object
```

Note on `domain_id=None`: `SearchResult` carries `domain_name`, not `domain_id`, so the link cannot report an id it was never given. The field stays on the entity for Phase 6's domain-scoping stage, which resolves the id before retrieval runs and can populate it then.

- [ ] **Step 4: Run to verify the tests pass**

Run: `uv run pytest tests/unit/test_schema_linking_service.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add genql/services/query/schema_linking_service.py tests/unit/test_schema_linking_service.py
git commit -m "feat(query): bind retrieval hits to concrete identifiers"
```

---

### Task 8: `PlanningService`

**Files:**
- Create: `genql/services/query/planning_service.py`, `tests/integration/test_planning_service_real_provider.py`
- Test: `tests/unit/test_planning_service.py`, `tests/integration/test_planning_service_real_provider.py`

**Interfaces:**
- Consumes: `QueryPlan`, `SchemaLink`, `PlanningError` (Task 1); Phase 4's `ChatProvider.complete(prompt: str, response_schema: type[T]) -> T` and `ChatProviderError`
- Produces: `PlanResponse(BaseModel)` with `plan_text: str` and `referenced_objects: list[str]`; `PlanningService(chat: ChatProvider).plan(question, links) -> QueryPlan` — satisfies the `Planner` port; module function `build_planning_prompt(question, links) -> str`

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_planning_service.py`:

```python
"""One ChatProvider call, one QueryPlan. The prompt assertions matter as much
as the happy path: a plan that is not grounded on the links it was given is
the exact failure mode the NL-planning stage exists to prevent."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, PlanningError
from genql.services.query.planning_service import PlanningService, build_planning_prompt

LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "total"),
        join_paths=("orders->customers",),
        metric_names=("net_revenue",),
    ),
    SchemaLink(object_qualified_name="local.shop.customers", column_names=("id", "email")),
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class RaisingChatProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        raise self._error


def test_the_plan_carries_the_question_the_caller_asked() -> None:
    chat = FakeChatProvider(
        {"plan_text": "join orders to customers", "referenced_objects": ["local.shop.orders"]}
    )

    plan = PlanningService(chat).plan("revenue by customer", LINKS)

    assert plan.question == "revenue by customer"
    assert plan.plan_text == "join orders to customers"
    assert plan.referenced_objects == ("local.shop.orders",)


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"plan_text": "p", "referenced_objects": []})

    PlanningService(chat).plan("q", LINKS)

    assert len(chat.prompts) == 1


def test_a_provider_failure_becomes_a_planning_error() -> None:
    service = PlanningService(RaisingChatProvider(ChatProviderError("502 from upstream")))

    with pytest.raises(PlanningError, match="502 from upstream"):
        service.plan("q", LINKS)


def test_an_unparseable_response_becomes_a_planning_error() -> None:
    chat = FakeChatProvider({"referenced_objects": []})  # plan_text missing

    with pytest.raises(PlanningError):
        PlanningService(chat).plan("q", LINKS)


def test_planning_without_links_is_refused_before_any_provider_call() -> None:
    chat = FakeChatProvider({"plan_text": "p", "referenced_objects": []})

    with pytest.raises(PlanningError, match="no schema links"):
        PlanningService(chat).plan("q", ())

    assert chat.prompts == []


def test_the_prompt_names_every_object_column_join_path_and_metric() -> None:
    prompt = build_planning_prompt("revenue by customer", LINKS)

    assert "local.shop.orders" in prompt
    assert "total" in prompt
    assert "orders->customers" in prompt
    assert "net_revenue" in prompt
    assert "revenue by customer" in prompt


def test_the_prompt_forbids_objects_outside_the_links() -> None:
    prompt = build_planning_prompt("revenue by customer", LINKS)

    assert "only the objects listed" in prompt.lower()


def test_a_validation_error_raised_by_the_provider_is_also_translated() -> None:
    class _Tiny(BaseModel):
        n: int

    try:
        _Tiny.model_validate({"n": "not a number"})
    except ValidationError as exc:
        service = PlanningService(RaisingChatProvider(exc))
        with pytest.raises(PlanningError):
            service.plan("q", LINKS)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_planning_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.planning_service'`

- [ ] **Step 3: Implement the service**

Create `genql/services/query/planning_service.py`:

```python
"""Produces the natural-language plan before any SQL exists.

The parent spec's §9 stage 6, and the technique behind Oracle's Archer
result: an explicit, inspectable plan that later stages check the SQL
against. Phase 5 has no critique stage yet, so the plan's job here is
grounding — it fixes which objects the candidate is allowed to be about
before the generator has a chance to invent one.

Refusing to plan with zero links is deliberate: an ungrounded plan is exactly
the hallucination this stage exists to prevent, and calling the provider to
produce one would cost money to obtain a worse answer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, PlanningError
from genql.domain.ports.chat_provider import ChatProvider


class PlanResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_text: str
    referenced_objects: list[str]


def _render_link(link: SchemaLink) -> str:
    parts = [f"- {link.object_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    if link.metric_names:
        parts.append(f"    metrics: {', '.join(link.metric_names)}")
    return "\n".join(parts)


def build_planning_prompt(question: str, links: tuple[SchemaLink, ...]) -> str:
    catalog = "\n".join(_render_link(link) for link in links)
    return (
        "You are planning how to answer an analytical question against a data warehouse.\n"
        "Write the plan in prose. Do NOT write SQL.\n\n"
        f"Question:\n{question}\n\n"
        f"Available objects:\n{catalog}\n\n"
        "Rules:\n"
        "- Use only the objects listed above. Naming anything else is an error.\n"
        "- Join only along the join paths listed above.\n"
        "- State the grain of the answer, the filters, and the aggregation.\n"
        "- Return `plan_text` (the prose plan) and `referenced_objects` (the fully "
        "qualified names, exactly as listed above, that the plan actually uses)."
    )


class PlanningService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        if not links:
            raise PlanningError(f"cannot plan {question!r} with no schema links")
        try:
            response = self._chat.complete(build_planning_prompt(question, links), PlanResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise PlanningError(f"failed to plan {question!r}: {exc}") from exc
        return QueryPlan(
            question=question,
            plan_text=response.plan_text,
            referenced_objects=tuple(response.referenced_objects),
        )
```

- [ ] **Step 4: Run to verify the unit tests pass**

Run: `uv run pytest tests/unit/test_planning_service.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the gated real-provider test**

Create `tests/integration/test_planning_service_real_provider.py`:

```python
"""One real planning call against a real model. Costs money and needs network,
so it is gated on the key exactly as Phase 4's provider tests are — a clean
skip here is not a failure."""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.schema_link import SchemaLink
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.planning_service import PlanningService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

LINKS = (
    SchemaLink(
        object_qualified_name="local.tpcds.store_sales",
        column_names=("ss_store_sk", "ss_net_paid", "ss_sold_date_sk"),
        join_paths=("store_sales->store",),
    ),
    SchemaLink(
        object_qualified_name="local.tpcds.store",
        column_names=("s_store_sk", "s_store_name"),
    ),
)


def test_a_real_model_plans_against_the_links_it_was_given() -> None:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )

    plan = PlanningService(provider).plan("total net paid by store name", LINKS)

    assert plan.question == "total net paid by store name"
    assert plan.plan_text.strip()
    assert any("store_sales" in name for name in plan.referenced_objects)
```

- [ ] **Step 6: Run it**

Run: `uv run pytest tests/integration/test_planning_service_real_provider.py -v`
Expected: PASS with a non-empty plan naming `store_sales`, or a clean `SKIPPED [1] GENQL_OPENROUTER_API_KEY not set`. Report the skip as a skip, not a failure.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/services/query/planning_service.py tests/unit/test_planning_service.py \
  tests/integration/test_planning_service_real_provider.py
git commit -m "feat(query): produce a natural-language plan before any SQL"
```

---

### Task 9: `CandidateGenerationService`

**Files:**
- Create: `genql/services/query/candidate_generation_service.py`, `tests/integration/test_candidate_generation_service_real_provider.py`
- Test: `tests/unit/test_candidate_generation_service.py`, `tests/integration/test_candidate_generation_service_real_provider.py`

**Interfaces:**
- Consumes: `QueryPlan`, `SchemaLink`, `SqlCandidate`, `GuardrailViolation`, `GenerationError` (Task 1); `ChatProvider`, `ChatProviderError`
- Produces: `SqlResponse(BaseModel)` with `sql: str`; `CandidateGenerationService(chat: ChatProvider).generate(plan, links, violations=()) -> SqlCandidate` — satisfies the `CandidateGenerator` port; module function `build_generation_prompt(plan, links, violations) -> str`

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_candidate_generation_service.py`:

```python
"""One ChatProvider call, one SqlCandidate. The retry-feedback assertions are
the load-bearing ones: without the previous attempt's violations in the
prompt, the graph's retry edge would hand the generator identical inputs and
get identical SQL back."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, GenerationError
from genql.services.query.candidate_generation_service import (
    CandidateGenerationService,
    build_generation_prompt,
)

PLAN = QueryPlan(
    question="revenue by customer",
    plan_text="sum orders.total grouped by customers.email",
    referenced_objects=("local.shop.orders", "local.shop.customers"),
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "total", "customer_id"),
        join_paths=("orders->customers",),
        metric_names=("net_revenue",),
    ),
    SchemaLink(object_qualified_name="local.shop.customers", column_names=("id", "email")),
)
VIOLATIONS = (
    GuardrailViolation(
        rule_name="object_allowlist",
        message="object(s) not in the semantic store for this datasource: shop.invoices",
    ),
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class RaisingChatProvider:
    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        raise ChatProviderError("upstream refused")


def test_the_candidate_carries_the_plan_it_came_from() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    candidate = CandidateGenerationService(chat).generate(PLAN, LINKS)

    assert candidate.sql == "SELECT 1"
    assert candidate.plan is PLAN


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    CandidateGenerationService(chat).generate(PLAN, LINKS)

    assert len(chat.prompts) == 1


def test_a_provider_failure_becomes_a_generation_error() -> None:
    with pytest.raises(GenerationError, match="upstream refused"):
        CandidateGenerationService(RaisingChatProvider()).generate(PLAN, LINKS)


def test_an_unparseable_response_becomes_a_generation_error() -> None:
    chat = FakeChatProvider({})  # sql missing

    with pytest.raises(GenerationError):
        CandidateGenerationService(chat).generate(PLAN, LINKS)


def test_an_empty_sql_string_is_refused() -> None:
    chat = FakeChatProvider({"sql": "   "})

    with pytest.raises(GenerationError, match="empty"):
        CandidateGenerationService(chat).generate(PLAN, LINKS)


def test_generating_without_links_is_refused_before_any_provider_call() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    with pytest.raises(GenerationError, match="no schema links"):
        CandidateGenerationService(chat).generate(PLAN, ())

    assert chat.prompts == []


def test_the_first_attempt_prompt_carries_the_plan_and_the_links() -> None:
    prompt = build_generation_prompt(PLAN, LINKS, ())

    assert "sum orders.total grouped by customers.email" in prompt
    assert "local.shop.orders" in prompt
    assert "customer_id" in prompt
    assert "previous attempt" not in prompt.lower()


def test_the_retry_prompt_carries_the_previous_violations() -> None:
    prompt = build_generation_prompt(PLAN, LINKS, VIOLATIONS)

    assert "previous attempt" in prompt.lower()
    assert "object_allowlist" in prompt
    assert "shop.invoices" in prompt


def test_the_violations_reach_the_provider_prompt() -> None:
    chat = FakeChatProvider({"sql": "SELECT 1"})

    CandidateGenerationService(chat).generate(PLAN, LINKS, VIOLATIONS)

    assert "object_allowlist" in chat.prompts[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_candidate_generation_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `genql/services/query/candidate_generation_service.py`:

```python
"""Produces exactly one SQL candidate from a plan and its schema links.

Phase 5 generates one candidate, not N. The parent spec's §9 stage 7 asks for
N candidates representing genuinely different interpretations, but critique,
probing, and selection — the stages that consume the disagreement between
them — are Phase 6. Generating a second candidate with nothing to resolve it
against would be dead work.

`violations` is empty on the first attempt. On the graph's single retry it
carries the previous attempt's guardrail failures, which is the only thing
that makes the retry more than a re-roll of the same dice.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ChatProviderError, GenerationError
from genql.domain.ports.chat_provider import ChatProvider


class SqlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str


def _render_link(link: SchemaLink) -> str:
    parts = [f"- {link.schema_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    if link.metric_names:
        parts.append(f"    metrics: {', '.join(link.metric_names)}")
    return "\n".join(parts)


def build_generation_prompt(
    plan: QueryPlan, links: tuple[SchemaLink, ...], violations: tuple[GuardrailViolation, ...]
) -> str:
    catalog = "\n".join(_render_link(link) for link in links)
    sections = [
        "Write one PostgreSQL SELECT statement that carries out the plan below.",
        f"Question:\n{plan.question}",
        f"Plan:\n{plan.plan_text}",
        f"Available objects (reference them as schema.object):\n{catalog}",
        (
            "Rules:\n"
            "- A single SELECT (a leading WITH is fine). No DDL, DML, or DCL.\n"
            "- Reference only the objects listed above, schema-qualified.\n"
            "- Join only along the join paths listed above.\n"
            "- Include an explicit LIMIT.\n"
            "- Return the statement in `sql`, with no markdown fence and no commentary."
        ),
    ]
    if violations:
        rendered = "\n".join(f"- {v.rule_name}: {v.message}" for v in violations)
        sections.append(
            "The previous attempt was rejected by static validation. Fix these and "
            f"do not repeat them:\n{rendered}"
        )
    return "\n\n".join(sections)


class CandidateGenerationService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        if not links:
            raise GenerationError(f"cannot generate SQL for {plan.question!r} with no schema links")
        try:
            response = self._chat.complete(
                build_generation_prompt(plan, links, violations), SqlResponse
            )
        except (ChatProviderError, ValidationError) as exc:
            raise GenerationError(
                f"failed to generate SQL for {plan.question!r}: {exc}"
            ) from exc
        if not response.sql.strip():
            raise GenerationError(
                f"the generator returned an empty statement for {plan.question!r}"
            )
        return SqlCandidate(sql=response.sql.strip(), plan=plan)
```

- [ ] **Step 4: Run to verify the unit tests pass**

Run: `uv run pytest tests/unit/test_candidate_generation_service.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Write the gated real-provider test**

Create `tests/integration/test_candidate_generation_service_real_provider.py`:

```python
"""One real generation call. Asserts the statement parses as a SELECT rather
than asserting its exact text — the point is that a real model, given a real
plan and real links, produces something static validation can even look at."""

from __future__ import annotations

import os

import pytest
import sqlglot
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.candidate_generation_service import CandidateGenerationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

PLAN = QueryPlan(
    question="total net paid by store name",
    plan_text=(
        "Join store_sales to store on ss_store_sk = s_store_sk, sum ss_net_paid, "
        "group by s_store_name."
    ),
    referenced_objects=("local.tpcds.store_sales", "local.tpcds.store"),
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.tpcds.store_sales",
        column_names=("ss_store_sk", "ss_net_paid"),
        join_paths=("store_sales->store",),
    ),
    SchemaLink(
        object_qualified_name="local.tpcds.store",
        column_names=("s_store_sk", "s_store_name"),
    ),
)


def test_a_real_model_produces_a_parseable_select() -> None:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )

    candidate = CandidateGenerationService(provider).generate(PLAN, LINKS)

    expression = sqlglot.parse_one(candidate.sql, dialect="postgres")
    assert isinstance(expression, exp.Select | exp.Union)
    assert "store_sales" in candidate.sql.lower()
```

- [ ] **Step 6: Run it**

Run: `uv run pytest tests/integration/test_candidate_generation_service_real_provider.py -v`
Expected: PASS with a parseable SELECT naming `store_sales`, or a clean skip when the key is unset.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/services/query/candidate_generation_service.py \
  tests/unit/test_candidate_generation_service.py \
  tests/integration/test_candidate_generation_service_real_provider.py
git commit -m "feat(query): generate one SQL candidate from the plan and links"
```

---

### Task 10: `QueryExecutorFactory` and `GuardedExecutionService`

**Files:**
- Create: `genql/infrastructure/query/query_executor_factory.py`, `genql/services/query/guarded_execution_service.py`
- Test: `tests/unit/test_guarded_execution_service.py`

**Interfaces:**
- Consumes: `QueryExecutor`, `QueryExecutorFactory`, `ExecutionResult`, `ExecutionError` (Task 1); `ReadOnlyQueryExecutorRepository` (Task 3); `DatasourceEngineProvider.readonly_engine_for` (Task 2); existing `DatasourceRepository.get(name)`
- Produces: `QueryExecutorFactoryImpl(provider: DatasourceEngineProvider, statement_timeout_ms: int).for_datasource(datasource) -> QueryExecutor`; `GuardedExecutionService(datasources, executors, row_cap).execute(sql: str, datasource_name: str) -> ExecutionResult`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_guarded_execution_service.py`:

```python
"""The service resolves the datasource, hands the SQL to the executor bound to
it, and applies the configured row cap. The cap assertion is the important
one: a service that forgets to pass it would make the executor's truncation
logic unreachable."""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import ExecutionError, UnknownDatasourceError
from genql.domain.ports.query_executor import QueryExecutor
from genql.services.query.guarded_execution_service import GuardedExecutionService

DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
RESULT = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        self.calls.append((sql, row_cap))
        return RESULT


class RaisingExecutor:
    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        raise ExecutionError("canceling statement due to statement timeout")


class FixedExecutorFactory:
    def __init__(self, executor: QueryExecutor) -> None:
        self.executor = executor
        self.datasources: list[str] = []

    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        self.datasources.append(datasource.name)
        return self.executor


class FakeDatasourceRepository:
    def __init__(self, datasource: Datasource | None) -> None:
        self._datasource = datasource

    def add(self, datasource: Datasource) -> None:
        raise NotImplementedError

    def get(self, name: str) -> Datasource:
        if self._datasource is None:
            raise UnknownDatasourceError(name, [])
        return self._datasource

    def list_all(self, enabled_only: bool = False) -> list[Datasource]:
        return [self._datasource] if self._datasource else []

    def remove(self, name: str) -> None:
        raise NotImplementedError


def test_the_configured_row_cap_is_passed_to_the_executor() -> None:
    executor = RecordingExecutor()
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS),
        executors=FixedExecutorFactory(executor),
        row_cap=250,
    )

    result = service.execute("SELECT 1 LIMIT 1", "local")

    assert executor.calls == [("SELECT 1 LIMIT 1", 250)]
    assert result is RESULT


def test_the_executor_is_resolved_for_the_datasource_asked_for() -> None:
    factory = FixedExecutorFactory(RecordingExecutor())
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS), executors=factory, row_cap=10
    )

    service.execute("SELECT 1", "local")

    assert factory.datasources == ["local"]


def test_an_executor_failure_propagates_as_an_execution_error() -> None:
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(DS),
        executors=FixedExecutorFactory(RaisingExecutor()),
        row_cap=10,
    )

    with pytest.raises(ExecutionError, match="timeout"):
        service.execute("SELECT pg_sleep(5)", "local")


def test_an_unknown_datasource_stays_an_unknown_datasource_error() -> None:
    """Not translated: a misspelled --datasource is the caller's mistake, not a
    failure of execution, and the existing error already says which names exist."""
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(None),
        executors=FixedExecutorFactory(RecordingExecutor()),
        row_cap=10,
    )

    with pytest.raises(UnknownDatasourceError):
        service.execute("SELECT 1", "nope")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_guarded_execution_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.guarded_execution_service'`

- [ ] **Step 3: Implement the factory and the service**

Create `genql/infrastructure/query/query_executor_factory.py`:

```python
"""Binds a QueryExecutor to one datasource's READ-ONLY engine.

This file is the entire reason the admin engine is unreachable from the
execution path: it calls `readonly_engine_for` and nothing else, and it is the
only place a QueryExecutor is ever constructed. A future caller that wanted an
admin-privileged executor would have to add a second factory, which is a
reviewable change rather than a silent one.
"""

from __future__ import annotations

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.query_executor import QueryExecutor
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.query.query_executor_repository import ReadOnlyQueryExecutorRepository


class QueryExecutorFactoryImpl:
    def __init__(self, provider: DatasourceEngineProvider, statement_timeout_ms: int) -> None:
        self._provider = provider
        self._statement_timeout_ms = statement_timeout_ms

    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        return ReadOnlyQueryExecutorRepository(
            self._provider.readonly_engine_for(datasource),
            statement_timeout_ms=self._statement_timeout_ms,
        )
```

Create `genql/services/query/guarded_execution_service.py`:

```python
"""Runs the validated statement under the configured row cap.

The parent spec's §9 stage 12 and §12's execution rules. The three safety
properties are split by layer on purpose: the read-only role is the engine
binding's job (infrastructure), the statement timeout is the repository's
(it needs a transaction), the row cap is this service's (it is configuration),
and the injected LIMIT is a guardrail's. No single layer can quietly drop all
four.

An unknown datasource is not translated: UnknownDatasourceError already names
the registered alternatives, and re-wrapping it as an execution failure would
lose that.
"""

from __future__ import annotations

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.query_executor_factory import QueryExecutorFactory


class GuardedExecutionService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        executors: QueryExecutorFactory,
        row_cap: int,
    ) -> None:
        self._datasources = datasources
        self._executors = executors
        self._row_cap = row_cap

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        datasource = self._datasources.get(datasource_name)
        return self._executors.for_datasource(datasource).execute(sql, self._row_cap)
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `uv run pytest tests/unit/test_guarded_execution_service.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add genql/infrastructure/query/query_executor_factory.py \
  genql/services/query/guarded_execution_service.py \
  tests/unit/test_guarded_execution_service.py
git commit -m "feat(query): execute validated SQL through the read-only binding"
```

---

### Task 11: The LangGraph graph, its nodes, and `genql query`

**Files:**
- Create: `genql/api/query_state.py`, `genql/api/query_nodes.py`, `genql/api/query_graph.py`, `genql/cli/commands/query.py`
- Modify: `genql/cli/main.py`
- Test: `tests/unit/test_query_nodes.py`, `tests/unit/test_query_graph.py`

**Interfaces:**
- Consumes: `SchemaLinker`, `Planner`, `CandidateGenerator` ports (Task 1); `StaticValidationService` (Task 6); `GuardedExecutionService` (Task 10); `langgraph` (Task 2); `Container` from `genql/composition_root.py` (the `query_graph` provider lands in Task 12 — the CLI is written against it here and only becomes runnable once Task 12 wires it)
- Produces: `QueryState` TypedDict and `initial_state(question, datasource_name, domain_id=None) -> QueryState`; node classes `SchemaLinkingNode(linker)`, `PlanningNode(planner)`, `CandidateGenerationNode(generator)`, `StaticValidationNode(service)`, `GuardedExecutionNode(service)`, each callable as `(QueryState) -> dict[str, Any]`; `route_after_validation(state) -> str`; `build_query_graph(schema_linking, planning, candidate_generation, static_validation, guarded_execution)`; `run_query(graph, question, datasource_name, domain_id=None) -> QueryState`; CLI command `genql query "<question>" --datasource NAME [--domain-id N]`

- [ ] **Step 1: Write the failing node tests**

Create `tests/unit/test_query_nodes.py`:

```python
"""Each node is an adapter: read the fields it needs off the state, call its
service, write the result back. The two that carry logic are the ones tested
hardest — static validation turns its typed failure into state so the router
can decide, and candidate generation counts a retry only when it was given
something to fix."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.api.query_state import initial_state
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.query_executor import QueryExecutor
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService

LINK = SchemaLink(object_qualified_name="local.shop.orders", column_names=("id",))
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 1", plan=PLAN)
VIOLATION = GuardrailViolation(rule_name="fake", message="bad", repairable=False)
RESULT = ExecutionResult(columns=("id",), rows=((1,),), row_count=1, truncated=False)
DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")


class FakeLinker:
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        return (LINK,)


class FakePlanner:
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        return PLAN


class FakeGenerator:
    def __init__(self) -> None:
        self.seen: list[tuple[GuardrailViolation, ...]] = []

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        self.seen.append(violations)
        return CANDIDATE


class PassingRule:
    name = "passing"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return sql


class FailingRule:
    name = "failing"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (VIOLATION,)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))


class FixedFactory:
    def __init__(self, rules: Sequence[Guardrail]) -> None:
        self._rules = rules

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return self._rules


class FixedExecutorFactory:
    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        class _Executor:
            def execute(self, sql: str, row_cap: int) -> ExecutionResult:
                return RESULT

        return _Executor()


class FakeDatasourceRepository:
    def add(self, datasource: Datasource) -> None:
        raise NotImplementedError

    def get(self, name: str) -> Datasource:
        return DS

    def list_all(self, enabled_only: bool = False) -> list[Datasource]:
        return [DS]

    def remove(self, name: str) -> None:
        raise NotImplementedError


def test_schema_linking_writes_links_onto_the_state() -> None:
    state = initial_state("q", "local")

    assert SchemaLinkingNode(FakeLinker())(state) == {"links": (LINK,)}


def test_planning_writes_the_plan_onto_the_state() -> None:
    state = initial_state("q", "local")
    state["links"] = (LINK,)

    assert PlanningNode(FakePlanner())(state) == {"plan": PLAN}


def test_candidate_generation_does_not_count_a_retry_on_the_first_attempt() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 0
    assert generator.seen == [()]


def test_candidate_generation_counts_a_retry_and_forwards_the_violations() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local")
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["violations"] = (VIOLATION,)

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 1
    assert generator.seen == [(VIOLATION,)]


def test_static_validation_writes_the_validated_sql_and_clears_violations() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))
    state = initial_state("q", "local")
    state["candidate"] = CANDIDATE

    update = node(state)

    assert update["violations"] == ()
    assert "shop.orders" in str(update["validated_sql"])


def test_static_validation_turns_its_failure_into_state_rather_than_raising() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local")
    state["candidate"] = CANDIDATE

    update = node(state)

    assert update["validated_sql"] is None
    assert update["violations"] == (VIOLATION,)


def test_guarded_execution_writes_the_result_onto_the_state() -> None:
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(),
        executors=FixedExecutorFactory(),
        row_cap=100,
    )
    state = initial_state("q", "local")
    state["validated_sql"] = "SELECT id FROM shop.orders LIMIT 1"

    assert GuardedExecutionNode(service)(state) == {"result": RESULT}


def test_a_node_reached_without_its_input_fails_loudly() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))

    with pytest.raises(StaticValidationError, match="without a candidate"):
        node(initial_state("q", "local"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_nodes'`

- [ ] **Step 3: Implement the state and the nodes**

Create `genql/api/query_state.py`:

```python
"""The graph's shared state.

`violations` rather than a rendered message: the router needs the failure to
decide, the regeneration node needs it as feedback, and the CLI needs it in
the error it prints — a tuple of entities serves all three, a string serves
none of them well.

No checkpointer field and no thread id: Phase 5's graph is a single stateless
run from question to answer. Phase 6 adds PostgresSaver, per-thread advisory
locks, and interrupt() around this same state.
"""

from __future__ import annotations

from typing import TypedDict

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


class QueryState(TypedDict):
    question: str
    datasource_name: str
    domain_id: int | None
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    candidate: SqlCandidate | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]


def initial_state(
    question: str, datasource_name: str, domain_id: int | None = None
) -> QueryState:
    return QueryState(
        question=question,
        datasource_name=datasource_name,
        domain_id=domain_id,
        links=None,
        plan=None,
        candidate=None,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
```

Create `genql/api/query_nodes.py`:

```python
"""Five adapters between QueryState and the five services.

Each one reads the fields it needs, calls its service, and returns only the
fields it changed. Nothing here decides anything: routing lives in
query_graph.py, and business logic lives in the services. The one exception is
StaticValidationNode, which converts its typed failure into state so the
router has something to route on — the failure is re-raised there, not
swallowed.

A node reached without the input it needs raises rather than returning a
half-filled state: that can only happen if the graph's edges are wrong, and a
wrong edge should fail at the first node it reaches.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import QueryState
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import ExecutionError, GenerationError, StaticValidationError
from genql.domain.ports.candidate_generator import CandidateGenerator
from genql.domain.ports.planner import Planner
from genql.domain.ports.schema_linker import SchemaLinker
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService


class SchemaLinkingNode:
    def __init__(self, linker: SchemaLinker) -> None:
        self._linker = linker

    def __call__(self, state: QueryState) -> dict[str, Any]:
        links = self._linker.link(
            state["question"], state["datasource_name"], state["domain_id"]
        )
        return {"links": links}


class PlanningNode:
    def __init__(self, planner: Planner) -> None:
        self._planner = planner

    def __call__(self, state: QueryState) -> dict[str, Any]:
        return {"plan": self._planner.plan(state["question"], state["links"] or ())}


class CandidateGenerationNode:
    def __init__(self, generator: CandidateGenerator) -> None:
        self._generator = generator

    def __call__(self, state: QueryState) -> dict[str, Any]:
        plan = state["plan"]
        if plan is None:
            raise GenerationError("candidate generation was reached without a plan")
        violations = state["violations"]
        candidate = self._generator.generate(plan, state["links"] or (), violations)
        return {
            "candidate": candidate,
            # Counted here, not in the validation node: this is the attempt
            # being retried, so this is where "retry" becomes true.
            "retry_count": state["retry_count"] + (1 if violations else 0),
        }


class StaticValidationNode:
    def __init__(self, service: StaticValidationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidate = state["candidate"]
        if candidate is None:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="graph",
                        message="static validation was reached without a candidate",
                    ),
                )
            )
        try:
            validated = self._service.validate(candidate, state["datasource_name"])
        except StaticValidationError as exc:
            return {"validated_sql": None, "violations": exc.violations}
        return {"validated_sql": validated, "violations": ()}


class GuardedExecutionNode:
    def __init__(self, service: GuardedExecutionService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        sql = state["validated_sql"]
        if sql is None:
            raise ExecutionError("guarded execution was reached without validated SQL")
        return {"result": self._service.execute(sql, state["datasource_name"])}
```

- [ ] **Step 4: Run to verify the node tests pass**

Run: `uv run pytest tests/unit/test_query_nodes.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing graph test**

Create `tests/unit/test_query_graph.py`:

```python
"""The wiring, proven with fake nodes so no ChatProvider, database, or
retriever is involved. Three paths matter: clean, exactly one retry, and a
second failure that stops rather than looping."""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_graph import build_query_graph, route_after_validation, run_query
from genql.api.query_state import initial_state
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError

LINK = SchemaLink(object_qualified_name="local.shop.orders")
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)
VIOLATIONS = (GuardrailViolation(rule_name="fake", message="bad", repairable=True),)
RESULT = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False)


def link_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"links": (LINK,)}


def plan_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"plan": PLAN}


class GenerateNode:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {
            "candidate": CANDIDATE,
            "retry_count": state["retry_count"] + (1 if state["violations"] else 0),
        }


class ValidateNode:
    """Fails its first `failures` invocations, then succeeds."""

    def __init__(self, failures: int) -> None:
        self.remaining = failures

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.remaining > 0:
            self.remaining -= 1
            return {"validated_sql": None, "violations": VIOLATIONS}
        return {"validated_sql": "SELECT 1 LIMIT 1", "violations": ()}


def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"result": RESULT}


def _graph(failures: int) -> tuple[Any, GenerateNode]:
    generate = GenerateNode()
    graph = build_query_graph(
        schema_linking=link_node,
        planning=plan_node,
        candidate_generation=generate,
        static_validation=ValidateNode(failures),
        guarded_execution=execute_node,
    )
    return graph, generate


def test_the_clean_path_generates_once_and_returns_a_result() -> None:
    graph, generate = _graph(failures=0)

    final = run_query(graph, "q", "local")

    assert generate.calls == 1
    assert final["retry_count"] == 0
    assert final["result"] == RESULT
    assert final["validated_sql"] == "SELECT 1 LIMIT 1"


def test_one_failure_routes_back_to_generation_exactly_once() -> None:
    graph, generate = _graph(failures=1)

    final = run_query(graph, "q", "local")

    assert generate.calls == 2
    assert final["retry_count"] == 1
    assert final["result"] == RESULT


def test_a_second_failure_raises_instead_of_looping() -> None:
    graph, generate = _graph(failures=2)

    with pytest.raises(StaticValidationError, match="bad"):
        run_query(graph, "q", "local")

    assert generate.calls == 2


def test_the_router_sends_a_validated_statement_to_execution() -> None:
    state = initial_state("q", "local")
    state["validated_sql"] = "SELECT 1 LIMIT 1"

    assert route_after_validation(state) == "guarded_execution"


def test_the_router_sends_a_first_failure_back_to_generation() -> None:
    state = initial_state("q", "local")
    state["violations"] = VIOLATIONS

    assert route_after_validation(state) == "candidate_generation"


def test_the_router_raises_on_a_failure_after_the_retry_was_used() -> None:
    state = initial_state("q", "local")
    state["violations"] = VIOLATIONS
    state["retry_count"] = 1

    with pytest.raises(StaticValidationError):
        route_after_validation(state)


def test_the_initial_state_starts_empty_with_no_retries_used() -> None:
    state = initial_state("q", "local", domain_id=3)

    assert state["retry_count"] == 0
    assert state["violations"] == ()
    assert state["domain_id"] == 3
    assert state["result"] is None
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_graph.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_graph'`

- [ ] **Step 7: Implement the graph**

Create `genql/api/query_graph.py`:

```python
"""The online pipeline as a LangGraph StateGraph — the only file in Phase 5
that imports langgraph.

No checkpointer and no interrupt(). The parent spec's §13 ties both
specifically to multi-turn clarification, which does not exist yet, so each
invocation here is a single stateless run from question to answer. Building a
real graph now is a deliberate bet: Phase 6 extends this graph rather than
migrating a plain function pipeline into one under more time pressure.

One conditional edge, out of static_validation. Success goes to execution; a
first failure goes back to candidate_generation with the violations attached;
a second failure raises. The graph does not catch or re-wrap — the CLI does.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from genql.api.query_state import QueryState, initial_state
from genql.domain.errors import StaticValidationError

NodeFn = Callable[[QueryState], dict[str, Any]]

SCHEMA_LINKING = "schema_linking"
PLANNING = "planning"
CANDIDATE_GENERATION = "candidate_generation"
STATIC_VALIDATION = "static_validation"
GUARDED_EXECUTION = "guarded_execution"


def route_after_validation(state: QueryState) -> str:
    if state["validated_sql"] is not None:
        return GUARDED_EXECUTION
    if state["retry_count"] == 0:
        return CANDIDATE_GENERATION
    raise StaticValidationError(state["violations"])


# The compiled-graph type's generic parameters change between langgraph minor
# releases, so this boundary is deliberately untyped; `run_query` below
# restores QueryState for every caller.
def build_query_graph(
    schema_linking: NodeFn,
    planning: NodeFn,
    candidate_generation: NodeFn,
    static_validation: NodeFn,
    guarded_execution: NodeFn,
) -> Any:
    graph: StateGraph[QueryState] = StateGraph(QueryState)
    graph.add_node(SCHEMA_LINKING, schema_linking)
    graph.add_node(PLANNING, planning)
    graph.add_node(CANDIDATE_GENERATION, candidate_generation)
    graph.add_node(STATIC_VALIDATION, static_validation)
    graph.add_node(GUARDED_EXECUTION, guarded_execution)

    graph.add_edge(START, SCHEMA_LINKING)
    graph.add_edge(SCHEMA_LINKING, PLANNING)
    graph.add_edge(PLANNING, CANDIDATE_GENERATION)
    graph.add_edge(CANDIDATE_GENERATION, STATIC_VALIDATION)
    graph.add_conditional_edges(
        STATIC_VALIDATION,
        route_after_validation,
        {
            CANDIDATE_GENERATION: CANDIDATE_GENERATION,
            GUARDED_EXECUTION: GUARDED_EXECUTION,
        },
    )
    graph.add_edge(GUARDED_EXECUTION, END)
    return graph.compile()


def run_query(
    graph: Any, question: str, datasource_name: str, domain_id: int | None = None
) -> QueryState:
    return cast(
        QueryState, graph.invoke(initial_state(question, datasource_name, domain_id))
    )
```

If `StateGraph[QueryState]` is rejected by the installed langgraph version's stubs, drop the subscript to a bare `StateGraph` annotation — the runtime call `StateGraph(QueryState)` is unchanged either way.

- [ ] **Step 8: Run to verify the graph tests pass**

Run: `uv run pytest tests/unit/test_query_graph.py -q`
Expected: PASS (7 tests)

- [ ] **Step 9: Write the CLI command**

Create `genql/cli/commands/query.py`:

```python
"""`genql query` — the first command that produces an answer rather than
metadata about one.

Every typed failure from the graph is caught here and printed as one line
with exit code 1, matching `genql discover`'s convention. The graph itself
never catches: a stage failure is a typed error all the way up, and this is
the only layer that knows it is talking to a human.
"""

from __future__ import annotations

import typer

from genql.api.query_graph import run_query
from genql.composition_root import Container
from genql.domain.errors import GenqlError


def query(
    question: str = typer.Argument(..., help="The analytical question, in English"),
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    domain_id: int | None = typer.Option(None, "--domain-id", help="Restrict to one domain"),
) -> None:
    """Plan, generate, statically validate, and safely execute SQL for a question."""
    try:
        final = run_query(Container().query_graph(), question, datasource, domain_id)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    plan = final["plan"]
    if plan is not None:
        typer.echo("Plan:")
        typer.echo(plan.plan_text)
        typer.echo("")

    typer.echo("SQL:")
    typer.echo(final["validated_sql"] or "")
    typer.echo("")

    result = final["result"]
    if result is None:
        typer.echo("no rows returned")
        return
    typer.echo(" | ".join(result.columns))
    for row in result.rows:
        typer.echo(" | ".join("" if value is None else str(value) for value in row))
    typer.echo(f"({result.row_count} rows)")
    if result.truncated:
        typer.echo("truncated at the configured row cap; refine the question for the full set")
```

Modify `genql/cli/main.py` — add the import beside the others and register the command after the `add_typer` calls:

```python
from genql.cli.commands import query as query_commands
```

```python
# `query` is a top-level command, not a sub-app: `genql query "..."` reads
# better than `genql query run "..."`, and there is nothing else under it.
app.command("query")(query_commands.query)
```

- [ ] **Step 10: Verify the command is registered**

Run: `uv run genql query --help`
Expected: the help text for `genql query`, listing `--datasource` and `--domain-id`. (Invoking it for real needs Task 12's `query_graph` provider; `--help` does not construct the container.)

- [ ] **Step 11: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — `lint-imports` confirms `genql.api` importing `genql.services` and `genql.domain` (and nothing lower) satisfies the layers contract

- [ ] **Step 12: Commit**

```bash
git add genql/api/query_state.py genql/api/query_nodes.py genql/api/query_graph.py \
  genql/cli/commands/query.py genql/cli/main.py tests/unit/test_query_nodes.py \
  tests/unit/test_query_graph.py
git commit -m "feat(api): wire the query pipeline as a LangGraph StateGraph"
```

---

### Task 12: Composition-root wiring

**Files:**
- Create: `genql/composition/query_container.py`
- Modify: `genql/composition_root.py`, `tests/unit/test_composition_root.py`
- Test: `tests/unit/test_composition_root.py`

**Interfaces:**
- Consumes: everything built in Tasks 1–11
- Produces: `QueryContainer` exposing `object_name_reader`, `join_path_reader`, `schema_linking_service`, `planning_service`, `candidate_generation_service`, `guardrail_factory`, `static_validation_service`, `query_executor_factory`, `guarded_execution_service`, and `query_graph`; `Container` now inherits `QueryContainer` instead of `SemanticContainer`

- [ ] **Step 1: Write the failing composition-root tests**

Append to `tests/unit/test_composition_root.py`:

```python
def test_the_container_builds_a_schema_linking_service(container: Container) -> None:
    assert hasattr(container.schema_linking_service(), "link")


def test_the_container_builds_a_planning_service(container: Container) -> None:
    assert hasattr(container.planning_service(), "plan")


def test_the_container_builds_a_candidate_generation_service(container: Container) -> None:
    assert hasattr(container.candidate_generation_service(), "generate")


def test_the_container_builds_a_static_validation_service(container: Container) -> None:
    assert hasattr(container.static_validation_service(), "validate")


def test_the_container_builds_a_guarded_execution_service(container: Container) -> None:
    assert hasattr(container.guarded_execution_service(), "execute")


def test_the_guardrail_factory_resolves_all_five_registered_rules(container: Container) -> None:
    from genql.repositories.guardrails.registry import GUARDRAILS

    assert len(GUARDRAILS.keys()) == 5
    assert hasattr(container.guardrail_factory(), "for_datasource")


def test_the_container_builds_an_invokable_query_graph(container: Container) -> None:
    assert hasattr(container.query_graph(), "invoke")
```

And extend the fixture's environment so `Settings()` has a read-only password to hand the engine provider — modify the `container` fixture in the same file by adding one line after the existing `GENQL_OPENROUTER_API_KEY` line:

```python
    monkeypatch.setenv("GENQL_READONLY_DB_PASSWORD", "test-readonly-password")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL — `AttributeError: 'Container' object has no attribute 'schema_linking_service'`

- [ ] **Step 3: Create the query container**

Create `genql/composition/query_container.py`:

```python
"""Online query-path providers: the two read repositories, the five stage
services, the two per-datasource factories, and the compiled LangGraph graph.

Inherits SemanticContainer because schema linking reuses Phase 4's
retrieval_service and semantic_catalog_reader, and planning and generation
reuse its chat_provider — nothing in this phase introduces a second model
surface, per the parent spec's §21 stance that model choice is configuration.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.api.query_graph import build_query_graph
from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.composition.semantic_container import SemanticContainer
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl
from genql.infrastructure.query.query_executor_factory import QueryExecutorFactoryImpl
from genql.repositories.query.object_name_repository import PostgresObjectNameReader
from genql.repositories.semantic.join_path_reader_repository import PostgresJoinPathReader
from genql.services.query.candidate_generation_service import CandidateGenerationService
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.planning_service import PlanningService
from genql.services.query.schema_linking_service import SchemaLinkingService
from genql.services.query.static_validation_service import StaticValidationService


class QueryContainer(SemanticContainer):
    object_name_reader = providers.Singleton(
        PostgresObjectNameReader, engine=SemanticContainer.semantic_engine
    )
    join_path_reader = providers.Singleton(
        PostgresJoinPathReader, engine=SemanticContainer.semantic_engine
    )

    schema_linking_service = providers.Singleton(
        SchemaLinkingService,
        retrieval=SemanticContainer.retrieval_service,
        reader=SemanticContainer.semantic_catalog_reader,
        join_paths=join_path_reader,
        metrics=SemanticContainer.metric_repository,
        top_k=SemanticContainer.settings.provided.search_top_k,
    )
    planning_service = providers.Singleton(
        PlanningService, chat=SemanticContainer.chat_provider
    )
    candidate_generation_service = providers.Singleton(
        CandidateGenerationService, chat=SemanticContainer.chat_provider
    )

    guardrail_factory = providers.Singleton(
        GuardrailFactoryImpl,
        objects=object_name_reader,
        row_cap=SemanticContainer.settings.provided.query_row_cap,
        statement_timeout_ms=SemanticContainer.settings.provided.query_statement_timeout_ms,
    )
    static_validation_service = providers.Singleton(
        StaticValidationService, guardrails=guardrail_factory
    )

    query_executor_factory = providers.Singleton(
        QueryExecutorFactoryImpl,
        provider=SemanticContainer.engine_provider,
        statement_timeout_ms=SemanticContainer.settings.provided.query_statement_timeout_ms,
    )
    guarded_execution_service = providers.Singleton(
        GuardedExecutionService,
        datasources=SemanticContainer.datasource_repository,
        executors=query_executor_factory,
        row_cap=SemanticContainer.settings.provided.query_row_cap,
    )

    query_graph = providers.Singleton(
        build_query_graph,
        schema_linking=providers.Singleton(SchemaLinkingNode, linker=schema_linking_service),
        planning=providers.Singleton(PlanningNode, planner=planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=static_validation_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=guarded_execution_service
        ),
    )
```

- [ ] **Step 4: Point `Container` at the new base**

Modify `genql/composition_root.py`. Replace the import:

```python
from genql.composition.query_container import QueryContainer
```

Replace the class declaration and its step map (the names are unchanged; only the base class they are read from moves):

```python
class Container(QueryContainer):
    # Every step name registered in DISCOVERY_STEPS must have an entry here so
    # its constructor can be injected with the service it needs. A step
    # registered without an entry fails fast (KeyError) at import time rather
    # than being silently dropped from the pipeline.
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": QueryContainer.catalog_scan_service,
        "data_profiling": QueryContainer.profiling_service,
        "graph_projection": QueryContainer.graph_projection_service,
        "object_profiling": QueryContainer.object_profiling_service,
    }

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
        registrations=QueryContainer.schema_registration_repository,
    )
```

Also update the module docstring's parenthetical to name the new context:

```
context (core/graph/gateway/semantic/query) to stay under the project's
```

- [ ] **Step 5: Run to verify the composition-root tests pass**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS — all pre-existing assertions plus the seven new ones

- [ ] **Step 6: Verify the CLI now constructs end to end without a warehouse**

Run: `uv run genql query --help && uv run genql query "x" --datasource nope`
Expected: the help text, then a single clean line naming `nope` as an unregistered datasource and exit code 1 — no traceback. (This proves the container assembles and the CLI's error handling works; it does not need a reachable warehouse.)

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/composition/query_container.py genql/composition_root.py \
  tests/unit/test_composition_root.py
git commit -m "feat(composition-root): wire the Phase 5 query pipeline"
```

---

### Task 13: Prove it end-to-end against real infrastructure

**Files:**
- Create: `tests/integration/test_phase5_end_to_end.py`
- Test: `tests/integration/test_phase5_end_to_end.py`

**Interfaces:**
- Consumes: the full CLI surface from Tasks 1–12, plus Phase 4's `genql discover` / `graph analyze` / `graph domains` / `semantic compile`

**Prerequisites for this task specifically** (beyond the shared Global Constraints): the VM reachable with ParadeDB and Neo4j up; `alembic upgrade head` applied (so `0006` has provisioned `genql_readonly`); `GENQL_READONLY_DB_PASSWORD` set to the same value the migration used; `local.tpcds` discovered and compiled through Phase 4's commands; and `GENQL_OPENROUTER_API_KEY` set. As of this plan's writing that key exists nowhere locally or on the VM, so this test is written to skip cleanly — **the skip is not this task failing.**

- [ ] **Step 1: Write the end-to-end test**

Create `tests/integration/test_phase5_end_to_end.py`:

```python
"""A natural-language question in, real rows out. The first point in the
project where GenQL produces an answer rather than metadata about one.

The assertions are deliberately about safety and shape, not about the answer
being right: accuracy measurement needs the golden-set runner, which is
Phase 8. What must hold here is that the statement executed was a SELECT, it
cleared every guardrail, and the warehouse returned at least one row through
the read-only role."""

from __future__ import annotations

import os

import pytest
import sqlglot
from sqlglot import exp
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

runner = CliRunner()


def _sql_block(stdout: str) -> str:
    """The CLI prints `Plan:`, then `SQL:`, then the rows. Take what sits
    between the SQL header and the blank line that ends it."""
    after_header = stdout.split("SQL:", 1)[1]
    return after_header.split("\n\n", 1)[0].strip()


@pytest.mark.skipif_no_tpcds
def test_a_tpcds_question_produces_a_validated_select_and_real_rows() -> None:
    result = runner.invoke(
        app,
        [
            "query",
            "What is the total net paid for each store, by store name?",
            "--datasource",
            "local",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Plan:" in result.stdout
    assert "SQL:" in result.stdout

    sql = _sql_block(result.stdout)
    expression = sqlglot.parse_one(sql, dialect="postgres")
    assert isinstance(expression, exp.Select | exp.Union)
    assert "store_sales" in sql.lower()
    assert "limit" in sql.lower()
    assert "(0 rows)" not in result.stdout


def test_an_unregistered_datasource_fails_with_one_clean_line() -> None:
    result = runner.invoke(app, ["query", "anything", "--datasource", "not_a_datasource"])

    assert result.exit_code == 1
    assert "not_a_datasource" in result.stdout
    assert "Traceback" not in result.stdout


@pytest.mark.skipif_no_tpcds
def test_a_question_with_no_catalogued_match_fails_as_a_schema_linking_error() -> None:
    result = runner.invoke(
        app,
        [
            "query",
            "zzqqxx nonexistent subject with no warehouse meaning at all",
            "--datasource",
            "local",
        ],
    )

    # Either retrieval returns nothing (SchemaLinkingError) or it returns
    # irrelevant objects and the candidate fails validation. Both are clean
    # one-line failures; neither is a traceback.
    assert "Traceback" not in result.stdout
```

- [ ] **Step 2: Prepare the warehouse (VM, once)**

Run:

```bash
uv run alembic upgrade head
uv run genql discover --datasource local --schema tpcds
uv run genql graph analyze --datasource local
uv run genql graph domains --datasource local
uv run genql semantic compile --datasource local
```

Expected: each command exits 0. `semantic compile` must report more than zero documents — without search documents, retrieval returns nothing and Step 3 fails at schema linking rather than at anything Phase 5 built.

- [ ] **Step 3: Run the end-to-end test**

Run: `uv run pytest tests/integration/test_phase5_end_to_end.py -v`
Expected: PASS — a validated `SELECT` naming `store_sales` with a `LIMIT`, at least one row printed, and both failure cases printing one clean line. If `GENQL_OPENROUTER_API_KEY` is unset, expect `SKIPPED [3] GENQL_OPENROUTER_API_KEY not set`; report that as a skip, not a failure.

- [ ] **Step 4: Run the whole suite once**

Run: `uv run pytest -q`
Expected: unit tests all green; integration tests green wherever the VM and the key are reachable, cleanly skipped where they are not.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_phase5_end_to_end.py
git commit -m "test(query): answer a real TPC-DS question end to end"
```

---

## Done When

- `genql query "<question>" --datasource local` prints an NL plan, a validated `SELECT`, and real rows read through `genql_readonly`.
- Migration `0006` provisions `genql_readonly`, and the integration test proves it can `SELECT` (including from a table created after the grant) and cannot `INSERT`, `DELETE`, or `DROP`.
- `GUARDRAILS` carries five working rules — `statement_kind`, `forbidden_function`, `object_allowlist`, `limit_injection`, `statement_timeout` — resolved per datasource and run in priority order, with exactly one repair attempt per repairable violation.
- `ReadOnlyQueryExecutorRepository` applies `SET LOCAL statement_timeout` per call and truncates at the row cap, both proven against real Postgres.
- The LangGraph `StateGraph` routes correctly on the clean path, on exactly one retry, and raises rather than looping on a second failure — proven with fake nodes and no provider.
- `SchemaLinkingService`, `PlanningService`, `CandidateGenerationService`, `StaticValidationService`, and `GuardedExecutionService` are each unit-tested against fakes with no network and no database.
- One real `PlanningService.plan` and one real `CandidateGenerationService.generate` call are exercised against a live model, or skipped cleanly without a key.
- `Container` exposes every Phase 5 provider and `query_graph`; `tests/unit/test_composition_root.py` asserts each one.
- The full local unit suite is green; `mypy --strict`, `ruff check`, `ruff format --check`, and `lint-imports` all pass; every file is under 250 lines.

---

## Deliberately Not Done

- **Intent classification (§9 stage 1).** Every question is assumed `analytical_sql`. Routing exists to be added when a caller first sends something else, which is not this phase.
- **The ambiguity gate, critique, probing, and candidate selection (§9 stages 2, 9–11).** All four are Phase 6, and all four are why Phase 5 generates one candidate rather than N — generating a second with nothing to resolve the disagreement between them would be dead work.
- **`PostgresSaver`, per-thread advisory locks, and `interrupt()` (§13).** Tied specifically to multi-turn clarification, which does not exist yet. The graph built here is the one Phase 6 extends.
- **Natural-language answer synthesis (§9 stage 14).** Phase 5 returns the SQL and the rows. Turning rows into prose is separately gradeable and deliberately deferred.
- **Rewrite and cost gating (§11).** Phase 7 inserts it between `static_validation` and `guarded_execution`; `limit_injection` and the executor's row cap stay as the safety floor beneath it.
- **Value-profile-aware schema linking.** §9 stage 5 wants a filter on "active customers" checked against real distinct values before it reaches SQL. `genql_column_profile.sample_values` exists from Phase 2 and this stage does not read it yet; it needs the ambiguity machinery to have somewhere to send a mismatch, which is Phase 6.
- **A per-stage model split (§21).** `Settings.chat_model` is reused for both planning and generation. The parent spec's policy table wants DeepSeek V4 Flash for routing-shaped stages and gemini-3-flash-preview for generation; splitting it is one extra `Settings` field and one extra container provider, and is worth doing when the ablation harness (Phase 8) can measure whether it helps.
- **Probe-query execution budgets.** §12's "probe queries carry a separate, stricter timeout and row budget" has no probe stage to apply to until Phase 6. `SET LOCAL` per call is the design decision that makes adding one cheap.
- **N-candidate cost control.** The parent spec's §20/§21 cost model assumes up to eight candidates on the hard path. One candidate per question needs no budget machinery.
