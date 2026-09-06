# GenQL Phase 6: Clarification and Multi-Turn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepend intent routing, an ambiguity gate, and automatic domain scoping to Phase 5's LangGraph pipeline, and make a turn pausable — a question missing a required dimension raises `interrupt()`, checkpoints through `PostgresSaver`, prints a `thread_id` plus one targeted clarifying question, and resumes to a validated, executed answer on the next `genql query --thread-id` invocation.

**Architecture:** Six new ports (`IntentClassifier`, `AmbiguityGate`, `DomainScoper`, `RuleReader`, `RuleWriter`, `DomainReader`, `ThreadLock`, `ThreadLockFactory`) and three new services under `genql/services/query/` implement stages 1–3 of the parent spec's §9. `IntentClassificationService` and `AmbiguityGateService` each make at most one `ChatProvider.complete` call, following Phase 5's grounded-call pattern exactly; `AmbiguityGateService` reads YAML-authored `genql_rule` defaults through `RuleReader` and skips the model call entirely when every dimension is already resolved. `DomainScopingService` composes Phase 4's `RetrievalService` with a new `DomainReader.domain_id_by_name` to turn a plurality vote over `SearchResult.domain_name` into the `domain_id` Phase 5's `SchemaLinkingService` already accepts. `genql_rule` extends the existing YAML-overlay path — a `rules` list on `SemanticOverlay`, a `PostgresRuleWriter` mirroring `PostgresMetricRepository`, upserted unconditionally by `SemanticOverlayService.apply`, with no new CLI verb. The graph gains three nodes and two conditional edges, is compiled with a `PostgresSaver` built over a `psycopg_pool.ConnectionPool`, and every turn runs inside a per-thread `pg_advisory_lock` held by a dedicated connection.

**Tech Stack:** Python 3.12 (uv), `langgraph>=1.2.11` (reused — now with a checkpointer, `interrupt()`, and `Command(resume=...)`), `langgraph-checkpoint-postgres` (new), `psycopg-pool` (new, direct import), `psycopg[binary]` 3.3.5 (reused), ParadeDB 0.25.6 on PostgreSQL 18 (reused), `sqlglot` (reused via Phase 5), OpenRouter over `httpx` via Phase 4's `ChatProvider` (reused), SQLAlchemy 2.0 Core, Alembic, Pydantic v2, pydantic-settings, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-07-genql-phase-6-clarification-and-multi-turn.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md` (§9 online pipeline stages 1–3, §12 safety and governance, §13 multi-turn interaction, §18 phasing, §20 demand-driven stage activation)

## Global Constraints

- Python 3.12 exactly, managed by `uv`. Run everything through `uv run`.
- **No SQL string, SQLAlchemy Core construct, psycopg call, `httpx` call, Cypher string, or GDS client call may appear outside `genql/repositories/`.** Enforced by import-linter: `genql.services` may not import `genql.repositories`, `genql.infrastructure`, `sqlalchemy`, `psycopg`, `neo4j`, `graphdatascience`, or `httpx`. This is why `PostgresThreadLock` lands in `genql/repositories/query/`, not in `genql/infrastructure/db/` as the spec's §4 suggests — it executes `SELECT pg_advisory_lock(...)`, which is SQL.
- `genql/infrastructure/` may import `sqlalchemy` and `psycopg_pool` to *build* a connection or pool, never to run a query. Building the `PostgresSaver` (which owns its own SQL) is infrastructure; that is the same call the composition root already makes for `create_engine_from_dsn`.
- `langgraph` and `langgraph.checkpoint.postgres` are not added to any import-linter forbidden list. By convention `langgraph` appears in exactly two places: `genql/api/query_graph.py` + `genql/api/query_turn_nodes.py` + `genql/api/query_turn.py` (graph construction, `interrupt()`, `Command`), and `genql/infrastructure/checkpoint/postgres_checkpointer.py` (the saver).
- `genql/domain/` imports no other `genql` package and performs no I/O. `ThreadLock` is a `Protocol`, never a psycopg object.
- The `layers` contract declares `genql.api > genql.services > genql.domain`. `genql/api/` may import `genql.services` and `genql.domain`; it may not import `genql.repositories` or `genql.infrastructure`. `genql/composition/` and `genql/cli/` are outside the layers contract and may import anything.
- Every file ≤ 250 lines (pre-commit hook `scripts/check_file_length.py`, `LIMIT = 250`). One class per file. One action per file.
- `uv run mypy genql` (strict) must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass. `uv run lint-imports` must pass.
- All entities and value objects are **frozen Pydantic v2 models** (`model_config = ConfigDict(frozen=True)`), not stdlib dataclasses. The spec's §2 code blocks are written as `@dataclass(frozen=True)` for brevity; the repository convention established in Phases 1–5 is Pydantic, and this plan follows the repository.
- All ports are `@runtime_checkable` `Protocol`s. `ThreadLock` carries only dunder methods, so `isinstance()` on it is vacuous — its test asserts the concrete lock is usable as a `with` block instead.
- Every typed failure inherits `GenqlError` from `genql/domain/errors.py`. The CLI catches `GenqlError` and prints one line plus exit code 1; it never shows a traceback. **A paused turn is not a failure** — it exits 0.
- Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`). Commit at the end of every task.
- **Execution note for whoever runs this plan under subagent-driven-development:** the user's standing preference is to group sequentially-dependent tasks into one dispatch, parallelize genuinely independent tasks, commit at batch boundaries, and run one review at the very end. See "Execution Batches" below.
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

  Real-provider tests (Tasks 5, 6, 13) additionally need `GENQL_OPENROUTER_API_KEY`; they are written to skip cleanly without it and **a clean skip is not a task failure**.
- **This plan may be executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit suite (`tests/unit/`) must be run and must pass there. Integration tests are written, committed, and left for a VM-connected run; report "unit green, integration written-but-unrun" exactly as Phases 2.5, 3, 4, and 5 did.
- The baseline before Task 1 is the full Phase 5 suite green. Never leave a task boundary with a red unit suite.

---

## Verified Library Facts (checked against the installed versions, not assumed)

These were confirmed by running against `langgraph==1.2.11` and `langgraph-checkpoint-postgres` in this repository's environment. Several contradict what the spec assumes. **Implement these, not the spec's phrasing.**

1. **`langgraph-checkpoint-postgres` is genuinely absent.** `uv.lock` pulls `langgraph-checkpoint` 4.2.0 (in-memory + base classes) transitively through `langgraph`, and nothing else. Task 2 adds it.
2. **`PostgresSaver.__init__` takes a live connection, not a DSN.** Its real signature is `PostgresSaver(conn: Conn, pipe: Pipeline | None = None, serde: SerializerProtocol | None = None)`, where `Conn = psycopg.Connection[DictRow] | psycopg_pool.ConnectionPool[psycopg.Connection[DictRow]]`. The pool's connections **must** use `row_factory=dict_row`; a default (tuple) row factory raises inside the saver.
3. **`PostgresSaver.from_conn_string(conn_string, *, pipeline=False)` is a context manager** (`-> Iterator[PostgresSaver]`), so it cannot back a `providers.Singleton` — the saver would be closed the moment the `with` block exits. The composition root builds a long-lived `ConnectionPool` and passes it to the constructor instead.
4. **`PostgresSaver.setup()` takes no arguments and returns `None`.** It is idempotent and creates langgraph's own `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations` tables. `get_next_version(current: str | None, channel: None) -> str` is internal to the saver and is never called by this codebase.
5. **`interrupt` and `Command` import from `langgraph.types`**, not `langgraph.graph`.
6. **An interrupted `graph.invoke(...)` does not raise.** It returns the state mapping with one extra key, `"__interrupt__"`, holding a list of `langgraph.types.Interrupt` objects, each with `.value` (whatever was passed to `interrupt()`) and `.id`. Verified output shape: `{'q': 'revenue', 'ans': None, '__interrupt__': [Interrupt(value='which time range?', id='1f41...')]}`.
7. **On resume, the interrupted node re-executes from its first line.** `interrupt()` raises `GraphInterrupt` on the first pass; on the resumed pass the *same call site* returns the resume value instead. Everything before that call site runs twice. `AmbiguityGateNode` is written to be idempotent under this: its only pre-interrupt work is one `assess` call whose result it overwrites on the second pass.
8. **Resuming is `graph.invoke(Command(resume=<answer>), config)`** with the same `{"configurable": {"thread_id": ...}}` config. Verified round trip returns `{'q': 'revenue', 'ans': 'last quarter'}` with no `__interrupt__` key.
9. **A checkpointer requires a `thread_id`.** `StateGraph.compile(checkpointer=...)` is keyword-first; invoking a checkpointed graph without `configurable.thread_id` raises. Passing a `thread_id` config to a *checkpointer-less* graph is harmless, which is what keeps Phase 5's existing `tests/unit/test_query_graph.py` runnable after Task 10's signature change.

---

## Deviations From the Spec (decided here, deliberately)

Each is a place where the spec's literal text conflicts with an established repository convention, with a verified library fact above, or with something that does not exist in the codebase. Implement the plan's version.

1. **Entities are frozen Pydantic v2 models, not `@dataclass(frozen=True)`.** Same resolution Phase 5 reached; `Rule`, `AmbiguityAssessment`, and `TurnResponse` all follow `Metric` and `SchemaLink`.
2. **`genql_rule` keys on `datasource_name TEXT`, not `datasource_id BIGINT`.** The spec's §4 DDL uses a surrogate FK to `genql_datasource(id)`, but §5 says "follow `PostgresMetricRepository`'s exact shape", and `genql_metric` keys on `datasource_name TEXT` with an FK to `genql.genql_datasource.name`. Both `RuleReader.read_rules(datasource_name)` and `RuleWriter.write_rules(datasource_name, ...)` already take the name. Using an id would make `genql_rule` the only table in `genql.*` that does not.
3. **`AmbiguityGate.assess` takes `datasource_name` and prior answers, not a pre-read `rules` tuple.** The spec's `assess(question, rules)` forces the *node* (in `genql/api/`) to read `genql_rule`, which puts repository access in the controller layer. It also makes the termination argument unprovable: without knowing which dimensions the user already answered, the gate can re-ask the same question forever. The port becomes `assess(question, datasource_name, answers=()) -> AmbiguityAssessment`, and `AmbiguityGateService` holds the `RuleReader`.
4. **`DomainRepository.by_name` does not exist and is not added.** There is no `genql/domain/ports/domain_repository.py` at all, and `PostgresDomainRepository` has exactly two methods: `write_domains` and `write_members`. This phase adds a **new** port `DomainReader` with `domain_id_by_name(datasource_name, name) -> int | None` and one new read method on `PostgresDomainRepository`.
5. **`PostgresThreadLock` lives in `genql/repositories/query/`, not `genql/infrastructure/db/`.** It issues `SELECT pg_advisory_lock(hashtext(%s))`, which is SQL, and the standing constraint is that SQL lives only in repositories. The *factory* that turns a DSN plus a `thread_id` into one lives in `genql/infrastructure/query/thread_lock_factory.py`, mirroring `QueryExecutorFactoryImpl` in the same package.
6. **A `ThreadLockFactory` port is added alongside `ThreadLock`.** The lock's key is the `thread_id`, which is runtime data unknown at container-construction time. The repository's established answer to that is a per-key factory port (`GuardrailFactory.for_datasource`, `QueryExecutorFactory.for_datasource`); `ThreadLockFactory.for_thread(thread_id) -> ThreadLock` follows it.
7. **No `Settings.database_url` is added.** `Settings.semantic_dsn` already names GenQL's own database, and adding a second field for the same database invites the checkpointer and the semantic store to drift apart. What is genuinely needed is a *format* conversion: `semantic_dsn` is a SQLAlchemy URL (`postgresql+psycopg://…`) and psycopg needs libpq form (`postgresql://…`). A pure helper `to_libpq_dsn` in `genql/infrastructure/db/psycopg_dsn.py` does that conversion.
8. **`PostgresSaver.setup()` is called inside the checkpointer builder, not from `genql/cli/main.py`.** The spec says "called once from `genql/cli/main.py`'s startup path the same way the engine provider already runs migrations lazily" — but `DatasourceEngineProvider` does not run migrations, so there is no such precedent to match, and putting it in `main.py` would make `genql --help` open a database connection. `build_checkpointer` is a `providers.Singleton`, so calling `setup()` there runs it exactly once, lazily, on first graph use.
9. **`QueryState` gains a fourth field, `clarifications: tuple[tuple[str, str], ...]`.** The spec lists three additive fields (`thread_id`, `intent`, `ambiguity`). A fourth is unavoidable: the answers the user has already given must survive the loop-back edge into the next `ambiguity_gate` pass, or the gate cannot know a dimension is resolved and the loop does not terminate. This *is* the spec's own §1 "accepted defaults, rejected interpretations … persist as `QueryState`".
10. **`build_query_graph` gains a keyword-only `checkpointer=None`, and `run_query` gains a required `thread_id`.** Existing Phase 5 unit tests build graphs with no checkpointer and are updated to pass `thread_id="t"`, which a checkpointer-less graph ignores (verified fact 9). `resume_query` is added beside `run_query`.
11. **`TurnResponse` is assembled in a new `genql/api/query_turn.py`, not returned by the graph.** The graph's output type stays `QueryState` plus langgraph's `__interrupt__` key; converting that into the CLI's DTO is a controller-adjacent concern and belongs in its own file, which also keeps `query_graph.py` under 250 lines.
12. **`OverlayReport` gains `rules_written: int` and the `genql semantic overlay` output line reports it.** The spec says rules are picked up automatically; a silent write with no count would be the only overlay artifact the command does not report.

---

## File Structure

**Created**

```
genql/domain/entities/rule.py                          Rule
genql/domain/entities/ambiguity_assessment.py          AMBIGUITY_DIMENSIONS, AmbiguityAssessment
genql/domain/entities/turn_response.py                 TurnResponse
genql/domain/value_objects/question_intent.py          QUESTION_INTENTS
genql/domain/ports/intent_classifier.py                IntentClassifier
genql/domain/ports/ambiguity_gate.py                   AmbiguityGate
genql/domain/ports/domain_scoper.py                    DomainScoper
genql/domain/ports/rule_reader.py                      RuleReader
genql/domain/ports/rule_writer.py                      RuleWriter
genql/domain/ports/domain_reader.py                    DomainReader
genql/domain/ports/thread_lock.py                      ThreadLock, ThreadLockFactory
migrations/versions/0007_rules_and_checkpoints.py      genql.genql_rule
genql/repositories/semantic/rule_repository.py         PostgresRuleReader, PostgresRuleWriter
genql/repositories/query/thread_lock_repository.py     PostgresThreadLock
genql/infrastructure/db/psycopg_dsn.py                 to_libpq_dsn
genql/infrastructure/query/thread_lock_factory.py      PostgresThreadLockFactory
genql/infrastructure/checkpoint/__init__.py            package marker
genql/infrastructure/checkpoint/postgres_checkpointer.py  build_checkpointer
genql/services/query/intent_classification_service.py  IntentClassificationService, IntentResponse
genql/services/query/ambiguity_gate_service.py         AmbiguityGateService, GateResponse
genql/services/query/domain_scoping_service.py         DomainScopingService
genql/api/query_turn_nodes.py                          three node adapters
genql/api/query_turn.py                                start_turn, resume_turn, TurnResponse assembly
genql/composition/turn_container.py                    TurnContainer
tests/unit/test_turn_entities.py
tests/unit/test_turn_ports_are_runtime_checkable.py
tests/unit/test_intent_classification_service.py
tests/unit/test_ambiguity_gate_service.py
tests/unit/test_domain_scoping_service.py
tests/unit/test_query_turn_nodes.py
tests/unit/test_query_turn.py
tests/unit/test_psycopg_dsn.py
tests/integration/test_migration_0007.py
tests/integration/test_rule_repository.py
tests/integration/test_thread_lock_repository.py
tests/integration/test_postgres_checkpointer.py
tests/integration/test_intent_classification_service_real_provider.py
tests/integration/test_ambiguity_gate_service_real_provider.py
tests/integration/test_phase6_end_to_end.py
```

**Modified**

```
genql/domain/errors.py                          + IntentClassificationError, AmbiguityGateError,
                                                  DomainScopingError, ThreadLockError
genql/domain/entities/semantic_overlay.py       + RuleOverlay, SemanticOverlay.rules
genql/services/semantic/semantic_overlay_service.py  + rule_writer ctor param, unconditional
                                                  write_rules, OverlayReport.rules_written
genql/repositories/semantic/domain_repository.py     + domain_id_by_name
genql/repositories/semantic/__init__.py         + PostgresRuleReader, PostgresRuleWriter
genql/api/query_state.py                        + thread_id, intent, ambiguity, clarifications
genql/api/query_graph.py                        + three nodes, two routers, checkpointer,
                                                  run_query(thread_id), resume_query
genql/cli/commands/query.py                     + --thread-id, turn rendering
genql/cli/commands/semantic.py                  + rules count in the overlay output line
genql/core/settings.py                          + ambiguity_threshold, domain_scoping_sample_size,
                                                  checkpoint_pool_max_size
genql/composition/semantic_container.py         + rule_reader, rule_writer, overlay rule wiring
genql/composition_root.py                       Container now inherits TurnContainer
pyproject.toml                                  + langgraph-checkpoint-postgres, psycopg-pool
.env.example                                    + GENQL_AMBIGUITY_THRESHOLD,
                                                  GENQL_DOMAIN_SCOPING_SAMPLE_SIZE,
                                                  GENQL_CHECKPOINT_POOL_MAX_SIZE
tests/unit/test_composition_root.py             + the eight new providers
tests/unit/test_semantic_overlay_service.py     + FakeRuleWriter, rules-written test
tests/unit/test_semantic_overlay_yaml_validation.py  + a rules block
tests/unit/test_query_graph.py                  three new fake nodes, thread_id argument
tests/unit/test_query_nodes.py                  thread_id argument to initial_state
tests/unit/test_query_cli.py                    stubs start_turn/resume_turn instead of run_query
semantic/local.yaml                             + a rules block (created if absent)
```

**Not modified, deliberately:** `.importlinter` (no new forbidden module — `psycopg_pool` is reachable only from `genql/infrastructure/`, which the contracts already permit, and adding it to the services forbidden list would be redundant with the existing `psycopg` entry only if the package names matched, which they do not; see Task 2 Step 6 for the explicit check), `docker/compose.yaml` (no new service — the checkpoint tables live in the existing `genql` database), `genql/repositories/semantic/registry.py` (no new retriever kind; §3 of the spec is explicit that `RETRIEVERS` and `GUARDRAILS` are untouched).

---

## Task Sequence and Why

Task 1 is pure declaration — three entities, one constant tuple, seven ports, four errors — so every later task is written against fixed names, exactly as Phases 4 and 5 started. Task 2 pays the two new dependencies, adds the three settings, and lands migration `0007`, because Task 3's repository integration test cannot run without `genql_rule` existing. Task 3 adds the rule repositories and the one new `DomainReader` read method. Task 4 extends the YAML overlay path end to end — entity, service, container wiring, CLI line — and is the last task that touches the offline side. Tasks 5, 6, and 7 are the three new services; each depends only on Task 1 (Task 6 also on Task 3's `RuleReader` *port*, which is Task 1's, not the implementation), so all three parallelize. Task 8 is the advisory lock, and Task 9 the checkpointer; they are split because they are the two genuinely novel infrastructure surfaces in this phase and each deserves its own reviewable failure mode, and they are sequential because Task 9 reuses Task 8's `to_libpq_dsn`. Task 10 extends the graph, which needs every service and the checkpointer to exist as types. Task 11 is the turn DTO and the CLI. Task 12 is composition-root wiring, held until everything it wires exists. Task 13 proves the pause/resume round trip against real infrastructure.

## Execution Batches

| Batch | Tasks | Parallelizable? |
|---|---|---|
| 1 | 1 | — |
| 2 | 2 → 3 | No (3 needs `genql_rule` to exist) |
| 3 | 4 | — |
| 4 | 5, 6, 7 | Yes |
| 5 | 8 → 9 | No (9 reuses 8's `to_libpq_dsn`) |
| 6 | 10 → 11 | No (11 calls 10's `run_query`/`resume_query`) |
| 7 | 12 → 13 | No (13 needs the wired CLI) |

---

### Task 1: Domain foundation — entities, the intent vocabulary, ports, typed errors

**Files:**
- Create: `genql/domain/entities/rule.py`, `genql/domain/entities/ambiguity_assessment.py`, `genql/domain/entities/turn_response.py`, `genql/domain/value_objects/question_intent.py`, `genql/domain/ports/intent_classifier.py`, `genql/domain/ports/ambiguity_gate.py`, `genql/domain/ports/domain_scoper.py`, `genql/domain/ports/rule_reader.py`, `genql/domain/ports/rule_writer.py`, `genql/domain/ports/domain_reader.py`, `genql/domain/ports/thread_lock.py`
- Modify: `genql/domain/errors.py`
- Test: `tests/unit/test_turn_entities.py`, `tests/unit/test_turn_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `genql.domain.entities.execution_result.ExecutionResult`, `genql.domain.errors.QueryError` (both existing, from Phase 5)
- Produces: constant `AMBIGUITY_DIMENSIONS: tuple[str, ...]` (6 names, in priority order); constant `QUESTION_INTENTS: tuple[str, ...]` (4 names); entities `Rule(name, dimension, value, description)`, `AmbiguityAssessment(is_ambiguous, missing_dimension, clarifying_question, applied_defaults)`, `TurnResponse(thread_id, clarifying_question, intent, validated_sql, result, applied_defaults)`; ports `IntentClassifier.classify(question) -> str`, `AmbiguityGate.assess(question, datasource_name, answers=()) -> AmbiguityAssessment`, `DomainScoper.resolve(question, datasource_name) -> int | None`, `RuleReader.read_rules(datasource_name) -> tuple[Rule, ...]`, `RuleWriter.write_rules(datasource_name, rules) -> int`, `DomainReader.domain_id_by_name(datasource_name, name) -> int | None`, `ThreadLock` (context manager), `ThreadLockFactory.for_thread(thread_id) -> ThreadLock`; errors `IntentClassificationError`, `AmbiguityGateError`, `DomainScopingError`, `ThreadLockError`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/test_turn_entities.py`:

```python
"""Phase 6's entities are frozen for the same reason Phase 5's are: they cross
node boundaries inside the graph and get checkpointed to Postgres, so a node
mutating one in place would be invisible here and corrupting there.

AMBIGUITY_DIMENSIONS is asserted by exact order, not by set membership: the
gate asks about the FIRST unresolved dimension in this tuple, so reordering it
silently changes which question a user is asked.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ambiguity_assessment import (
    AMBIGUITY_DIMENSIONS,
    AmbiguityAssessment,
)
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.rule import Rule
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.value_objects.question_intent import QUESTION_INTENTS


def test_the_six_ambiguity_dimensions_are_in_priority_order() -> None:
    assert AMBIGUITY_DIMENSIONS == (
        "entity",
        "metric",
        "time_range",
        "grain",
        "filter",
        "comparison_baseline",
    )


def test_the_four_question_intents_are_fixed() -> None:
    assert QUESTION_INTENTS == ("analytical_sql", "metadata_question", "followup", "non_sql")


def test_a_rule_carries_a_dimension_and_a_value() -> None:
    rule = Rule(
        name="default_period",
        dimension="time_range",
        value="fiscal_year_to_date",
        description="Unqualified periods mean the fiscal year to date.",
    )

    assert rule.dimension == "time_range"
    assert rule.value == "fiscal_year_to_date"


def test_a_rule_is_frozen() -> None:
    rule = Rule(name="r", dimension="filter", value="status = 'active'", description="d")

    with pytest.raises(ValidationError):
        rule.value = "other"


def test_a_rule_dimension_is_not_validated_against_the_dimension_list() -> None:
    """A typo'd dimension is silently never applied, not rejected at write time.

    Documented as a known gap in the spec's §11. This test pins the current
    behaviour so that closing the gap later is a deliberate, visible change
    rather than an accident.
    """
    rule = Rule(name="r", dimension="time_rnage", value="v", description="d")

    assert rule.dimension not in AMBIGUITY_DIMENSIONS


def test_an_unambiguous_assessment_names_no_dimension() -> None:
    assessment = AmbiguityAssessment(is_ambiguous=False)

    assert assessment.missing_dimension is None
    assert assessment.clarifying_question is None
    assert assessment.applied_defaults == ()


def test_an_ambiguous_assessment_carries_one_dimension_and_one_question() -> None:
    assessment = AmbiguityAssessment(
        is_ambiguous=True,
        missing_dimension="time_range",
        clarifying_question="Over what time period?",
        applied_defaults=(("filter", "active_only"),),
    )

    assert assessment.missing_dimension == "time_range"
    assert assessment.applied_defaults == (("filter", "active_only"),)


def test_an_assessment_coerces_applied_defaults_to_a_tuple_of_tuples() -> None:
    assessment = AmbiguityAssessment(
        is_ambiguous=False, applied_defaults=[["filter", "active_only"]]
    )

    assert assessment.applied_defaults == (("filter", "active_only"),)


def test_a_paused_turn_response_carries_a_question_and_no_result() -> None:
    response = TurnResponse(thread_id="t-1", clarifying_question="Over what time period?")

    assert response.result is None
    assert response.validated_sql is None
    assert response.intent is None


def test_a_finished_turn_response_carries_sql_and_rows() -> None:
    response = TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT 1 LIMIT 1",
        result=ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False),
        applied_defaults=(("time_range", "default_period"),),
    )

    assert response.clarifying_question is None
    assert response.result is not None
    assert response.result.row_count == 1


def test_a_short_circuited_turn_response_carries_only_an_intent() -> None:
    response = TurnResponse(thread_id="t-1", intent="non_sql")

    assert response.intent == "non_sql"
    assert response.validated_sql is None
    assert response.result is None


def test_a_turn_response_is_frozen() -> None:
    response = TurnResponse(thread_id="t-1", intent="non_sql")

    with pytest.raises(ValidationError):
        response.thread_id = "t-2"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_turn_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.rule'`

- [ ] **Step 3: Create the entities and the two constant tuples**

Create `genql/domain/entities/rule.py`:

```python
"""A YAML-authored default for one ambiguity-gate dimension.

Never LLM-guessed, exactly like Metric: nothing else in the system proposes a
rule, so there is no merge step and no provenance column to reconcile — the
YAML file is the only author, and `genql semantic overlay` simply upserts it.

`dimension` is a plain str, not Literal[*AMBIGUITY_DIMENSIONS]. A typo'd
dimension is silently never applied rather than rejected at write time, which
is the same "fail visibly downstream, not upfront" tradeoff Phase 4 accepted
for Metric.sql_expression. Tightening it is a one-line follow-up once it
proves worth doing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dimension: str
    value: str
    description: str
```

Create `genql/domain/entities/ambiguity_assessment.py`:

```python
"""What the ambiguity gate decided about one question.

The tuple order is the priority order, and it is load-bearing: the gate asks
about the FIRST unresolved dimension, never a batch, per the parent spec's
"raises interrupt() with one targeted question". It is also the termination
argument — every clarifying answer resolves exactly one member of a fixed
six-element tuple, so at most six rounds can occur and no retry counter is
needed.

`applied_defaults` records (dimension, rule_name) rather than
(dimension, value): the response layer needs to tell the user *which rule*
was applied so they can go change it, and the value is one lookup away.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

AMBIGUITY_DIMENSIONS: tuple[str, ...] = (
    "entity",
    "metric",
    "time_range",
    "grain",
    "filter",
    "comparison_baseline",
)


class AmbiguityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_ambiguous: bool
    missing_dimension: str | None = None
    clarifying_question: str | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
```

Create `genql/domain/value_objects/question_intent.py`:

```python
"""The four intents stage 1 routes on.

A plain tuple constant rather than a Registry: nothing registers a per-intent
*implementation*. Only `analytical_sql` proceeds past intent classification,
and the other three all map to the same "explain what this cannot do yet"
response, so there is no second implementation for a registry to hold.
"""

from __future__ import annotations

QUESTION_INTENTS: tuple[str, ...] = (
    "analytical_sql",
    "metadata_question",
    "followup",
    "non_sql",
)
```

Create `genql/domain/entities/turn_response.py`:

```python
"""What the CLI prints for one turn: a paused clarification, a short-circuited
non-SQL explanation, or a finished answer.

One DTO rather than three because the CLI's job is the same in all three cases
— print something and exit 0 — and because a paused turn is not an error. The
thread_id is always set: even a turn that finishes in one shot has one, so a
follow-up question can attach to it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_result import ExecutionResult


class TurnResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    clarifying_question: str | None = None
    intent: str | None = None
    validated_sql: str | None = None
    result: ExecutionResult | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
```

- [ ] **Step 4: Run to verify the entity tests pass**

Run: `uv run pytest tests/unit/test_turn_entities.py -q`
Expected: PASS — 12 tests

- [ ] **Step 5: Write the failing port tests**

Create `tests/unit/test_turn_ports_are_runtime_checkable.py`:

```python
"""Phase 6's ports get their own file rather than joining Phase 5's, keeping
both comfortably under the 250-line cap.

ThreadLock is asserted differently from the rest: a Protocol whose only members
are __enter__/__exit__ is satisfied by almost anything, so isinstance() on it
proves nothing. What actually matters is that a conforming object works as a
`with` block, so that is what is asserted.
"""

from __future__ import annotations

from types import TracebackType

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.rule import Rule
from genql.domain.ports.ambiguity_gate import AmbiguityGate
from genql.domain.ports.domain_reader import DomainReader
from genql.domain.ports.domain_scoper import DomainScoper
from genql.domain.ports.intent_classifier import IntentClassifier
from genql.domain.ports.rule_reader import RuleReader
from genql.domain.ports.rule_writer import RuleWriter
from genql.domain.ports.thread_lock import ThreadLock, ThreadLockFactory


class Classifier:
    def classify(self, question: str) -> str:
        return "analytical_sql"


class Gate:
    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
    ) -> AmbiguityAssessment:
        return AmbiguityAssessment(is_ambiguous=False)


class Scoper:
    def resolve(self, question: str, datasource_name: str) -> int | None:
        return None


class Rules:
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        return ()

    def write_rules(self, datasource_name: str, rules: tuple[Rule, ...]) -> int:
        return len(rules)


class Domains:
    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        return 7


class Lock:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> None:
        self.entered = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exited = True


class Locks:
    def for_thread(self, thread_id: str) -> ThreadLock:
        return Lock()


def test_intent_classifier_is_structurally_satisfied() -> None:
    assert isinstance(Classifier(), IntentClassifier)


def test_ambiguity_gate_is_structurally_satisfied() -> None:
    assert isinstance(Gate(), AmbiguityGate)


def test_domain_scoper_is_structurally_satisfied() -> None:
    assert isinstance(Scoper(), DomainScoper)


def test_rule_reader_and_writer_are_structurally_satisfied() -> None:
    assert isinstance(Rules(), RuleReader)
    assert isinstance(Rules(), RuleWriter)


def test_domain_reader_is_structurally_satisfied() -> None:
    assert isinstance(Domains(), DomainReader)


def test_thread_lock_factory_is_structurally_satisfied() -> None:
    assert isinstance(Locks(), ThreadLockFactory)


def test_a_thread_lock_works_as_a_with_block_and_always_releases() -> None:
    lock = Lock()

    with lock:
        pass

    assert lock.entered
    assert lock.exited


def test_a_thread_lock_releases_even_when_the_body_raises() -> None:
    lock = Lock()

    with pytest.raises(RuntimeError):
        with lock:
            raise RuntimeError("boom")

    assert lock.exited
```

The file's import block needs `pytest` for that last test:

```python
import pytest
```

- [ ] **Step 6: Run to verify they fail**

Run: `uv run pytest tests/unit/test_turn_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.intent_classifier'`

- [ ] **Step 7: Create the seven port files**

Create `genql/domain/ports/intent_classifier.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntentClassifier(Protocol):
    """Stage 1. Returns one of QUESTION_INTENTS; anything else is an error the
    implementation raises, not a value it returns."""

    def classify(self, question: str) -> str: ...
```

Create `genql/domain/ports/ambiguity_gate.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment


@runtime_checkable
class AmbiguityGate(Protocol):
    """Stage 2.

    Takes `datasource_name` rather than a pre-read tuple of rules so the
    implementation owns its RuleReader — reading genql_rule from the graph node
    would put repository access in the controller layer.

    Takes `answers` — the (dimension, answer) pairs already collected in this
    thread — because without them a resumed assessment cannot tell a resolved
    dimension from an unresolved one, and would re-ask the same question
    forever. With them, each round strictly shrinks a fixed six-element set.
    """

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
    ) -> AmbiguityAssessment: ...
```

Create `genql/domain/ports/domain_scoper.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainScoper(Protocol):
    """Stage 3. Best-effort: returns None rather than raising when no domain
    can be resolved, because an unscoped retrieval is a correct fallback and a
    hard failure here would break questions that simply span domains."""

    def resolve(self, question: str, datasource_name: str) -> int | None: ...
```

Create `genql/domain/ports/rule_reader.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rule import Rule


@runtime_checkable
class RuleReader(Protocol):
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]: ...
```

Create `genql/domain/ports/rule_writer.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rule import Rule


@runtime_checkable
class RuleWriter(Protocol):
    """Returns the count written, matching MetricWriter.write — the overlay
    report prints it, so a None return would make the report lie."""

    def write_rules(self, datasource_name: str, rules: tuple[Rule, ...]) -> int: ...
```

Create `genql/domain/ports/domain_reader.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainReader(Protocol):
    """The read side of genql_domain, added in Phase 6 because domain scoping
    is the first caller that needs to go from a domain NAME (which retrieval
    hits carry) back to the id that SchemaLinker.link takes."""

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None: ...
```

Create `genql/domain/ports/thread_lock.py`:

```python
"""One thread, one in-flight turn.

A second `genql query` on the same thread_id waits rather than corrupting
checkpoint state. The lock is a context manager rather than an
acquire/release pair so that release is structurally guaranteed by the
`with` block instead of by every caller remembering a `finally`.

ThreadLockFactory exists because the lock's key — the thread_id — is runtime
data unknown when the container is constructed. That is the same shape
GuardrailFactory.for_datasource and QueryExecutorFactory.for_datasource
already use for per-key resources.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable


@runtime_checkable
class ThreadLock(Protocol):
    def __enter__(self) -> None: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class ThreadLockFactory(Protocol):
    def for_thread(self, thread_id: str) -> ThreadLock: ...
```

- [ ] **Step 8: Add the four typed errors**

Modify `genql/domain/errors.py`. Append at the end of the file (all four hang off `QueryError`, since all four fail online rather than during discovery — the same placement rule `SchemaLinkingError` and the rest already follow):

```python
class IntentClassificationError(QueryError):
    """The classifier returned something that is not a known question intent."""


class AmbiguityGateError(QueryError):
    """The ambiguity gate could not score the question's dimensions."""


class DomainScopingError(QueryError):
    """Domain scoping could not run at all.

    Distinct from "no domain resolved", which is a plain None return: this
    means the retrieval pass or the domain lookup itself failed, and the turn
    cannot continue with a silently unscoped search.
    """


class ThreadLockError(QueryError):
    """The per-thread advisory lock could not be acquired or released."""
```

- [ ] **Step 9: Run to verify the port tests pass**

Run: `uv run pytest tests/unit/test_turn_ports_are_runtime_checkable.py tests/unit/test_turn_entities.py -q`
Expected: PASS — 20 tests

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — the whole Phase 5 suite plus the 20 new tests

- [ ] **Step 11: Commit**

```bash
git add genql/domain/entities/rule.py genql/domain/entities/ambiguity_assessment.py \
  genql/domain/entities/turn_response.py genql/domain/value_objects/question_intent.py \
  genql/domain/ports/intent_classifier.py genql/domain/ports/ambiguity_gate.py \
  genql/domain/ports/domain_scoper.py genql/domain/ports/rule_reader.py \
  genql/domain/ports/rule_writer.py genql/domain/ports/domain_reader.py \
  genql/domain/ports/thread_lock.py genql/domain/errors.py \
  tests/unit/test_turn_entities.py tests/unit/test_turn_ports_are_runtime_checkable.py
git commit -m "feat(domain): add Phase 6 clarification entities, ports, and errors"
```

---

### Task 2: Dependencies, settings, and migration `0007`

**Files:**
- Create: `migrations/versions/0007_rules_and_checkpoints.py`, `tests/integration/test_migration_0007.py`
- Modify: `pyproject.toml`, `uv.lock`, `genql/core/settings.py`, `.env.example`
- Test: `tests/integration/test_migration_0007.py`

**Interfaces:**
- Consumes: migration `0006` as `down_revision`; `genql.genql_datasource(name)` for the foreign key
- Produces: table `genql.genql_rule (id, datasource_name, name, dimension, value, description, discovered_at)` with `UNIQUE (datasource_name, name)` named `uq_genql_rule_identity`; `Settings.ambiguity_threshold: float = 0.7`, `Settings.domain_scoping_sample_size: int = 20`, `Settings.checkpoint_pool_max_size: int = 4`; importable `langgraph.checkpoint.postgres.PostgresSaver` and `psycopg_pool.ConnectionPool`

- [ ] **Step 1: Confirm the dependency really is missing before adding it**

Run: `uv run python -c "import langgraph.checkpoint.postgres"`
Expected: FAIL — `ModuleNotFoundError: No module named 'langgraph.checkpoint.postgres'`. (Base `langgraph` pulls `langgraph-checkpoint` 4.2.0, which carries only the in-memory saver and the base classes.)

- [ ] **Step 2: Add the two dependencies**

Run:

```bash
uv add langgraph-checkpoint-postgres psycopg-pool
```

`psycopg-pool` arrives transitively with `langgraph-checkpoint-postgres`, but `genql/infrastructure/checkpoint/postgres_checkpointer.py` imports `psycopg_pool` **directly** in Task 9, and a direct import of a transitive dependency is exactly the breakage that a minor upgrade of the parent package causes silently. Declare it.

- [ ] **Step 3: Verify the new surface imports and has the signatures this plan assumes**

Run:

```bash
uv run python -c "
import inspect
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
print(inspect.signature(PostgresSaver.__init__))
print(inspect.signature(PostgresSaver.setup))
"
```

Expected, exactly:

```
(self, conn: '_internal.Conn', pipe: 'Pipeline | None' = None, serde: 'SerializerProtocol | None' = None) -> 'None'
(self) -> 'None'
```

If `__init__` does not take a connection as its first positional parameter, **stop and re-plan Task 9** — everything built on the checkpointer depends on this shape.

- [ ] **Step 4: Add the three settings**

Modify `genql/core/settings.py`. Append three fields after `readonly_db_password`:

```python
    # Below this per-dimension confidence, the gate treats the dimension as
    # unspecified and asks about it. 0.7 rather than 0.5 because a wrong
    # assumption costs a whole wasted pipeline run, while an unnecessary
    # question costs one round trip.
    ambiguity_threshold: float = 0.7
    # How many retrieval hits the plurality vote is taken over. Larger than
    # search_top_k (10) on purpose: scoping wants a broad sample of which
    # domains the question touches, not the best ten objects.
    domain_scoping_sample_size: int = 20
    # PostgresSaver's own pool, separate from the SQLAlchemy engine pool and
    # from the advisory lock's dedicated connection. Small because a CLI turn
    # is single-threaded; an API server would raise it.
    checkpoint_pool_max_size: int = 4
```

- [ ] **Step 5: Document them in `.env.example`**

Modify `.env.example`. Append:

```
# Per-dimension confidence below which the ambiguity gate asks a question.
GENQL_AMBIGUITY_THRESHOLD=0.7
# Retrieval hits sampled for the domain-scoping plurality vote.
GENQL_DOMAIN_SCOPING_SAMPLE_SIZE=20
# Connection pool size for LangGraph's PostgresSaver.
GENQL_CHECKPOINT_POOL_MAX_SIZE=4
```

- [ ] **Step 6: Confirm no import-linter contract needs changing**

Run: `uv run lint-imports`
Expected: PASS unchanged. `psycopg_pool` is a distinct top-level package from `psycopg`, so the existing `forbidden_modules` entry for `psycopg` in the `no-sql-in-services` and `domain-is-pure` contracts does **not** cover it. That is acceptable and deliberate: nothing under `genql/services/` or `genql/domain/` imports it, and the file-level review gate plus this plan's Global Constraints keep it that way. Do **not** add it — a forbidden entry for a package no source file imports is noise that the next phase would have to reason about.

- [ ] **Step 7: Write the failing migration test**

Create `tests/integration/test_migration_0007.py`:

```python
"""0007 is one additive table. The upgrade/downgrade pair is asserted the same
way 0005's and 0006's are: the table exists after `head`, the unique constraint
that the upsert names exists by that exact name, the datasource FK cascades,
and stepping back to 0006 removes it cleanly.

LangGraph's own checkpoint tables are deliberately NOT asserted here — they are
created by PostgresSaver.setup(), not by Alembic, because they are langgraph's
schema to evolve across its own releases. tests/integration/test_postgres_
checkpointer.py covers them.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


@pytest.fixture()
def alembic_config(paradedb_dsn: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    return cfg


def test_upgrade_creates_genql_rule(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass('genql.genql_rule') IS NOT NULL")
        ).scalar_one()

    assert present


def test_the_identity_constraint_is_named_for_the_upsert(migrated_engine: Engine) -> None:
    """PostgresRuleWriter says ON CONFLICT ON CONSTRAINT uq_genql_rule_identity."""
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname = 'uq_genql_rule_identity'"
            )
        ).scalar_one()

    assert present == 1


def test_a_rule_row_requires_a_registered_datasource(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn, pytest.raises(Exception):
        conn.execute(
            text(
                "INSERT INTO genql.genql_rule "
                "(datasource_name, name, dimension, value, description) "
                "VALUES ('no-such-datasource', 'r', 'time_range', 'v', 'd')"
            )
        )


def test_deleting_the_datasource_cascades_to_its_rules(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("cascade_ds", "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_rule "
                "(datasource_name, name, dimension, value, description) "
                "VALUES ('cascade_ds', 'r', 'time_range', 'v', 'd')"
            )
        )
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'cascade_ds'"))
        remaining = conn.execute(
            text("SELECT count(*) FROM genql.genql_rule WHERE datasource_name = 'cascade_ds'")
        ).scalar_one()

    assert remaining == 0


def test_downgrade_to_0006_drops_genql_rule_and_upgrade_restores_it(
    migrated_engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "0006")
    with migrated_engine.connect() as conn:
        gone = conn.execute(
            text("SELECT to_regclass('genql.genql_rule') IS NULL")
        ).scalar_one()
    assert gone

    command.upgrade(alembic_config, "head")
    with migrated_engine.connect() as conn:
        back = conn.execute(
            text("SELECT to_regclass('genql.genql_rule') IS NOT NULL")
        ).scalar_one()
    assert back
```

- [ ] **Step 8: Run to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0007.py -q`
Expected: FAIL — `assert False` on `test_upgrade_creates_genql_rule` (the table does not exist). Without a reachable database this errors at fixture setup instead; that is the sandbox case described in the Global Constraints, and the migration is still written in Step 9.

- [ ] **Step 9: Write the migration**

Create `migrations/versions/0007_rules_and_checkpoints.py`:

```python
"""rules and checkpoints

Revision ID: 0007
Revises: 0006

One additive table, genql_rule: the YAML-authored defaults the ambiguity gate
applies before deciding a question is under-specified.

Keyed on datasource_name TEXT, not a surrogate datasource_id, so it matches
genql_metric — the table the spec explicitly says to mirror — and so both
RuleReader and RuleWriter can take the name they are already given by the
overlay service. `dimension` is a plain TEXT column with no CHECK constraint
against the six known dimensions: a typo'd dimension is silently never applied
rather than rejected here, the same tradeoff genql_metric.sql_expression
already accepts.

Nothing here creates LangGraph's checkpoint tables. `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` belong to
langgraph and are created by PostgresSaver.setup(), which runs once when the
composition root first builds the saver. Hand-writing them as Alembic DDL
would freeze langgraph's schema at this release and break on its next one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_rule",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("dimension", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_rule_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_rule_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_rule", schema="genql")
    # LangGraph's checkpoint tables are not dropped: this migration never
    # created them, and a downgrade that deleted another library's state
    # would silently destroy every paused turn.
```

- [ ] **Step 10: Run the migration test**

Run: `uv run pytest tests/integration/test_migration_0007.py -q`
Expected: PASS — 5 tests. In a sandbox with no database, report "written but unrun".

- [ ] **Step 11: Confirm the whole migration chain still linearises**

Run: `uv run pytest tests/integration/test_migrations.py -q`
Expected: PASS — a single head, `0001 → 0007`.

- [ ] **Step 12: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 13: Commit**

```bash
git add pyproject.toml uv.lock genql/core/settings.py .env.example \
  migrations/versions/0007_rules_and_checkpoints.py tests/integration/test_migration_0007.py
git commit -m "feat(migrations): add genql_rule and the Phase 6 checkpoint dependencies"
```

---

### Task 3: Rule repositories and the domain read side

**Files:**
- Create: `genql/repositories/semantic/rule_repository.py`, `tests/integration/test_rule_repository.py`
- Modify: `genql/repositories/semantic/domain_repository.py`, `genql/repositories/semantic/__init__.py`, `tests/integration/test_domain_repository.py`
- Test: `tests/integration/test_rule_repository.py`, `tests/integration/test_domain_repository.py`

**Interfaces:**
- Consumes: `Rule` entity and the `RuleReader` / `RuleWriter` / `DomainReader` ports (Task 1); `genql.genql_rule` (Task 2)
- Produces: `PostgresRuleReader(engine).read_rules(datasource_name) -> tuple[Rule, ...]` ordered by `name`; `PostgresRuleWriter(engine).write_rules(datasource_name, rules) -> int`, upserting on `uq_genql_rule_identity`; `PostgresDomainRepository.domain_id_by_name(datasource_name, name) -> int | None`

- [ ] **Step 1: Write the failing rule-repository integration test**

Create `tests/integration/test_rule_repository.py`:

```python
"""Rules behave exactly like metrics: YAML-authored, upserted by natural key,
read back in a deterministic order. The ordering is asserted because the
ambiguity gate takes the FIRST rule for a dimension when two rules claim the
same one, so an unordered read would make which default wins depend on
physical row order.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.rule import Rule
from genql.repositories.semantic.rule_repository import PostgresRuleReader, PostgresRuleWriter

DS = "rules_ds"

FISCAL = Rule(
    name="default_period",
    dimension="time_range",
    value="fiscal_year_to_date",
    description="An unqualified period means the fiscal year to date.",
)
ACTIVE = Rule(
    name="active_only",
    dimension="filter",
    value="status = 'active'",
    description="Customers means active customers unless stated otherwise.",
)


@pytest.fixture()
def seeded(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> Engine:
    register_schema(DS, "public")
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_rule WHERE datasource_name = :ds"), {"ds": DS})
    return migrated_engine


def test_written_rules_read_back_ordered_by_name(seeded: Engine) -> None:
    PostgresRuleWriter(seeded).write_rules(DS, (FISCAL, ACTIVE))

    rules = PostgresRuleReader(seeded).read_rules(DS)

    assert [r.name for r in rules] == ["active_only", "default_period"]
    assert rules[1].value == "fiscal_year_to_date"


def test_writing_the_same_name_twice_updates_rather_than_duplicates(seeded: Engine) -> None:
    writer = PostgresRuleWriter(seeded)
    writer.write_rules(DS, (FISCAL,))

    writer.write_rules(
        DS,
        (
            Rule(
                name="default_period",
                dimension="time_range",
                value="trailing_twelve_months",
                description="Changed.",
            ),
        ),
    )

    rules = PostgresRuleReader(seeded).read_rules(DS)
    assert len(rules) == 1
    assert rules[0].value == "trailing_twelve_months"
    assert rules[0].description == "Changed."


def test_writing_no_rules_is_a_no_op_returning_zero(seeded: Engine) -> None:
    assert PostgresRuleWriter(seeded).write_rules(DS, ()) == 0


def test_write_returns_the_number_written(seeded: Engine) -> None:
    assert PostgresRuleWriter(seeded).write_rules(DS, (FISCAL, ACTIVE)) == 2


def test_rules_are_scoped_to_their_datasource(
    seeded: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("other_rules_ds", "public")
    PostgresRuleWriter(seeded).write_rules(DS, (FISCAL,))

    assert PostgresRuleReader(seeded).read_rules("other_rules_ds") == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_rule_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.semantic.rule_repository'`

- [ ] **Step 3: Write the rule repository**

Create `genql/repositories/semantic/rule_repository.py`:

```python
"""YAML-authored ambiguity defaults, upserted by (datasource_name, name) and
read back by datasource.

Two classes in one file, deliberately: they are the two halves of one table's
access and they share its two statements. This mirrors how the metric side is
organised, except that metrics happen to need only a writer plus a reader on
the same class — here the reader is consumed by a service (AmbiguityGateService)
and the writer by a different one (SemanticOverlayService), so they are split
into two types the container can inject independently.

ORDER BY name is not cosmetic: when two rules claim the same dimension, the
gate takes the first, so an unordered read would make the winner depend on
physical row order.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.rule import Rule

_UPSERT_RULE = text("""
    INSERT INTO genql.genql_rule (datasource_name, name, dimension, value, description)
    VALUES (:datasource_name, :name, :dimension, :value, :description)
    ON CONFLICT ON CONSTRAINT uq_genql_rule_identity DO UPDATE
        SET dimension = EXCLUDED.dimension,
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            discovered_at = now()
""")

_SELECT_RULES = text("""
    SELECT name, dimension, value, description
    FROM genql.genql_rule
    WHERE datasource_name = :datasource_name
    ORDER BY name
""")


class PostgresRuleReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_RULES, {"datasource_name": datasource_name}).all()
        return tuple(Rule.model_validate(r._mapping) for r in rows)  # noqa: SLF001


class PostgresRuleWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_rules(self, datasource_name: str, rules: Sequence[Rule]) -> int:
        if not rules:
            return 0
        params = [
            {"datasource_name": datasource_name, **rule.model_dump(mode="json")}
            for rule in rules
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_RULE, params)
        return len(params)
```

- [ ] **Step 4: Export both from the package `__init__`**

Modify `genql/repositories/semantic/__init__.py`. Add the import and both names to `__all__`:

```python
from genql.repositories.semantic.rule_repository import PostgresRuleReader, PostgresRuleWriter
```

```python
__all__ = [
    "DescriptionEnricher",
    "AliasEnricher",
    "UnitEnricher",
    "Bm25Retriever",
    "DenseRetriever",
    "DomainScopedRetriever",
    "HybridRrfRetriever",
    "PostgresJoinPathReader",
    "PostgresRuleReader",
    "PostgresRuleWriter",
]
```

- [ ] **Step 5: Run the rule-repository test**

Run: `uv run pytest tests/integration/test_rule_repository.py -q`
Expected: PASS — 5 tests. Sandbox: "written but unrun".

- [ ] **Step 6: Write the failing domain-read test**

Append to `tests/integration/test_domain_repository.py`:

```python
def test_domain_id_by_name_returns_the_written_id(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")
    repo = PostgresDomainRepository(migrated_engine)
    written = repo.write_domains(
        [
            BusinessDomain(
                datasource_name="lookup_ds",
                name="Sales",
                description="Orders and revenue.",
                provenance=Provenance.LLM,
            )
        ]
    )

    found = repo.domain_id_by_name("lookup_ds", "Sales")

    assert found == written[0].domain_id


def test_domain_id_by_name_returns_none_for_an_unknown_name(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")

    assert PostgresDomainRepository(migrated_engine).domain_id_by_name(
        "lookup_ds", "No Such Domain"
    ) is None


def test_domain_id_by_name_does_not_cross_datasources(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")
    register_schema("lookup_ds_2", "public")
    repo = PostgresDomainRepository(migrated_engine)
    repo.write_domains(
        [
            BusinessDomain(
                datasource_name="lookup_ds",
                name="Sales",
                description="Orders and revenue.",
                provenance=Provenance.LLM,
            )
        ]
    )

    assert repo.domain_id_by_name("lookup_ds_2", "Sales") is None
```

If `Callable`, `BusinessDomain`, or `Provenance` are not already imported in that file, add:

```python
from collections.abc import Callable

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.value_objects.provenance import Provenance
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/integration/test_domain_repository.py -q`
Expected: FAIL — `AttributeError: 'PostgresDomainRepository' object has no attribute 'domain_id_by_name'`

- [ ] **Step 8: Add the read method**

Modify `genql/repositories/semantic/domain_repository.py`. Add the statement beside the two existing ones:

```python
_SELECT_DOMAIN_ID = text("""
    SELECT id
    FROM genql.genql_domain
    WHERE datasource_name = :datasource_name AND name = :name
""")
```

And add the method to `PostgresDomainRepository`, after `write_members`:

```python
    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        """The read side domain scoping needs: retrieval hits carry a domain
        NAME, SchemaLinker.link takes an id. Returns None rather than raising
        on a miss, because a name that no longer resolves is a stale index,
        not a broken query — the caller falls back to unscoped retrieval."""
        with self._engine.connect() as conn:
            row = conn.execute(
                _SELECT_DOMAIN_ID, {"datasource_name": datasource_name, "name": name}
            ).one_or_none()
        return None if row is None else int(row[0])
```

Extend the module docstring's second sentence so it still describes the file:

```
BusinessDomain instances arrive with domain_id=None before the first write.
`domain_id_by_name` is the read side, added in Phase 6 for domain scoping.
```

- [ ] **Step 9: Run the domain test**

Run: `uv run pytest tests/integration/test_domain_repository.py -q`
Expected: PASS — the pre-existing tests plus the three new ones.

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 11: Commit**

```bash
git add genql/repositories/semantic/rule_repository.py \
  genql/repositories/semantic/domain_repository.py \
  genql/repositories/semantic/__init__.py \
  tests/integration/test_rule_repository.py tests/integration/test_domain_repository.py
git commit -m "feat(repositories): add rule read/write and domain id lookup by name"
```

---

### Task 4: `genql_rule` joins the YAML overlay path

**Files:**
- Modify: `genql/domain/entities/semantic_overlay.py`, `genql/services/semantic/semantic_overlay_service.py`, `genql/composition/semantic_container.py`, `genql/cli/commands/semantic.py`, `tests/unit/test_semantic_overlay_service.py`, `tests/unit/test_semantic_overlay_yaml_validation.py`
- Test: `tests/unit/test_semantic_overlay_service.py`, `tests/unit/test_semantic_overlay_yaml_validation.py`

**Interfaces:**
- Consumes: `Rule` entity and `RuleWriter` port (Task 1); `PostgresRuleWriter` (Task 3)
- Produces: `RuleOverlay(name, dimension, value, description)`; `SemanticOverlay.rules: tuple[RuleOverlay, ...] = ()`; `SemanticOverlayService(enrichment_reader, enrichment_writer, metric_writer, rule_writer, join_path_writer, enrichers)` — note `rule_writer` sits immediately after `metric_writer`, matching the order the two are handled in `apply`; `OverlayReport(objects_updated, columns_updated, metrics_written, rules_written, join_hints_written)`
- Note: this task wires `rule_reader` / `rule_writer` into `SemanticContainer` as well, because adding a required constructor parameter to `SemanticOverlayService` would otherwise leave `tests/unit/test_composition_root.py` red at this task boundary. The *query-turn* container wiring stays in Task 12.

- [ ] **Step 1: Write the failing YAML-validation test**

Append to `tests/unit/test_semantic_overlay_yaml_validation.py`:

```python
def test_a_rules_block_parses_into_rule_overlays() -> None:
    overlay = SemanticOverlay.model_validate(
        yaml.safe_load(
            """
            datasource: local
            rules:
              - name: default_period
                dimension: time_range
                value: fiscal_year_to_date
                description: An unqualified period means the fiscal year to date.
              - name: active_only
                dimension: filter
                value: status = 'active'
                description: Customers means active customers unless stated otherwise.
            """
        )
    )

    assert [r.name for r in overlay.rules] == ["default_period", "active_only"]
    assert overlay.rules[0].dimension == "time_range"


def test_an_overlay_with_no_rules_block_defaults_to_empty() -> None:
    overlay = SemanticOverlay.model_validate(yaml.safe_load("datasource: local\n"))

    assert overlay.rules == ()


def test_a_rule_missing_a_required_field_fails_validation() -> None:
    with pytest.raises(ValidationError):
        SemanticOverlay.model_validate(
            yaml.safe_load(
                """
                datasource: local
                rules:
                  - name: default_period
                    dimension: time_range
                """
            )
        )
```

If `pytest`, `yaml`, `ValidationError`, or `SemanticOverlay` are not already imported in that file, add:

```python
import pytest
import yaml
from pydantic import ValidationError

from genql.domain.entities.semantic_overlay import SemanticOverlay
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_semantic_overlay_yaml_validation.py -q`
Expected: FAIL — `AttributeError: 'SemanticOverlay' object has no attribute 'rules'`

- [ ] **Step 3: Add `RuleOverlay` to the overlay model**

Modify `genql/domain/entities/semantic_overlay.py`. Add the model after `MetricOverlay` (it is placed there, not at the end, because rules and metrics are the two always-YAML-authored kinds and reading them together is how the file is understood):

```python
class RuleOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dimension: str
    value: str
    description: str
```

And add the field to `SemanticOverlay`, between `metrics` and `join_hints`:

```python
    rules: tuple[RuleOverlay, ...] = ()
```

- [ ] **Step 4: Run to verify the YAML tests pass**

Run: `uv run pytest tests/unit/test_semantic_overlay_yaml_validation.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing service test**

Modify `tests/unit/test_semantic_overlay_service.py`.

Add a fake writer beside the existing `FakeMetricWriter`:

```python
class FakeRuleWriter:
    def __init__(self) -> None:
        self.written: list[Rule] = []
        self.datasources: list[str] = []

    def write_rules(self, datasource_name: str, rules: Sequence[Rule]) -> int:
        self.datasources.append(datasource_name)
        self.written.extend(rules)
        return len(rules)
```

Add the imports it needs:

```python
from genql.domain.entities.rule import Rule
from genql.domain.entities.semantic_overlay import RuleOverlay
```

Change the `_service` helper so it constructs and returns the rule writer too. Replace its body's construction and return with:

```python
    metrics = FakeMetricWriter()
    rules = FakeRuleWriter()
    join_paths = FakeJoinPathWriter()
    service = SemanticOverlayService(
        reader,
        writer,
        metrics,
        rules,
        join_paths,
        [DescriptionEnricher(), AliasEnricher(), UnitEnricher()],
    )
    return service, writer, metrics, rules, join_paths
```

Every existing call site of `_service` unpacks four values; update each to five by inserting `rules` (or `_`) in the fourth position — for example `service, _, metrics, _, _ = _service([])`.

Then append the two new tests:

```python
def test_rules_are_written_unconditionally_with_no_merge_step() -> None:
    """Same shape as test_metrics_are_written_as_is: nothing else in the system
    proposes a rule, so there is no discovered value to merge against and the
    Enricher registry is not consulted."""
    service, _, _, rules, _ = _service([])

    report = service.apply(
        SemanticOverlay(
            datasource="local",
            rules=(
                RuleOverlay(
                    name="default_period",
                    dimension="time_range",
                    value="fiscal_year_to_date",
                    description="An unqualified period means the fiscal year to date.",
                ),
            ),
        )
    )

    assert report.rules_written == 1
    assert rules.datasources == ["local"]
    assert rules.written[0] == Rule(
        name="default_period",
        dimension="time_range",
        value="fiscal_year_to_date",
        description="An unqualified period means the fiscal year to date.",
    )


def test_an_overlay_with_no_rules_writes_none_and_reports_zero() -> None:
    service, _, _, rules, _ = _service([])

    report = service.apply(SemanticOverlay(datasource="local"))

    assert report.rules_written == 0
    assert rules.written == []
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_semantic_overlay_service.py -q`
Expected: FAIL — `TypeError: SemanticOverlayService.__init__() takes 6 positional arguments but 7 were given`

- [ ] **Step 7: Wire rules into the overlay service**

Modify `genql/services/semantic/semantic_overlay_service.py`.

Add the imports:

```python
from genql.domain.entities.rule import Rule
from genql.domain.ports.rule_writer import RuleWriter
```

Add the field to `OverlayReport`, between `metrics_written` and `join_hints_written`:

```python
    rules_written: int
```

Change the constructor signature and body — `rule_writer` goes immediately after `metric_writer`, matching the order the two are handled in `apply`:

```python
    def __init__(
        self,
        enrichment_reader: EnrichmentReader,
        enrichment_writer: EnrichmentWriter,
        metric_writer: MetricWriter,
        rule_writer: RuleWriter,
        join_path_writer: JoinPathWriter,
        enrichers: Sequence[Enricher],
    ) -> None:
        self._reader = enrichment_reader
        self._writer = enrichment_writer
        self._metric_writer = metric_writer
        self._rule_writer = rule_writer
        self._join_path_writer = join_path_writer
        self._enrichers = {e.key: e for e in enrichers}
```

In `apply`, insert the rule block immediately after the `metrics_written = ...` line and before the `join_hints` block:

```python
        rules = tuple(
            Rule(
                name=r.name,
                dimension=r.dimension,
                value=r.value,
                description=r.description,
            )
            for r in overlay.rules
        )
        rules_written = self._rule_writer.write_rules(overlay.datasource, rules) if rules else 0
```

And add it to the returned report:

```python
        return OverlayReport(
            objects_updated=objects_updated,
            columns_updated=columns_updated,
            metrics_written=metrics_written,
            rules_written=rules_written,
            join_hints_written=join_hints_written,
        )
```

Extend the module docstring's second paragraph so the file still explains itself:

```
Metrics have no merge step: nothing else proposes a metric, so they are
always YAML-authored and simply upserted. Rules follow that precedent exactly
— nothing else proposes an ambiguity default either, so genql_rule is written
unconditionally through RuleWriter with no Enricher involved. Join hints
become JoinPath rows with provenance=YAML, written through the existing
JoinPathWriter — a YAML join hint is not a new concept, it is another path
with a different provenance.
```

- [ ] **Step 8: Wire the rule repositories into `SemanticContainer`**

Modify `genql/composition/semantic_container.py`.

Add the import:

```python
from genql.repositories.semantic.rule_repository import PostgresRuleReader, PostgresRuleWriter
```

Add the two providers immediately after `metric_repository`:

```python
    rule_reader = providers.Singleton(
        PostgresRuleReader, engine=GraphContainer.semantic_engine
    )
    rule_writer = providers.Singleton(
        PostgresRuleWriter, engine=GraphContainer.semantic_engine
    )
```

And add the argument to the existing `semantic_overlay_service` provider, between `metric_writer` and `join_path_writer`:

```python
    semantic_overlay_service = providers.Singleton(
        SemanticOverlayService,
        enrichment_reader=enrichment_repository,
        enrichment_writer=enrichment_repository,
        metric_writer=metric_repository,
        rule_writer=rule_writer,
        join_path_writer=GraphContainer.join_path_writer,
        enrichers=providers.Factory(build_enrichers),
    )
```

- [ ] **Step 9: Report the rule count from the CLI**

Modify `genql/cli/commands/semantic.py`. Replace the `overlay` command's final `typer.echo` with:

```python
    typer.echo(
        f"{report.objects_updated} objects, {report.columns_updated} columns, "
        f"{report.metrics_written} metrics, {report.rules_written} rules, "
        f"{report.join_hints_written} join hints"
    )
```

- [ ] **Step 10: Add the container assertion**

Append to `tests/unit/test_composition_root.py`:

```python
def test_the_container_builds_a_rule_reader_and_writer(container: Container) -> None:
    assert hasattr(container.rule_reader(), "read_rules")
    assert hasattr(container.rule_writer(), "write_rules")
```

- [ ] **Step 11: Run the affected suites**

Run: `uv run pytest tests/unit/test_semantic_overlay_service.py tests/unit/test_semantic_overlay_yaml_validation.py tests/unit/test_semantic_overlay_entity.py tests/unit/test_composition_root.py -q`
Expected: PASS — including the two new service tests, the three new YAML tests, and the new container test

- [ ] **Step 12: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 13: Commit**

```bash
git add genql/domain/entities/semantic_overlay.py \
  genql/services/semantic/semantic_overlay_service.py \
  genql/composition/semantic_container.py genql/cli/commands/semantic.py \
  tests/unit/test_semantic_overlay_service.py \
  tests/unit/test_semantic_overlay_yaml_validation.py tests/unit/test_composition_root.py
git commit -m "feat(semantic): write genql_rule from the YAML overlay"
```

---

### Task 5: `IntentClassificationService`

**Files:**
- Create: `genql/services/query/intent_classification_service.py`, `tests/unit/test_intent_classification_service.py`, `tests/integration/test_intent_classification_service_real_provider.py`
- Test: `tests/unit/test_intent_classification_service.py`, `tests/integration/test_intent_classification_service_real_provider.py`

**Interfaces:**
- Consumes: `ChatProvider` port (Phase 4), `QUESTION_INTENTS` and `IntentClassificationError` (Task 1)
- Produces: `IntentResponse(intent: str)`; `build_intent_prompt(question: str) -> str`; `IntentClassificationService(chat: ChatProvider).classify(question: str) -> str` returning a member of `QUESTION_INTENTS`

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_intent_classification_service.py`:

```python
"""Stage 1, tested against a fake ChatProvider — no network, no database.

The interesting behaviour is not "it returns what the model said". It is the
two guards around that: a model that answers with something outside
QUESTION_INTENTS must fail loudly rather than let an unroutable value reach the
graph's conditional edge, and a provider failure must arrive as
IntentClassificationError rather than as a raw ChatProviderError, so the CLI's
single `except GenqlError` prints one line either way.
"""

from __future__ import annotations

from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.errors import ChatProviderError, IntentClassificationError
from genql.domain.value_objects.question_intent import QUESTION_INTENTS
from genql.services.query.intent_classification_service import (
    IntentClassificationService,
    IntentResponse,
    build_intent_prompt,
)

T = TypeVar("T", bound=BaseModel)


class FakeChat:
    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.prompts.append(prompt)
        return response_schema.model_validate({"intent": self.intent})


class RaisingChat:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        raise self.exc


@pytest.mark.parametrize("intent", QUESTION_INTENTS)
def test_every_known_intent_is_returned_unchanged(intent: str) -> None:
    service = IntentClassificationService(FakeChat(intent))

    assert service.classify("how many stores do we have") == intent


def test_an_unknown_intent_is_a_typed_failure() -> None:
    service = IntentClassificationService(FakeChat("write_me_a_poem"))

    with pytest.raises(IntentClassificationError) as exc:
        service.classify("q")

    assert "write_me_a_poem" in str(exc.value)


def test_a_provider_failure_becomes_an_intent_classification_error() -> None:
    service = IntentClassificationService(RaisingChat(ChatProviderError("502")))

    with pytest.raises(IntentClassificationError):
        service.classify("q")


def test_a_malformed_response_becomes_an_intent_classification_error() -> None:
    service = IntentClassificationService(
        RaisingChat(ValidationError.from_exception_data("IntentResponse", []))
    )

    with pytest.raises(IntentClassificationError):
        service.classify("q")


def test_the_prompt_carries_the_question_and_every_allowed_intent() -> None:
    chat = FakeChat("analytical_sql")

    IntentClassificationService(chat).classify("how many stores do we have")

    prompt = chat.prompts[0]
    assert "how many stores do we have" in prompt
    for intent in QUESTION_INTENTS:
        assert intent in prompt


def test_the_prompt_builder_is_pure() -> None:
    assert build_intent_prompt("q") == build_intent_prompt("q")


def test_the_response_model_is_frozen() -> None:
    response = IntentResponse(intent="analytical_sql")

    with pytest.raises(ValidationError):
        response.intent = "non_sql"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_intent_classification_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.intent_classification_service'`

- [ ] **Step 3: Write the service**

Create `genql/services/query/intent_classification_service.py`:

```python
"""Stage 1 of the parent spec's §9: route away from SQL generation when SQL is
not the answer.

One ChatProvider.complete call, using the same grounded-call pattern
PlanningService established — a validated Pydantic response, not prose to
parse. The model is asked for a bare label rather than a label plus a
rationale: nothing downstream reads a rationale, and asking for one would pay
output tokens (five times input, per the parent spec's §20) for text nobody
sees.

The returned label is re-checked against QUESTION_INTENTS rather than trusted.
A structured-output call can still return a well-formed string that is not one
of the four, and letting that reach the graph's conditional edge would raise a
KeyError deep inside langgraph instead of a typed error here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.errors import ChatProviderError, IntentClassificationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.value_objects.question_intent import QUESTION_INTENTS


class IntentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str


def build_intent_prompt(question: str) -> str:
    return (
        "Classify what a user is asking a data warehouse assistant.\n\n"
        f"Question:\n{question}\n\n"
        "Return `intent` as exactly one of these four labels:\n"
        "- analytical_sql: asks for numbers, aggregates, or rows that a SQL "
        "query over business data would answer.\n"
        "- metadata_question: asks about the schema itself — which tables or "
        "columns exist, what something means — not about the data in it.\n"
        "- followup: refines, corrects, or narrows a previous question, and "
        "cannot be answered without it.\n"
        "- non_sql: anything else, including greetings, instructions, and "
        "requests no database could answer.\n\n"
        "Return the label alone. Do not explain the choice."
    )


class IntentClassificationService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def classify(self, question: str) -> str:
        try:
            response = self._chat.complete(build_intent_prompt(question), IntentResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise IntentClassificationError(
                f"failed to classify {question!r}: {exc}"
            ) from exc
        if response.intent not in QUESTION_INTENTS:
            raise IntentClassificationError(
                f"{response.intent!r} is not a known question intent. "
                f"Expected one of: {', '.join(QUESTION_INTENTS)}"
            )
        return response.intent
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_intent_classification_service.py -q`
Expected: PASS — 10 tests (four parametrised)

- [ ] **Step 5: Write the gated real-provider test**

Create `tests/integration/test_intent_classification_service_real_provider.py`:

```python
"""One real classification against a live model, skipped cleanly without a key.

Two questions, not one: a passing test that only ever sees analytical_sql
would also pass against a service hardcoded to return it. The negative case is
what proves the prompt actually discriminates.
"""

from __future__ import annotations

import os

import pytest

from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.intent_classification_service import IntentClassificationService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


@pytest.fixture()
def service() -> IntentClassificationService:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return IntentClassificationService(provider)


def test_a_counting_question_classifies_as_analytical_sql(
    service: IntentClassificationService,
) -> None:
    assert service.classify("how many stores did we open last quarter") == "analytical_sql"


def test_a_greeting_does_not_classify_as_analytical_sql(
    service: IntentClassificationService,
) -> None:
    assert service.classify("hey there, how are you doing today") != "analytical_sql"
```

The `OpenRouterChatProvider(client=OpenRouterClient(api_key=...), model=...)` construction is copied verbatim from `tests/integration/test_planning_service_real_provider.py`, which already builds one this way.

- [ ] **Step 6: Run the gated test**

Run: `uv run pytest tests/integration/test_intent_classification_service_real_provider.py -q`
Expected: SKIPPED (2 skipped) without a key — a clean skip is a pass for this step.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/services/query/intent_classification_service.py \
  tests/unit/test_intent_classification_service.py \
  tests/integration/test_intent_classification_service_real_provider.py
git commit -m "feat(query): add IntentClassificationService"
```

---

### Task 6: `AmbiguityGateService`

**Files:**
- Create: `genql/services/query/ambiguity_gate_service.py`, `tests/unit/test_ambiguity_gate_service.py`, `tests/integration/test_ambiguity_gate_service_real_provider.py`
- Test: `tests/unit/test_ambiguity_gate_service.py`, `tests/integration/test_ambiguity_gate_service_real_provider.py`

**Interfaces:**
- Consumes: `ChatProvider` (Phase 4); `Rule`, `AMBIGUITY_DIMENSIONS`, `AmbiguityAssessment`, `RuleReader`, `AmbiguityGateError` (Task 1); `Settings.ambiguity_threshold` (Task 2)
- Produces: `DimensionScore(dimension: str, confidence: float)`; `GateResponse(scores: tuple[DimensionScore, ...], clarifying_question: str)`; `build_gate_prompt(question, open_dimensions, answers) -> str`; `AmbiguityGateService(chat: ChatProvider, rules: RuleReader, threshold: float).assess(question, datasource_name, answers=()) -> AmbiguityAssessment`

**The termination argument, stated once so every test below can point at it:** `assess` computes `open_dimensions` as the members of `AMBIGUITY_DIMENSIONS` that are neither covered by a rule nor already present in `answers`. It only ever names a `missing_dimension` drawn from `open_dimensions`. The graph appends `(missing_dimension, answer)` to `answers` before the next pass. So each pass strictly shrinks a fixed six-element set, and when the set is empty `assess` returns `is_ambiguous=False` **without calling the model at all**. At most six clarifying questions can be asked for one turn, and no retry counter is needed — unlike Phase 5's guardrail loop, where the rule set does not shrink.

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_ambiguity_gate_service.py`:

```python
"""Stage 2, against a fake ChatProvider and a fake RuleReader.

Four behaviours carry the phase: rules suppress a dimension without a model
call, the FIRST low-confidence dimension in priority order is the one asked
about, an already-answered dimension is never re-asked, and a fully covered
question skips the model entirely (the parent spec's §20 demand-driven rule —
a well-specified question must not pay for the gate's own call either).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from genql.domain.entities.ambiguity_assessment import AMBIGUITY_DIMENSIONS
from genql.domain.entities.rule import Rule
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.services.query.ambiguity_gate_service import (
    AmbiguityGateService,
    GateResponse,
    build_gate_prompt,
)

T = TypeVar("T", bound=BaseModel)

SPECIFIED = 0.95
VAGUE = 0.10


def rule(name: str, dimension: str) -> Rule:
    return Rule(name=name, dimension=dimension, value="v", description="d")


class FakeRules:
    def __init__(self, rules: Sequence[Rule] = ()) -> None:
        self._rules = tuple(rules)
        self.datasources: list[str] = []

    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        self.datasources.append(datasource_name)
        return self._rules


class FakeChat:
    """Scores every dimension SPECIFIED except the ones named `vague`."""

    def __init__(self, vague: Sequence[str] = (), question: str = "Which one?") -> None:
        self.vague = set(vague)
        self.question = question
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        self.calls += 1
        self.prompts.append(prompt)
        return response_schema.model_validate(
            {
                "scores": [
                    {"dimension": d, "confidence": VAGUE if d in self.vague else SPECIFIED}
                    for d in AMBIGUITY_DIMENSIONS
                ],
                "clarifying_question": self.question,
            }
        )


class RaisingChat:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        raise self.exc


def service(
    chat: object, rules: Sequence[Rule] = (), threshold: float = 0.7
) -> AmbiguityGateService:
    return AmbiguityGateService(chat, FakeRules(rules), threshold)  # type: ignore[arg-type]


def test_a_fully_specified_question_is_not_ambiguous() -> None:
    assessment = service(FakeChat()).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert assessment.missing_dimension is None
    assert assessment.clarifying_question is None


def test_the_first_low_confidence_dimension_in_priority_order_is_the_one_asked_about() -> None:
    chat = FakeChat(vague=("grain", "time_range"), question="Over what time period?")

    assessment = service(chat).assess("show me revenue", "local")

    assert assessment.is_ambiguous is True
    # time_range precedes grain in AMBIGUITY_DIMENSIONS, so it wins even though
    # the fake listed grain first.
    assert assessment.missing_dimension == "time_range"
    assert assessment.clarifying_question == "Over what time period?"


def test_only_one_dimension_is_ever_asked_about() -> None:
    chat = FakeChat(vague=("entity", "metric", "time_range", "grain"))

    assessment = service(chat).assess("q", "local")

    assert assessment.missing_dimension == "entity"


def test_a_rule_covering_a_dimension_suppresses_it_and_is_recorded() -> None:
    chat = FakeChat(vague=("time_range",))

    assessment = service(chat, rules=(rule("default_period", "time_range"),)).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert assessment.applied_defaults == (("time_range", "default_period"),)


def test_applied_defaults_are_reported_in_dimension_priority_order() -> None:
    rules = (rule("active_only", "filter"), rule("default_period", "time_range"))

    assessment = service(FakeChat(), rules=rules).assess("q", "local")

    assert assessment.applied_defaults == (
        ("time_range", "default_period"),
        ("filter", "active_only"),
    )


def test_a_rule_naming_an_unknown_dimension_is_ignored_entirely() -> None:
    """The typo'd-dimension gap the spec's §11 documents: silently inert."""
    chat = FakeChat(vague=("time_range",))

    assessment = service(chat, rules=(rule("typo", "time_rnage"),)).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "time_range"
    assert assessment.applied_defaults == ()


def test_the_first_rule_by_name_wins_when_two_claim_one_dimension() -> None:
    rules = (rule("aaa_first", "time_range"), rule("zzz_second", "time_range"))

    assessment = service(FakeChat(), rules=rules).assess("q", "local")

    assert assessment.applied_defaults == (("time_range", "aaa_first"),)


def test_an_already_answered_dimension_is_never_re_asked() -> None:
    chat = FakeChat(vague=("time_range", "grain"))

    assessment = service(chat).assess("q", "local", answers=(("time_range", "last quarter"),))

    assert assessment.missing_dimension == "grain"


def test_the_loop_terminates_after_the_last_open_dimension_is_answered() -> None:
    """The termination proof, as the spec's §9 asks for it.

    Rules cover five of the six dimensions; the model calls the sixth vague. One
    round asks about that sixth; feeding its answer back must reach
    is_ambiguous=False on the very next pass, with no further model call.
    """
    covered = [d for d in AMBIGUITY_DIMENSIONS if d != "grain"]
    rules = tuple(rule(f"r_{d}", d) for d in covered)
    chat = FakeChat(vague=("grain",), question="At what grain?")
    gate = service(chat, rules=rules)

    first = gate.assess("q", "local")
    assert first.is_ambiguous is True
    assert first.missing_dimension == "grain"

    second = gate.assess("q", "local", answers=(("grain", "by region"),))

    assert second.is_ambiguous is False
    assert second.missing_dimension is None
    # No open dimensions were left, so the second pass never called the model.
    assert chat.calls == 1


def test_no_model_call_is_made_when_rules_cover_every_dimension() -> None:
    chat = FakeChat(vague=AMBIGUITY_DIMENSIONS)
    rules = tuple(rule(f"r_{d}", d) for d in AMBIGUITY_DIMENSIONS)

    assessment = service(chat, rules=rules).assess("q", "local")

    assert assessment.is_ambiguous is False
    assert chat.calls == 0
    assert len(assessment.applied_defaults) == len(AMBIGUITY_DIMENSIONS)


def test_a_confidence_exactly_at_the_threshold_counts_as_specified() -> None:
    class AtThreshold:
        def complete(self, prompt: str, response_schema: type[T]) -> T:
            return response_schema.model_validate(
                {
                    "scores": [{"dimension": d, "confidence": 0.7} for d in AMBIGUITY_DIMENSIONS],
                    "clarifying_question": "Which one?",
                }
            )

    assessment = service(AtThreshold()).assess("q", "local")

    assert assessment.is_ambiguous is False


def test_a_dimension_the_model_omitted_is_treated_as_unspecified() -> None:
    class PartialScores:
        def complete(self, prompt: str, response_schema: type[T]) -> T:
            return response_schema.model_validate(
                {
                    "scores": [{"dimension": "entity", "confidence": 0.99}],
                    "clarifying_question": "Which metric?",
                }
            )

    assessment = service(PartialScores()).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "metric"


def test_an_ambiguous_result_with_an_empty_question_is_a_typed_failure() -> None:
    chat = FakeChat(vague=("entity",), question="   ")

    with pytest.raises(AmbiguityGateError):
        service(chat).assess("q", "local")


def test_a_provider_failure_becomes_an_ambiguity_gate_error() -> None:
    with pytest.raises(AmbiguityGateError):
        service(RaisingChat(ChatProviderError("502"))).assess("q", "local")


def test_a_malformed_response_becomes_an_ambiguity_gate_error() -> None:
    with pytest.raises(AmbiguityGateError):
        service(RaisingChat(ValidationError.from_exception_data("GateResponse", []))).assess(
            "q", "local"
        )


def test_rules_are_read_for_the_datasource_the_turn_names() -> None:
    rules = FakeRules(())
    AmbiguityGateService(FakeChat(), rules, 0.7).assess("q", "warehouse_two")  # type: ignore[arg-type]

    assert rules.datasources == ["warehouse_two"]


def test_the_prompt_lists_only_the_open_dimensions_and_the_answers_so_far() -> None:
    chat = FakeChat(vague=("grain",))

    service(chat, rules=(rule("default_period", "time_range"),)).assess(
        "show me revenue", "local", answers=(("entity", "stores"),)
    )

    prompt = chat.prompts[0]
    assert "show me revenue" in prompt
    assert "grain" in prompt
    # Covered by a rule, so it is not the gate's business any more.
    assert "time_range" not in prompt
    # Already answered, so it is presented as context, not as an open question.
    assert "stores" in prompt


def test_the_prompt_builder_is_pure() -> None:
    assert build_gate_prompt("q", ("grain",), ()) == build_gate_prompt("q", ("grain",), ())


def test_the_response_model_is_frozen() -> None:
    response = GateResponse(scores=(), clarifying_question="Which one?")

    with pytest.raises(ValidationError):
        response.clarifying_question = "other"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ambiguity_gate_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.ambiguity_gate_service'`

- [ ] **Step 3: Write the service**

Create `genql/services/query/ambiguity_gate_service.py`:

```python
"""Stage 2 of the parent spec's §9: decide whether to ask, and if so, ask about
exactly one thing.

Three decisions are worth stating.

First, rules are applied BEFORE the model call, not after it. A dimension a
YAML rule covers is not a question the user should ever see, so it never
reaches the prompt, and if rules cover everything the model is not called at
all. That is the §20 demand-driven cost rule applied to the gate itself: a
well-specified question against a well-ruled datasource pays nothing here.

Second, one question, never a batch. The parent spec asks for "one targeted
question", so the first dimension below threshold in AMBIGUITY_DIMENSIONS order
wins and the rest wait for the next pass.

Third, this terminates without a retry counter. `open_dimensions` is
AMBIGUITY_DIMENSIONS minus the rule-covered ones minus the already-answered
ones; the caller appends the answered dimension to `answers` before the next
pass, so the set strictly shrinks and is empty after at most six rounds. Phase
5's guardrail loop needed a counter because its rule set does not shrink; this
one does.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.ambiguity_assessment import (
    AMBIGUITY_DIMENSIONS,
    AmbiguityAssessment,
)
from genql.domain.errors import AmbiguityGateError, ChatProviderError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.rule_reader import RuleReader


class DimensionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    confidence: float


class GateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scores: tuple[DimensionScore, ...]
    clarifying_question: str


def build_gate_prompt(
    question: str,
    open_dimensions: tuple[str, ...],
    answers: tuple[tuple[str, str], ...],
) -> str:
    context = (
        "\n".join(f"- {dimension}: {answer}" for dimension, answer in answers)
        or "- (none yet)"
    )
    dimensions = "\n".join(f"- {dimension}" for dimension in open_dimensions)
    return (
        "You are judging how completely an analytical question specifies what "
        "it wants, so a SQL generator does not have to guess.\n\n"
        f"Question:\n{question}\n\n"
        f"Already clarified by the user:\n{context}\n\n"
        f"Dimensions still to judge:\n{dimensions}\n\n"
        "Rules:\n"
        "- For each dimension listed above, return a `confidence` between 0.0 "
        "and 1.0 that the question (plus the clarifications) already specifies "
        "it well enough to write SQL without guessing.\n"
        "- Judge only the dimensions listed. Do not invent others.\n"
        "- Return `clarifying_question`: a single, specific question you would "
        "ask about the LOWEST-confidence dimension. Ask about one thing. Never "
        "ask a compound question and never present a form."
    )


class AmbiguityGateService:
    def __init__(self, chat: ChatProvider, rules: RuleReader, threshold: float) -> None:
        self._chat = chat
        self._rules = rules
        self._threshold = threshold

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
    ) -> AmbiguityAssessment:
        defaults = self._defaults(datasource_name)
        applied = tuple(
            (dimension, defaults[dimension])
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension in defaults
        )
        answered = {dimension for dimension, _ in answers}
        open_dimensions = tuple(
            dimension
            for dimension in AMBIGUITY_DIMENSIONS
            if dimension not in defaults and dimension not in answered
        )
        if not open_dimensions:
            return AmbiguityAssessment(is_ambiguous=False, applied_defaults=applied)

        response = self._score(question, open_dimensions, answers)
        scored = {score.dimension: score.confidence for score in response.scores}
        missing = next(
            (
                dimension
                for dimension in open_dimensions
                # A dimension the model omitted scores 0.0: silence is not
                # evidence that the question specified it.
                if scored.get(dimension, 0.0) < self._threshold
            ),
            None,
        )
        if missing is None:
            return AmbiguityAssessment(is_ambiguous=False, applied_defaults=applied)
        clarifying_question = response.clarifying_question.strip()
        if not clarifying_question:
            raise AmbiguityGateError(
                f"the gate found {missing!r} under-specified in {question!r} but "
                "returned no clarifying question to ask"
            )
        return AmbiguityAssessment(
            is_ambiguous=True,
            missing_dimension=missing,
            clarifying_question=clarifying_question,
            applied_defaults=applied,
        )

    def _defaults(self, datasource_name: str) -> dict[str, str]:
        """First rule by name wins per dimension; the reader orders by name, so
        the winner is stable rather than dependent on row order. A rule naming
        a dimension outside AMBIGUITY_DIMENSIONS is inert, per the spec's §11."""
        defaults: dict[str, str] = {}
        for rule in self._rules.read_rules(datasource_name):
            if rule.dimension in AMBIGUITY_DIMENSIONS and rule.dimension not in defaults:
                defaults[rule.dimension] = rule.name
        return defaults

    def _score(
        self,
        question: str,
        open_dimensions: tuple[str, ...],
        answers: tuple[tuple[str, str], ...],
    ) -> GateResponse:
        try:
            return self._chat.complete(
                build_gate_prompt(question, open_dimensions, answers), GateResponse
            )
        except (ChatProviderError, ValidationError) as exc:
            raise AmbiguityGateError(f"failed to assess {question!r}: {exc}") from exc
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_ambiguity_gate_service.py -q`
Expected: PASS — 19 tests

- [ ] **Step 5: Confirm the file is under the length cap**

Run: `uv run python scripts/check_file_length.py genql/services/query/ambiguity_gate_service.py`
Expected: exit 0, no output. (This is the longest new service in the phase; check it explicitly rather than waiting for pre-commit.)

- [ ] **Step 6: Write the gated real-provider test**

Create `tests/integration/test_ambiguity_gate_service_real_provider.py`:

```python
"""One real gate assessment against a live model, skipped cleanly without a key.

Two questions again, for the same reason as the intent test: a gate that always
said "ambiguous" would pass a one-sided test. The well-specified case is the
one that proves it discriminates, and it is also the case the parent spec's §20
cost model depends on — a gate that fires on everything makes the cheap path
disappear.
"""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.rule import Rule
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.ambiguity_gate_service import AmbiguityGateService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)


class NoRules:
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        return ()


@pytest.fixture()
def gate() -> AmbiguityGateService:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return AmbiguityGateService(provider, NoRules(), 0.7)


def test_a_bare_two_word_question_is_judged_ambiguous(gate: AmbiguityGateService) -> None:
    assessment = gate.assess("show me revenue", "local")

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension is not None
    assert assessment.clarifying_question


def test_a_fully_specified_question_is_not_judged_ambiguous(
    gate: AmbiguityGateService,
) -> None:
    assessment = gate.assess(
        "for each store, total net paid on store sales in calendar year 2001, "
        "counting only completed sales, compared with calendar year 2000",
        "local",
    )

    assert assessment.is_ambiguous is False
```

- [ ] **Step 7: Run the gated test**

Run: `uv run pytest tests/integration/test_ambiguity_gate_service_real_provider.py -q`
Expected: SKIPPED (2 skipped) without a key.

- [ ] **Step 8: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add genql/services/query/ambiguity_gate_service.py \
  tests/unit/test_ambiguity_gate_service.py \
  tests/integration/test_ambiguity_gate_service_real_provider.py
git commit -m "feat(query): add AmbiguityGateService with rule-backed defaults"
```

---

### Task 7: `DomainScopingService`

**Files:**
- Create: `genql/services/query/domain_scoping_service.py`, `tests/unit/test_domain_scoping_service.py`
- Test: `tests/unit/test_domain_scoping_service.py`

**Interfaces:**
- Consumes: `RetrievalService.search(datasource_name, query, top_k, domain_id=None) -> Sequence[SearchResult]` (Phase 4, `SearchResult.domain_name: str | None`); `DomainReader` and `DomainScopingError` (Task 1); `Settings.domain_scoping_sample_size` (Task 2)
- Produces: `DomainScopingService(retrieval: RetrievalService, domains: DomainReader, sample_size: int).resolve(question, datasource_name) -> int | None`

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_domain_scoping_service.py`:

```python
"""Stage 3, against a fake RetrievalService and a fake DomainReader.

This is deliberately a best-effort heuristic, so the tests pin the shape of the
heuristic rather than its accuracy: an unscoped sample, a plurality vote over
domain_name, a name-to-id lookup, and None wherever any of the three has
nothing to work with. Getting the domain WRONG is a documented risk (spec §11)
that --domain-id overrides; getting it wrong SILENTLY and irreversibly is what
these tests exist to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.errors import RetrievalError
from genql.domain.ports.retriever import SearchResult
from genql.services.query.domain_scoping_service import DomainScopingService


def hit(domain_name: str | None, object_name: str = "t", score: float = 1.0) -> SearchResult:
    return SearchResult(
        datasource_name="local",
        schema_name="tpcds",
        object_name=object_name,
        domain_name=domain_name,
        score=score,
    )


class FakeRetrieval:
    def __init__(self, results: Sequence[SearchResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str, int, int | None]] = []

    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        self.calls.append((datasource_name, query, top_k, domain_id))
        return self.results


class RaisingRetrieval:
    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        raise RetrievalError("index unavailable")


class FakeDomains:
    def __init__(self, ids: dict[str, int] | None = None) -> None:
        self.ids = ids or {}
        self.looked_up: list[tuple[str, str]] = []

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        self.looked_up.append((datasource_name, name))
        return self.ids.get(name)


def service(
    results: Sequence[SearchResult], ids: dict[str, int] | None = None, sample_size: int = 20
) -> tuple[DomainScopingService, FakeRetrieval, FakeDomains]:
    retrieval = FakeRetrieval(results)
    domains = FakeDomains(ids)
    return (
        DomainScopingService(retrieval, domains, sample_size),  # type: ignore[arg-type]
        retrieval,
        domains,
    )


def test_the_plurality_domain_is_resolved_to_its_id() -> None:
    scoper, _, domains = service(
        [hit("Sales"), hit("Sales"), hit("Inventory")], ids={"Sales": 3, "Inventory": 9}
    )

    assert scoper.resolve("q", "local") == 3
    assert domains.looked_up == [("local", "Sales")]


def test_the_sample_is_unscoped_and_sized_from_settings() -> None:
    """The first real caller of the unscoped pass: scoping cannot pass a
    domain_id, because resolving one is the whole point of this stage."""
    scoper, retrieval, _ = service([hit("Sales")], ids={"Sales": 3}, sample_size=25)

    scoper.resolve("how much did we sell", "local")

    assert retrieval.calls == [("local", "how much did we sell", 25, None)]


def test_an_empty_sample_resolves_to_none_without_a_lookup() -> None:
    scoper, _, domains = service([])

    assert scoper.resolve("q", "local") is None
    assert domains.looked_up == []


def test_hits_with_no_domain_are_ignored() -> None:
    scoper, _, _ = service([hit(None), hit(None), hit("Sales")], ids={"Sales": 3})

    assert scoper.resolve("q", "local") == 3


def test_a_sample_where_every_hit_lacks_a_domain_resolves_to_none() -> None:
    scoper, _, domains = service([hit(None), hit(None)])

    assert scoper.resolve("q", "local") is None
    assert domains.looked_up == []


def test_a_tie_is_broken_by_the_highest_ranked_hit() -> None:
    """Counter.most_common preserves insertion order on ties, and retrieval
    returns hits already ranked, so the tie-break is "whichever domain the best
    hit belonged to" — deterministic, and the most defensible answer available
    without adding a confidence model this phase deliberately defers."""
    scoper, _, _ = service(
        [hit("Inventory"), hit("Sales")], ids={"Sales": 3, "Inventory": 9}
    )

    assert scoper.resolve("q", "local") == 9


def test_a_domain_name_that_no_longer_resolves_yields_none() -> None:
    """A stale search index is not a broken query: fall back to unscoped."""
    scoper, _, _ = service([hit("Retired Domain")], ids={})

    assert scoper.resolve("q", "local") is None


def test_a_retrieval_failure_becomes_a_domain_scoping_error() -> None:
    from genql.domain.errors import DomainScopingError

    scoper = DomainScopingService(RaisingRetrieval(), FakeDomains(), 20)  # type: ignore[arg-type]

    with pytest.raises(DomainScopingError):
        scoper.resolve("q", "local")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_domain_scoping_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.domain_scoping_service'`

- [ ] **Step 3: Write the service**

Create `genql/services/query/domain_scoping_service.py`:

```python
"""Stage 3 of the parent spec's §9, and the first real caller of Phase 4's
domain-scoped retrieval path.

The heuristic is deliberately plain: one unscoped retrieval pass, a plurality
vote over the domain_name each hit carries, one name-to-id lookup. There is no
confidence floor, and a wrongly-resolved domain narrows retrieval to the wrong
slice of the schema — which is exactly the risk the spec's §11 names and
accepts. It is accepted because --domain-id remains a manual override for that
failure mode, and because real disambiguation (asking the user, or making
domain a seventh ambiguity dimension) is a design decision worth making on
evidence rather than half-building here.

None is returned, not raised, wherever the vote has nothing to work with: an
empty sample, a sample with no domains at all, or a domain name the store no
longer knows. All three mean "search unscoped", which is precisely what Phase 5
did on every question. A retrieval failure IS raised, because that means the
turn cannot search at all.
"""

from __future__ import annotations

from collections import Counter

from genql.domain.errors import DomainScopingError, RetrievalError
from genql.domain.ports.domain_reader import DomainReader
from genql.services.semantic.retrieval_service import RetrievalService


class DomainScopingService:
    def __init__(
        self, retrieval: RetrievalService, domains: DomainReader, sample_size: int
    ) -> None:
        self._retrieval = retrieval
        self._domains = domains
        self._sample_size = sample_size

    def resolve(self, question: str, datasource_name: str) -> int | None:
        try:
            results = self._retrieval.search(datasource_name, question, self._sample_size)
        except RetrievalError as exc:
            raise DomainScopingError(
                f"failed to sample {datasource_name!r} for {question!r}: {exc}"
            ) from exc

        names = [r.domain_name for r in results if r.domain_name]
        if not names:
            return None
        # Counter.most_common breaks ties by first insertion, and `results` is
        # already ranked, so a tie resolves to the better-ranked hit's domain.
        plurality, _ = Counter(names).most_common(1)[0]
        return self._domains.domain_id_by_name(datasource_name, plurality)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_domain_scoping_service.py -q`
Expected: PASS — 8 tests

- [ ] **Step 5: Confirm the layering still holds**

Run: `uv run lint-imports`
Expected: PASS. `DomainScopingService` imports another service (`RetrievalService`) and a domain port, and nothing from `genql.repositories` or `genql.infrastructure` — service-to-service composition is what `SchemaLinkingService` already does with the same `RetrievalService`.

- [ ] **Step 6: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add genql/services/query/domain_scoping_service.py \
  tests/unit/test_domain_scoping_service.py
git commit -m "feat(query): add DomainScopingService"
```

---

### Task 8: The per-thread advisory lock

**Files:**
- Create: `genql/infrastructure/db/psycopg_dsn.py`, `genql/repositories/query/thread_lock_repository.py`, `genql/infrastructure/query/thread_lock_factory.py`, `tests/unit/test_psycopg_dsn.py`, `tests/integration/test_thread_lock_repository.py`
- Test: `tests/unit/test_psycopg_dsn.py`, `tests/integration/test_thread_lock_repository.py`

**Interfaces:**
- Consumes: `ThreadLock` / `ThreadLockFactory` ports and `ThreadLockError` (Task 1); `psycopg` (already a dependency)
- Produces: `to_libpq_dsn(url: str) -> str` stripping a SQLAlchemy driver token; `PostgresThreadLock(dsn: str, thread_id: str)` usable as a `with` block; `PostgresThreadLockFactory(dsn: str).for_thread(thread_id) -> ThreadLock`

- [ ] **Step 1: Write the failing DSN-helper test**

Create `tests/unit/test_psycopg_dsn.py`:

```python
"""Settings.semantic_dsn is a SQLAlchemy URL; psycopg needs libpq form.

This exists so there is exactly ONE setting naming GenQL's own database. A
second setting for the same database would let the checkpointer and the
semantic store drift onto different servers, which would fail silently — the
checkpoints would simply never be found again.
"""

from __future__ import annotations

import pytest

from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn


def test_the_sqlalchemy_driver_token_is_stripped() -> None:
    assert (
        to_libpq_dsn("postgresql+psycopg://genql:genql@localhost:5433/genql")
        == "postgresql://genql:genql@localhost:5433/genql"
    )


def test_any_driver_token_is_stripped_not_just_psycopg() -> None:
    assert (
        to_libpq_dsn("postgresql+psycopg2://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"
    )


def test_a_plain_libpq_dsn_passes_through_unchanged() -> None:
    assert to_libpq_dsn("postgresql://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_the_postgres_scheme_alias_is_accepted() -> None:
    assert to_libpq_dsn("postgres://u:p@h:5432/d") == "postgres://u:p@h:5432/d"


def test_query_parameters_survive() -> None:
    assert (
        to_libpq_dsn("postgresql+psycopg://u:p@h:5432/d?sslmode=require")
        == "postgresql://u:p@h:5432/d?sslmode=require"
    )


def test_a_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="postgres"):
        to_libpq_dsn("mysql://u:p@h:3306/d")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_psycopg_dsn.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.db.psycopg_dsn'`

- [ ] **Step 3: Write the DSN helper**

Create `genql/infrastructure/db/psycopg_dsn.py`:

```python
"""Convert GenQL's SQLAlchemy URL into the libpq DSN psycopg wants.

Pure string work, no I/O, no driver import — so it stays a plain function and
is unit-testable without a database. Rejecting a non-Postgres URL rather than
passing it through is deliberate: everything that calls this is about to open a
psycopg connection, and failing here names the setting, while failing there
names a socket.
"""

from __future__ import annotations

import re

_DRIVER_TOKEN = re.compile(r"^(postgresql|postgres)\+[A-Za-z0-9_]+://")


def to_libpq_dsn(url: str) -> str:
    if not url.startswith(("postgresql://", "postgres://")) and not _DRIVER_TOKEN.match(url):
        raise ValueError(
            f"{url!r} is not a postgres URL; GENQL_SEMANTIC_DSN must name GenQL's "
            "own PostgreSQL database"
        )
    return _DRIVER_TOKEN.sub(r"\1://", url)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_psycopg_dsn.py -q`
Expected: PASS — 6 tests

- [ ] **Step 5: Write the failing lock integration test**

Create `tests/integration/test_thread_lock_repository.py`:

```python
"""The lock's whole reason to exist is that a SECOND acquire blocks.

That cannot be asserted from one connection — pg_advisory_lock is re-entrant
within a session, so a same-session second acquire returns immediately and
would prove nothing. Each lock therefore opens its own connection, and the test
uses a real background thread to prove the second one genuinely waits.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import Engine, text

from genql.domain.errors import ThreadLockError
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn
from genql.infrastructure.query.thread_lock_factory import PostgresThreadLockFactory


@pytest.fixture()
def dsn(paradedb_dsn: str, migrated_engine: Engine) -> str:
    return to_libpq_dsn(paradedb_dsn)


def test_a_lock_can_be_acquired_and_released(dsn: str) -> None:
    with PostgresThreadLockFactory(dsn).for_thread("t-solo"):
        pass


def test_the_same_thread_id_is_reusable_after_release(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)
    with factory.for_thread("t-reuse"):
        pass
    with factory.for_thread("t-reuse"):
        pass


def test_a_second_acquire_on_the_same_thread_id_waits_for_the_first(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)
    order: list[str] = []
    second_acquired = threading.Event()

    def second() -> None:
        with factory.for_thread("t-contended"):
            order.append("second")
            second_acquired.set()

    with factory.for_thread("t-contended"):
        worker = threading.Thread(target=second, daemon=True)
        worker.start()
        # Long enough that a non-blocking implementation would have appended
        # "second" before "first"; short enough to keep the suite quick.
        time.sleep(1.0)
        assert not second_acquired.is_set()
        order.append("first")

    worker.join(timeout=10)
    assert second_acquired.is_set()
    assert order == ["first", "second"]


def test_different_thread_ids_do_not_block_each_other(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)

    with factory.for_thread("t-a"), factory.for_thread("t-b"):
        pass


def test_the_lock_is_released_when_the_body_raises(dsn: str) -> None:
    factory = PostgresThreadLockFactory(dsn)

    with pytest.raises(RuntimeError):
        with factory.for_thread("t-raises"):
            raise RuntimeError("boom")

    # If the first lock leaked, this would hang rather than return.
    with factory.for_thread("t-raises"):
        pass


def test_another_session_cannot_take_the_lock_until_it_is_released(
    dsn: str, migrated_engine: Engine
) -> None:
    """pg_try_advisory_lock is the non-blocking probe: False while held, True
    once released. Asserted from a separate SQLAlchemy connection, because a
    same-session probe would succeed re-entrantly and prove nothing."""
    probe = text("SELECT pg_try_advisory_lock(hashtext('t-cleanup'))")
    unprobe = text("SELECT pg_advisory_unlock(hashtext('t-cleanup'))")

    with PostgresThreadLockFactory(dsn).for_thread("t-cleanup"):
        with migrated_engine.connect() as conn:
            assert conn.execute(probe).scalar_one() is False

    with migrated_engine.connect() as conn:
        assert conn.execute(probe).scalar_one() is True
        conn.execute(unprobe)


def test_an_unreachable_database_is_a_typed_failure() -> None:
    factory = PostgresThreadLockFactory("postgresql://nobody@127.0.0.1:1/none")

    with pytest.raises(ThreadLockError):
        with factory.for_thread("t-unreachable"):
            pass
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/integration/test_thread_lock_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.query.thread_lock_factory'`

- [ ] **Step 7: Write the lock repository**

Create `genql/repositories/query/thread_lock_repository.py`:

```python
"""One thread, one in-flight turn, enforced by a session-scoped Postgres
advisory lock.

This lives in repositories, not infrastructure, because it issues SQL — the
standing rule is that SQL appears only here. The spec's §4 places it in
infrastructure/db/; the factory that BUILDS it does, which is the same split
QueryExecutorFactoryImpl and ReadOnlyQueryExecutorRepository already use.

A dedicated psycopg connection, not the SQLAlchemy engine's pool:
pg_advisory_lock is session-scoped, so the lock lives exactly as long as the
connection that took it. Borrowing a pooled connection would release the lock
whenever the pool recycled it, and sharing the checkpointer's pool would
deadlock — the checkpointer needs a connection to write the very checkpoint the
lock is protecting.

The connection's lifetime IS the lock's lifetime, which is also the crash-safety
story: a process that dies holding the lock drops its connection, and Postgres
releases the lock itself. There is no stale-lock cleanup path to get wrong.
"""

from __future__ import annotations

from types import TracebackType

import psycopg

from genql.domain.errors import ThreadLockError

_ACQUIRE = "SELECT pg_advisory_lock(hashtext(%s))"
_RELEASE = "SELECT pg_advisory_unlock(hashtext(%s))"


class PostgresThreadLock:
    def __init__(self, dsn: str, thread_id: str) -> None:
        self._dsn = dsn
        self._thread_id = thread_id
        self._conn: psycopg.Connection[tuple[object, ...]] | None = None

    def __enter__(self) -> None:
        try:
            conn = psycopg.connect(self._dsn, autocommit=True)
        except psycopg.Error as exc:
            raise ThreadLockError(
                f"could not connect to take the lock for thread {self._thread_id!r}: {exc}"
            ) from exc
        try:
            conn.execute(_ACQUIRE, (self._thread_id,))
        except psycopg.Error as exc:
            conn.close()
            raise ThreadLockError(
                f"could not lock thread {self._thread_id!r}: {exc}"
            ) from exc
        self._conn = conn

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.execute(_RELEASE, (self._thread_id,))
        except psycopg.Error:
            # Closing the connection releases the lock regardless, so a failed
            # explicit unlock is not worth masking the body's own exception.
            pass
        finally:
            conn.close()
```

- [ ] **Step 8: Write the factory**

Create `genql/infrastructure/query/thread_lock_factory.py`:

```python
"""Binds the process-wide DSN to a per-turn thread_id.

Infrastructure rather than a repository because it opens no connection and runs
no statement — it only decides which lock object to construct, exactly as
QueryExecutorFactoryImpl decides which executor to construct.
"""

from __future__ import annotations

from genql.domain.ports.thread_lock import ThreadLock
from genql.repositories.query.thread_lock_repository import PostgresThreadLock


class PostgresThreadLockFactory:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def for_thread(self, thread_id: str) -> ThreadLock:
        return PostgresThreadLock(self._dsn, thread_id)
```

- [ ] **Step 9: Run the lock test**

Run: `uv run pytest tests/integration/test_thread_lock_repository.py -q`
Expected: PASS — 7 tests. Sandbox: "written but unrun". The contended test takes about a second by design.

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — in particular `lint-imports` must still pass, proving `psycopg` stayed out of `genql/services/`.

- [ ] **Step 11: Commit**

```bash
git add genql/infrastructure/db/psycopg_dsn.py \
  genql/repositories/query/thread_lock_repository.py \
  genql/infrastructure/query/thread_lock_factory.py \
  tests/unit/test_psycopg_dsn.py tests/integration/test_thread_lock_repository.py
git commit -m "feat(query): add the per-thread Postgres advisory lock"
```

---

### Task 9: The `PostgresSaver` checkpointer

**Files:**
- Create: `genql/infrastructure/checkpoint/__init__.py`, `genql/infrastructure/checkpoint/postgres_checkpointer.py`, `tests/integration/test_postgres_checkpointer.py`
- Test: `tests/integration/test_postgres_checkpointer.py`

**Interfaces:**
- Consumes: `to_libpq_dsn` (Task 8); `langgraph-checkpoint-postgres` and `psycopg-pool` (Task 2); `Settings.checkpoint_pool_max_size` (Task 2)
- Produces: `build_checkpointer(dsn: str, max_size: int) -> PostgresSaver` — a fully set-up saver over a long-lived, `dict_row`, autocommit `ConnectionPool`

**Why this is its own task:** it is the one genuinely new library surface in the phase, and its constructor is not what the spec assumed (see Verified Library Facts 2–4). Everything in Task 10 sits on top of it, so it gets its own failing-test cycle and its own reviewable boundary rather than being folded into the graph task.

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_postgres_checkpointer.py`:

```python
"""The checkpointer, proven against real Postgres — the only thing that can
prove it, since its whole job is durability across processes.

The round trip is run through a two-node toy graph rather than through GenQL's
real graph on purpose: this asserts the SAVER, and a failure here should point
at langgraph wiring rather than at schema linking. tests/integration/
test_phase6_end_to_end.py runs the same round trip through the real pipeline.
"""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import Engine, text

from genql.infrastructure.checkpoint.postgres_checkpointer import build_checkpointer
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn

CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


class ToyState(TypedDict):
    question: str
    answer: str | None
    passes: int


def gate(state: ToyState) -> dict[str, Any]:
    if state["answer"] is None:
        return {"answer": interrupt("which time range?"), "passes": state["passes"] + 1}
    return {"passes": state["passes"] + 1}


@pytest.fixture()
def saver(paradedb_dsn: str, migrated_engine: Engine) -> Any:
    return build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)


@pytest.fixture()
def toy_graph(saver: Any) -> Any:
    graph: StateGraph[ToyState] = StateGraph(ToyState)
    graph.add_node("gate", gate)
    graph.add_edge(START, "gate")
    graph.add_edge("gate", END)
    return graph.compile(checkpointer=saver)


@pytest.mark.parametrize("table", CHECKPOINT_TABLES)
def test_setup_creates_langgraphs_own_tables(saver: Any, migrated_engine: Engine, table: str) -> None:
    """Created by PostgresSaver.setup(), not by Alembic — migration 0007
    deliberately does not own langgraph's schema."""
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}
        ).scalar_one()

    assert present


def test_building_the_checkpointer_twice_is_idempotent(paradedb_dsn: str, migrated_engine: Engine) -> None:
    """setup() runs on every build; a second build must not fail on tables the
    first one already created, because a reset_singletons() in any test does
    exactly this."""
    build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)
    build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)


def test_an_interrupted_run_returns_the_question_without_raising(toy_graph: Any) -> None:
    config = {"configurable": {"thread_id": "cp-interrupt"}}

    out = toy_graph.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    assert out["__interrupt__"][0].value == "which time range?"
    assert out["answer"] is None


def test_resuming_with_a_command_produces_the_answered_state(toy_graph: Any) -> None:
    config = {"configurable": {"thread_id": "cp-resume"}}
    toy_graph.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    out = toy_graph.invoke(Command(resume="last quarter"), config)

    assert "__interrupt__" not in out
    assert out["answer"] == "last quarter"
    assert out["question"] == "revenue"


def test_the_resumed_node_re_executes_from_its_first_line(toy_graph: Any) -> None:
    """LangGraph resumes a node by re-running it, not by continuing after the
    interrupt() call. Every node this phase adds is written to be idempotent
    under that, and this pins the behaviour so a langgraph upgrade that changed
    it would be caught here rather than in production."""
    config = {"configurable": {"thread_id": "cp-reexec"}}
    toy_graph.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    out = toy_graph.invoke(Command(resume="last quarter"), config)

    assert out["passes"] == 2


def test_a_second_saver_over_the_same_database_sees_the_checkpointed_state(
    paradedb_dsn: str, migrated_engine: Engine
) -> None:
    """The durability claim, stated as a test: a checkpoint written by one
    saver must resume through a DIFFERENT saver, because a resumed `genql
    query` is a brand-new process."""
    config = {"configurable": {"thread_id": "cp-cross-process"}}

    def build() -> Any:
        graph: StateGraph[ToyState] = StateGraph(ToyState)
        graph.add_node("gate", gate)
        graph.add_edge(START, "gate")
        graph.add_edge("gate", END)
        return graph.compile(
            checkpointer=build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)
        )

    build().invoke({"question": "revenue", "answer": None, "passes": 0}, config)
    out = build().invoke(Command(resume="last quarter"), config)

    assert out["answer"] == "last quarter"


def test_threads_do_not_see_each_others_state(toy_graph: Any) -> None:
    toy_graph.invoke(
        {"question": "revenue", "answer": None, "passes": 0},
        {"configurable": {"thread_id": "cp-a"}},
    )
    toy_graph.invoke(
        {"question": "headcount", "answer": None, "passes": 0},
        {"configurable": {"thread_id": "cp-b"}},
    )

    out = toy_graph.invoke(
        Command(resume="last quarter"), {"configurable": {"thread_id": "cp-a"}}
    )

    assert out["question"] == "revenue"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_postgres_checkpointer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.checkpoint'`

- [ ] **Step 3: Create the package marker**

Create `genql/infrastructure/checkpoint/__init__.py` as an empty file (matching `genql/infrastructure/query/__init__.py`):

```python
```

- [ ] **Step 4: Write the checkpointer builder**

Create `genql/infrastructure/checkpoint/postgres_checkpointer.py`:

```python
"""Builds LangGraph's PostgresSaver over GenQL's own database.

Three things here are not what they look like, and all three were checked
against the installed package rather than assumed.

PostgresSaver takes a live connection, not a DSN: its signature is
`PostgresSaver(conn, pipe=None, serde=None)` where conn is a psycopg
Connection[DictRow] or a ConnectionPool of them. `from_conn_string` exists but
is a CONTEXT MANAGER, so a container Singleton built from it would hand back a
saver whose connection had already closed.

The pool must produce dict rows. `row_factory=dict_row` is not a preference —
the saver indexes its result rows by column name and raises with the default
tuple factory. `autocommit=True` matches what langgraph's own documentation
requires for the saver's transaction handling.

setup() is called here rather than from cli/main.py. The spec suggested a
startup hook "the same way the engine provider already runs migrations
lazily", but the engine provider runs no migrations, so there is no such
precedent; and a startup hook would open a database connection for `genql
--help`. This function backs a providers.Singleton, so setup() runs exactly
once, lazily, the first time a turn actually needs the graph. It is idempotent,
so re-running it after reset_singletons() is safe.

The tables it creates — checkpoints, checkpoint_blobs, checkpoint_writes,
checkpoint_migrations — are langgraph's to own and evolve across its releases,
which is why migration 0007 deliberately does not declare them.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def build_checkpointer(dsn: str, max_size: int) -> PostgresSaver:
    pool = ConnectionPool(
        conninfo=dsn,
        max_size=max_size,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver
```

- [ ] **Step 5: Run the checkpointer test**

Run: `uv run pytest tests/integration/test_postgres_checkpointer.py -q`
Expected: PASS — 9 tests (three parametrised). Sandbox: "written but unrun".

- [ ] **Step 6: Confirm the layering still holds**

Run: `uv run lint-imports`
Expected: PASS. `psycopg_pool` and `langgraph.checkpoint.postgres` are imported only from `genql/infrastructure/`, which no contract restricts.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/infrastructure/checkpoint/__init__.py \
  genql/infrastructure/checkpoint/postgres_checkpointer.py \
  tests/integration/test_postgres_checkpointer.py
git commit -m "feat(checkpoint): build LangGraph's PostgresSaver over the semantic database"
```

---

### Task 10: Three new nodes, two new edges, and the interrupt loop

**Files:**
- Create: `genql/api/query_turn_nodes.py`, `tests/unit/test_query_turn_nodes.py`
- Modify: `genql/api/query_state.py`, `genql/api/query_graph.py`, `tests/unit/test_query_graph.py`, `tests/unit/test_query_nodes.py`
- Test: `tests/unit/test_query_turn_nodes.py`, `tests/unit/test_query_graph.py`, `tests/unit/test_query_nodes.py`

**Interfaces:**
- Consumes: `IntentClassifier`, `AmbiguityGate`, `DomainScoper` ports and `AmbiguityAssessment` (Task 1); the five Phase 5 node classes (unchanged)
- Produces: `QueryState` gains `thread_id: str`, `intent: str | None`, `ambiguity: AmbiguityAssessment | None`, `clarifications: tuple[tuple[str, str], ...]`; `initial_state(question, datasource_name, thread_id, domain_id=None) -> QueryState`; node classes `IntentClassificationNode(classifier)`, `AmbiguityGateNode(gate)`, `DomainScopingNode(scoper)`; routers `route_after_intent(state) -> str`, `route_after_gate(state) -> str`; `build_query_graph(intent_classification, ambiguity_gate, domain_scoping, schema_linking, planning, candidate_generation, static_validation, guarded_execution, *, checkpointer=None)`; `run_query(graph, question, datasource_name, thread_id, domain_id=None) -> dict[str, Any]`; `resume_query(graph, answer, thread_id) -> dict[str, Any]`

**Why `run_query` returns `dict[str, Any]` and not `QueryState`:** an interrupted invoke returns the state mapping plus langgraph's own `"__interrupt__"` key, which is not a `QueryState` field. Typing the return as `QueryState` and then reading `__interrupt__` off it would be a lie mypy would (correctly) reject. Task 11 narrows it back to a typed `TurnResponse`.

- [ ] **Step 1: Extend `QueryState`**

Modify `genql/api/query_state.py`.

Replace the module docstring's final paragraph — Phase 6 has now happened, so the file must stop claiming otherwise:

```python
"""The graph's shared state.

`violations` rather than a rendered message: the router needs the failure to
decide, the regeneration node needs it as feedback, and the CLI needs it in
the error it prints — a tuple of entities serves all three, a string serves
none of them well.

`clarifications` is what makes the interrupt loop terminate. Each pause
appends one (dimension, answer) pair, and the gate treats an answered
dimension as resolved, so the set of dimensions it can still ask about
strictly shrinks toward empty. It is also, literally, the parent spec's §13
"structured state, not appended chat text": what persists is which dimension
was settled and how, not a transcript.

`thread_id` is required rather than optional: every turn has one, including a
turn that finishes without pausing, because a follow-up question needs
something to attach to.
"""
```

Add the imports:

```python
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
```

Add the four fields to `QueryState`, placed before `links` so the state reads in pipeline order:

```python
class QueryState(TypedDict):
    question: str
    datasource_name: str
    thread_id: str
    domain_id: int | None
    intent: str | None
    ambiguity: AmbiguityAssessment | None
    clarifications: tuple[tuple[str, str], ...]
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    candidate: SqlCandidate | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]
```

And update the factory:

```python
def initial_state(
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> QueryState:
    return QueryState(
        question=question,
        datasource_name=datasource_name,
        thread_id=thread_id,
        domain_id=domain_id,
        intent=None,
        ambiguity=None,
        clarifications=(),
        links=None,
        plan=None,
        candidate=None,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
```

- [ ] **Step 2: Write the failing node tests**

Create `tests/unit/test_query_turn_nodes.py`:

```python
"""The three new adapters, with no provider, no database, and no graph.

AmbiguityGateNode is the one with real behaviour, and it is tested through a
fake `interrupt` rather than a real one: calling langgraph's interrupt() outside
a running graph raises, and what these tests need to assert is the node's
bookkeeping — that it appends exactly the dimension it asked about, paired with
exactly the answer it got back. The real interrupt is exercised by the graph
tests below and by the checkpointer integration test.
"""

from __future__ import annotations

import pytest

import genql.api.query_turn_nodes as turn_nodes
from genql.api.query_state import initial_state
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.errors import IntentClassificationError

VAGUE = AmbiguityAssessment(
    is_ambiguous=True,
    missing_dimension="time_range",
    clarifying_question="Over what time period?",
    applied_defaults=(("filter", "active_only"),),
)
CLEAR = AmbiguityAssessment(is_ambiguous=False, applied_defaults=(("filter", "active_only"),))


class FakeClassifier:
    def __init__(self, intent: str = "analytical_sql") -> None:
        self.intent = intent
        self.questions: list[str] = []

    def classify(self, question: str) -> str:
        self.questions.append(question)
        return self.intent


class RaisingClassifier:
    def classify(self, question: str) -> str:
        raise IntentClassificationError("bad label")


class FakeGate:
    """Returns each queued assessment in turn, recording what it was asked."""

    def __init__(self, *assessments: AmbiguityAssessment) -> None:
        self.queue = list(assessments)
        self.calls: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
    ) -> AmbiguityAssessment:
        self.calls.append((question, datasource_name, answers))
        return self.queue.pop(0) if self.queue else CLEAR


class FakeScoper:
    def __init__(self, domain_id: int | None) -> None:
        self.domain_id = domain_id
        self.calls: list[tuple[str, str]] = []

    def resolve(self, question: str, datasource_name: str) -> int | None:
        self.calls.append((question, datasource_name))
        return self.domain_id


@pytest.fixture()
def no_interrupt(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replaces langgraph's interrupt() with a recorder that returns an answer."""
    asked: list[str] = []

    def fake_interrupt(value: str) -> str:
        asked.append(value)
        return "last quarter"

    monkeypatch.setattr(turn_nodes, "interrupt", fake_interrupt)
    return asked


def test_intent_classification_writes_the_intent() -> None:
    classifier = FakeClassifier("metadata_question")

    update = IntentClassificationNode(classifier)(initial_state("q", "local", "t-1"))

    assert update == {"intent": "metadata_question"}
    assert classifier.questions == ["q"]


def test_intent_classification_does_not_swallow_its_typed_failure() -> None:
    with pytest.raises(IntentClassificationError):
        IntentClassificationNode(RaisingClassifier())(initial_state("q", "local", "t-1"))


def test_an_unambiguous_gate_writes_the_assessment_and_asks_nothing(
    no_interrupt: list[str],
) -> None:
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update == {"ambiguity": CLEAR}
    assert no_interrupt == []


def test_an_ambiguous_gate_interrupts_with_the_clarifying_question(
    no_interrupt: list[str],
) -> None:
    AmbiguityGateNode(FakeGate(VAGUE))(initial_state("q", "local", "t-1"))

    assert no_interrupt == ["Over what time period?"]


def test_the_answer_is_recorded_against_the_dimension_that_was_asked_about(
    no_interrupt: list[str],
) -> None:
    update = AmbiguityGateNode(FakeGate(VAGUE))(initial_state("q", "local", "t-1"))

    assert update["clarifications"] == (("time_range", "last quarter"),)
    assert update["ambiguity"] == VAGUE


def test_clarifications_accumulate_rather_than_replace(no_interrupt: list[str]) -> None:
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("entity", "stores"),)

    update = AmbiguityGateNode(FakeGate(VAGUE))(state)

    assert update["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )


def test_the_gate_is_given_the_answers_collected_so_far(no_interrupt: list[str]) -> None:
    gate = FakeGate(VAGUE)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("entity", "stores"),)

    AmbiguityGateNode(gate)(state)

    assert gate.calls == [("q", "local", (("entity", "stores"),))]


def test_an_ambiguous_assessment_with_no_question_never_interrupts(
    no_interrupt: list[str],
) -> None:
    """Defence in depth: AmbiguityGateService already rejects this, but a node
    that called interrupt(None) would pause the turn with nothing to show the
    user and no way to answer."""
    broken = AmbiguityAssessment(is_ambiguous=True, missing_dimension="grain")

    update = AmbiguityGateNode(FakeGate(broken))(initial_state("q", "local", "t-1"))

    assert no_interrupt == []
    assert update == {"ambiguity": broken}


def test_domain_scoping_writes_the_resolved_id() -> None:
    scoper = FakeScoper(7)

    update = DomainScopingNode(scoper)(initial_state("q", "local", "t-1"))

    assert update == {"domain_id": 7}
    assert scoper.calls == [("q", "local")]


def test_domain_scoping_writes_none_when_nothing_resolves() -> None:
    update = DomainScopingNode(FakeScoper(None))(initial_state("q", "local", "t-1"))

    assert update == {"domain_id": None}


def test_an_explicit_domain_id_is_never_overwritten() -> None:
    """--domain-id is the manual override for a mis-scoped question, per the
    spec's §11 mitigation. A stage that recomputed over it would delete the
    override."""
    scoper = FakeScoper(7)

    update = DomainScopingNode(scoper)(initial_state("q", "local", "t-1", domain_id=42))

    assert update == {}
    assert scoper.calls == []
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_query_turn_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_turn_nodes'`

- [ ] **Step 4: Write the three nodes**

Create `genql/api/query_turn_nodes.py`:

```python
"""Three adapters for the three stages prepended to Phase 5's graph.

They live in their own file rather than joining query_nodes.py for two
reasons: query_nodes.py is already the five generation-path adapters and one
file per responsibility is the house rule, and this is the only module in
genql/api/ that calls interrupt(), which is worth being able to find.

AmbiguityGateNode is the one that carries real behaviour, and it is written to
be idempotent under re-execution. LangGraph resumes an interrupted node by
running it AGAIN from its first line — interrupt() raises on the first pass and
returns the resume value on the second — so everything before the interrupt
call runs twice. Here that is one `assess` call whose result is overwritten,
which costs one model call and changes nothing. Anything with a side effect
would have to move after the interrupt.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from genql.api.query_state import QueryState
from genql.domain.ports.ambiguity_gate import AmbiguityGate
from genql.domain.ports.domain_scoper import DomainScoper
from genql.domain.ports.intent_classifier import IntentClassifier


class IntentClassificationNode:
    def __init__(self, classifier: IntentClassifier) -> None:
        self._classifier = classifier

    def __call__(self, state: QueryState) -> dict[str, Any]:
        return {"intent": self._classifier.classify(state["question"])}


class AmbiguityGateNode:
    def __init__(self, gate: AmbiguityGate) -> None:
        self._gate = gate

    def __call__(self, state: QueryState) -> dict[str, Any]:
        assessment = self._gate.assess(
            state["question"], state["datasource_name"], state["clarifications"]
        )
        if not assessment.is_ambiguous:
            return {"ambiguity": assessment}
        # Both guards matter. Without a dimension there is nothing to record
        # the answer against, so the loop would not shrink and would not
        # terminate; without a question there is nothing to show the user, so
        # the turn would pause with no way to resume it. AmbiguityGateService
        # already refuses to produce either, and this refuses to act on one.
        dimension = assessment.missing_dimension
        question = assessment.clarifying_question
        if dimension is None or not question:
            return {"ambiguity": assessment}
        answer = interrupt(question)
        return {
            "ambiguity": assessment,
            "clarifications": state["clarifications"] + ((dimension, str(answer)),),
        }


class DomainScopingNode:
    def __init__(self, scoper: DomainScoper) -> None:
        self._scoper = scoper

    def __call__(self, state: QueryState) -> dict[str, Any]:
        # An explicit --domain-id wins: it is the documented manual override
        # for a question this heuristic would scope wrongly.
        if state["domain_id"] is not None:
            return {}
        return {
            "domain_id": self._scoper.resolve(state["question"], state["datasource_name"])
        }
```

- [ ] **Step 5: Run to verify the node tests pass**

Run: `uv run pytest tests/unit/test_query_turn_nodes.py -q`
Expected: PASS — 11 tests

- [ ] **Step 6: Write the failing graph tests**

Modify `tests/unit/test_query_graph.py`.

Extend the module docstring:

```python
"""The wiring, proven with fake nodes so no ChatProvider, database, or
retriever is involved. Four generation paths matter: clean, exactly one retry,
a second failure that stops rather than looping, and an unrepairable violation
that never spends the retry at all.

Phase 6 adds three more: a non-analytical intent that reaches END without
touching retrieval, an ambiguous question that pauses and then resumes to a
finished answer, and a gate that asks about a second dimension after the first
is answered and still terminates. Those three need a checkpointer, so they use
InMemorySaver — the Postgres saver is proven separately in
tests/integration/test_postgres_checkpointer.py, and what these assert is the
GRAPH's routing, which is saver-independent.
"""
```

Add imports:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from genql.api.query_graph import (
    build_query_graph,
    resume_query,
    route_after_gate,
    route_after_intent,
    route_after_validation,
    run_query,
)
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
```

Add fake nodes for the three new stages, beside the existing `link_node` / `plan_node`:

```python
CLEAR = AmbiguityAssessment(is_ambiguous=False)


def analytical_intent(state: dict[str, Any]) -> dict[str, Any]:
    return {"intent": "analytical_sql"}


def clear_gate(state: dict[str, Any]) -> dict[str, Any]:
    return {"ambiguity": CLEAR}


def no_scope(state: dict[str, Any]) -> dict[str, Any]:
    return {"domain_id": None}


def build(
    validate: Any,
    generate: Any,
    intent: Any = analytical_intent,
    gate: Any = clear_gate,
    scope: Any = no_scope,
    checkpointer: Any = None,
) -> Any:
    """One helper so the seven graph tests below differ only where they mean to."""
    return build_query_graph(
        intent,
        gate,
        scope,
        link_node,
        plan_node,
        generate,
        validate,
        execute_node,
        checkpointer=checkpointer,
    )
```

There is exactly one existing `build_query_graph(...)` call site — inside the `_graph` helper. Rewrite that helper to delegate:

```python
def _graph(
    failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS
) -> tuple[Any, GenerateNode]:
    generate = GenerateNode()
    graph = build(ValidateNode(failures, violations), generate)
    return graph, generate
```

Then update the rest of the file mechanically: every `run_query(graph, "q", "local")` becomes `run_query(graph, "q", "local", "t-1")`, and every `initial_state("q", "local")` becomes `initial_state("q", "local", "t-1")` (including `initial_state("q", "local", domain_id=3)` → `initial_state("q", "local", "t-1", domain_id=3)`). A checkpointer-less graph ignores the thread_id config, so the four Phase 5 paths are unchanged in behaviour.

Then append the Phase 6 tests:

```python
def test_a_non_analytical_intent_reaches_the_end_without_linking() -> None:
    linked: list[str] = []

    def recording_link(state: dict[str, Any]) -> dict[str, Any]:
        linked.append(state["question"])
        return {"links": (LINK,)}

    graph = build_query_graph(
        lambda state: {"intent": "non_sql"},
        clear_gate,
        no_scope,
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        execute_node,
    )

    final = run_query(graph, "hello there", "local", "t-intent")

    assert final["intent"] == "non_sql"
    assert final["validated_sql"] is None
    assert final["result"] is None
    assert linked == []


def test_route_after_intent_sends_only_analytical_sql_onward() -> None:
    from langgraph.graph import END

    from genql.api.query_graph import AMBIGUITY_GATE

    assert route_after_intent({"intent": "analytical_sql"}) == AMBIGUITY_GATE
    for intent in ("metadata_question", "followup", "non_sql", None):
        assert route_after_intent({"intent": intent}) == END


def test_route_after_gate_loops_back_while_ambiguous() -> None:
    from genql.api.query_graph import AMBIGUITY_GATE, DOMAIN_SCOPING

    ambiguous = AmbiguityAssessment(
        is_ambiguous=True, missing_dimension="grain", clarifying_question="At what grain?"
    )

    assert route_after_gate({"ambiguity": ambiguous}) == AMBIGUITY_GATE
    assert route_after_gate({"ambiguity": CLEAR}) == DOMAIN_SCOPING
    assert route_after_gate({"ambiguity": None}) == DOMAIN_SCOPING


def test_an_ambiguous_question_pauses_and_then_resumes_to_an_answer() -> None:
    """The whole phase, as one test: pause, resume, finish."""
    from langgraph.types import interrupt as real_interrupt

    class Gate:
        def __init__(self) -> None:
            self.passes = 0

        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            self.passes += 1
            if state["clarifications"]:
                return {"ambiguity": CLEAR}
            answer = real_interrupt("Over what time period?")
            return {
                "ambiguity": AmbiguityAssessment(
                    is_ambiguous=True,
                    missing_dimension="time_range",
                    clarifying_question="Over what time period?",
                ),
                "clarifications": (("time_range", str(answer)),),
            }

    graph = build(ValidateNode(0), GenerateNode(), gate=Gate(), checkpointer=InMemorySaver())

    paused = run_query(graph, "show me revenue", "local", "t-pause")
    assert paused["__interrupt__"][0].value == "Over what time period?"
    assert paused["validated_sql"] is None

    finished = resume_query(graph, "last quarter", "t-pause")

    assert "__interrupt__" not in finished
    assert finished["clarifications"] == (("time_range", "last quarter"),)
    assert finished["validated_sql"] == "SELECT 1 LIMIT 1"
    assert finished["result"] == RESULT


def test_two_dimensions_take_two_rounds_and_then_terminate() -> None:
    """The termination claim at the graph level: the loop-back edge does not
    spin, because each answered dimension removes itself from the gate's
    remaining set."""
    from langgraph.types import interrupt as real_interrupt

    remaining = ["entity", "time_range"]

    def gate(state: dict[str, Any]) -> dict[str, Any]:
        answered = {dimension for dimension, _ in state["clarifications"]}
        pending = [d for d in remaining if d not in answered]
        if not pending:
            return {"ambiguity": CLEAR}
        dimension = pending[0]
        answer = real_interrupt(f"Which {dimension}?")
        return {
            "ambiguity": AmbiguityAssessment(
                is_ambiguous=True,
                missing_dimension=dimension,
                clarifying_question=f"Which {dimension}?",
            ),
            "clarifications": state["clarifications"] + ((dimension, str(answer)),),
        }

    graph = build(ValidateNode(0), GenerateNode(), gate=gate, checkpointer=InMemorySaver())

    first = run_query(graph, "revenue", "local", "t-two")
    assert first["__interrupt__"][0].value == "Which entity?"

    second = resume_query(graph, "stores", "t-two")
    assert second["__interrupt__"][0].value == "Which time_range?"

    third = resume_query(graph, "last quarter", "t-two")

    assert "__interrupt__" not in third
    assert third["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )
    assert third["result"] == RESULT


def test_two_threads_pause_independently() -> None:
    from langgraph.types import interrupt as real_interrupt

    def gate(state: dict[str, Any]) -> dict[str, Any]:
        if state["clarifications"]:
            return {"ambiguity": CLEAR}
        answer = real_interrupt("Over what time period?")
        return {
            "ambiguity": CLEAR,
            "clarifications": (("time_range", str(answer)),),
        }

    graph = build(ValidateNode(0), GenerateNode(), gate=gate, checkpointer=InMemorySaver())

    run_query(graph, "revenue", "local", "t-x")
    run_query(graph, "headcount", "local", "t-y")

    finished = resume_query(graph, "last quarter", "t-x")

    assert finished["question"] == "revenue"


def test_an_explicit_domain_id_survives_to_schema_linking() -> None:
    seen: list[int | None] = []

    def recording_link(state: dict[str, Any]) -> dict[str, Any]:
        seen.append(state["domain_id"])
        return {"links": (LINK,)}

    graph = build_query_graph(
        analytical_intent,
        clear_gate,
        lambda state: {},
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        execute_node,
    )

    run_query(graph, "q", "local", "t-domain", domain_id=42)

    assert seen == [42]
```

`execute_node`, `RESULT`, `LINK`, `GenerateNode`, and `ValidateNode` are all already defined in this file by Phase 5 — reuse them, do not redefine them.

`tests/unit/test_query_nodes.py` also calls `initial_state("q", "local")` in nine places and must get the same `"t-1"` third argument. It needs no other change: none of Phase 5's five nodes read the new fields.

- [ ] **Step 7: Run to verify they fail**

Run: `uv run pytest tests/unit/test_query_graph.py -q`
Expected: FAIL — `ImportError: cannot import name 'route_after_intent' from 'genql.api.query_graph'`

- [ ] **Step 8: Extend the graph**

Modify `genql/api/query_graph.py`.

Extend the module docstring's second paragraph, which currently claims there is no checkpointer:

```python
"""The online pipeline as a LangGraph StateGraph — the only file in the
project that builds one.

Phase 6 gives it a checkpointer and an interrupt. `checkpointer` is optional
so that a graph can still be built for a test that only cares about routing;
a graph compiled without one cannot pause, and run_query's thread_id is then
inert.

Three conditional edges now. Out of intent_classification: only
`analytical_sql` proceeds, and the other three intents reach END with the
intent recorded — cheap, and it keeps questions the downstream stages were
never designed for away from them. Out of ambiguity_gate: an ambiguous
assessment routes back to ambiguity_gate itself, so the node re-runs after the
resumed answer lands in state. Out of static_validation: Phase 5's retry edge,
unchanged.

The gate self-loop provably terminates without a retry counter. Every pass
either finds nothing left to ask (AMBIGUITY_DIMENSIONS is a fixed six-element
tuple, and a dimension that has been answered or defaulted is never asked
again) or removes exactly one dimension from that set. Phase 5's guardrail loop
needed a counter because guardrail rules do not shrink; this one does.

The graph does not catch or re-wrap — the CLI does.
"""
```

Add imports:

```python
from langgraph.types import Command
```

Add the two new stage-name constants beside the existing five:

```python
INTENT_CLASSIFICATION = "intent_classification"
AMBIGUITY_GATE = "ambiguity_gate"
DOMAIN_SCOPING = "domain_scoping"
```

Add the two routers above `route_after_validation`:

```python
def route_after_intent(state: QueryState) -> str:
    """Only analytical_sql proceeds.

    A missing intent routes to END too, not to the gate: that can only happen
    if the classification node was skipped, and continuing into retrieval on an
    unclassified question is exactly what this stage exists to prevent.
    """
    return AMBIGUITY_GATE if state["intent"] == "analytical_sql" else END


def route_after_gate(state: QueryState) -> str:
    """Ambiguous, so re-assess after the answer; otherwise proceed to scoping.

    The loop-back target is ambiguity_gate itself. On re-entry the node sees a
    `clarifications` tuple one pair longer than last time, so the gate has one
    fewer dimension it can ask about.
    """
    ambiguity = state["ambiguity"]
    if ambiguity is not None and ambiguity.is_ambiguous:
        return AMBIGUITY_GATE
    return DOMAIN_SCOPING
```

Extend `build_query_graph`:

```python
def build_query_graph(
    intent_classification: NodeFn,
    ambiguity_gate: NodeFn,
    domain_scoping: NodeFn,
    schema_linking: NodeFn,
    planning: NodeFn,
    candidate_generation: NodeFn,
    static_validation: NodeFn,
    guarded_execution: NodeFn,
    *,
    checkpointer: Any = None,
) -> Any:
    graph: StateGraph[QueryState] = StateGraph(QueryState)
    graph.add_node(INTENT_CLASSIFICATION, intent_classification)
    graph.add_node(AMBIGUITY_GATE, ambiguity_gate)
    graph.add_node(DOMAIN_SCOPING, domain_scoping)
    graph.add_node(SCHEMA_LINKING, schema_linking)
    graph.add_node(PLANNING, planning)
    graph.add_node(CANDIDATE_GENERATION, candidate_generation)
    graph.add_node(STATIC_VALIDATION, static_validation)
    graph.add_node(GUARDED_EXECUTION, guarded_execution)

    graph.add_edge(START, INTENT_CLASSIFICATION)
    graph.add_conditional_edges(
        INTENT_CLASSIFICATION,
        route_after_intent,
        {AMBIGUITY_GATE: AMBIGUITY_GATE, END: END},
    )
    graph.add_conditional_edges(
        AMBIGUITY_GATE,
        route_after_gate,
        {AMBIGUITY_GATE: AMBIGUITY_GATE, DOMAIN_SCOPING: DOMAIN_SCOPING},
    )
    graph.add_edge(DOMAIN_SCOPING, SCHEMA_LINKING)
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
    return graph.compile(checkpointer=checkpointer)
```

Replace `run_query` and add `resume_query`:

```python
def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def run_query(
    graph: Any,
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> dict[str, Any]:
    """Start a turn.

    Returns the raw mapping rather than QueryState: an interrupted run carries
    langgraph's own `__interrupt__` key, which is not a QueryState field, and
    typing the return as QueryState would make reading it a lie. query_turn.py
    narrows this into a TurnResponse.
    """
    return cast(
        dict[str, Any],
        graph.invoke(
            initial_state(question, datasource_name, thread_id, domain_id),
            _config(thread_id),
        ),
    )


def resume_query(graph: Any, answer: str, thread_id: str) -> dict[str, Any]:
    """Answer the question a paused turn asked.

    Command(resume=...) hands the value back to the interrupt() call site that
    raised, so the gate node re-runs with the answer in hand. Intent
    classification does not run again — it already ran on the original
    question, and the checkpoint resumes at the paused node, not at START.
    """
    return cast(dict[str, Any], graph.invoke(Command(resume=answer), _config(thread_id)))
```

- [ ] **Step 9: Run the graph tests**

Run: `uv run pytest tests/unit/test_query_graph.py tests/unit/test_query_nodes.py -q`
Expected: PASS — the four Phase 5 paths plus the seven new ones, and the five Phase 5 node tests unchanged

- [ ] **Step 10: Confirm both api files are under the length cap**

Run: `uv run python scripts/check_file_length.py genql/api/query_graph.py genql/api/query_turn_nodes.py genql/api/query_state.py`
Expected: exit 0, no output

- [ ] **Step 11: Note the one temporarily-red suite**

`tests/unit/test_query_cli.py` monkeypatches `run_query` with a four-argument fake and will fail on the new `thread_id` parameter. Task 11 rewrites that file. Run it now to confirm the failure is exactly that and nothing else:

Run: `uv run pytest tests/unit/test_query_cli.py -q`
Expected: FAIL — `TypeError: fake_run_query() takes 4 positional arguments but 5 were given`. This is the one place in the plan where a task boundary is red, and it is red for exactly one file, for exactly one reason, fixed by the very next task. Tasks 10 and 11 are one batch (see Execution Batches) precisely so that boundary is never committed as green-looking.

- [ ] **Step 12: Local checks except the CLI suite**

Run: `uv run pytest tests/unit -q --deselect tests/unit/test_query_cli.py && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 13: Commit**

```bash
git add genql/api/query_state.py genql/api/query_graph.py genql/api/query_turn_nodes.py \
  tests/unit/test_query_turn_nodes.py tests/unit/test_query_graph.py \
  tests/unit/test_query_nodes.py
git commit -m "feat(api): prepend intent, ambiguity gate, and domain scoping to the graph"
```

---

### Task 11: `TurnResponse` assembly and `genql query --thread-id`

**Files:**
- Create: `genql/api/query_turn.py`, `tests/unit/test_query_turn.py`
- Modify: `genql/cli/commands/query.py`, `tests/unit/test_query_cli.py`
- Test: `tests/unit/test_query_turn.py`, `tests/unit/test_query_cli.py`

**Interfaces:**
- Consumes: `run_query` / `resume_query` (Task 10); `TurnResponse` (Task 1); `ThreadLockFactory` port (Task 1); `Container.query_graph()` and `Container.thread_lock_factory()` (the provider lands in Task 12 — the CLI is written against it here and only becomes runnable then)
- Produces: `new_thread_id() -> str`; `start_turn(graph, locks, question, datasource_name, domain_id=None, thread_id=None) -> TurnResponse`; `resume_turn(graph, locks, answer, thread_id) -> TurnResponse`; CLI `genql query "<text>" --datasource NAME [--domain-id N] [--thread-id ID]`

- [ ] **Step 1: Write the failing turn tests**

Create `tests/unit/test_query_turn.py`:

```python
"""Turning what the graph returned into what the CLI prints.

Three shapes come back from an invoke: a mapping carrying `__interrupt__` (the
turn paused), a mapping whose intent short-circuited it (no SQL was ever
attempted), and a finished mapping. The lock is asserted here rather than in the
CLI test because it is the api layer that holds it, and because "released even
when the graph raises" is exactly the behaviour a `finally` gets wrong.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pytest

from genql.api.query_state import initial_state
from genql.api.query_turn import new_thread_id, resume_turn, start_turn
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import PlanningError

RESULT = ExecutionResult(columns=("n",), rows=((7,),), row_count=1, truncated=False)


class Interrupt:
    def __init__(self, value: str) -> None:
        self.value = value
        self.id = "i-1"


class FakeGraph:
    """Records every invoke and returns whatever it was primed with."""

    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.invocations: list[tuple[Any, Any]] = []

    def invoke(self, payload: Any, config: Any = None) -> Any:
        self.invocations.append((payload, config))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeLock:
    def __init__(self, log: list[str], thread_id: str) -> None:
        self.log = log
        self.thread_id = thread_id

    def __enter__(self) -> None:
        self.log.append(f"acquire:{self.thread_id}")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.log.append(f"release:{self.thread_id}")


class FakeLocks:
    def __init__(self) -> None:
        self.log: list[str] = []

    def for_thread(self, thread_id: str) -> FakeLock:
        return FakeLock(self.log, thread_id)


def finished_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "analytical_sql"
    state["ambiguity"] = AmbiguityAssessment(
        is_ambiguous=False, applied_defaults=(("time_range", "default_period"),)
    )
    state["validated_sql"] = "SELECT 7 LIMIT 1"
    state["result"] = RESULT
    return state


def paused_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "analytical_sql"
    state["ambiguity"] = AmbiguityAssessment(
        is_ambiguous=True,
        missing_dimension="time_range",
        clarifying_question="Over what time period?",
        applied_defaults=(("filter", "active_only"),),
    )
    state["__interrupt__"] = [Interrupt("Over what time period?")]
    return state


def short_circuited_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "non_sql"
    return state


def test_a_generated_thread_id_is_unique_and_non_empty() -> None:
    assert new_thread_id() != new_thread_id()
    assert new_thread_id()


def test_a_finished_turn_carries_sql_rows_and_the_applied_defaults() -> None:
    response = start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local")

    assert response.clarifying_question is None
    assert response.intent is None
    assert response.validated_sql == "SELECT 7 LIMIT 1"
    assert response.result == RESULT
    assert response.applied_defaults == (("time_range", "default_period"),)


def test_a_paused_turn_carries_the_question_and_the_thread_id() -> None:
    graph = FakeGraph(paused_state())

    response = start_turn(graph, FakeLocks(), "q", "local", thread_id="t-9")

    assert response.thread_id == "t-9"
    assert response.clarifying_question == "Over what time period?"
    assert response.validated_sql is None
    assert response.result is None
    assert response.applied_defaults == (("filter", "active_only"),)


def test_a_short_circuited_turn_reports_only_its_intent() -> None:
    response = start_turn(FakeGraph(short_circuited_state()), FakeLocks(), "q", "local")

    assert response.intent == "non_sql"
    assert response.clarifying_question is None
    assert response.validated_sql is None


def test_a_finished_analytical_turn_does_not_report_an_intent() -> None:
    """intent is set only on a short circuit, per the spec's §2 — reporting
    'analytical_sql' beside real rows would be noise on every successful turn."""
    response = start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local")

    assert response.intent is None


def test_a_generated_thread_id_is_used_when_none_is_given() -> None:
    graph = FakeGraph(paused_state())

    response = start_turn(graph, FakeLocks(), "q", "local")

    assert response.thread_id
    _, config = graph.invocations[0]
    assert config == {"configurable": {"thread_id": response.thread_id}}


def test_the_question_datasource_and_domain_reach_the_graph() -> None:
    graph = FakeGraph(finished_state())

    start_turn(graph, FakeLocks(), "how many stores", "wh2", domain_id=42, thread_id="t-3")

    payload, _ = graph.invocations[0]
    assert payload["question"] == "how many stores"
    assert payload["datasource_name"] == "wh2"
    assert payload["domain_id"] == 42
    assert payload["thread_id"] == "t-3"


def test_resuming_sends_a_command_carrying_the_answer() -> None:
    graph = FakeGraph(finished_state())

    response = resume_turn(graph, FakeLocks(), "last quarter", "t-7")

    payload, config = graph.invocations[0]
    assert payload.resume == "last quarter"
    assert config == {"configurable": {"thread_id": "t-7"}}
    assert response.thread_id == "t-7"


def test_a_resumed_turn_can_pause_again() -> None:
    response = resume_turn(FakeGraph(paused_state()), FakeLocks(), "stores", "t-7")

    assert response.clarifying_question == "Over what time period?"
    assert response.thread_id == "t-7"


def test_the_lock_is_taken_for_the_thread_and_released(monkeypatch: pytest.MonkeyPatch) -> None:
    locks = FakeLocks()

    start_turn(FakeGraph(finished_state()), locks, "q", "local", thread_id="t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_lock_is_taken_on_resume_too() -> None:
    locks = FakeLocks()

    resume_turn(FakeGraph(finished_state()), locks, "last quarter", "t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_lock_is_released_when_the_graph_raises() -> None:
    locks = FakeLocks()

    with pytest.raises(PlanningError):
        start_turn(FakeGraph(PlanningError("no links")), locks, "q", "local", thread_id="t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_typed_failure_is_not_swallowed() -> None:
    with pytest.raises(PlanningError):
        resume_turn(FakeGraph(PlanningError("no links")), FakeLocks(), "a", "t-5")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_turn.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_turn'`

- [ ] **Step 3: Write the turn module**

Create `genql/api/query_turn.py`:

```python
"""One turn, start to finish or start to pause.

This is where the graph's raw output mapping becomes a typed TurnResponse, and
it is the only place that knows an interrupted invoke returns a
`__interrupt__` key rather than raising. Keeping that knowledge in one file
means a langgraph release that changed the convention breaks here, once.

The lock wraps the invoke, not the whole command, and it is a `with` block so
release survives an exception, an interrupt, and a clean finish alike — one
thread, one in-flight turn, per the parent spec's §13.

A thread id is generated when the caller does not supply one, because even a
turn that finishes without pausing needs one for a follow-up to attach to.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from genql.api.query_graph import resume_query, run_query
from genql.api.query_state import QueryState
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.thread_lock import ThreadLockFactory


def new_thread_id() -> str:
    return f"t-{uuid.uuid4().hex}"


def _applied_defaults(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ambiguity = raw.get("ambiguity")
    return () if ambiguity is None else ambiguity.applied_defaults


def _to_response(thread_id: str, raw: dict[str, Any]) -> TurnResponse:
    interrupts = raw.get("__interrupt__") or ()
    if interrupts:
        return TurnResponse(
            thread_id=thread_id,
            clarifying_question=str(interrupts[0].value),
            applied_defaults=_applied_defaults(raw),
        )
    state = cast(QueryState, raw)
    # An intent is reported only when it stopped the turn. On a finished
    # analytical turn it would be noise beside the rows.
    short_circuited = state["validated_sql"] is None and state["result"] is None
    return TurnResponse(
        thread_id=thread_id,
        intent=state["intent"] if short_circuited else None,
        validated_sql=state["validated_sql"],
        result=state["result"],
        applied_defaults=_applied_defaults(raw),
    )


def start_turn(
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
) -> TurnResponse:
    resolved = thread_id or new_thread_id()
    with locks.for_thread(resolved):
        raw = run_query(graph, question, datasource_name, resolved, domain_id)
    return _to_response(resolved, raw)


def resume_turn(
    graph: Any, locks: ThreadLockFactory, answer: str, thread_id: str
) -> TurnResponse:
    with locks.for_thread(thread_id):
        raw = resume_query(graph, answer, thread_id)
    return _to_response(thread_id, raw)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_query_turn.py -q`
Expected: PASS — 13 tests

- [ ] **Step 5: Write the failing CLI tests**

Replace `tests/unit/test_query_cli.py` entirely — the file's fakes are built around the removed `run_query` signature, and patching them piecemeal would leave a test that reads as if Phase 5's shape were still current:

```python
"""`genql query`'s three jobs: render a finished turn, render a paused one, and
turn any typed failure into one line plus exit code 1 rather than a traceback.

The container, the graph, and the turn functions are all stubbed — this asserts
the command's presentation and its error boundary, not the pipeline, which the
node, graph, and turn tests already cover.

A paused turn exits 0. That is the single most important assertion in this
file: a clarifying question is the system working, and a non-zero exit would
make every shell caller treat it as breakage.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import genql.cli.commands.query as query_command
from genql.cli.main import app
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import ExecutionError, SchemaLinkingError

runner = CliRunner()


class StubContainer:
    def query_graph(self) -> object:
        return object()

    def thread_lock_factory(self) -> object:
        return object()


def _install(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> dict[str, Any]:
    """Stubs both turn entry points and records which one was called."""
    monkeypatch.setattr(query_command, "Container", StubContainer)
    seen: dict[str, Any] = {}

    def fake_start(
        graph: Any,
        locks: Any,
        question: str,
        datasource_name: str,
        domain_id: int | None = None,
        thread_id: str | None = None,
    ) -> TurnResponse:
        seen["call"] = "start"
        seen["args"] = (question, datasource_name, domain_id, thread_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def fake_resume(graph: Any, locks: Any, answer: str, thread_id: str) -> TurnResponse:
        seen["call"] = "resume"
        seen["args"] = (answer, thread_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(query_command, "start_turn", fake_start)
    monkeypatch.setattr(query_command, "resume_turn", fake_resume)
    return seen


def finished(truncated: bool = False) -> TurnResponse:
    return TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT count(*) FROM shop.orders LIMIT 1",
        result=ExecutionResult(
            columns=("count", "note"), rows=((7, None),), row_count=1, truncated=truncated
        ),
        applied_defaults=(("time_range", "default_period"),),
    )


def test_a_finished_turn_prints_the_sql_and_the_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert result.exit_code == 0
    assert "SELECT count(*) FROM shop.orders LIMIT 1" in result.stdout
    assert "count | note" in result.stdout
    assert "7 |" in result.stdout
    assert "(1 rows)" in result.stdout


def test_a_finished_turn_reports_the_defaults_it_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default the user did not ask for must be visible, or the answer is
    silently about a different question than the one they asked."""
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "time_range" in result.stdout
    assert "default_period" in result.stdout


def test_a_truncated_result_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, finished(truncated=True))

    result = runner.invoke(app, ["query", "q", "--datasource", "local"])

    assert "truncated" in result.stdout


def test_a_paused_turn_prints_the_question_the_thread_id_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        TurnResponse(
            thread_id="t-abc", clarifying_question="Over what time period?"
        ),
    )

    result = runner.invoke(app, ["query", "show me revenue", "--datasource", "local"])

    assert result.exit_code == 0
    assert "Over what time period?" in result.stdout
    assert "t-abc" in result.stdout
    assert "--thread-id" in result.stdout


def test_a_non_analytical_question_is_explained_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, TurnResponse(thread_id="t-1", intent="non_sql"))

    result = runner.invoke(app, ["query", "hello there", "--datasource", "local"])

    assert result.exit_code == 0
    assert "non_sql" in result.stdout


def test_a_thread_id_routes_to_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install(monkeypatch, finished())

    runner.invoke(
        app, ["query", "last quarter", "--datasource", "local", "--thread-id", "t-abc"]
    )

    assert seen["call"] == "resume"
    assert seen["args"] == ("last quarter", "t-abc")


def test_no_thread_id_routes_to_start_with_the_domain_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install(monkeypatch, finished())

    runner.invoke(
        app, ["query", "how many orders", "--datasource", "local", "--domain-id", "42"]
    )

    assert seen["call"] == "start"
    assert seen["args"] == ("how many orders", "local", 42, None)


def test_a_typed_failure_is_one_line_and_exit_code_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, SchemaLinkingError("nothing matched"))

    result = runner.invoke(app, ["query", "q", "--datasource", "local"])

    assert result.exit_code == 1
    assert "nothing matched" in result.stdout
    assert "Traceback" not in result.stdout


def test_a_failure_during_resume_is_also_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, ExecutionError("statement timeout"))

    result = runner.invoke(
        app, ["query", "last quarter", "--datasource", "local", "--thread-id", "t-abc"]
    )

    assert result.exit_code == 1
    assert "statement timeout" in result.stdout
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_cli.py -q`
Expected: FAIL — `AttributeError: <module 'genql.cli.commands.query'> has no attribute 'start_turn'`

- [ ] **Step 7: Rewrite the CLI command**

Replace `genql/cli/commands/query.py` entirely:

```python
"""`genql query` — one turn of the online pipeline.

Three outcomes, three renderings, two exit codes. A finished turn prints its
SQL and rows; a paused turn prints its clarifying question plus the thread id
to resume with; a question the system does not answer prints why. Only a typed
failure exits non-zero — a paused turn is the system working, and a non-zero
exit would make every shell caller treat a clarifying question as breakage.

Every typed failure from the graph is caught here and printed as one line,
matching `genql discover`'s convention. The graph itself never catches: a stage
failure is a typed error all the way up, and this is the only layer that knows
it is talking to a human.
"""

from __future__ import annotations

import typer

from genql.api.query_turn import resume_turn, start_turn
from genql.composition_root import Container
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import GenqlError


def _render_defaults(response: TurnResponse) -> None:
    if not response.applied_defaults:
        return
    typer.echo("Applied defaults:")
    for dimension, rule_name in response.applied_defaults:
        typer.echo(f"  {dimension}: {rule_name}")
    typer.echo("")


def _render_paused(response: TurnResponse) -> None:
    typer.echo(response.clarifying_question or "")
    typer.echo("")
    _render_defaults(response)
    typer.echo(f"thread: {response.thread_id}")
    typer.echo(
        f'Answer with: genql query "<answer>" --thread-id {response.thread_id}'
    )


def _render_intent(response: TurnResponse) -> None:
    typer.echo(
        f"This looks like a {response.intent} question, not an analytical one. "
        "GenQL answers questions about the data in a registered warehouse; ask "
        "for numbers, totals, or rows and it will generate SQL for them."
    )
    typer.echo(f"thread: {response.thread_id}")


def _render_finished(response: TurnResponse) -> None:
    _render_defaults(response)
    typer.echo("SQL:")
    typer.echo(response.validated_sql or "")
    typer.echo("")

    result = response.result
    if result is None:
        typer.echo("no rows returned")
    else:
        typer.echo(" | ".join(result.columns))
        for row in result.rows:
            typer.echo(" | ".join("" if value is None else str(value) for value in row))
        typer.echo(f"({result.row_count} rows)")
        if result.truncated:
            typer.echo(
                "truncated at the configured row cap; refine the question for the full set"
            )
    typer.echo(f"thread: {response.thread_id}")


def _render(response: TurnResponse) -> None:
    if response.clarifying_question is not None:
        _render_paused(response)
    elif response.intent is not None:
        _render_intent(response)
    else:
        _render_finished(response)


def query(
    question: str = typer.Argument(
        ..., help="The analytical question, or the answer to a clarifying question"
    ),
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    domain_id: int | None = typer.Option(None, "--domain-id", help="Restrict to one domain"),
    thread_id: str | None = typer.Option(
        None, "--thread-id", help="Resume a paused turn instead of starting a new one"
    ),
) -> None:
    """Answer a question, or ask one back when the question is under-specified."""
    container = Container()
    graph = container.query_graph()
    locks = container.thread_lock_factory()
    try:
        if thread_id is not None:
            response = resume_turn(graph, locks, question, thread_id)
        else:
            response = start_turn(graph, locks, question, datasource, domain_id)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _render(response)
```

Note what is deliberately gone: the Phase 5 `Plan:` block. `TurnResponse` does not carry the `QueryPlan` — the plan is an internal grounding artefact, and Phase 8's response layer is where it becomes part of a structured answer alongside provenance. Reproducing it here would mean widening the DTO for a field nothing else reads yet.

- [ ] **Step 8: Run the CLI tests**

Run: `uv run pytest tests/unit/test_query_cli.py -q`
Expected: PASS — 9 tests

- [ ] **Step 9: Confirm the resume path does not re-validate `--datasource`**

Read the command back and confirm that on the `thread_id is not None` branch, `datasource` is unused. That is deliberate and matches the spec: the thread's own checkpointed state already carries the datasource it started with, and re-deriving it from a flag would let a resumed turn silently switch warehouses mid-conversation. `--datasource` stays required only because Typer options that are required for one branch and not the other read worse at the terminal than one that is always required.

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — including `tests/unit/test_query_cli.py`, which Task 10 left red

- [ ] **Step 11: Confirm the two files are under the length cap**

Run: `uv run python scripts/check_file_length.py genql/api/query_turn.py genql/cli/commands/query.py`
Expected: exit 0, no output

- [ ] **Step 12: Commit**

```bash
git add genql/api/query_turn.py genql/cli/commands/query.py \
  tests/unit/test_query_turn.py tests/unit/test_query_cli.py
git commit -m "feat(cli): add genql query --thread-id and the paused-turn rendering"
```

---

### Task 12: Composition-root wiring

**Files:**
- Create: `genql/composition/turn_container.py`
- Modify: `genql/composition_root.py`, `tests/unit/test_composition_root.py`
- Test: `tests/unit/test_composition_root.py`

**Interfaces:**
- Consumes: everything built in Tasks 1–11
- Produces: `TurnContainer` exposing `intent_classification_service`, `ambiguity_gate_service`, `domain_scoping_service`, `checkpoint_dsn`, `checkpointer`, `thread_lock_factory`, and an overriding `query_graph` compiled with all eight nodes plus the checkpointer; `Container` now inherits `TurnContainer` instead of `QueryContainer`

- [ ] **Step 1: Write the failing composition-root tests**

Append to `tests/unit/test_composition_root.py`:

```python
def test_the_container_builds_an_intent_classification_service(container: Container) -> None:
    assert hasattr(container.intent_classification_service(), "classify")


def test_the_container_builds_an_ambiguity_gate_service(container: Container) -> None:
    assert hasattr(container.ambiguity_gate_service(), "assess")


def test_the_container_builds_a_domain_scoping_service(container: Container) -> None:
    assert hasattr(container.domain_scoping_service(), "resolve")


def test_the_container_builds_a_thread_lock_factory(container: Container) -> None:
    assert hasattr(container.thread_lock_factory(), "for_thread")


def test_the_checkpoint_dsn_is_derived_from_the_semantic_dsn(container: Container) -> None:
    """One setting names GenQL's own database. A second would let the
    checkpointer and the semantic store drift onto different servers, and a
    paused turn would simply never be found again."""
    assert container.checkpoint_dsn() == "postgresql://x:x@localhost/x"


def test_the_query_graph_carries_all_eight_stages(container: Container) -> None:
    """The graph provider is overridden in TurnContainer, so this is where a
    forgotten node would show up — an eight-node graph compiled from a
    five-node provider would still be `invoke`-able and silently skip the gate.

    The checkpointer is overridden with InMemorySaver because building the real
    one opens a psycopg pool and runs setup() against it, and this fixture's DSN
    points at a host that does not exist. Overriding it is not weakening the
    test: what is under test is which nodes the provider wires, and that is
    saver-independent. The real saver is proven in
    tests/integration/test_postgres_checkpointer.py.
    """
    from dependency_injector import providers
    from langgraph.checkpoint.memory import InMemorySaver

    from genql.api.query_graph import (
        AMBIGUITY_GATE,
        CANDIDATE_GENERATION,
        DOMAIN_SCOPING,
        GUARDED_EXECUTION,
        INTENT_CLASSIFICATION,
        PLANNING,
        SCHEMA_LINKING,
        STATIC_VALIDATION,
    )

    with container.checkpointer.override(providers.Object(InMemorySaver())):
        nodes = set(container.query_graph().get_graph().nodes)

    for stage in (
        INTENT_CLASSIFICATION,
        AMBIGUITY_GATE,
        DOMAIN_SCOPING,
        SCHEMA_LINKING,
        PLANNING,
        CANDIDATE_GENERATION,
        STATIC_VALIDATION,
        GUARDED_EXECUTION,
    ):
        assert stage in nodes
```

The pre-existing `test_the_container_builds_an_invokable_query_graph` needs the same override for the same reason — it now resolves the overridden eight-node provider. Replace its body with:

```python
def test_the_container_builds_an_invokable_query_graph(container: Container) -> None:
    from dependency_injector import providers
    from langgraph.checkpoint.memory import InMemorySaver

    with container.checkpointer.override(providers.Object(InMemorySaver())):
        assert hasattr(container.query_graph(), "invoke")
```

`test_the_container_builds_an_invokable_query_graph` already exists in this file and must keep passing — it now exercises the overridden provider, which is exactly the point.

Note that the `container` fixture's `GENQL_SEMANTIC_DSN` is already `postgresql+psycopg://x:x@localhost/x`, which is why the derived DSN assertion above has that exact expected value. No fixture change is needed for this task.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL — `AttributeError: 'Container' object has no attribute 'intent_classification_service'`

- [ ] **Step 3: Create the turn container**

Create `genql/composition/turn_container.py`:

```python
"""Multi-turn providers: the three new stage services, the checkpointer, the
per-thread lock factory, and the graph rebuilt over all eight stages.

Its own container rather than more lines in QueryContainer, matching the
split-by-bounded-context convention the rest of genql/composition/ follows and
keeping both files well under the per-file line cap.

`query_graph` is deliberately re-declared here, overriding QueryContainer's
five-node version. Declarative containers resolve the most-derived declaration,
so every consumer — the CLI included — gets the eight-node graph with the
checkpointer attached, and there is exactly one graph provider in play rather
than two that could drift.

checkpoint_dsn is derived from settings.semantic_dsn rather than being its own
setting. GenQL's own database is singular; a second setting for it would let
the checkpointer and the semantic store point at different servers, and a
paused turn would then simply never be found again.
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
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.query_container import QueryContainer
from genql.infrastructure.checkpoint.postgres_checkpointer import build_checkpointer
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn
from genql.infrastructure.query.thread_lock_factory import PostgresThreadLockFactory
from genql.services.query.ambiguity_gate_service import AmbiguityGateService
from genql.services.query.domain_scoping_service import DomainScopingService
from genql.services.query.intent_classification_service import IntentClassificationService


class TurnContainer(QueryContainer):
    intent_classification_service = providers.Singleton(
        IntentClassificationService, chat=QueryContainer.chat_provider
    )
    ambiguity_gate_service = providers.Singleton(
        AmbiguityGateService,
        chat=QueryContainer.chat_provider,
        rules=QueryContainer.rule_reader,
        threshold=QueryContainer.settings.provided.ambiguity_threshold,
    )
    domain_scoping_service = providers.Singleton(
        DomainScopingService,
        retrieval=QueryContainer.retrieval_service,
        domains=QueryContainer.domain_repository,
        sample_size=QueryContainer.settings.provided.domain_scoping_sample_size,
    )

    checkpoint_dsn = providers.Callable(
        to_libpq_dsn, QueryContainer.settings.provided.semantic_dsn
    )
    # Singleton, so PostgresSaver.setup() runs once, lazily, the first time a
    # turn actually needs the graph — never on `genql --help`.
    checkpointer = providers.Singleton(
        build_checkpointer,
        dsn=checkpoint_dsn,
        max_size=QueryContainer.settings.provided.checkpoint_pool_max_size,
    )
    # A separate connection from the checkpointer's pool, on purpose:
    # pg_advisory_lock is session-scoped, and sharing the pool would deadlock
    # — the checkpointer needs a connection to write the checkpoint the lock
    # is protecting.
    thread_lock_factory = providers.Singleton(
        PostgresThreadLockFactory, dsn=checkpoint_dsn
    )

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(AmbiguityGateNode, gate=ambiguity_gate_service),
        domain_scoping=providers.Singleton(DomainScopingNode, scoper=domain_scoping_service),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=QueryContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=QueryContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=QueryContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=QueryContainer.static_validation_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=QueryContainer.guarded_execution_service
        ),
        checkpointer=checkpointer,
    )
```

- [ ] **Step 4: Point `Container` at the new base**

Modify `genql/composition_root.py`. Replace the import:

```python
from genql.composition.turn_container import TurnContainer
```

Replace the class declaration and its step map — the names are unchanged; only the base class they are read from moves:

```python
class Container(TurnContainer):
    # Every step name registered in DISCOVERY_STEPS must have an entry here so
    # its constructor can be injected with the service it needs. A step
    # registered without an entry fails fast (KeyError) at import time rather
    # than being silently dropped from the pipeline.
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": TurnContainer.catalog_scan_service,
        "data_profiling": TurnContainer.profiling_service,
        "graph_projection": TurnContainer.graph_projection_service,
        "object_profiling": TurnContainer.object_profiling_service,
    }

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
        registrations=TurnContainer.schema_registration_repository,
    )
```

Update the module docstring's parenthetical so it still names every context:

```
context (core/graph/gateway/semantic/query/turn) to stay under the project's
```

- [ ] **Step 5: Run the composition-root tests**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS — every pre-existing assertion plus the six new ones.

Any test that resolves `container.query_graph()` must override `checkpointer` first, as both graph tests above now do. `build_query_graph` is a Singleton taking `checkpointer=` as an argument, so resolving the graph resolves the saver, which opens a pool and runs `setup()` — and this fixture's DSN names a host that does not exist. A container unit test must never open a real database connection.

- [ ] **Step 6: Verify the CLI assembles end to end without a warehouse**

Run: `uv run genql query --help`
Expected: help text listing `--datasource`, `--domain-id`, and `--thread-id`, exit code 0, no traceback and no database connection.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add genql/composition/turn_container.py genql/composition_root.py \
  tests/unit/test_composition_root.py
git commit -m "feat(composition-root): wire the Phase 6 clarification and multi-turn pipeline"
```

---

### Task 13: Prove the pause/resume round trip end to end

**Files:**
- Create: `tests/integration/test_phase6_end_to_end.py`
- Modify: `semantic/local.yaml` (add a `rules` block; create the file if it does not exist)
- Test: `tests/integration/test_phase6_end_to_end.py`

**Interfaces:**
- Consumes: the wired CLI (Task 12), migration `0007` (Task 2), a seeded `tpcds` schema, and `GENQL_OPENROUTER_API_KEY`
- Produces: nothing importable — this is the phase's acceptance evidence

- [ ] **Step 1: Add a rules block to the local overlay**

Modify `semantic/local.yaml` (create it with just these two keys if the file does not exist). Append:

```yaml
rules:
  - name: default_period
    dimension: time_range
    value: the most recent complete calendar year present in the data
    description: >-
      A question with no stated period means the most recent complete calendar
      year, not all history — TPC-DS spans several years and an unbounded scan
      answers a question nobody asked.
  - name: default_comparison
    dimension: comparison_baseline
    value: none unless the question asks for one
    description: >-
      Do not invent a year-over-year or prior-period comparison. A question
      that wants one says so.
```

Two rules, not six, on purpose: the end-to-end pause test needs at least one dimension to remain genuinely open, and covering everything would make the gate skip its model call and never interrupt — which would pass the "well-specified" test and silently delete the "under-specified" one.

- [ ] **Step 2: Write the end-to-end test**

Create `tests/integration/test_phase6_end_to_end.py`:

```python
"""The phase's acceptance evidence, driven through the real CLI.

Everything below needs a live model, a seeded tpcds schema, and a migrated
database. Gated and skipped cleanly without them, exactly as Phase 5's
end-to-end file is.

The pause/resume test is the only one that proves the phase actually works.
The others exist so that a failure has somewhere to point: if the well-specified
question also pauses, the gate is over-firing; if the non-SQL question reaches
schema linking, the intent edge is wrong; if the resumed turn re-asks the same
question, the clarifications are not surviving the checkpoint.
"""

from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("GENQL_OPENROUTER_API_KEY"),
        reason="GENQL_OPENROUTER_API_KEY not set",
    ),
    pytest.mark.skipif_no_tpcds,
]

runner = CliRunner()
THREAD_LINE = re.compile(r"^thread: (t-[0-9a-f]+)$", re.MULTILINE)


@pytest.fixture(autouse=True)
def _fresh_container(migrated_engine: Engine) -> None:
    """Singletons carry a connection pool; reset so each test builds its own."""
    Container().reset_singletons()


def test_a_well_specified_question_answers_in_one_invocation() -> None:
    result = runner.invoke(app, ["query", "how many stores do we have", "--datasource", "local"])

    assert result.exit_code == 0, result.stdout
    assert "SQL:" in result.stdout
    assert "select" in result.stdout.lower()
    # No pause: a fully specified counting question must not cost a round trip.
    assert "Answer with:" not in result.stdout
    assert "rows)" in result.stdout


def test_an_under_specified_question_pauses_and_then_resumes_to_real_rows() -> None:
    """The whole phase, end to end."""
    paused = runner.invoke(
        app, ["query", "show me store sales", "--datasource", "local"]
    )

    assert paused.exit_code == 0, paused.stdout
    assert "Answer with:" in paused.stdout
    match = THREAD_LINE.search(paused.stdout)
    assert match is not None, paused.stdout
    thread_id = match.group(1)

    resumed = runner.invoke(
        app,
        [
            "query",
            "net paid, by store name, for calendar year 2001",
            "--datasource",
            "local",
            "--thread-id",
            thread_id,
        ],
    )

    assert resumed.exit_code == 0, resumed.stdout
    assert "SQL:" in resumed.stdout
    assert "select" in resumed.stdout.lower()
    assert "rows)" in resumed.stdout


def test_a_non_analytical_question_short_circuits_without_generating_sql() -> None:
    result = runner.invoke(app, ["query", "hello, who are you", "--datasource", "local"])

    assert result.exit_code == 0, result.stdout
    assert "SQL:" not in result.stdout
    assert "analytical" in result.stdout.lower()


def test_the_yaml_rules_are_reported_as_applied_defaults() -> None:
    """genql_rule reaching the answer, proving the whole overlay path: YAML →
    PostgresRuleWriter → genql_rule → PostgresRuleReader → the gate → the CLI."""
    overlay = runner.invoke(app, ["semantic", "overlay", "--datasource", "local"])
    assert overlay.exit_code == 0, overlay.stdout
    assert "rules" in overlay.stdout

    result = runner.invoke(app, ["query", "how many stores do we have", "--datasource", "local"])

    assert "Applied defaults:" in result.stdout
    assert "time_range" in result.stdout


def test_resuming_an_unknown_thread_does_not_crash() -> None:
    """A thread id nobody checkpointed has no paused node to resume, so the
    graph runs from START with an empty state. It must fail as one typed line,
    not as a traceback."""
    result = runner.invoke(
        app,
        ["query", "last quarter", "--datasource", "local", "--thread-id", "t-deadbeef"],
    )

    assert "Traceback" not in result.stdout
    assert result.exit_code in (0, 1)
```

- [ ] **Step 3: Apply the overlay so `genql_rule` is populated**

Run: `uv run genql semantic overlay --datasource local`
Expected: one line ending `..., 2 rules, N join hints`

- [ ] **Step 4: Run the end-to-end suite**

Run: `uv run pytest tests/integration/test_phase6_end_to_end.py -q`
Expected: PASS — 5 tests, or a clean skip without a key or a seeded warehouse. Sandbox: "written but unrun".

- [ ] **Step 5: Drive the round trip by hand once**

Run:

```bash
uv run genql query "how many stores do we have" --datasource local
uv run genql query "show me store sales" --datasource local
```

Expected: the first prints SQL and rows in one shot. The second prints one clarifying question, a `thread: t-...` line, and an `Answer with:` hint, and exits 0. Then, with that thread id:

```bash
uv run genql query "net paid, by store name, for calendar year 2001" \
  --datasource local --thread-id <ID>
```

Expected: a validated `SELECT` and real rows. Reading the actual clarifying question here is worth more than any assertion in Step 2 — a question that is vague, compound, or about a dimension the rules already cover means the gate prompt needs work, and this is the only place that shows up.

- [ ] **Step 6: Confirm the lock actually serialises a thread**

With a paused thread id in hand, run two resumes at once:

```bash
uv run genql query "for calendar year 2001" --datasource local --thread-id <ID> &
uv run genql query "for calendar year 2000" --datasource local --thread-id <ID> &
wait
```

Expected: both complete, one after the other, neither with a traceback. The second waits on the first's advisory lock rather than racing it into the checkpoint.

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 8: Confirm every file in the phase is under the cap**

Run: `uv run python scripts/check_file_length.py $(git diff --name-only master...HEAD -- '*.py')`
Expected: exit 0, no output

- [ ] **Step 9: Commit**

```bash
git add tests/integration/test_phase6_end_to_end.py semantic/local.yaml
git commit -m "test(phase6): prove the clarification pause and resume end to end"
```

---

## Done When

- `genql query "how many stores do we have" --datasource local` answers in one invocation, with no clarifying question and no wasted round trip.
- `genql query "show me store sales" --datasource local` prints exactly one targeted clarifying question plus a `thread: t-...` line, and exits 0.
- Resuming that thread with `--thread-id` produces a validated `SELECT` and real rows, without re-running intent classification or re-asking the answered dimension.
- A non-`analytical_sql` question reaches END with its intent reported, having touched neither retrieval nor planning nor execution.
- `genql_rule` is written by `genql semantic overlay` from a `rules:` block in `semantic/<datasource>.yaml`, with no new CLI verb, and the rules it writes show up in the CLI's `Applied defaults:` block.
- `AmbiguityGateService` makes **zero** model calls when rules cover every dimension, and asks about exactly one dimension — the highest-priority unresolved one — when they do not.
- The re-assessment loop is proven to terminate by a unit test that answers the single remaining dimension and reaches `is_ambiguous=False` on the next pass with no further model call, and by a graph test that runs two rounds and finishes.
- `DomainScopingService` resolves the plurality domain to an id, returns `None` on an empty or domain-less sample, and never overrides an explicit `--domain-id`.
- Migration `0007` creates `genql.genql_rule` with `uq_genql_rule_identity`, cascades from `genql_datasource`, and downgrades cleanly to `0006`.
- `PostgresThreadLock` provably blocks a second acquire on the same `thread_id` from a second connection until the first releases, and releases on the exception path.
- `PostgresSaver.setup()` creates langgraph's checkpoint tables, and a checkpoint written by one saver resumes through a different saver over the same database.
- `Container` exposes every Phase 6 provider, and `query_graph` compiles all eight stages with the checkpointer attached.
- The full local unit suite is green; `mypy --strict`, `ruff check`, `ruff format --check`, and `lint-imports` all pass; every file is under 250 lines.

---

## Deliberately Not Done

- **Multi-candidate generation, critique, ambiguity probing, and candidate selection (§9 stages 7, 9–11).** All four move to Phase 6.5. Nothing consumes candidate disagreement until critique exists, and §20's demand-driven cost model requires this phase's gate to exist *first* — building the expensive multi-candidate path before anything can decide when to skip it would leave that path permanently on.
- **`genql_query_log` / `genql_query_feature` and the query-weighted join-path strategy.** Deferred to Phase 8, where the golden-set runner first generates real traffic. Building them now produces tables nothing populates.
- **A confidence floor on domain scoping.** The plurality vote can pick the wrong domain, and `--domain-id` is the documented override. Real disambiguation — asking the user, or making domain a seventh ambiguity dimension — is a design decision worth making on evidence from Phase 8's evaluation harness rather than guessing at now.
- **`Literal[*AMBIGUITY_DIMENSIONS]` validation on `RuleOverlay.dimension`.** A typo'd dimension is silently inert rather than rejected at overlay time. Pinned by a test so closing the gap later is deliberate; it is a small follow-up, not a blocker.
- **Re-validating `--datasource` on resume.** The thread's checkpointed state already carries the datasource it started with. Deriving it again from a flag would let a resumed turn silently switch warehouses; enforcing agreement between the two is Phase 8's problem, when the API layer has a session concept to hang it on.
- **Natural-language answer synthesis (§9 stage 14) and the plan in the response.** `TurnResponse` carries SQL, rows, and applied defaults. The NL plan stays an internal grounding artefact until Phase 8's response layer assembles it alongside provenance and a visualization spec.
- **A per-stage model split (§21).** `Settings.chat_model` serves intent classification and the gate as well as planning and generation. The parent spec wants the merged gate on Haiku 4.5 because it reads no schema prefix, which is a real saving — and one worth measuring with Phase 8's ablation harness rather than asserting.
- **Prompt caching and `cache_control` breakpoints (§20).** The gate prompt is small and schema-free, so it is the one stage that gains least from caching. Placing breakpoints belongs with the prompt-assembly layer the cost model describes, which no phase has built yet.
- **Semantic caching of validated prior questions (§20's $0.0001 path).** Needs a corpus of validated questions, which needs Phase 8's golden-set runner.
- **Cross-process lock supervision.** Session-scoped advisory locks release themselves when a connection drops, which is Postgres's own guarantee, so there is no stale-lock cleanup path — and deliberately no monitoring for one.
