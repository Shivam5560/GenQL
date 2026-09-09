# GenQL Phases 7 and 8: Optimizer, API, and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make correct SQL *affordable* and the whole system *measurable* — insert a static-rewrite and cost-gate stage between candidate selection and guarded execution that never executes an over-budget query, record post-execution actuals behind an off-by-default switch so index recommendations have evidence, then put the engine behind a FastAPI surface with per-stage SSE streaming and build the two evaluation mechanisms the parent spec's §15 substitutes for public benchmarks: a golden-set runner that compares execution results, and an ablation harness that disables one enrichment layer at a time so the project's central claim can finally be falsified.

**Architecture:** Phase 7 adds one graph node (`REWRITE_AND_COST_GATE`) between `CANDIDATE_SELECTION` and `GUARDED_EXECUTION`, backed by an `OptimizationService` that qualifies the selected statement against a sqlglot schema built from the turn's `SchemaLink`s, runs every `REWRITE_RULES` entry once, estimates cost with `EXPLAIN (FORMAT JSON)`, and — only when still over budget — spends exactly one LLM decomposition call before returning a non-executing `narrowing_suggestion`. Phase 8 adds `genql/api/app.py` with four controllers over the existing `start_turn`/`resume_turn` path plus a new `stream_query` that renders each langgraph node update as one `StageEvent`, and `genql/services/eval/` with a `ResultComparator`, a `GoldenEvaluationService` driving turns through a `TurnRunner` port, and an `AblationService` that resolves named `Ablation` values from a registry into `Container.with_overrides(...)` settings — so no service ever branches on whether it is being ablated.

**Tech Stack:** Python 3.12 (uv). Phase 7 adds **no new dependency** — every rewrite rule wraps a pass that already ships inside `sqlglot 30.18.0` (`pushdown_predicates`, `eliminate_joins`, `eliminate_subqueries`, `pushdown_projections`). Phase 8 adds exactly three: `fastapi`, `uvicorn[standard]`, `sse-starlette`. Everything else is the established stack — `langgraph>=1.2.11` with `PostgresSaver`, SQLAlchemy 2.0 Core, Alembic, psycopg 3, Pydantic v2, pydantic-settings, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter.

**Specs:**
- `docs/superpowers/specs/2026-09-08-genql-phase-7-optimizer.md` (Part A)
- `docs/superpowers/specs/2026-09-09-genql-phase-8-api-and-evaluation.md` (Part B)

**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md` (§9 stages 13–14; §11 the optimizer's three sub-phases; §12 governance; §14 layer 4, the golden set; §15 evaluation; §16 repository structure; §17 testing strategy; §18 phases 7 and 8)

**Previous plan:** `docs/superpowers/plans/2026-09-08-genql-phase-6-5-ambiguity-machinery.md` — this plan assumes it is fully merged. It is present in the tree on this branch: `genql/api/query_ambiguity_nodes.py`, `genql/services/query/candidate_selection_service.py`, `genql/repositories/query/registry.py`, and migration `0008` all exist, and `QueryState` already carries `candidates`, `validated_sqls`, `contested`, `selection`, and `escalated`.

## Global Constraints

- Python 3.12 exactly, managed by `uv`. Run everything through `uv run`.
- **No SQL string, SQLAlchemy Core construct, psycopg call, `httpx` call, Cypher string, GDS client call, or filesystem read may appear outside `genql/repositories/`.** Enforced by import-linter's `no-sql-in-services` and `domain-is-pure` contracts.
- The `layers` contract declares `genql.api > genql.services > genql.domain`. `genql/composition/`, `genql/composition_root.py`, and `genql/cli/` sit outside the layers contract and may import anything.
- `genql/domain/` imports no other `genql` package and performs no I/O. Every new port is a `@runtime_checkable` `Protocol`.
- Every file ≤ 250 lines (pre-commit hook `scripts/check_file_length.py`). One class per file, except adapter-node modules, which the codebase already lets hold several tightly related node classes (`genql/api/query_nodes.py`, `genql/api/query_turn_nodes.py`, `genql/api/query_ambiguity_nodes.py`).
- All entities are **frozen Pydantic v2 models** (`model_config = ConfigDict(frozen=True)`). Both specs' §2 code blocks are written as plain classes for brevity; this plan follows the repository convention.
- `uv run mypy genql` (strict) must pass with zero errors. `uv run ruff check .`, `uv run ruff format --check .`, and `uv run lint-imports` must all pass.
- Every typed failure inherits `GenqlError` from `genql/domain/errors.py`.
- Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`). Commit at the end of every task.
- **Execution note.** The user's standing preferences for this repository: dispatch **one subagent per task**, run genuinely independent tasks in parallel, commit at task boundaries, skip per-task review gates and run **one review at the very end of each Part**, and keep every status report to pass/fail plus the failure location — no narrative summaries.
- Docker (ParadeDB) runs on the Debian VM (`ssh genql-vm`, 100.99.72.99). Export before running integration tests:

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_READONLY_DB_PASSWORD=genql_readonly_dev
  ```

  Real-provider tests additionally need `GENQL_OPENROUTER_API_KEY`; they are written to skip cleanly without it, and **a clean skip is not a task failure**.
- **This plan may be executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit suite (`tests/unit/`) must be run and must pass there. Integration tests are written, committed, and left for a VM-connected run; report "unit green, integration written-but-unrun" exactly as every prior phase did.
- The baseline before Task 1 is the full Phase 6.5 suite green: 504 unit tests passing, ruff clean, mypy strict clean, 3/3 import-linter contracts kept. Never leave a task boundary with a red unit suite.

---

## Deviations From the Specs (decided here, deliberately)

Each is a place where a spec's literal text conflicts with what the libraries actually do, with an established repository convention, or with something not present in the codebase. **Implement the plan's version.**

1. **Every rewrite rule wraps a sqlglot optimizer pass rather than hand-writing AST surgery.** Phase 7's spec §5 describes four transforms in prose; sqlglot 30.18.0 already ships all four as tested, semantics-preserving passes — `pushdown_predicates`, `eliminate_joins`, `eliminate_subqueries` (which is exactly "wrap a repeated subquery in a CTE"), and `pushdown_projections`. Phase 7's own §11 names "a rewrite rule that is not actually semantics-preserving corrupts results silently" as the phase's largest risk; using the library's own passes is the single largest reduction available in that risk, and it is why this phase adds no dependency.

2. **`OptimizationService` fully qualifies the statement against a schema built from the turn's `SchemaLink`s before applying any rule, and skips rewriting entirely when that fails.** This is not optional polish — it is a correctness requirement discovered by running the passes. Given `SELECT o.id FROM shop.orders AS o JOIN (SELECT oid, qty FROM shop.items) AS i ON i.oid = o.id WHERE i.qty > 5` qualified *without* a schema (`qualify_columns=False`, which is what `StaticValidationService` does), `pushdown_predicates` emits:

   ```sql
   SELECT o.id FROM shop.orders AS o JOIN (SELECT * FROM shop.items AS items WHERE i.qty > 5) AS i ...
   ```

   — the predicate lands inside the subquery still referencing the *outer* alias `i`, which is invalid SQL. With a schema (`{"shop": {"orders": {...}, "items": {...}}}`) the same pass emits the correct `WHERE items.qty > 5`. `SchemaLink.column_names` is exactly the data needed to build that schema. When qualification raises `OptimizeError` (an unknown column or an object retrieval did not return), `OptimizationService` logs, applies **no** rules, and cost-gates the original statement — a query that cannot be safely rewritten still gets its budget checked.

3. **`projection_pruning`'s `SELECT *` expansion is a side effect of the schema-qualification step, not of the rule.** Phase 7's §5 folds "expands a bare `SELECT *` into its actual column list" into the rule. In sqlglot, `qualify(expression, schema=...)` performs star expansion, and `pushdown_projections` performs the unused-column removal. Since the plan already qualifies with a schema (Deviation 2), expansion has happened before any rule runs, and the rule is the pruning half alone.

4. **`OptimizationService` receives a `RewriteRuleFactory` port, not `REWRITE_RULES.all()`.** `Registry[T]` has no `all()` method — it exposes `keys()`, `get()`, and `create()` — so something must turn the registry into a list. It cannot be the service: `genql/services/` may not import `genql/repositories/`, and `REWRITE_RULES` lives there beside the rules it registers. A `RewriteRuleFactory` port with a single `rules() -> Sequence[RewriteRule]` method, implemented in `genql/infrastructure/query/`, is the same arrangement `GuardrailFactory` already uses for the identical problem. It takes no arguments, because Deviation 3 hoists the only per-turn context any rule needed (the sqlglot schema) into `OptimizationService`'s qualification step, which happens before the first rule runs.

5. **"Registration order" is `Registry.keys()` order, which is sorted alphabetically.** `Registry.keys()` returns `sorted(self._items)`. The four rules therefore run as `cte_materialization`, `predicate_pushdown`, `projection_pruning`, `redundant_join_elimination`. Phase 7's §1 argues the pipeline is order-independent by construction ("none of them re-creates a pattern another one removes"), which is exactly what makes alphabetical order acceptable — but the spec's phrase "registration order" would mislead a reader of the code, so the registry module says so in its docstring.

6. **`redundant_join_elimination` is registered knowing it is a no-op in the common case.** sqlglot's `eliminate_joins` removes a join only when it can prove the joined relation is unique on the join key, which it infers from the query's own structure (a `GROUP BY` or `DISTINCT` subquery), not from GenQL's foreign-key metadata. On a plain `LEFT JOIN shop.customers AS c ON c.id = o.cid` with `c` unreferenced, it correctly declines. Phase 7's §5 describes FK-driven elimination; implementing that by hand is exactly the semantics risk Deviation 1 exists to avoid. The rule is registered as the library's pass, its unit test asserts the no-op case explicitly, and the gap is recorded in "Deliberately Not Done".

7. **`QueryDecomposer`'s implementation is named `LlmQueryDecomposer` and lives in `genql/services/query/`**, beside `LlmProbeDesigner`, which Phase 6.5 placed there for the same reason: it is a `ChatProvider`-driven adapter that holds a prompt, performs no I/O of its own, and would be the only occupant of a new package.

8. **`GraphTurnRunner` lives in `genql/api/`, not `genql/services/`.** It wraps the compiled graph and `start_turn`, both of which live in `genql/api/`, and `genql/services/` may not import `genql.api`. `GoldenEvaluationService` depends on the `TurnRunner` *protocol* in `genql/domain/ports/`; the composition root injects the api-layer adapter into the service, exactly as it injects repository adapters. `lint-imports` verifies this.

9. **The ablation switches are never read from the environment in normal operation.** They are `Settings` fields so that `Container.with_overrides` can replace them, but `.env.example` does not list them and the CLI does not expose them, because a stray `GENQL_ENRICHMENT_ENABLED=false` would silently degrade every real turn with no indication in the output.

10. **`Container.with_overrides` returns a `Container`, constructed with a pre-built `Settings` instance**, rather than using `dependency_injector`'s `override()` machinery. The container hierarchy resolves `settings` through `providers.Singleton(Settings)`; passing an already-constructed instance through `providers.Object` is one line, is obviously correct, and does not depend on override-reset semantics across six inherited container classes.

---

## File Structure

### Part A — Phase 7 (Optimizer)

**Created**

```
genql/domain/entities/optimization_result.py            OptimizationResult
genql/domain/entities/rewrite_outcome.py                RewriteOutcome
genql/domain/entities/index_recommendation.py           IndexRecommendation
genql/domain/ports/rewrite_rule.py                      RewriteRule
genql/domain/ports/rewrite_rule_factory.py              RewriteRuleFactory
genql/domain/ports/cost_estimator.py                    CostEstimator
genql/domain/ports/query_decomposer.py                  QueryDecomposer
genql/domain/ports/rewrite_outcome_writer.py            RewriteOutcomeWriter
genql/domain/ports/index_recommender.py                 IndexRecommender
migrations/versions/0009_rewrite_outcomes.py            genql.genql_rewrite_outcome
genql/repositories/query/rewrite_rules/__init__.py      registration imports
genql/repositories/query/rewrite_rules/registry.py      REWRITE_RULES
genql/repositories/query/rewrite_rules/cte_materialization.py
genql/repositories/query/rewrite_rules/predicate_pushdown.py
genql/repositories/query/rewrite_rules/projection_pruning.py
genql/repositories/query/rewrite_rules/redundant_join_elimination.py
genql/infrastructure/query/rewrite_rule_factory.py      RewriteRuleFactoryImpl
genql/repositories/query/cost_estimator_repository.py   PostgresCostEstimator
genql/repositories/query/rewrite_outcome_repository.py  PostgresRewriteOutcomeWriter
genql/repositories/query/index_recommender_repository.py PostgresIndexRecommender
genql/services/query/optimization_service.py            OptimizationService
genql/services/query/query_decomposer.py                LlmQueryDecomposer
genql/services/query/rewrite_recording_service.py       RewriteOutcomeRecordingService
genql/services/query/index_recommendation_service.py    IndexRecommendationService
genql/api/query_optimizer_nodes.py                      RewriteAndCostGateNode
genql/composition/optimizer_container.py                OptimizerContainer
genql/cli/commands/optimizer.py                         `genql optimizer`
golden/phase7_equivalence.yaml                          the six shared fixtures
tests/unit/test_optimizer_entities.py
tests/unit/test_optimizer_ports_are_runtime_checkable.py
tests/unit/test_rewrite_rules.py
tests/unit/test_rewrite_rule_factory.py
tests/unit/test_optimization_service.py
tests/unit/test_query_decomposer.py
tests/unit/test_rewrite_recording_service.py
tests/unit/test_index_recommendation_service.py
tests/unit/test_query_optimizer_nodes.py
tests/integration/test_migration_0009.py
tests/integration/test_cost_estimator_repository.py
tests/integration/test_rewrite_outcome_repository.py
tests/integration/test_query_decomposer_real_provider.py
tests/integration/test_rewrite_equivalence.py
tests/integration/test_cli_optimizer.py
tests/integration/test_phase7_end_to_end.py
```

**Modified**

```
genql/core/settings.py                    + cost_budget, record_execution_actuals
genql/domain/errors.py                    + OptimizationError, CostEstimationError
genql/domain/entities/turn_response.py    + narrowing_suggestion, rewrite_rules_applied
genql/api/query_state.py                  + optimization
genql/api/query_nodes.py                  GuardedExecutionNode + optional recorder
genql/api/query_graph.py                  + REWRITE_AND_COST_GATE, route_after_cost_gate
genql/api/query_turn.py                   _to_response reads optimization
genql/composition_root.py                 Container now extends OptimizerContainer
genql/cli/main.py                         + `optimizer` sub-app
genql/repositories/query/__init__.py      + rewrite_rules registration import
```

### Part B — Phase 8 (API and Evaluation)

**Created**

```
genql/domain/entities/golden_case.py                    GoldenCase
genql/domain/entities/golden_outcome.py                 GoldenOutcome
genql/domain/entities/golden_run_report.py              GoldenRunReport
genql/domain/entities/ablation.py                       Ablation
genql/domain/entities/feedback.py                       Feedback
genql/domain/entities/stage_event.py                    StageEvent
genql/domain/ports/golden_set_reader.py                 GoldenSetReader
genql/domain/ports/turn_runner.py                       TurnRunner
genql/domain/ports/turn_runner_factory.py               TurnRunnerFactory
genql/domain/ports/search_document_recompiler.py        SearchDocumentRecompiler
genql/domain/ports/feedback_writer.py                   FeedbackWriter
genql/domain/ports/report_writer.py                     ReportWriter
migrations/versions/0010_feedback.py                    genql.genql_feedback
genql/repositories/semantic/feedback_repository.py      PostgresFeedbackWriter
genql/repositories/eval/__init__.py
genql/repositories/eval/yaml_golden_set_repository.py   YamlGoldenSetReader
genql/repositories/eval/json_report_repository.py       JsonReportWriter
genql/repositories/null/__init__.py
genql/repositories/null/null_join_path_reader.py        NullJoinPathReader
genql/repositories/null/null_ambiguity_example_reader.py NullAmbiguityExampleReader
genql/services/eval/__init__.py
genql/services/eval/registry.py                         ABLATIONS
genql/services/eval/ablations/__init__.py               registration imports
genql/services/eval/ablations/full.py
genql/services/eval/ablations/no_descriptions.py
genql/services/eval/ablations/no_domains.py
genql/services/eval/ablations/no_join_paths.py
genql/services/eval/ablations/no_probing.py
genql/services/eval/ablations/no_ambiguity_examples.py
genql/services/eval/result_comparator.py                ResultComparator
genql/services/eval/golden_evaluation_service.py        GoldenEvaluationService
genql/services/eval/ablation_service.py                 AblationService
genql/services/semantic/feedback_service.py             FeedbackService
genql/api/graph_turn_runner.py                          GraphTurnRunner
genql/api/app.py                                        create_app
genql/api/deps.py                                       container dependency
genql/api/dtos/__init__.py
genql/api/dtos/query_dtos.py                            StartTurnRequest, ResumeTurnRequest, TurnResponseDto
genql/api/dtos/feedback_dtos.py                         FeedbackRequest
genql/api/dtos/datasource_dtos.py                       DatasourceDto
genql/api/controllers/__init__.py
genql/api/controllers/query_controller.py
genql/api/controllers/stream_controller.py
genql/api/controllers/feedback_controller.py
genql/api/controllers/datasource_controller.py
genql/api/sse/__init__.py
genql/api/sse/stage_events.py                           to_stage_event, terminal_event
genql/api/sse/event_stream.py                           stage_event_stream
genql/composition/eval_container.py                     EvalContainer
genql/infrastructure/eval/__init__.py
genql/infrastructure/eval/turn_runner_factory.py        TurnRunnerFactoryImpl
genql/infrastructure/eval/search_document_recompiler.py SearchDocumentRecompilerImpl
genql/cli/commands/serve.py                             `genql serve`
genql/cli/commands/eval.py                              `genql eval`
golden/tpcds_core.yaml                                  the first curated cases
tests/unit/test_eval_entities.py
tests/unit/test_eval_ports_are_runtime_checkable.py
tests/unit/test_result_comparator.py
tests/unit/test_golden_evaluation_service.py
tests/unit/test_ablations.py
tests/unit/test_ablation_service.py
tests/unit/test_feedback_service.py
tests/unit/test_stage_events.py
tests/unit/test_api_dtos.py
tests/unit/test_search_document_compiler_ablation.py
tests/integration/test_migration_0010.py
tests/integration/test_feedback_repository.py
tests/integration/test_yaml_golden_set_repository.py
tests/integration/test_api_routes.py
tests/integration/test_api_stream.py
tests/integration/test_cli_eval.py
tests/integration/test_ablation_harness.py
tests/golden/__init__.py
tests/golden/test_golden_runner.py
```

**Modified**

```
pyproject.toml                            + fastapi, uvicorn[standard], sse-starlette
.importlinter                             + fastapi, starlette, sse_starlette forbidden below api/
genql/core/settings.py                    + 5 ablation switches, api_host, api_port, golden_set_dir
genql/domain/errors.py                    + EvaluationError, GoldenSetError, UnknownAblationError, FeedbackError
genql/domain/entities/turn_response.py    + plan_text, referenced_objects, selection_method,
                                            selection_rationale, candidate_count, probe_count
genql/api/query_turn.py                   + stream helpers' to_response rename; provenance fields filled
genql/api/query_graph.py                  + stream_query, stream_resume
genql/repositories/semantic/search_document_repository.py  + include_enrichment flag
genql/repositories/semantic/__init__.py   + PostgresFeedbackWriter
genql/composition_root.py                 Container extends EvalContainer, + with_overrides
genql/cli/main.py                         + `serve` command and `eval` sub-app
```

---

## Task Sequence and Why

**Part A.** Task 1 is pure declaration — three entities, six ports, two errors, two settings — so every later task is written against fixed names. Task 2 lands migration `0009`, because Task 4's repository integration tests cannot run without `genql_rewrite_outcome`. Tasks 3, 4, and 5 are then independent of one another: the rewrite-rule registry and its factory (3), the three Postgres repositories (4), and the LLM decomposer (5) each depend only on Task 1, and Task 4 also on Task 2. Task 6 is `OptimizationService`, held until the factory in Task 3 exists as a type. Task 7 is the two small recording/reporting services. Task 8 rewires `QueryState`, `TurnResponse`, the new node, and the graph edge, and is held until every service exists. Task 9 is composition wiring plus the CLI. Task 10 proves Part A: rewrite-equivalence against real data, and an over-budget question that returns a suggestion instead of rows.

**Part B.** Task 11 is Part B's declaration task — dependencies, six entities, six ports, four errors, eight settings — mirroring Task 1's role. Tasks 12, 13, and 14 are independent: feedback capture end to end (12), the pure `ResultComparator` (13), and the two file repositories plus the first fixtures (14). Task 15 is `GoldenEvaluationService`, needing 13's comparator and 14's reader as types. Task 16 is the ablation registry, the two null adapters, and the compiler flag — independent of 15. Task 17 wires the composition-level pieces the harness needs (`with_overrides`, `GraphTurnRunner`, the two factory adapters). Task 18 is `AblationService`, held until 16 and 17. Task 19 is the `genql eval` CLI. Tasks 20 and 21 are the HTTP surface and the SSE surface, independent of each other once Task 11's DTO-adjacent entities exist. Task 22 threads provenance through `TurnResponse` and proves both halves end to end.

## Execution Batches

| Batch | Tasks | Parallelizable? |
|---|---|---|
| 1 | 1 | — |
| 2 | 2 | — |
| 3 | 3, 4, 5 | Yes |
| 4 | 6 | — |
| 5 | 7 | — |
| 6 | 8 | — |
| 7 | 9 | — |
| 8 | 10 | — |
| — | **Part A review gate** | one review of Part A as a whole |
| 9 | 11 | — |
| 10 | 12, 13, 14 | Yes |
| 11 | 15, 16 | Yes |
| 12 | 17 | — |
| 13 | 18 | — |
| 14 | 19 | — |
| 15 | 20, 21 | Yes |
| 16 | 22 | — |
| — | **Part B review gate** | one review of Part B as a whole |

---
# PART A — Phase 7: Optimizer

### Task 1: Optimizer domain foundation — entities, ports, errors, settings

**Files:**
- Create: `genql/domain/entities/optimization_result.py`, `genql/domain/entities/rewrite_outcome.py`, `genql/domain/entities/execution_actuals.py`, `genql/domain/entities/index_recommendation.py`, `genql/domain/ports/rewrite_rule.py`, `genql/domain/ports/rewrite_rule_factory.py`, `genql/domain/ports/cost_estimator.py`, `genql/domain/ports/execution_actuals_reader.py`, `genql/domain/ports/query_decomposer.py`, `genql/domain/ports/rewrite_outcome_writer.py`, `genql/domain/ports/index_recommender.py`
- Modify: `genql/domain/errors.py`, `genql/core/settings.py`
- Test: `tests/unit/test_optimizer_entities.py`, `tests/unit/test_optimizer_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `genql.domain.entities.query_plan.QueryPlan`, `genql.domain.entities.schema_link.SchemaLink` (both existing)
- Produces: entities `OptimizationResult(sql, rules_applied, estimated_cost, within_budget, narrowing_suggestion)`, `ExecutionActuals(total_time_ms, rows, shared_buffers_hit, shared_buffers_read)`, `RewriteOutcome(sql_hash, datasource_name, rules_applied, estimated_cost, actuals)`, `IndexRecommendation(object_qualified_name, column_name, rationale, supporting_execution_count)`; ports `RewriteRule` (attribute `name: str`, `apply(exp.Expression) -> exp.Expression`), `RewriteRuleFactory.rules() -> Sequence[RewriteRule]`, `CostEstimator.estimate(sql, datasource_name) -> float`, `ExecutionActualsReader.read_actuals(sql, datasource_name) -> ExecutionActuals`, `QueryDecomposer.decompose(plan, sql, estimated_cost, budget) -> str`, `RewriteOutcomeWriter.write(outcome) -> None`, `IndexRecommender.recommend(datasource_name) -> tuple[IndexRecommendation, ...]`; errors `OptimizationError`, `CostEstimationError`; settings `cost_budget: float = 100_000.0`, `record_execution_actuals: bool = False`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/test_optimizer_entities.py`:

```python
"""Four new entities. The behaviour worth testing directly is the invariant
that ties OptimizationResult's two failure-facing fields together: a result
that is within budget must not carry a narrowing suggestion, and one that is
not must carry one. RewriteAndCostGateNode routes on `within_budget` and the
CLI prints `narrowing_suggestion`, so a result where those disagree would
either print an empty suggestion or silently execute an over-budget query."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.rewrite_outcome import RewriteOutcome

ACTUALS = ExecutionActuals(
    total_time_ms=12.5, rows=42, shared_buffers_hit=100, shared_buffers_read=7
)


def test_a_within_budget_result_carries_no_narrowing_suggestion() -> None:
    result = OptimizationResult(
        sql="SELECT 1",
        rules_applied=("predicate_pushdown",),
        estimated_cost=10.0,
        within_budget=True,
        narrowing_suggestion=None,
    )

    assert result.within_budget is True
    assert result.narrowing_suggestion is None


def test_a_within_budget_result_rejects_a_narrowing_suggestion() -> None:
    with pytest.raises(ValidationError):
        OptimizationResult(
            sql="SELECT 1",
            rules_applied=(),
            estimated_cost=10.0,
            within_budget=True,
            narrowing_suggestion="narrow the date range",
        )


def test_an_over_budget_result_requires_a_narrowing_suggestion() -> None:
    with pytest.raises(ValidationError):
        OptimizationResult(
            sql="SELECT 1",
            rules_applied=(),
            estimated_cost=1_000_000.0,
            within_budget=False,
            narrowing_suggestion=None,
        )


def test_an_over_budget_result_with_a_suggestion_is_valid() -> None:
    result = OptimizationResult(
        sql="SELECT 1",
        rules_applied=(),
        estimated_cost=1_000_000.0,
        within_budget=False,
        narrowing_suggestion="narrow the date range",
    )

    assert result.narrowing_suggestion == "narrow the date range"


def test_an_optimization_result_is_frozen() -> None:
    result = OptimizationResult(
        sql="SELECT 1", rules_applied=(), estimated_cost=1.0, within_budget=True
    )

    with pytest.raises(ValidationError):
        result.sql = "SELECT 2"


def test_execution_actuals_carry_the_four_explain_analyze_numbers() -> None:
    assert ACTUALS.total_time_ms == 12.5
    assert ACTUALS.rows == 42
    assert ACTUALS.shared_buffers_hit == 100
    assert ACTUALS.shared_buffers_read == 7


def test_a_rewrite_outcome_keys_on_the_sql_hash() -> None:
    outcome = RewriteOutcome(
        sql_hash="a" * 64,
        datasource_name="local",
        rules_applied=("projection_pruning",),
        estimated_cost=500.0,
        actuals=ACTUALS,
    )

    assert outcome.sql_hash == "a" * 64
    assert outcome.actuals.rows == 42


def test_an_index_recommendation_carries_its_supporting_evidence_count() -> None:
    recommendation = IndexRecommendation(
        object_qualified_name="local.tpcds.store_sales",
        column_name="ss_sold_date_sk",
        rationale="3 of 3 recorded executions filtered this column via sequential scan",
        supporting_execution_count=3,
    )

    assert recommendation.supporting_execution_count == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_optimizer_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.execution_actuals'`

- [ ] **Step 3: Create the four entities**

Create `genql/domain/entities/execution_actuals.py`:

```python
"""What `EXPLAIN (ANALYZE, BUFFERS)` measured, as opposed to what
`EXPLAIN (FORMAT JSON)` predicted.

Its own entity rather than four fields on RewriteOutcome because the
repository that reads it does not know which rewrite produced the statement —
it reads a plan and reports numbers, and RewriteOutcomeRecordingService is
what joins those numbers to the rules that were applied.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExecutionActuals(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_time_ms: float
    rows: int
    shared_buffers_hit: int
    shared_buffers_read: int
```

Create `genql/domain/entities/optimization_result.py`:

```python
"""What the rewrite-and-cost-gate stage decided about one statement.

`within_budget` and `narrowing_suggestion` are validated against each other
rather than left independent: the graph routes on the first and the CLI prints
the second, so a result where they disagree either prints an empty explanation
to the user or executes a query the gate meant to stop.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    rules_applied: tuple[str, ...] = ()
    estimated_cost: float
    within_budget: bool
    narrowing_suggestion: str | None = None

    @model_validator(mode="after")
    def _suggestion_matches_verdict(self) -> Self:
        if self.within_budget and self.narrowing_suggestion is not None:
            raise ValueError("a within-budget result must not carry a narrowing suggestion")
        if not self.within_budget and self.narrowing_suggestion is None:
            raise ValueError("an over-budget result must carry a narrowing suggestion")
        return self
```

Create `genql/domain/entities/rewrite_outcome.py`:

```python
"""One executed statement's predicted cost beside its measured cost.

`sql_hash` rather than the statement text is the natural key: the table
accumulates one row per execution, the same question asked twice produces the
same statement, and aggregating by hash is what lets IndexRecommender say "3
of 3 recorded executions" rather than "3 statements that look similar".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_actuals import ExecutionActuals


class RewriteOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql_hash: str
    datasource_name: str
    rules_applied: tuple[str, ...]
    estimated_cost: float
    actuals: ExecutionActuals
```

Create `genql/domain/entities/index_recommendation.py`:

```python
"""One index GenQL suggests a human create.

The parent spec's §11 is explicit that GenQL never creates an index itself, so
this entity is a report line, not a command. `rationale` is a full sentence
because an operator reading `genql optimizer recommend-indexes` needs to judge
the suggestion, not just apply it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IndexRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_qualified_name: str
    column_name: str
    rationale: str
    supporting_execution_count: int
```

- [ ] **Step 4: Run the entity tests**

Run: `uv run pytest tests/unit/test_optimizer_entities.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the failing port tests**

Create `tests/unit/test_optimizer_ports_are_runtime_checkable.py`:

```python
"""Every port is a runtime_checkable Protocol, matching every port since
Phase 1. The check is cheap and catches the one mistake that is otherwise
invisible until composition: a Protocol declared without the decorator, which
makes `isinstance` raise rather than answer."""

from __future__ import annotations

from collections.abc import Sequence

import sqlglot
from sqlglot import exp

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.ports.cost_estimator import CostEstimator
from genql.domain.ports.execution_actuals_reader import ExecutionActualsReader
from genql.domain.ports.index_recommender import IndexRecommender
from genql.domain.ports.query_decomposer import QueryDecomposer
from genql.domain.ports.rewrite_outcome_writer import RewriteOutcomeWriter
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory


class _Rule:
    name = "noop"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression


class _Factory:
    def rules(self) -> Sequence[RewriteRule]:
        return (_Rule(),)


class _Estimator:
    def estimate(self, sql: str, datasource_name: str) -> float:
        return 1.0


class _ActualsReader:
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        return ExecutionActuals(
            total_time_ms=1.0, rows=1, shared_buffers_hit=1, shared_buffers_read=0
        )


class _Decomposer:
    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str:
        return sql


class _Writer:
    def write(self, outcome: RewriteOutcome) -> None:
        return None


class _Recommender:
    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return ()


def test_every_optimizer_port_is_runtime_checkable() -> None:
    assert isinstance(_Rule(), RewriteRule)
    assert isinstance(_Factory(), RewriteRuleFactory)
    assert isinstance(_Estimator(), CostEstimator)
    assert isinstance(_ActualsReader(), ExecutionActualsReader)
    assert isinstance(_Decomposer(), QueryDecomposer)
    assert isinstance(_Writer(), RewriteOutcomeWriter)
    assert isinstance(_Recommender(), IndexRecommender)


def test_a_rewrite_rule_returns_an_expression_not_none() -> None:
    """The contract OptimizationService's identity comparison depends on."""
    expression = sqlglot.parse_one("SELECT 1", dialect="postgres")

    assert _Rule().apply(expression) is expression
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_optimizer_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.rewrite_rule'`

- [ ] **Step 7: Create the seven ports**

Create `genql/domain/ports/rewrite_rule.py`:

```python
"""A pure, semantics-preserving sqlglot AST transform.

Returns an expression in every case — never None, never raising, including on
input it cannot handle, where it returns what it was given. `OptimizationService`
decides whether a rule fired by comparing the *rendered SQL* before and after,
not by object identity: sqlglot's own optimizer passes mutate the tree in place
and hand back the same object, so an identity check would report every rule as
a no-op.

Importing sqlglot here does not breach the domain-is-pure contract:
`.importlinter` forbids sqlalchemy, psycopg, neo4j, graphdatascience, and
httpx, and sqlglot is a pure parser with no I/O — the same reasoning
`StaticValidationService` records for importing it from `services/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlglot import exp


@runtime_checkable
class RewriteRule(Protocol):
    name: str

    def apply(self, expression: exp.Expression) -> exp.Expression: ...
```

Create `genql/domain/ports/rewrite_rule_factory.py`:

```python
"""Turns the REWRITE_RULES registry into an ordered rule list.

Exists so `OptimizationService` never imports `genql/repositories/`, which the
layering forbids and which is where the registry and its rules live. Mirrors
GuardrailFactory, which exists for exactly the same reason.

It takes no arguments: the sqlglot schema the rules used to need is built and
applied by OptimizationService's qualification step, before any rule runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.ports.rewrite_rule import RewriteRule


@runtime_checkable
class RewriteRuleFactory(Protocol):
    def rules(self) -> Sequence[RewriteRule]: ...
```

Create `genql/domain/ports/cost_estimator.py`:

```python
"""Predicts a statement's cost without running it.

`EXPLAIN` without `ANALYZE` never executes the statement, which is what makes
this port as safe as static validation rather than as consequential as guarded
execution — the distinction that lets the cost gate sit before execution
rather than after it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CostEstimator(Protocol):
    def estimate(self, sql: str, datasource_name: str) -> float: ...
```

Create `genql/domain/ports/execution_actuals_reader.py`:

```python
"""Measures a statement by running it under `EXPLAIN (ANALYZE, BUFFERS)`.

A separate port from CostEstimator despite sharing an implementation class,
because the two have opposite safety profiles: estimating is free and never
executes, measuring re-runs the whole statement and doubles its cost. A caller
that holds only CostEstimator structurally cannot start a second execution.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.execution_actuals import ExecutionActuals


@runtime_checkable
class ExecutionActualsReader(Protocol):
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals: ...
```

Create `genql/domain/ports/query_decomposer.py`:

```python
"""One grounded LLM call that narrows an over-budget statement.

Given the plan, the statement, and the size of the gap, it returns a
simplified statement — a narrower date range, or a filter the static rules
could not prove safe on their own. It is the only model call in Phase 7, and
it is spent at most once per turn.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.query_plan import QueryPlan


@runtime_checkable
class QueryDecomposer(Protocol):
    def decompose(
        self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float
    ) -> str: ...
```

Create `genql/domain/ports/rewrite_outcome_writer.py`:

```python
"""Appends one measured execution to the evidence table."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rewrite_outcome import RewriteOutcome


@runtime_checkable
class RewriteOutcomeWriter(Protocol):
    def write(self, outcome: RewriteOutcome) -> None: ...
```

Create `genql/domain/ports/index_recommender.py`:

```python
"""Reads accumulated rewrite outcomes and proposes indexes for a human."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.index_recommendation import IndexRecommendation


@runtime_checkable
class IndexRecommender(Protocol):
    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]: ...
```

- [ ] **Step 8: Add the two errors**

Append to `genql/domain/errors.py`, after `UnknownThreadError`:

```python
class OptimizationError(QueryError):
    """The rewrite-and-cost-gate stage could not reach a verdict.

    Not raised when a query is over budget — that is a normal, typed outcome
    carried in OptimizationResult, not a failure. This is for the stage being
    unable to run at all.
    """


class CostEstimationError(QueryError):
    """EXPLAIN itself failed against the warehouse."""
```

- [ ] **Step 9: Add the two settings**

Append to the `Settings` class in `genql/core/settings.py`:

```python
    # PostgreSQL planner cost units (arbitrary, not wall-clock) read from
    # EXPLAIN's Total Cost. A rough proxy until Phase 8's ablation harness can
    # correlate it against measured time on this specific warehouse.
    cost_budget: float = 100_000.0
    # Off by default because EXPLAIN (ANALYZE, BUFFERS) re-runs the statement:
    # recording actuals for every turn would silently double warehouse load
    # for a purely diagnostic feature.
    record_execution_actuals: bool = False
```

- [ ] **Step 10: Run everything**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: PASS — 504 + 10 tests, all checks clean, 3/3 contracts kept

- [ ] **Step 11: Commit**

```bash
git add genql/domain genql/core/settings.py tests/unit/test_optimizer_entities.py tests/unit/test_optimizer_ports_are_runtime_checkable.py
git commit -m "feat(domain): declare the Phase 7 optimizer entities, ports, errors, and settings"
```

---

### Task 2: Migration `0009` — `genql_rewrite_outcome`

**Files:**
- Create: `migrations/versions/0009_rewrite_outcomes.py`, `tests/integration/test_migration_0009.py`
- Test: `tests/integration/test_migration_0009.py`

**Interfaces:**
- Consumes: migration `0008_ambiguity_examples` as `down_revision`
- Produces: table `genql.genql_rewrite_outcome`, revision id `"0009"`

- [ ] **Step 1: Read the previous migration to copy its exact conventions**

Run: `sed -n '1,40p' migrations/versions/0008_ambiguity_examples.py`

Note the revision-identifier style, the `schema="genql"` argument on every operation, and the `downgrade()` shape. Match them exactly — a migration that omits `schema="genql"` creates the table in `public` and every repository test then fails with a confusing "relation does not exist".

- [ ] **Step 2: Write the failing migration test**

Create `tests/integration/test_migration_0009.py`:

```python
"""Upgrade to head creates the table with the columns the repositories read,
and downgrade removes it. The columns are asserted by name because
PostgresIndexRecommender aggregates on `shared_buffers_read` and
`datasource_id`, and a rename would fail there at query time rather than
here."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.integration

EXPECTED_COLUMNS = {
    "id",
    "sql_hash",
    "datasource_id",
    "rules_applied",
    "estimated_cost",
    "actual_total_time_ms",
    "actual_rows",
    "shared_buffers_hit",
    "shared_buffers_read",
    "recorded_at",
}


def test_upgrade_creates_the_rewrite_outcome_table(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("genql_rewrite_outcome", schema="genql")}

    assert EXPECTED_COLUMNS <= columns


def test_the_table_is_indexed_by_datasource(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    indexes = inspector.get_indexes("genql_rewrite_outcome", schema="genql")

    assert any("datasource_id" in index["column_names"] for index in indexes)
```

Reuse the `migrated_engine` fixture already defined in `tests/integration/conftest.py`; do not define a new one. Read it first: `grep -n "migrated_engine" tests/integration/conftest.py`.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0009.py -q`
Expected: FAIL — `NoSuchTableError: genql_rewrite_outcome` (or a clean skip with no `GENQL_TEST_DSN`, in which case write the migration and verify it on a VM-connected run)

- [ ] **Step 4: Write the migration**

Create `migrations/versions/0009_rewrite_outcomes.py`:

```python
"""rewrite outcomes

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_rewrite_outcome",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sql_hash", sa.Text(), nullable=False),
        sa.Column(
            "datasource_id",
            sa.BigInteger(),
            sa.ForeignKey("genql.genql_datasource.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rules_applied", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("estimated_cost", sa.Double(), nullable=False),
        sa.Column("actual_total_time_ms", sa.Double(), nullable=False),
        sa.Column("actual_rows", sa.BigInteger(), nullable=False),
        sa.Column("shared_buffers_hit", sa.BigInteger(), nullable=False),
        sa.Column("shared_buffers_read", sa.BigInteger(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="genql",
    )
    op.create_index(
        "genql_rewrite_outcome_datasource_idx",
        "genql_rewrite_outcome",
        ["datasource_id"],
        schema="genql",
    )


def downgrade() -> None:
    op.drop_index(
        "genql_rewrite_outcome_datasource_idx", table_name="genql_rewrite_outcome", schema="genql"
    )
    op.drop_table("genql_rewrite_outcome", schema="genql")
```

- [ ] **Step 5: Run the migration test**

Run: `uv run pytest tests/integration/test_migration_0009.py -q`
Expected: PASS, or a clean skip without `GENQL_TEST_DSN`

- [ ] **Step 6: Verify the unit suite and static checks are still clean**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check .`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/0009_rewrite_outcomes.py tests/integration/test_migration_0009.py
git commit -m "feat(migrations): add genql_rewrite_outcome for recorded execution actuals"
```

---
### Task 3: `REWRITE_RULES`, the four rules, and `RewriteRuleFactoryImpl`

**Files:**
- Create: `genql/repositories/query/rewrite_rules/__init__.py`, `genql/repositories/query/rewrite_rules/registry.py`, `genql/repositories/query/rewrite_rules/safe_apply.py`, `genql/repositories/query/rewrite_rules/cte_materialization.py`, `genql/repositories/query/rewrite_rules/predicate_pushdown.py`, `genql/repositories/query/rewrite_rules/projection_pruning.py`, `genql/repositories/query/rewrite_rules/redundant_join_elimination.py`, `genql/infrastructure/query/rewrite_rule_factory.py`
- Modify: `genql/repositories/query/__init__.py`
- Test: `tests/unit/test_rewrite_rules.py`, `tests/unit/test_rewrite_rule_factory.py`

**Interfaces:**
- Consumes: `genql.domain.ports.rewrite_rule.RewriteRule`, `genql.domain.ports.rewrite_rule_factory.RewriteRuleFactory`, `genql.registries.registry.Registry` (Task 1 and existing)
- Produces: `REWRITE_RULES: Registry[RewriteRule]` with keys `cte_materialization`, `predicate_pushdown`, `projection_pruning`, `redundant_join_elimination`; `safe_apply(pass_fn, expression) -> exp.Expression`; `RewriteRuleFactoryImpl.rules() -> Sequence[RewriteRule]`

- [ ] **Step 1: Write the failing rule tests**

Create `tests/unit/test_rewrite_rules.py`:

```python
"""Each rule against a hand-built statement, asserting the specific transform,
and each rule against input it must not touch, asserting the no-op.

Every input here is already fully qualified against a schema, because that is
what OptimizationService guarantees before the first rule runs — and because
sqlglot's passes produce invalid SQL on unqualified input, which is the whole
reason for that guarantee.
"""

from __future__ import annotations

import sqlglot
from sqlglot.optimizer.qualify import qualify

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES

DIALECT = "postgres"
SCHEMA = {
    "shop": {
        "orders": {"id": "INT", "cid": "INT", "total": "DECIMAL"},
        "items": {"oid": "INT", "qty": "INT"},
        "customers": {"id": "INT", "name": "TEXT"},
    }
}


def _qualified(sql: str) -> sqlglot.exp.Expression:
    return qualify(sqlglot.parse_one(sql, dialect=DIALECT), dialect=DIALECT, schema=SCHEMA,
                   identify=False)


def _apply(key: str, sql: str) -> str:
    rule = REWRITE_RULES.create(key)
    return str(rule.apply(_qualified(sql)).sql(dialect=DIALECT))


def test_the_registry_holds_exactly_the_four_rules() -> None:
    assert REWRITE_RULES.keys() == [
        "cte_materialization",
        "predicate_pushdown",
        "projection_pruning",
        "redundant_join_elimination",
    ]


def test_every_rule_reports_its_own_registry_key_as_its_name() -> None:
    for key in REWRITE_RULES.keys():
        assert REWRITE_RULES.create(key).name == key


def test_predicate_pushdown_moves_a_predicate_into_the_joined_subquery() -> None:
    rewritten = _apply(
        "predicate_pushdown",
        "SELECT o.id FROM shop.orders AS o "
        "JOIN (SELECT oid, qty FROM shop.items) AS i ON i.oid = o.id WHERE i.qty > 5",
    )

    # The predicate now sits inside the subquery, bound to the inner alias.
    assert "items.qty > 5" in rewritten
    assert rewritten.index("items.qty > 5") < rewritten.index("ON i.oid = o.id")


def test_predicate_pushdown_leaves_a_single_table_select_alone() -> None:
    sql = "SELECT o.id FROM shop.orders AS o WHERE o.total > 10"

    assert _apply("predicate_pushdown", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_cte_materialization_deduplicates_a_repeated_subquery_into_one_cte() -> None:
    rewritten = _apply(
        "cte_materialization",
        "SELECT a.id FROM (SELECT id FROM shop.orders) AS a "
        "JOIN (SELECT id FROM shop.orders) AS b ON a.id = b.id",
    )

    assert rewritten.startswith("WITH ")
    # One CTE, referenced twice — not two identical CTEs.
    assert rewritten.count(" AS (SELECT") == 1


def test_cte_materialization_leaves_a_statement_with_no_subquery_alone() -> None:
    sql = "SELECT o.id FROM shop.orders AS o"

    assert _apply("cte_materialization", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_projection_pruning_drops_a_column_the_outer_query_never_reads() -> None:
    rewritten = _apply(
        "projection_pruning",
        "SELECT x.id FROM (SELECT id, cid, total FROM shop.orders) AS x",
    )

    assert "cid" not in rewritten
    assert "total" not in rewritten
    assert "id" in rewritten


def test_projection_pruning_keeps_every_column_the_outer_query_reads() -> None:
    rewritten = _apply(
        "projection_pruning",
        "SELECT x.id, x.total FROM (SELECT id, cid, total FROM shop.orders) AS x",
    )

    assert "total" in rewritten
    assert "cid" not in rewritten


def test_redundant_join_elimination_is_a_no_op_when_uniqueness_is_unprovable() -> None:
    """sqlglot eliminates a join only when it can prove the joined relation is
    unique on the key from the query's own structure. A plain FK join carries
    no such proof, so declining is the correct, safe answer — and asserting it
    here documents the gap rather than leaving a silent surprise."""
    sql = "SELECT o.id FROM shop.orders AS o LEFT JOIN shop.customers AS c ON c.id = o.cid"

    assert _apply("redundant_join_elimination", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_redundant_join_elimination_removes_a_provably_unique_unused_join() -> None:
    rewritten = _apply(
        "redundant_join_elimination",
        "SELECT o.id FROM shop.orders AS o "
        "LEFT JOIN (SELECT id FROM shop.customers GROUP BY id) AS c ON c.id = o.cid",
    )

    assert "JOIN" not in rewritten


def test_every_rule_returns_the_input_unchanged_on_input_it_cannot_process() -> None:
    """The port's hard contract: a rule never raises and never returns None."""
    expression = sqlglot.parse_one("SELECT 1", dialect=DIALECT)

    for key in REWRITE_RULES.keys():
        result = REWRITE_RULES.create(key).apply(expression)
        assert result is not None
        assert isinstance(result, sqlglot.exp.Expression)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_rewrite_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.query.rewrite_rules'`

- [ ] **Step 3: Create the registry and the shared safety helper**

Create `genql/repositories/query/rewrite_rules/registry.py`:

```python
"""The rewrite-rule registry, keyed by rule name.

Mirrors GUARDRAILS and CANDIDATE_STRATEGIES: one file plus one decorator adds
a rule, and OptimizationService never names one.

`Registry.keys()` returns its keys *sorted*, so the pipeline runs
alphabetically — cte_materialization, predicate_pushdown, projection_pruning,
redundant_join_elimination — not in decorator order. That is acceptable only
because the pipeline is order-independent by construction: no rule re-creates
a pattern another one removes, which is also why it is a single pass rather
than a loop to a fixpoint. A rule that ever needs to run after another one
must instead be written to iterate internally.
"""

from __future__ import annotations

from genql.domain.ports.rewrite_rule import RewriteRule
from genql.registries.registry import Registry

REWRITE_RULES: Registry[RewriteRule] = Registry("rewrite_rules")
```

Create `genql/repositories/query/rewrite_rules/safe_apply.py`:

```python
"""One place where a sqlglot optimizer pass is made to honour the RewriteRule
contract.

The port promises a rule never raises and always returns an expression.
sqlglot's passes raise OptimizeError on input they cannot resolve — a
correlated reference they cannot scope, an unqualified column that survived
validation — and a rewrite that cannot run is not a turn-ending failure: the
statement is already correct, it just does not get faster. Swallowing here
keeps that judgment in one file instead of four.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError


def safe_apply(
    pass_fn: Callable[[exp.Expression], exp.Expression], expression: exp.Expression
) -> exp.Expression:
    try:
        return pass_fn(expression)
    except (OptimizeError, ParseError):
        return expression
```

- [ ] **Step 4: Create the four rules**

Create `genql/repositories/query/rewrite_rules/predicate_pushdown.py`:

```python
"""Push WHERE predicates down past joins and into subqueries.

sqlglot's own pass rather than hand-written AST surgery, for the reason the
plan's Deviation 1 gives: a rule that is not actually semantics-preserving
corrupts results silently, and the library's pass is the most tested version
of this transform available.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.pushdown_predicates import pushdown_predicates

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("predicate_pushdown")
class PredicatePushdownRule:
    name = "predicate_pushdown"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(lambda e: pushdown_predicates(e, dialect="postgres"), expression)
```

Create `genql/repositories/query/rewrite_rules/redundant_join_elimination.py`:

```python
"""Remove a joined relation nothing references and whose join cannot change
cardinality.

sqlglot proves "cannot change cardinality" from the query's own structure — a
GROUP BY or DISTINCT that makes the joined relation unique on the key — not
from GenQL's foreign-key metadata. On a plain FK join it therefore declines,
which is the safe answer and is asserted as a test rather than left to be
discovered. See the plan's "Deliberately Not Done".
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.eliminate_joins import eliminate_joins

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("redundant_join_elimination")
class RedundantJoinEliminationRule:
    name = "redundant_join_elimination"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(eliminate_joins, expression)
```

Create `genql/repositories/query/rewrite_rules/cte_materialization.py`:

```python
"""Lift derived tables into CTEs, deduplicating identical ones.

This is precisely the spec's "wraps a repeated subquery referenced more than
once in the same statement in a WITH CTE, so the planner does not re-evaluate
it": sqlglot's eliminate_subqueries rewrites every derived table as a CTE and
collapses duplicates into one.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.eliminate_subqueries import eliminate_subqueries

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("cte_materialization")
class CteMaterializationRule:
    name = "cte_materialization"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(eliminate_subqueries, expression)
```

Create `genql/repositories/query/rewrite_rules/projection_pruning.py`:

```python
"""Drop selected columns nothing downstream reads.

The `SELECT *` expansion half of the spec's projection_pruning is not here: it
happens in OptimizationService's schema-qualification step, before any rule
runs, because in sqlglot star expansion is what `qualify(schema=...)` does.
What remains — and what this rule is — is the unused-column removal.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.pushdown_projections import pushdown_projections

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("projection_pruning")
class ProjectionPruningRule:
    name = "projection_pruning"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(lambda e: pushdown_projections(e, dialect="postgres"), expression)
```

Create `genql/repositories/query/rewrite_rules/__init__.py`:

```python
"""Importing this package is what populates REWRITE_RULES.

Each module registers its rule with a decorator at import time, so the
registry is empty until every module below has been imported once. This is the
same pattern `genql/repositories/guardrails/__init__.py` uses.
"""

from genql.repositories.query.rewrite_rules import (  # noqa: F401 - registration side effect
    cte_materialization,
    predicate_pushdown,
    projection_pruning,
    redundant_join_elimination,
)
from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES

__all__ = ["REWRITE_RULES"]
```

- [ ] **Step 5: Run the rule tests**

Run: `uv run pytest tests/unit/test_rewrite_rules.py -q`
Expected: PASS (11 tests)

If `test_cte_materialization_deduplicates_a_repeated_subquery_into_one_cte` fails on the `count(" AS (SELECT")` assertion, print the actual rewritten SQL and adjust the assertion to match sqlglot's real output shape — assert the *behaviour* (one CTE definition, two references), never a brittle string. Do not change the rule to satisfy a string.

- [ ] **Step 6: Write the failing factory test**

Create `tests/unit/test_rewrite_rule_factory.py`:

```python
"""The factory is the only thing that reads the registry, so this is where the
"one file plus one decorator" claim is actually verified."""

from __future__ import annotations

from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory
from genql.infrastructure.query.rewrite_rule_factory import RewriteRuleFactoryImpl


def test_the_factory_satisfies_its_port() -> None:
    assert isinstance(RewriteRuleFactoryImpl(), RewriteRuleFactory)


def test_the_factory_returns_every_registered_rule_in_registry_order() -> None:
    names = [rule.name for rule in RewriteRuleFactoryImpl().rules()]

    assert names == [
        "cte_materialization",
        "predicate_pushdown",
        "projection_pruning",
        "redundant_join_elimination",
    ]


def test_the_factory_returns_fresh_instances_per_call() -> None:
    """Rules are stateless today, but the registry stores classes, and a rule
    that later holds per-call state must not be shared across turns."""
    first = RewriteRuleFactoryImpl().rules()
    second = RewriteRuleFactoryImpl().rules()

    assert first[0] is not second[0]
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/unit/test_rewrite_rule_factory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.infrastructure.query.rewrite_rule_factory'`

- [ ] **Step 8: Create the factory**

Create `genql/infrastructure/query/rewrite_rule_factory.py`:

```python
"""Builds the rewrite pipeline from REWRITE_RULES.

Importing `genql.repositories.query.rewrite_rules` is what populates the
registry. Nothing here names a rule class, so adding a rule is one new file
plus one decorator plus one import line in that package's `__init__` — never
an edit here. Mirrors GuardrailFactoryImpl exactly.
"""

from __future__ import annotations

from collections.abc import Sequence

import genql.repositories.query.rewrite_rules  # noqa: F401 - registration side effect
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES


class RewriteRuleFactoryImpl:
    def rules(self) -> Sequence[RewriteRule]:
        return [
            REWRITE_RULES.create(key)
            for key in REWRITE_RULES.keys()  # noqa: SIM118 - Registry, not a dict
        ]
```

- [ ] **Step 9: Register the package for import side effects**

Append to `genql/repositories/query/__init__.py`:

```python
from genql.repositories.query.rewrite_rules import REWRITE_RULES
```

and add `"REWRITE_RULES"` to its `__all__`.

- [ ] **Step 10: Run everything**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add genql/repositories/query genql/infrastructure/query/rewrite_rule_factory.py tests/unit/test_rewrite_rules.py tests/unit/test_rewrite_rule_factory.py
git commit -m "feat(query): add the rewrite-rule registry, four sqlglot-backed rules, and their factory"
```

---

### Task 4: The three optimizer repositories

**Files:**
- Create: `genql/repositories/query/cost_estimator_repository.py`, `genql/repositories/query/rewrite_outcome_repository.py`, `genql/repositories/query/index_recommender_repository.py`
- Test: `tests/integration/test_cost_estimator_repository.py`, `tests/integration/test_rewrite_outcome_repository.py`

**Interfaces:**
- Consumes: Task 1's `CostEstimator`, `ExecutionActualsReader`, `RewriteOutcomeWriter`, `IndexRecommender` ports and the `ExecutionActuals`, `RewriteOutcome`, `IndexRecommendation` entities; Task 2's `genql_rewrite_outcome` table; existing `genql.infrastructure.db.engine_provider.EngineProvider`, `genql.domain.ports.datasource_repository.DatasourceRepository`
- Produces: `PostgresCostEstimator(provider, datasources)` implementing both `CostEstimator` and `ExecutionActualsReader`; `PostgresRewriteOutcomeWriter(engine, datasources)`; `PostgresIndexRecommender(engine)`

- [ ] **Step 1: Read how the existing executor resolves a per-datasource read-only engine**

Run: `cat genql/infrastructure/query/query_executor_factory.py genql/infrastructure/db/engine_provider.py`

`PostgresCostEstimator` must use the **read-only** binding, exactly as `ReadOnlyQueryExecutorRepository` does. `EXPLAIN` without `ANALYZE` executes nothing, and `EXPLAIN (ANALYZE)` on a `SELECT` is still a read — but resolving the admin binding here would make the admin engine reachable from the query path, which is the property Phase 5 deliberately established.

- [ ] **Step 2: Write the failing cost-estimator integration test**

Create `tests/integration/test_cost_estimator_repository.py`:

```python
"""Estimated cost is a planner number, so the assertions are relative, never
absolute: a full scan of the largest fact table must estimate materially more
than the same query with a LIMIT. Asserting an absolute cost would encode this
machine's page counts into the suite."""

from __future__ import annotations

import pytest

from genql.domain.errors import CostEstimationError

pytestmark = pytest.mark.integration


def test_a_full_scan_estimates_more_than_the_same_query_limited(cost_estimator) -> None:
    full = cost_estimator.estimate("SELECT * FROM tpcds.store_sales", "local")
    limited = cost_estimator.estimate("SELECT * FROM tpcds.store_sales LIMIT 10", "local")

    assert full > limited


def test_estimating_never_executes_the_statement(cost_estimator) -> None:
    """A statement that would take minutes to run estimates instantly, which is
    only possible because EXPLAIN without ANALYZE does not run it."""
    cost = cost_estimator.estimate(
        "SELECT count(*) FROM tpcds.store_sales AS a, tpcds.store_sales AS b", "local"
    )

    assert cost > 0


def test_an_unparseable_statement_raises_a_typed_error(cost_estimator) -> None:
    with pytest.raises(CostEstimationError):
        cost_estimator.estimate("SELECT FROM WHERE", "local")


def test_reading_actuals_returns_measured_numbers(cost_estimator) -> None:
    actuals = cost_estimator.read_actuals("SELECT count(*) FROM tpcds.date_dim", "local")

    assert actuals.total_time_ms > 0
    assert actuals.rows >= 1
    assert actuals.shared_buffers_hit + actuals.shared_buffers_read > 0
```

Add a `cost_estimator` fixture to `tests/integration/conftest.py` built the same way the existing per-datasource fixtures are — read that file first and follow its established pattern rather than inventing a new one.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/integration/test_cost_estimator_repository.py -q`
Expected: FAIL — `ModuleNotFoundError`, or a clean skip without `GENQL_TEST_DSN`

- [ ] **Step 4: Create the cost estimator**

Create `genql/repositories/query/cost_estimator_repository.py`:

```python
"""EXPLAIN, in both of its forms, against a datasource's read-only binding.

One class implementing two ports. They share a connection path, a JSON plan
parser, and an error translation, and splitting them into two classes would
duplicate all three — but they are separate ports because their safety
profiles are opposite: `estimate` never runs the statement, `read_actuals`
runs it a second time. A caller holding only CostEstimator cannot reach the
expensive one.

`EXPLAIN (FORMAT JSON)` returns a single row holding a JSON array shaped
`[{"Plan": {...}}]`. psycopg decodes a json column into Python objects
already, but a driver or a server version that hands back the raw text is
cheap to tolerate, so both are handled.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.errors import CostEstimationError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.infrastructure.db.engine_provider import EngineProvider


def _plan(raw: Any) -> dict[str, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, list) or not payload:
        raise CostEstimationError(f"EXPLAIN returned an unexpected payload: {payload!r}")
    plan = payload[0].get("Plan")
    if not isinstance(plan, dict):
        raise CostEstimationError("EXPLAIN returned no Plan node")
    return plan


class PostgresCostEstimator:
    def __init__(self, provider: EngineProvider, datasources: DatasourceRepository) -> None:
        self._provider = provider
        self._datasources = datasources

    def estimate(self, sql: str, datasource_name: str) -> float:
        plan = self._explain(f"EXPLAIN (FORMAT JSON) {sql}", datasource_name)
        cost = plan.get("Total Cost")
        if not isinstance(cost, int | float):
            raise CostEstimationError("EXPLAIN returned no Total Cost")
        return float(cost)

    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        plan = self._explain(
            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", datasource_name
        )
        return ExecutionActuals(
            total_time_ms=float(plan.get("Actual Total Time", 0.0)),
            rows=int(plan.get("Actual Rows", 0)),
            shared_buffers_hit=int(plan.get("Shared Hit Blocks", 0)),
            shared_buffers_read=int(plan.get("Shared Read Blocks", 0)),
        )

    def _explain(self, statement: str, datasource_name: str) -> dict[str, Any]:
        datasource = self._datasources.get(datasource_name)
        engine = self._provider.readonly_engine(datasource)
        try:
            with engine.begin() as conn:
                raw = conn.execute(text(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise CostEstimationError(f"EXPLAIN failed: {exc}") from exc
        return _plan(raw)
```

If `EngineProvider`'s read-only accessor is named something other than `readonly_engine`, use the real name — Step 1 is where you learn it. Do not add a method to `EngineProvider`.

- [ ] **Step 5: Write the failing outcome-writer integration test**

Create `tests/integration/test_rewrite_outcome_repository.py`:

```python
"""A round trip through the table, then one aggregation over it. The
recommender's own SQL is what turns rows into advice, so it is exercised
against rows this test inserts rather than against a fixture of its output."""

from __future__ import annotations

import pytest

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.rewrite_outcome import RewriteOutcome

pytestmark = pytest.mark.integration


def _outcome(sql_hash: str, reads: int) -> RewriteOutcome:
    return RewriteOutcome(
        sql_hash=sql_hash,
        datasource_name="local",
        rules_applied=("predicate_pushdown",),
        estimated_cost=1234.5,
        actuals=ExecutionActuals(
            total_time_ms=42.0, rows=10, shared_buffers_hit=5, shared_buffers_read=reads
        ),
    )


def test_writing_an_outcome_persists_every_field(rewrite_outcome_writer, semantic_engine) -> None:
    rewrite_outcome_writer.write(_outcome("a" * 64, 900))

    with semantic_engine.begin() as conn:
        row = conn.exec_driver_sql(
            "SELECT sql_hash, rules_applied, estimated_cost, actual_total_time_ms, "
            "shared_buffers_read FROM genql.genql_rewrite_outcome WHERE sql_hash = %s",
            ("a" * 64,),
        ).one()

    assert row.sql_hash == "a" * 64
    assert row.rules_applied == ["predicate_pushdown"]
    assert row.estimated_cost == pytest.approx(1234.5)
    assert row.shared_buffers_read == 900


def test_writing_an_outcome_for_an_unknown_datasource_raises(rewrite_outcome_writer) -> None:
    from genql.domain.errors import UnknownDatasourceError

    outcome = _outcome("b" * 64, 1).model_copy(update={"datasource_name": "nope"})
    with pytest.raises(UnknownDatasourceError):
        rewrite_outcome_writer.write(outcome)
```

Add `rewrite_outcome_writer` and `semantic_engine` fixtures following `tests/integration/conftest.py`'s existing conventions (`semantic_engine` may already exist — check before adding).

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/integration/test_rewrite_outcome_repository.py -q`
Expected: FAIL — `ModuleNotFoundError`, or a clean skip

- [ ] **Step 7: Create the outcome writer and the index recommender**

Create `genql/repositories/query/rewrite_outcome_repository.py`:

```python
"""Appends one measured execution.

The entity carries `datasource_name` and the table stores `datasource_id`, so
the name is resolved here rather than by the service: a service that knew the
integer key would be holding a persistence detail.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.errors import OptimizationError
from genql.domain.ports.datasource_repository import DatasourceRepository

_INSERT = text("""
    INSERT INTO genql.genql_rewrite_outcome
        (sql_hash, datasource_id, rules_applied, estimated_cost, actual_total_time_ms,
         actual_rows, shared_buffers_hit, shared_buffers_read)
    VALUES
        (:sql_hash, :datasource_id, :rules_applied, :estimated_cost, :actual_total_time_ms,
         :actual_rows, :shared_buffers_hit, :shared_buffers_read)
""")


class PostgresRewriteOutcomeWriter:
    def __init__(self, engine: Engine, datasources: DatasourceRepository) -> None:
        self._engine = engine
        self._datasources = datasources

    def write(self, outcome: RewriteOutcome) -> None:
        datasource = self._datasources.get(outcome.datasource_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "sql_hash": outcome.sql_hash,
                        "datasource_id": datasource.id,
                        "rules_applied": list(outcome.rules_applied),
                        "estimated_cost": outcome.estimated_cost,
                        "actual_total_time_ms": outcome.actuals.total_time_ms,
                        "actual_rows": outcome.actuals.rows,
                        "shared_buffers_hit": outcome.actuals.shared_buffers_hit,
                        "shared_buffers_read": outcome.actuals.shared_buffers_read,
                    },
                )
        except SQLAlchemyError as exc:
            raise OptimizationError(f"failed to record a rewrite outcome: {exc}") from exc
```

If `Datasource` exposes its primary key under a name other than `id`, use the real attribute.

Create `genql/repositories/query/index_recommender_repository.py`:

```python
"""Turns accumulated outcomes into index advice for a human.

The signal is buffer *reads* (pages fetched from disk) rather than total time:
time varies with cache state and concurrency, while a statement that
repeatedly reads many pages is repeatedly scanning something. The threshold
lives in the SQL rather than in configuration because it is a property of what
"repeatedly scanning" means, not a knob an operator should be tuning before
there is evidence about what a good value is.

Columns come from parsing each recorded statement's WHERE clause with sqlglot,
not from the plan text: the plan names a filter expression, the AST names the
column, and only the second can be joined against the catalog.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.errors import OptimizationError

_MIN_EXECUTIONS = 3
_MIN_BUFFER_READS = 1_000

_SELECT_HEAVY = text("""
    SELECT o.sql_hash, count(*) AS executions, max(o.shared_buffers_read) AS reads
    FROM genql.genql_rewrite_outcome o
    JOIN genql.genql_datasource d ON d.id = o.datasource_id
    WHERE d.name = :datasource_name AND o.shared_buffers_read >= :min_reads
    GROUP BY o.sql_hash
    HAVING count(*) >= :min_executions
    ORDER BY max(o.shared_buffers_read) DESC
""")

_SELECT_STATEMENTS = text("""
    SELECT DISTINCT sql_hash FROM genql.genql_rewrite_outcome WHERE sql_hash = ANY(:hashes)
""")


class PostgresIndexRecommender:
    """Reads evidence and proposes indexes. Never creates one — the parent
    spec's §11 is explicit that GenQL reports and a human acts."""

    def __init__(self, engine: Engine, statements: dict[str, str] | None = None) -> None:
        # `statements` maps sql_hash -> statement text. The outcome table
        # stores the hash, not the text, so the recommender is constructed
        # with whatever the caller can supply; an empty map yields no
        # recommendations rather than a wrong one.
        self._engine = engine
        self._statements = statements or {}

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(
                    _SELECT_HEAVY,
                    {
                        "datasource_name": datasource_name,
                        "min_reads": _MIN_BUFFER_READS,
                        "min_executions": _MIN_EXECUTIONS,
                    },
                ).all()
        except SQLAlchemyError as exc:
            raise OptimizationError(f"failed to read rewrite outcomes: {exc}") from exc

        recommendations: list[IndexRecommendation] = []
        for row in rows:
            statement = self._statements.get(row.sql_hash)
            if statement is None:
                continue
            for table, column in _filtered_columns(statement):
                recommendations.append(
                    IndexRecommendation(
                        object_qualified_name=f"{datasource_name}.{table}",
                        column_name=column,
                        rationale=(
                            f"{row.executions} recorded executions filtered this column while "
                            f"reading {row.reads} shared buffer pages from disk"
                        ),
                        supporting_execution_count=int(row.executions),
                    )
                )
        return tuple(recommendations)


def _filtered_columns(statement: str) -> list[tuple[str, str]]:
    try:
        expression = sqlglot.parse_one(statement, dialect="postgres")
    except sqlglot.errors.ParseError:
        return []
    found: list[tuple[str, str]] = []
    for where in expression.find_all(exp.Where):
        for column in where.find_all(exp.Column):
            table = column.table or ""
            if table and column.name:
                found.append((table, column.name))
    return found
```

**Note for the implementer:** the `statements` map is the honest shape of this repository given that the table stores only a hash. Task 7 is where the recording service decides what to pass; on a fresh installation the map is empty and `recommend` correctly returns nothing, which is exactly what the CLI's "no recommendations yet" branch prints.

- [ ] **Step 8: Run the integration tests and the full unit suite**

Run: `uv run pytest tests/integration/test_cost_estimator_repository.py tests/integration/test_rewrite_outcome_repository.py -q; uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run lint-imports`
Expected: integration PASS or clean skip; unit PASS; all static checks clean

- [ ] **Step 9: Commit**

```bash
git add genql/repositories/query tests/integration/test_cost_estimator_repository.py tests/integration/test_rewrite_outcome_repository.py tests/integration/conftest.py
git commit -m "feat(query): add the EXPLAIN cost estimator, outcome writer, and index recommender"
```

---

### Task 5: `LlmQueryDecomposer`

**Files:**
- Create: `genql/services/query/query_decomposer.py`
- Test: `tests/unit/test_query_decomposer.py`, `tests/integration/test_query_decomposer_real_provider.py`

**Interfaces:**
- Consumes: Task 1's `QueryDecomposer` port; existing `genql.domain.ports.chat_provider.ChatProvider`, `genql.domain.entities.query_plan.QueryPlan`
- Produces: `LlmQueryDecomposer(chat)` with `decompose(plan, sql, estimated_cost, budget) -> str`

- [ ] **Step 1: Read the prompt conventions of the existing adapter**

Run: `cat genql/services/query/probe_designer.py`

Match its shape exactly: a module-level prompt constant, a single `chat.complete(...)` call, structured-output parsing, and **no** wrapping of `ChatProviderError` — Phase 6.5's Deviation 7 established that a provider failure in an adapter propagates as itself.

- [ ] **Step 2: Write the failing unit test**

Create `tests/unit/test_query_decomposer.py`:

```python
"""Three behaviours: the prompt carries the numbers the model needs to narrow
by the right amount, the returned SQL is unwrapped from any markdown fence,
and a provider that returns nothing usable yields the original statement
rather than an empty one — an empty statement would fail cost estimation and
turn a recoverable over-budget turn into a crash."""

from __future__ import annotations

from genql.domain.entities.query_plan import QueryPlan
from genql.services.query.query_decomposer import LlmQueryDecomposer

PLAN = QueryPlan(
    question="total sales by month",
    plan_text="sum ss_ext_sales_price grouped by month",
    referenced_objects=("local.tpcds.store_sales",),
)
SQL = "SELECT sum(ss_ext_sales_price) FROM tpcds.store_sales"


class _Chat:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs: object) -> str:
        self.prompts.append(prompt)
        return self.reply


def test_the_prompt_carries_the_statement_the_cost_and_the_budget() -> None:
    chat = _Chat("SELECT 1")
    LlmQueryDecomposer(chat).decompose(PLAN, SQL, 500_000.0, 100_000.0)

    prompt = chat.prompts[0]
    assert SQL in prompt
    assert "500000" in prompt.replace(",", "").replace(".0", "")
    assert "100000" in prompt.replace(",", "").replace(".0", "")
    assert PLAN.plan_text in prompt


def test_a_fenced_reply_is_unwrapped_to_bare_sql() -> None:
    chat = _Chat("```sql\nSELECT 1 LIMIT 10\n```")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == "SELECT 1 LIMIT 10"


def test_an_empty_reply_yields_the_original_statement() -> None:
    chat = _Chat("   ")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == SQL


def test_a_reply_that_is_not_a_select_yields_the_original_statement() -> None:
    """The decomposed statement goes straight to cost estimation and then to
    guarded execution. A DELETE here would be caught by the guardrails, but
    refusing it at the source keeps the failure legible."""
    chat = _Chat("DELETE FROM tpcds.store_sales")

    assert LlmQueryDecomposer(chat).decompose(PLAN, SQL, 5.0, 1.0) == SQL
```

Match `_Chat.complete`'s real signature to `ChatProvider`'s — read `genql/domain/ports/chat_provider.py` in Step 1 and mirror it exactly.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_decomposer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.query_decomposer'`

- [ ] **Step 4: Implement the decomposer**

Create `genql/services/query/query_decomposer.py`:

```python
"""The one LLM call Phase 7 makes, spent at most once per turn.

It is asked to narrow, never to rewrite for speed: the static rules already
did every transform that is provably safe, so what is left is a semantic
decision — a shorter date range, a filter the plan implies but the SQL did not
state — that only a model reading the plan can make.

Every unusable reply falls back to the original statement rather than raising.
The caller has already decided this query is over budget; a failed narrowing
attempt means it stays over budget and the user gets a suggestion, which is a
worse outcome than a narrowed query but a much better one than a crashed turn.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.ports.chat_provider import ChatProvider

_PROMPT = """You are narrowing a SQL statement that is too expensive to run.

The user asked: {question}

The plan the statement implements:
{plan_text}

The statement:
{sql}

Its estimated planner cost is {estimated_cost:.0f}, and the budget is {budget:.0f}.

Return ONE SELECT statement that answers the same question over a smaller slice
of data — a narrower date range, a more selective filter the plan implies, or a
smaller grain. Do not change which columns are returned. Do not add a LIMIT.
Reply with the SQL only, no explanation and no markdown fence."""


def _unfence(reply: str) -> str:
    text = reply.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _is_select(sql: str) -> bool:
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError:
        return False
    return isinstance(parsed, exp.Select | exp.Subquery) or bool(parsed.find(exp.Select))


class LlmQueryDecomposer:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def decompose(
        self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float
    ) -> str:
        reply = self._chat.complete(
            _PROMPT.format(
                question=plan.question,
                plan_text=plan.plan_text,
                sql=sql,
                estimated_cost=estimated_cost,
                budget=budget,
            )
        )
        candidate = _unfence(reply)
        if not candidate or not _is_select(candidate):
            return sql
        return candidate
```

Adjust the `self._chat.complete(...)` call to `ChatProvider`'s real signature.

- [ ] **Step 5: Run the unit test**

Run: `uv run pytest tests/unit/test_query_decomposer.py -q`
Expected: PASS (4 tests)

- [ ] **Step 6: Write the gated real-provider test**

Create `tests/integration/test_query_decomposer_real_provider.py`, modelled on `tests/integration/test_probe_designer_real_provider.py` — read that file and copy its skip guard exactly. Assert only that the reply parses as a `SELECT` and differs from the input; never assert specific SQL text from a live model.

- [ ] **Step 7: Run everything**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run lint-imports`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add genql/services/query/query_decomposer.py tests/unit/test_query_decomposer.py tests/integration/test_query_decomposer_real_provider.py
git commit -m "feat(query): add the LLM query decomposer for over-budget statements"
```

---
### Task 6: `OptimizationService`

**Files:**
- Create: `genql/services/query/optimization_service.py`
- Test: `tests/unit/test_optimization_service.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 5 — `RewriteRuleFactory`, `CostEstimator`, `QueryDecomposer`, `OptimizationResult`, `SchemaLink`, `QueryPlan`
- Produces: `OptimizationService(rules, estimator, decomposer, budget)` with `optimize(plan, sql, links, datasource_name) -> OptimizationResult`

**Signature note:** Phase 7's spec §6 writes `optimize(plan, sql, datasource_name)`. This plan adds `links` as the third parameter, because the plan's Deviation 2 makes the sqlglot schema — which is built from `SchemaLink.column_names` — a correctness requirement rather than an optimization. `QueryState` already carries `links`, so the node has it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_optimization_service.py`:

```python
"""Every branch of the gate, against fakes. The three that matter most:
within-budget after static rewriting never calls the decomposer (it is the
only LLM call in the phase and it must stay demand-driven), an over-budget
query that decomposition rescues reports the decomposed statement, and one
decomposition cannot rescue returns a suggestion rather than raising."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlglot import exp

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import CostEstimationError
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.services.query.optimization_service import OptimizationService

PLAN = QueryPlan(
    question="q", plan_text="p", referenced_objects=("local.shop.orders",)
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.orders",
        column_names=("id", "cid", "total"),
    ),
)
SQL = "SELECT id FROM shop.orders WHERE total > 10"


class _LimitRule:
    """Changes the statement, so OptimizationService must record it as fired."""

    name = "adds_a_limit"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression.limit(100)


class _NoopRule:
    name = "does_nothing"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return expression


class _Factory:
    def __init__(self, *rules: RewriteRule) -> None:
        self._rules = rules

    def rules(self) -> Sequence[RewriteRule]:
        return self._rules


class _Estimator:
    def __init__(self, *costs: float) -> None:
        self._costs = list(costs)
        self.calls: list[str] = []

    def estimate(self, sql: str, datasource_name: str) -> float:
        self.calls.append(sql)
        return self._costs.pop(0) if self._costs else 1.0


class _RaisingEstimator:
    def __init__(self, first: float) -> None:
        self._first = first
        self.calls = 0

    def estimate(self, sql: str, datasource_name: str) -> float:
        self.calls += 1
        if self.calls == 1:
            return self._first
        raise CostEstimationError("boom")


class _Decomposer:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str:
        self.calls += 1
        return self.reply


def _service(factory, estimator, decomposer, budget=100.0) -> OptimizationService:
    return OptimizationService(
        rules=factory, estimator=estimator, decomposer=decomposer, budget=budget
    )


def test_a_rule_that_changes_the_statement_is_recorded_as_applied() -> None:
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.rules_applied == ("adds_a_limit",)
    assert "LIMIT 100" in result.sql


def test_a_rule_that_changes_nothing_is_not_recorded() -> None:
    service = _service(_Factory(_NoopRule()), _Estimator(10.0), _Decomposer(SQL))

    assert service.optimize(PLAN, SQL, LINKS, "local").rules_applied == ()


def test_a_within_budget_statement_never_calls_the_decomposer() -> None:
    decomposer = _Decomposer(SQL)
    service = _service(_Factory(_NoopRule()), _Estimator(10.0), decomposer)

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is True
    assert result.narrowing_suggestion is None
    assert decomposer.calls == 0


def test_an_over_budget_statement_decomposition_rescues_is_within_budget() -> None:
    decomposer = _Decomposer("SELECT id FROM shop.orders WHERE total > 1000")
    # First estimate: over budget. Second (the decomposed statement): under.
    service = _service(_Factory(_NoopRule()), _Estimator(5_000.0, 50.0), decomposer)

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is True
    assert result.estimated_cost == 50.0
    assert result.sql == "SELECT id FROM shop.orders WHERE total > 1000"
    assert decomposer.calls == 1


def test_decomposition_is_attempted_exactly_once() -> None:
    decomposer = _Decomposer(SQL)
    service = _service(_Factory(_NoopRule()), _Estimator(5_000.0, 4_000.0), decomposer)

    service.optimize(PLAN, SQL, LINKS, "local")

    assert decomposer.calls == 1


def test_a_statement_still_over_budget_returns_a_suggestion_and_never_raises() -> None:
    service = _service(
        _Factory(_NoopRule()), _Estimator(5_000.0, 4_000.0), _Decomposer(SQL), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.within_budget is False
    assert result.narrowing_suggestion is not None
    assert "40" in result.narrowing_suggestion  # 4000 / 100 = 40x the budget


def test_a_decomposition_that_costs_more_is_discarded() -> None:
    service = _service(
        _Factory(_NoopRule()), _Estimator(5_000.0, 9_000.0), _Decomposer("SELECT 1"), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.estimated_cost == 5_000.0
    assert result.sql != "SELECT 1"


def test_a_failed_estimate_of_the_decomposed_statement_keeps_the_rewritten_one() -> None:
    service = _service(
        _Factory(_NoopRule()), _RaisingEstimator(5_000.0), _Decomposer("SELECT 1"), budget=100.0
    )

    result = service.optimize(PLAN, SQL, LINKS, "local")

    assert result.estimated_cost == 5_000.0
    assert result.within_budget is False


def test_a_statement_that_cannot_be_qualified_is_cost_gated_without_rewriting() -> None:
    """A column no link declares makes qualification raise. The statement is
    already valid — static validation passed it — so it must still be gated,
    just not rewritten."""
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(
        PLAN, "SELECT unknown_column FROM shop.orders", LINKS, "local"
    )

    assert result.rules_applied == ()
    assert result.sql == "SELECT unknown_column FROM shop.orders"
    assert result.within_budget is True


def test_an_unparseable_statement_is_cost_gated_without_rewriting() -> None:
    service = _service(_Factory(_LimitRule()), _Estimator(10.0), _Decomposer(SQL))

    result = service.optimize(PLAN, "SELECT FROM WHERE", LINKS, "local")

    assert result.rules_applied == ()
    assert result.sql == "SELECT FROM WHERE"


def test_a_cost_estimation_failure_on_the_first_estimate_propagates() -> None:
    """Unlike the decomposed statement's estimate, this one has no fallback:
    a gate that cannot estimate at all has not gated anything, and silently
    executing would defeat the stage."""

    class _AlwaysRaises:
        def estimate(self, sql: str, datasource_name: str) -> float:
            raise CostEstimationError("boom")

    service = _service(_Factory(_NoopRule()), _AlwaysRaises(), _Decomposer(SQL))

    with pytest.raises(CostEstimationError):
        service.optimize(PLAN, SQL, LINKS, "local")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_optimization_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.optimization_service'`

- [ ] **Step 3: Implement the service**

Create `genql/services/query/optimization_service.py`:

```python
"""The rewrite-and-cost-gate stage: the parent spec's §11, first two
sub-phases.

Qualification comes first and is not optional. sqlglot's optimizer passes
assume every column is bound to a relation; given an unqualified tree, the
predicate-pushdown pass will happily move a predicate into a subquery while
leaving it pointing at the *outer* alias, producing invalid SQL. Qualifying
against a schema built from the turn's SchemaLinks is what makes the passes
safe, and it is also what expands `SELECT *` into a real column list.

When qualification fails — a column no link declared, a statement sqlglot
cannot parse — this stage rewrites nothing and gates the original statement.
That is deliberate: static validation already passed the statement, so it is
correct; it simply does not get faster. Refusing to gate it would be worse
than not rewriting it.

A rule is recorded as applied when it changed the *rendered SQL*, not when it
returned a different object: sqlglot's passes mutate the tree in place and
return the same instance.

The single decomposition attempt is the only model call this stage makes, and
it is reached only when static rewriting left the statement over budget.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlglot
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import CostEstimationError
from genql.domain.ports.cost_estimator import CostEstimator
from genql.domain.ports.query_decomposer import QueryDecomposer
from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory

_DIALECT = "postgres"


def _schema_of(links: Sequence[SchemaLink]) -> dict[str, dict[str, dict[str, str]]]:
    """`{schema: {object: {column: type}}}`, the shape sqlglot's qualifier wants.

    Every column is typed UNKNOWN: qualification binds names to relations and
    expands stars, and none of that needs real types. Claiming types GenQL has
    not verified would be the only way this could be wrong.
    """
    schema: dict[str, dict[str, dict[str, str]]] = {}
    for link in links:
        schema_name, _, object_name = link.schema_qualified_name.partition(".")
        if not object_name:
            continue
        schema.setdefault(schema_name, {})[object_name] = dict.fromkeys(
            link.column_names, "UNKNOWN"
        )
    return schema


def _suggestion(cost: float, budget: float) -> str:
    ratio = cost / budget if budget > 0 else float("inf")
    return (
        f"this query's estimated cost is {ratio:.0f}x the configured budget, so it was not "
        "run — narrow the date range, add a more selective filter, or ask for a coarser grain"
    )


class OptimizationService:
    def __init__(
        self,
        rules: RewriteRuleFactory,
        estimator: CostEstimator,
        decomposer: QueryDecomposer,
        budget: float,
    ) -> None:
        self._rules = rules
        self._estimator = estimator
        self._decomposer = decomposer
        self._budget = budget

    def optimize(
        self,
        plan: QueryPlan,
        sql: str,
        links: Sequence[SchemaLink],
        datasource_name: str,
    ) -> OptimizationResult:
        rewritten, applied = self._rewrite(sql, links)
        cost = self._estimator.estimate(rewritten, datasource_name)
        if cost <= self._budget:
            return OptimizationResult(
                sql=rewritten,
                rules_applied=applied,
                estimated_cost=cost,
                within_budget=True,
            )
        return self._decompose(plan, rewritten, applied, cost, datasource_name)

    def _rewrite(self, sql: str, links: Sequence[SchemaLink]) -> tuple[str, tuple[str, ...]]:
        try:
            expression = qualify(
                sqlglot.parse_one(sql, dialect=_DIALECT),
                dialect=_DIALECT,
                schema=_schema_of(links),
                identify=False,
            )
        except (ParseError, OptimizeError):
            return sql, ()

        applied: list[str] = []
        for rule in self._rules.rules():
            before = expression.sql(dialect=_DIALECT)
            expression = rule.apply(expression)
            if expression.sql(dialect=_DIALECT) != before:
                applied.append(rule.name)
        return str(expression.sql(dialect=_DIALECT)), tuple(applied)

    def _decompose(
        self,
        plan: QueryPlan,
        sql: str,
        applied: tuple[str, ...],
        cost: float,
        datasource_name: str,
    ) -> OptimizationResult:
        candidate = self._decomposer.decompose(plan, sql, cost, self._budget)
        best_sql, best_cost = sql, cost
        if candidate != sql:
            try:
                candidate_cost = self._estimator.estimate(candidate, datasource_name)
            except CostEstimationError:
                candidate_cost = None
            if candidate_cost is not None and candidate_cost < cost:
                best_sql, best_cost = candidate, candidate_cost

        within = best_cost <= self._budget
        return OptimizationResult(
            sql=best_sql,
            rules_applied=applied,
            estimated_cost=best_cost,
            within_budget=within,
            narrowing_suggestion=None if within else _suggestion(best_cost, self._budget),
        )
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_optimization_service.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Run everything**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add genql/services/query/optimization_service.py tests/unit/test_optimization_service.py
git commit -m "feat(query): add OptimizationService — schema-qualified rewriting behind a cost gate"
```

---

### Task 7: `RewriteOutcomeRecordingService` and `IndexRecommendationService`

**Files:**
- Create: `genql/services/query/rewrite_recording_service.py`, `genql/services/query/index_recommendation_service.py`
- Test: `tests/unit/test_rewrite_recording_service.py`, `tests/unit/test_index_recommendation_service.py`

**Interfaces:**
- Consumes: Task 1's `ExecutionActualsReader`, `RewriteOutcomeWriter`, `IndexRecommender`, `RewriteOutcome`, `IndexRecommendation`
- Produces: `RewriteOutcomeRecordingService(actuals, writer)` with `record(sql, rules_applied, estimated_cost, datasource_name) -> None`; `IndexRecommendationService(recommender)` with `recommend(datasource_name) -> tuple[IndexRecommendation, ...]`

- [ ] **Step 1: Write the failing recording test**

Create `tests/unit/test_rewrite_recording_service.py`:

```python
"""The hash is the identity the recommender later aggregates on, so it is
asserted directly. Failure handling lives at the call site (the node), not
here — this service is allowed to raise, and the node is where the
"diagnostics must never fail a successful turn" rule is enforced."""

from __future__ import annotations

import hashlib

import pytest

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService

SQL = "SELECT count(*) FROM tpcds.store_sales"
ACTUALS = ExecutionActuals(
    total_time_ms=88.0, rows=1, shared_buffers_hit=10, shared_buffers_read=2000
)


class _Reader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        self.calls.append((sql, datasource_name))
        return ACTUALS


class _Writer:
    def __init__(self) -> None:
        self.written: list[RewriteOutcome] = []

    def write(self, outcome: RewriteOutcome) -> None:
        self.written.append(outcome)


class _RaisingReader:
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        raise RuntimeError("explain analyze failed")


def test_recording_hashes_the_executed_statement() -> None:
    writer = _Writer()
    RewriteOutcomeRecordingService(_Reader(), writer).record(
        SQL, ("predicate_pushdown",), 1234.0, "local"
    )

    assert writer.written[0].sql_hash == hashlib.sha256(SQL.encode()).hexdigest()


def test_recording_carries_the_rules_and_the_estimate_beside_the_actuals() -> None:
    writer = _Writer()
    RewriteOutcomeRecordingService(_Reader(), writer).record(
        SQL, ("predicate_pushdown", "projection_pruning"), 1234.0, "local"
    )

    outcome = writer.written[0]
    assert outcome.rules_applied == ("predicate_pushdown", "projection_pruning")
    assert outcome.estimated_cost == 1234.0
    assert outcome.actuals.shared_buffers_read == 2000
    assert outcome.datasource_name == "local"


def test_the_actuals_are_measured_against_the_statement_that_ran() -> None:
    reader = _Reader()
    RewriteOutcomeRecordingService(reader, _Writer()).record(SQL, (), 1.0, "local")

    assert reader.calls == [(SQL, "local")]


def test_a_reader_failure_propagates_for_the_caller_to_swallow() -> None:
    with pytest.raises(RuntimeError):
        RewriteOutcomeRecordingService(_RaisingReader(), _Writer()).record(SQL, (), 1.0, "local")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_rewrite_recording_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the recording service**

Create `genql/services/query/rewrite_recording_service.py`:

```python
"""Post-execution learning: what the planner predicted, beside what happened.

Reached only when `Settings.record_execution_actuals` is true, because
`EXPLAIN (ANALYZE, BUFFERS)` genuinely re-runs the statement — recording every
turn would double warehouse load for a diagnostic.

This service does not catch. Its caller (GuardedExecutionNode) does, because
the rule being enforced there is "a diagnostic must never fail a turn whose
query already succeeded", and that is a property of the call site, not of the
recording.
"""

from __future__ import annotations

import hashlib

from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.ports.execution_actuals_reader import ExecutionActualsReader
from genql.domain.ports.rewrite_outcome_writer import RewriteOutcomeWriter


class RewriteOutcomeRecordingService:
    def __init__(self, actuals: ExecutionActualsReader, writer: RewriteOutcomeWriter) -> None:
        self._actuals = actuals
        self._writer = writer

    def record(
        self,
        sql: str,
        rules_applied: tuple[str, ...],
        estimated_cost: float,
        datasource_name: str,
    ) -> None:
        measured = self._actuals.read_actuals(sql, datasource_name)
        self._writer.write(
            RewriteOutcome(
                sql_hash=hashlib.sha256(sql.encode()).hexdigest(),
                datasource_name=datasource_name,
                rules_applied=rules_applied,
                estimated_cost=estimated_cost,
                actuals=measured,
            )
        )
```

- [ ] **Step 4: Write the failing recommendation test**

Create `tests/unit/test_index_recommendation_service.py`:

```python
"""One line of logic, and it is the ordering an operator reads top-down."""

from __future__ import annotations

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.services.query.index_recommendation_service import IndexRecommendationService


def _rec(column: str, count: int) -> IndexRecommendation:
    return IndexRecommendation(
        object_qualified_name="local.tpcds.store_sales",
        column_name=column,
        rationale="r",
        supporting_execution_count=count,
    )


class _Recommender:
    def __init__(self, *recs: IndexRecommendation) -> None:
        self._recs = recs

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return self._recs


def test_recommendations_are_ranked_by_supporting_evidence_descending() -> None:
    service = IndexRecommendationService(_Recommender(_rec("a", 2), _rec("b", 9), _rec("c", 5)))

    assert [r.column_name for r in service.recommend("local")] == ["b", "c", "a"]


def test_ties_are_broken_by_column_name_so_output_is_stable() -> None:
    service = IndexRecommendationService(_Recommender(_rec("z", 3), _rec("a", 3)))

    assert [r.column_name for r in service.recommend("local")] == ["a", "z"]


def test_no_evidence_yields_no_recommendations() -> None:
    assert IndexRecommendationService(_Recommender()).recommend("local") == ()
```

- [ ] **Step 5: Run to verify it fails**

Run: `uv run pytest tests/unit/test_index_recommendation_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 6: Implement the recommendation service**

Create `genql/services/query/index_recommendation_service.py`:

```python
"""Ranks index recommendations for the operator who will act on them.

A service for one line of sorting, rather than the CLI calling the port
directly, because "controllers hold no business logic" is a rule the codebase
keeps without exception — and because the tie-break is a real decision: equal
evidence sorts by column name so that two runs over the same data print the
same order.
"""

from __future__ import annotations

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.ports.index_recommender import IndexRecommender


class IndexRecommendationService:
    def __init__(self, recommender: IndexRecommender) -> None:
        self._recommender = recommender

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return tuple(
            sorted(
                self._recommender.recommend(datasource_name),
                key=lambda r: (-r.supporting_execution_count, r.column_name),
            )
        )
```

- [ ] **Step 7: Run everything**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run lint-imports`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add genql/services/query/rewrite_recording_service.py genql/services/query/index_recommendation_service.py tests/unit/test_rewrite_recording_service.py tests/unit/test_index_recommendation_service.py
git commit -m "feat(query): record execution actuals and rank index recommendations"
```

---
### Task 8: `QueryState`, `TurnResponse`, the gate node, and the graph edge

**Files:**
- Create: `genql/api/query_optimizer_nodes.py`, `tests/unit/test_query_optimizer_nodes.py`
- Modify: `genql/api/query_state.py`, `genql/api/query_graph.py`, `genql/api/query_nodes.py`, `genql/api/query_turn.py`, `genql/domain/entities/turn_response.py`
- Test: `tests/unit/test_query_optimizer_nodes.py`, plus the existing `tests/unit/test_query_graph*.py` and `tests/unit/test_query_turn*.py` (find them with `ls tests/unit | grep -E 'graph|turn'`)

**Interfaces:**
- Consumes: Task 6's `OptimizationService`, Task 7's `RewriteOutcomeRecordingService`, Task 1's `OptimizationResult`
- Produces: `QueryState["optimization"]: OptimizationResult | None`; `TurnResponse.narrowing_suggestion: str | None`, `TurnResponse.rewrite_rules_applied: tuple[str, ...]`; `RewriteAndCostGateNode(service)`; graph constant `REWRITE_AND_COST_GATE = "rewrite_and_cost_gate"` and router `route_after_cost_gate`; `GuardedExecutionNode(service, recorder=None)`

- [ ] **Step 1: Write the failing node test**

Create `tests/unit/test_query_optimizer_nodes.py`:

```python
"""The gate node and the recorder hook on GuardedExecutionNode.

The property that matters most is the last one: a recorder that explodes must
not fail a turn whose query already returned rows. Recording is a diagnostic,
and a diagnostic that can break a successful answer is worse than no
diagnostic."""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_nodes import GuardedExecutionNode
from genql.api.query_optimizer_nodes import RewriteAndCostGateNode
from genql.api.query_state import initial_state
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import OptimizationError

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1", plan=PLAN)
SELECTION = CandidateSelection(
    selected=CANDIDATE,
    selected_sql="SELECT id FROM shop.orders",
    method="single_survivor",
    rationale="r",
)
RESULT = ExecutionResult(columns=("id",), rows=((1,),), row_count=1, truncated=False)


def _state(**overrides: Any) -> Any:
    state = initial_state("q", "local", "t-1")
    state["plan"] = PLAN
    state["links"] = (SchemaLink(object_qualified_name="local.shop.orders"),)
    state["selection"] = SELECTION
    state["validated_sql"] = SELECTION.selected_sql
    state.update(overrides)
    return state


class _Service:
    def __init__(self, result: OptimizationResult) -> None:
        self.result = result
        self.calls = 0

    def optimize(self, plan, sql, links, datasource_name):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.result


def test_the_gate_writes_the_optimization_result_and_the_rewritten_sql() -> None:
    service = _Service(
        OptimizationResult(
            sql="SELECT id FROM shop.orders LIMIT 100",
            rules_applied=("projection_pruning",),
            estimated_cost=10.0,
            within_budget=True,
        )
    )

    delta = RewriteAndCostGateNode(service).__call__(_state())

    assert delta["validated_sql"] == "SELECT id FROM shop.orders LIMIT 100"
    assert delta["optimization"].rules_applied == ("projection_pruning",)


def test_an_over_budget_gate_still_reports_the_sql_it_declined_to_run() -> None:
    service = _Service(
        OptimizationResult(
            sql="SELECT id FROM shop.orders",
            estimated_cost=900_000.0,
            within_budget=False,
            narrowing_suggestion="too big",
        )
    )

    delta = RewriteAndCostGateNode(service).__call__(_state())

    assert delta["validated_sql"] == "SELECT id FROM shop.orders"
    assert delta["optimization"].within_budget is False


def test_the_gate_reached_without_a_selection_raises() -> None:
    service = _Service(
        OptimizationResult(sql="SELECT 1", estimated_cost=1.0, within_budget=True)
    )

    with pytest.raises(OptimizationError):
        RewriteAndCostGateNode(service).__call__(_state(selection=None))


def test_the_gate_reached_without_a_plan_raises() -> None:
    service = _Service(
        OptimizationResult(sql="SELECT 1", estimated_cost=1.0, within_budget=True)
    )

    with pytest.raises(OptimizationError):
        RewriteAndCostGateNode(service).__call__(_state(plan=None))


class _Execution:
    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        return RESULT


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], float, str]] = []

    def record(self, sql, rules_applied, estimated_cost, datasource_name):  # type: ignore[no-untyped-def]
        self.calls.append((sql, rules_applied, estimated_cost, datasource_name))


class _ExplodingRecorder:
    def record(self, sql, rules_applied, estimated_cost, datasource_name):  # type: ignore[no-untyped-def]
        raise RuntimeError("explain analyze failed")


def _executed_state() -> Any:
    return _state(
        optimization=OptimizationResult(
            sql="SELECT id FROM shop.orders",
            rules_applied=("predicate_pushdown",),
            estimated_cost=42.0,
            within_budget=True,
        )
    )


def test_guarded_execution_without_a_recorder_behaves_exactly_as_before() -> None:
    delta = GuardedExecutionNode(_Execution()).__call__(_executed_state())

    assert delta["result"] == RESULT


def test_guarded_execution_with_a_recorder_records_what_actually_ran() -> None:
    recorder = _Recorder()

    GuardedExecutionNode(_Execution(), recorder=recorder).__call__(_executed_state())

    assert recorder.calls == [
        ("SELECT id FROM shop.orders", ("predicate_pushdown",), 42.0, "local")
    ]


def test_a_recorder_that_raises_never_fails_a_successful_turn() -> None:
    delta = GuardedExecutionNode(_Execution(), recorder=_ExplodingRecorder()).__call__(
        _executed_state()
    )

    assert delta["result"] == RESULT


def test_a_recorder_is_not_called_when_the_turn_carried_no_optimization() -> None:
    """Defensive: the recorder needs the estimate and the rules, and a state
    with no optimization has neither."""
    recorder = _Recorder()

    GuardedExecutionNode(_Execution(), recorder=recorder).__call__(_state())

    assert recorder.calls == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_query_optimizer_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_optimizer_nodes'`

- [ ] **Step 3: Extend `QueryState`**

In `genql/api/query_state.py`, add the import and the field, and set it in `initial_state`:

```python
from genql.domain.entities.optimization_result import OptimizationResult
```

```python
    # What the rewrite-and-cost-gate stage decided. None until that node runs;
    # the router reads `within_budget` from it, and query_turn reads
    # `narrowing_suggestion` and `rules_applied` for the response.
    optimization: OptimizationResult | None
```

and `optimization=None,` in `initial_state`'s constructor call.

- [ ] **Step 4: Extend `TurnResponse`**

In `genql/domain/entities/turn_response.py`, add two fields with defaults, and extend the module docstring to name the fourth outcome:

```python
    # Set, alongside a None `result`, exactly when the turn ended because the
    # query stayed over budget. This is the fourth outcome the CLI renders,
    # beside paused, short-circuited, and finished.
    narrowing_suggestion: str | None = None
    rewrite_rules_applied: tuple[str, ...] = ()
```

- [ ] **Step 5: Create the gate node**

Create `genql/api/query_optimizer_nodes.py`:

```python
"""The adapter between QueryState and OptimizationService.

Its own module rather than another class in query_nodes.py, following the
convention query_turn_nodes.py and query_ambiguity_nodes.py established: a
phase's new nodes get a file named for the phase, so a reader can find them.

The node writes `validated_sql` even when the gate refuses to run the query.
That looks odd until you read the CLI: a user told "this was too expensive"
wants to see the statement that was too expensive, and the router — not the
presence of SQL — is what decides whether execution happens.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import QueryState
from genql.domain.errors import OptimizationError
from genql.services.query.optimization_service import OptimizationService


class RewriteAndCostGateNode:
    def __init__(self, service: OptimizationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        selection = state["selection"]
        if selection is None:
            raise OptimizationError("the cost gate was reached without a selected candidate")
        plan = state["plan"]
        if plan is None:
            raise OptimizationError("the cost gate was reached without a plan")

        result = self._service.optimize(
            plan, selection.selected_sql, state["links"] or (), state["datasource_name"]
        )
        return {"optimization": result, "validated_sql": result.sql}
```

- [ ] **Step 6: Add the recorder hook to `GuardedExecutionNode`**

Replace `GuardedExecutionNode` in `genql/api/query_nodes.py` with:

```python
class GuardedExecutionNode:
    """Runs the statement, then — only when a recorder was constructed —
    measures it.

    The recorder is `None` whenever `Settings.record_execution_actuals` is
    false, because the composition root simply does not build one. That keeps
    the disabled path a single `is not None` check rather than a second
    conditional edge in the graph.

    The try/except is deliberately bare-`Exception`: the recording path runs
    EXPLAIN (ANALYZE, BUFFERS) against the warehouse and writes a row to
    GenQL's store, and *no* failure of a diagnostic may lose a turn whose
    query already returned rows to the user.
    """

    def __init__(
        self,
        service: GuardedExecutionService,
        recorder: RewriteOutcomeRecordingService | None = None,
    ) -> None:
        self._service = service
        self._recorder = recorder

    def __call__(self, state: QueryState) -> dict[str, Any]:
        sql = state["validated_sql"]
        if sql is None:
            raise ExecutionError("guarded execution was reached without validated SQL")
        result = self._service.execute(sql, state["datasource_name"])

        optimization = state["optimization"]
        if self._recorder is not None and optimization is not None:
            try:
                self._recorder.record(
                    sql,
                    optimization.rules_applied,
                    optimization.estimated_cost,
                    state["datasource_name"],
                )
            except Exception:  # noqa: BLE001 - a diagnostic must never fail a served turn
                pass

        return {"result": result}
```

Add the import `from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService` at the top of the module.

If `ruff` rejects the bare `except Exception: pass` under a rule other than `BLE001`, log through the project's existing `structlog` logger instead of `pass` — check whether `genql/api/` already binds one and follow that; never narrow the except to make a linter happy, because the point is that *nothing* escapes.

- [ ] **Step 7: Wire the node into the graph**

In `genql/api/query_graph.py`:

1. Add the constant beside the others: `REWRITE_AND_COST_GATE = "rewrite_and_cost_gate"`.
2. Add the router:

```python
def route_after_cost_gate(state: QueryState) -> str:
    """Over budget means the turn ends here, with the statement and an
    explanation but no rows — the parent spec's §11: "queries that remain over
    budget after rewriting return an explanation and a suggested narrowing
    rather than executing."

    A missing optimization also ends the turn rather than executing: the gate
    node raises rather than returning None, so this can only be reached with a
    result present, and defaulting to END keeps "no verdict" from meaning
    "run it".
    """
    optimization = state["optimization"]
    if optimization is not None and optimization.within_budget:
        return GUARDED_EXECUTION
    return END
```

3. Add `rewrite_and_cost_gate: NodeFn` to `build_query_graph`'s parameters (keep the existing `# noqa: PLR0913, PLR0917` comment), register the node, and replace the `CANDIDATE_SELECTION → GUARDED_EXECUTION` edge:

```python
    graph.add_node(REWRITE_AND_COST_GATE, rewrite_and_cost_gate)
    ...
    graph.add_edge(CANDIDATE_SELECTION, REWRITE_AND_COST_GATE)
    graph.add_conditional_edges(
        REWRITE_AND_COST_GATE,
        route_after_cost_gate,
        {GUARDED_EXECUTION: GUARDED_EXECUTION, END: END},
    )
```

4. Extend the module docstring: there are now four conditional edges, and the newest one is the only one that can end a turn without either rows or a question.

- [ ] **Step 8: Teach `query_turn.py` the fourth outcome**

In `genql/api/query_turn.py`, rewrite `_to_response`'s finished branch:

```python
    state = cast(QueryState, raw)
    optimization = state.get("optimization")
    over_budget = optimization is not None and not optimization.within_budget
    # An intent is reported only when it stopped the turn. An over-budget turn
    # also has no result, so it must be excluded here or a perfectly
    # well-classified analytical question would be reported as the wrong kind
    # of question.
    short_circuited = (
        state["validated_sql"] is None and state["result"] is None and not over_budget
    )
    return TurnResponse(
        thread_id=thread_id,
        intent=state["intent"] if short_circuited else None,
        validated_sql=state["validated_sql"],
        result=state["result"],
        applied_defaults=_applied_defaults(raw),
        narrowing_suggestion=optimization.narrowing_suggestion if over_budget else None,
        rewrite_rules_applied=optimization.rules_applied if optimization else (),
    )
```

- [ ] **Step 9: Render the fourth outcome in the CLI**

In `genql/cli/commands/query.py`, add a branch to `_render` before the finished branch:

```python
def _render_over_budget(response: TurnResponse) -> None:
    typer.echo("SQL (not executed):")
    typer.echo(response.validated_sql or "")
    typer.echo("")
    typer.echo(response.narrowing_suggestion or "")
    typer.echo(f"thread: {response.thread_id}")
```

and in `_render`:

```python
    if response.clarifying_question is not None:
        _render_paused(response)
    elif response.narrowing_suggestion is not None:
        _render_over_budget(response)
    elif response.intent is not None:
        _render_intent(response)
    else:
        _render_finished(response)
```

Also extend `_render_finished` to print the applied rules when there are any:

```python
    if response.rewrite_rules_applied:
        typer.echo(f"rewrites applied: {', '.join(response.rewrite_rules_applied)}")
```

- [ ] **Step 10: Update the existing graph and turn tests**

Run: `uv run pytest tests/unit -q`

Every existing test that calls `build_query_graph(...)` now fails on a missing `rewrite_and_cost_gate` argument, and every test constructing a `QueryState` literal fails on the missing `optimization` key. Fix each by adding the new node/field — **do not** give `build_query_graph`'s new parameter a default to avoid touching them: a graph missing a stage should fail loudly at construction, which is the property the other ten parameters already have.

Add one routing test to whichever file holds the existing router tests:

```python
def test_an_over_budget_gate_routes_to_end_not_to_execution() -> None:
    state = initial_state("q", "local", "t-1")
    state["optimization"] = OptimizationResult(
        sql="SELECT 1", estimated_cost=9e9, within_budget=False, narrowing_suggestion="s"
    )

    assert route_after_cost_gate(state) == END


def test_a_within_budget_gate_routes_to_guarded_execution() -> None:
    state = initial_state("q", "local", "t-1")
    state["optimization"] = OptimizationResult(
        sql="SELECT 1", estimated_cost=1.0, within_budget=True
    )

    assert route_after_cost_gate(state) == GUARDED_EXECUTION
```

- [ ] **Step 11: Run everything**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add genql/api genql/domain/entities/turn_response.py genql/cli/commands/query.py tests/unit
git commit -m "feat(api): add the rewrite-and-cost-gate node and its graph edge"
```

---

### Task 9: Composition wiring and the `genql optimizer` command

**Files:**
- Create: `genql/composition/optimizer_container.py`, `genql/cli/commands/optimizer.py`, `tests/integration/test_cli_optimizer.py`
- Modify: `genql/composition_root.py`, `genql/cli/main.py`
- Test: `tests/integration/test_cli_optimizer.py`, plus the existing container test (find it: `ls tests/unit | grep -i contain`)

**Interfaces:**
- Consumes: every service and repository from Tasks 3–8
- Produces: `OptimizerContainer` providing `cost_estimator`, `rewrite_outcome_writer`, `index_recommender`, `rewrite_rule_factory`, `query_decomposer`, `optimization_service`, `rewrite_recording_service`, `index_recommendation_service`, and a re-declared `query_graph` with twelve nodes; `Container` now extends `OptimizerContainer`; `genql optimizer recommend-indexes --datasource X`

- [ ] **Step 1: Read the container that currently declares `query_graph` last**

Run: `cat genql/composition/ambiguity_container.py`

`OptimizerContainer` extends `AmbiguityContainer` and re-declares `query_graph` with the new node, exactly as `AmbiguityContainer` re-declared `TurnContainer`'s. Declarative containers resolve the most-derived declaration, so every consumer gets the twelve-node graph and there is one graph provider in play rather than two that could drift. `composition_root.Container` must then extend `OptimizerContainer` instead of `AmbiguityContainer`.

- [ ] **Step 2: Create the container**

Create `genql/composition/optimizer_container.py`:

```python
"""Phase 7's providers: three repositories, four services, the rule factory,
and the graph rebuilt over twelve stages.

`rewrite_recording_service` is a Callable provider rather than a Singleton so
that it evaluates to None when `record_execution_actuals` is false. That is
the whole disabled-by-default mechanism: the node's constructor parameter
receives None, and its `is not None` check does the rest. Nothing else in the
graph changes shape between the two configurations.
"""

from __future__ import annotations

from dependency_injector import providers

from genql.api.query_ambiguity_nodes import (
    AmbiguityProbingNode,
    CandidateSelectionNode,
    CritiqueNode,
)
from genql.api.query_graph import build_query_graph
from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.api.query_optimizer_nodes import RewriteAndCostGateNode
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.ambiguity_container import AmbiguityContainer
from genql.infrastructure.query.rewrite_rule_factory import RewriteRuleFactoryImpl
from genql.repositories.query.cost_estimator_repository import PostgresCostEstimator
from genql.repositories.query.index_recommender_repository import PostgresIndexRecommender
from genql.repositories.query.rewrite_outcome_repository import PostgresRewriteOutcomeWriter
from genql.services.query.index_recommendation_service import IndexRecommendationService
from genql.services.query.optimization_service import OptimizationService
from genql.services.query.query_decomposer import LlmQueryDecomposer
from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService


def _recorder_if_enabled(
    enabled: bool, actuals: object, writer: object
) -> RewriteOutcomeRecordingService | None:
    """None when recording is off, so GuardedExecutionNode's `is not None`
    check is the only place the switch is read at runtime."""
    if not enabled:
        return None
    return RewriteOutcomeRecordingService(actuals=actuals, writer=writer)  # type: ignore[arg-type]


class OptimizerContainer(AmbiguityContainer):
    cost_estimator = providers.Singleton(
        PostgresCostEstimator,
        provider=AmbiguityContainer.engine_provider,
        datasources=AmbiguityContainer.datasource_repository,
    )
    rewrite_outcome_writer = providers.Singleton(
        PostgresRewriteOutcomeWriter,
        engine=AmbiguityContainer.semantic_engine,
        datasources=AmbiguityContainer.datasource_repository,
    )
    index_recommender = providers.Singleton(
        PostgresIndexRecommender, engine=AmbiguityContainer.semantic_engine
    )

    rewrite_rule_factory = providers.Singleton(RewriteRuleFactoryImpl)
    query_decomposer = providers.Singleton(
        LlmQueryDecomposer, chat=AmbiguityContainer.chat_provider
    )
    optimization_service = providers.Singleton(
        OptimizationService,
        rules=rewrite_rule_factory,
        estimator=cost_estimator,
        decomposer=query_decomposer,
        budget=AmbiguityContainer.settings.provided.cost_budget,
    )
    rewrite_recording_service = providers.Callable(
        _recorder_if_enabled,
        AmbiguityContainer.settings.provided.record_execution_actuals,
        cost_estimator,
        rewrite_outcome_writer,
    )
    index_recommendation_service = providers.Singleton(
        IndexRecommendationService, recommender=index_recommender
    )

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=AmbiguityContainer.intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(
            AmbiguityGateNode, gate=AmbiguityContainer.ambiguity_gate_service
        ),
        domain_scoping=providers.Singleton(
            DomainScopingNode, scoper=AmbiguityContainer.domain_scoping_service
        ),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=AmbiguityContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=AmbiguityContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=AmbiguityContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=AmbiguityContainer.static_validation_service
        ),
        critique=providers.Singleton(CritiqueNode, service=AmbiguityContainer.critique_service),
        ambiguity_probing=providers.Singleton(
            AmbiguityProbingNode, service=AmbiguityContainer.ambiguity_probing_service
        ),
        candidate_selection=providers.Singleton(
            CandidateSelectionNode, service=AmbiguityContainer.candidate_selection_service
        ),
        rewrite_and_cost_gate=providers.Singleton(
            RewriteAndCostGateNode, service=optimization_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode,
            service=AmbiguityContainer.guarded_execution_service,
            recorder=rewrite_recording_service,
        ),
        checkpointer=AmbiguityContainer.checkpointer,
    )
```

If `AmbiguityContainer` does not expose `engine_provider` or `semantic_engine` under those exact names, use the real ones — Step 1 is where you learn them.

- [ ] **Step 3: Point the composition root at the new container**

In `genql/composition_root.py`, replace the `AmbiguityContainer` import and base class with `OptimizerContainer`, and update `_step_service_providers` to reference `OptimizerContainer.<service>` instead of `AmbiguityContainer.<service>`. Nothing else changes.

- [ ] **Step 4: Run the container test**

Run: `uv run pytest tests/unit -q -k container`
Expected: PASS. If a test asserts the exact provider set, extend it with the eight new providers.

- [ ] **Step 5: Write the failing CLI test**

Create `tests/integration/test_cli_optimizer.py`:

```python
"""The command's two outputs: a ranked table, and the empty-state line that
tells the operator why there is nothing to show. The empty state is the one a
fresh installation always hits, so it is the one worth a test."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = pytest.mark.integration

runner = CliRunner()


def test_recommend_indexes_on_a_fresh_store_explains_why_it_is_empty() -> None:
    result = runner.invoke(app, ["optimizer", "recommend-indexes", "--datasource", "local"])

    assert result.exit_code == 0
    assert "no recommendations yet" in result.stdout


def test_recommend_indexes_on_an_unknown_datasource_exits_nonzero() -> None:
    result = runner.invoke(app, ["optimizer", "recommend-indexes", "--datasource", "nope"])

    assert result.exit_code == 1
```

- [ ] **Step 6: Create the CLI command**

Create `genql/cli/commands/optimizer.py`:

```python
"""`genql optimizer` — the operator-facing half of Phase 7.

The parent spec's §11 is explicit that GenQL never creates an index itself, so
this command prints and exits. The empty-state message names both reasons the
list can be empty, because on a fresh installation the operator has no way to
tell "nothing to recommend" from "nothing was ever recorded".
"""

from __future__ import annotations

import psycopg
import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError

app = typer.Typer(help="Inspect and act on the optimizer's accumulated evidence")


@app.command("recommend-indexes")
def recommend_indexes(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
) -> None:
    """Print indexes worth creating, ranked by how much evidence supports them."""
    try:
        container = Container()
        recommendations = container.index_recommendation_service().recommend(datasource)
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if not recommendations:
        typer.echo(
            "no recommendations yet — either record_execution_actuals is off, or no "
            "executions have been recorded for this datasource"
        )
        return

    typer.echo("object | column | executions | rationale")
    for recommendation in recommendations:
        typer.echo(
            f"{recommendation.object_qualified_name} | {recommendation.column_name} | "
            f"{recommendation.supporting_execution_count} | {recommendation.rationale}"
        )
```

- [ ] **Step 7: Register the sub-app**

In `genql/cli/main.py`, add the import and `app.add_typer(optimizer_commands.app, name="optimizer")` beside the existing sub-apps.

- [ ] **Step 8: Run everything**

Run: `uv run pytest tests/unit -q && uv run pytest tests/integration/test_cli_optimizer.py -q; uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: unit PASS; CLI test PASS or clean skip; all static checks clean

- [ ] **Step 9: Commit**

```bash
git add genql/composition genql/composition_root.py genql/cli tests
git commit -m "feat(composition): wire the Phase 7 optimizer services, graph node, and CLI"
```

---

### Task 10: Prove Part A — rewrite equivalence and the over-budget path

**Files:**
- Create: `golden/phase7_equivalence.yaml`, `tests/integration/test_rewrite_equivalence.py`, `tests/integration/test_phase7_end_to_end.py`
- Test: both created files

**Interfaces:**
- Consumes: everything from Tasks 1–9; real `local.tpcds`
- Produces: `golden/phase7_equivalence.yaml`, the fixture file **Part B's golden-set runner reuses rather than re-authoring**

- [ ] **Step 1: Write the six fixtures**

Create `golden/phase7_equivalence.yaml`. Each case carries the fields Part B's `GoldenCase` will read, so the file serves both phases:

```yaml
# Six hand-picked TPC-DS questions with their reference SQL.
#
# Phase 7 uses `reference_sql` as the statement whose results must survive each
# rewrite rule unchanged. Phase 8's golden-set runner uses the same field as the
# expected result for `question`. One file, two consumers, no duplicate authoring
# — which is why the schema carries `question` and `failure_class` even though
# Phase 7 reads neither.
cases:
  - case_id: tpcds_store_sales_by_month
    question: total store sales by month in 2001
    datasource_name: local
    failure_class: context_sensitivity
    reference_sql: |
      SELECT d.d_moy AS month, sum(ss.ss_ext_sales_price) AS total
      FROM tpcds.store_sales AS ss
      JOIN tpcds.date_dim AS d ON d.d_date_sk = ss.ss_sold_date_sk
      WHERE d.d_year = 2001
      GROUP BY d.d_moy
      ORDER BY d.d_moy

  - case_id: tpcds_customer_count_by_state
    question: how many customers are in each state
    datasource_name: local
    failure_class: ambiguous_intent
    reference_sql: |
      SELECT ca.ca_state AS state, count(*) AS customers
      FROM tpcds.customer AS c
      JOIN tpcds.customer_address AS ca ON ca.ca_address_sk = c.c_current_addr_sk
      GROUP BY ca.ca_state

  - case_id: tpcds_top_items_by_revenue
    question: the ten items with the highest store revenue
    datasource_name: local
    failure_class: absent_business_knowledge
    reference_sql: |
      SELECT i.i_item_id AS item, sum(ss.ss_ext_sales_price) AS revenue
      FROM tpcds.store_sales AS ss
      JOIN tpcds.item AS i ON i.i_item_sk = ss.ss_item_sk
      GROUP BY i.i_item_id
      ORDER BY revenue DESC, item
      LIMIT 10

  - case_id: tpcds_returns_share
    question: what share of store sales were returned
    datasource_name: local
    failure_class: physical_modelling_variation
    reference_sql: |
      SELECT count(sr.sr_returned_date_sk) AS returned, count(*) AS sold
      FROM tpcds.store_sales AS ss
      LEFT JOIN tpcds.store_returns AS sr
        ON sr.sr_item_sk = ss.ss_item_sk AND sr.sr_ticket_number = ss.ss_ticket_number

  - case_id: tpcds_sales_by_channel
    question: total sales through each channel
    datasource_name: local
    failure_class: absent_business_knowledge
    reference_sql: |
      SELECT 'store' AS channel, sum(ss_ext_sales_price) AS total FROM tpcds.store_sales
      UNION ALL
      SELECT 'catalog' AS channel, sum(cs_ext_sales_price) AS total FROM tpcds.catalog_sales

  - case_id: tpcds_promotion_lift
    question: average sale price for promoted versus unpromoted items
    datasource_name: local
    failure_class: absent_business_knowledge
    reference_sql: |
      SELECT ss.ss_promo_sk IS NOT NULL AS promoted, avg(ss.ss_ext_sales_price) AS avg_price
      FROM tpcds.store_sales AS ss
      GROUP BY ss.ss_promo_sk IS NOT NULL
```

Before committing, run every `reference_sql` against the real warehouse and confirm each returns rows. A fixture that returns nothing proves nothing about a rewrite rule, and would silently pass Part B's runner too.

- [ ] **Step 2: Write the equivalence test**

Create `tests/integration/test_rewrite_equivalence.py`:

```python
"""The parent spec's §17: "each rewrite rule preserves results on the golden
set", scaled to what this phase can build.

One rule at a time, in isolation, rather than the whole pipeline: a pipeline
test tells you the output changed, a per-rule test tells you which rule broke
it. The comparison is order-insensitive because a rewrite may legitimately
change row order — which is exactly why §15 forbids comparing SQL strings and
requires comparing result sets.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import sqlglot
import yaml
from sqlglot.optimizer.qualify import qualify

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES

pytestmark = pytest.mark.integration

CASES = yaml.safe_load(Path("golden/phase7_equivalence.yaml").read_text())["cases"]


def _multiset(result) -> Counter:  # type: ignore[no-untyped-def]
    return Counter(tuple(row) for row in result.rows)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
@pytest.mark.parametrize("rule_key", REWRITE_RULES.keys())
def test_each_rule_preserves_the_result_set(case, rule_key, warehouse_executor, tpcds_schema):  # type: ignore[no-untyped-def]
    original = case["reference_sql"]
    expression = qualify(
        sqlglot.parse_one(original, dialect="postgres"),
        dialect="postgres",
        schema=tpcds_schema,
        identify=False,
    )
    rewritten = REWRITE_RULES.create(rule_key).apply(expression).sql(dialect="postgres")

    before = warehouse_executor.execute(expression.sql(dialect="postgres"), 10_000)
    after = warehouse_executor.execute(rewritten, 10_000)

    assert _multiset(before) == _multiset(after), (
        f"{rule_key} changed the result of {case['case_id']}\n"
        f"before: {expression.sql(dialect='postgres')}\nafter:  {rewritten}"
    )
```

Add a `tpcds_schema` fixture to `tests/integration/conftest.py` that builds the sqlglot schema dict from the real catalog — read `genql_column` through the existing semantic engine fixture, shaped `{schema: {object: {column: "UNKNOWN"}}}`, matching `OptimizationService._schema_of`'s output. Add a `warehouse_executor` fixture returning a `ReadOnlyQueryExecutorRepository` bound to `local` if one does not already exist.

- [ ] **Step 3: Run the equivalence suite**

Run: `uv run pytest tests/integration/test_rewrite_equivalence.py -q`
Expected: PASS (24 parametrized cases: 6 fixtures × 4 rules), or a clean skip

**If a rule fails equivalence on a fixture, that is the finding this task exists to produce.** Do not weaken the assertion and do not delete the fixture. Report which rule and which case, and unregister that rule by removing its import from `genql/repositories/query/rewrite_rules/__init__.py` — containment through the registry is exactly what Phase 7's §11 says the registry design is for.

- [ ] **Step 4: Write the end-to-end test**

Create `tests/integration/test_phase7_end_to_end.py`:

```python
"""The claim Phase 7 exists to make: an unaffordable query is explained, not
executed — and the same query under a realistic budget runs normally.

Two runs of one question, differing only in `cost_budget`, so the assertion is
about the gate rather than about the question."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.real_provider]

EXPENSIVE = "join every store sale to every catalog sale and count the pairs"


def test_an_over_budget_question_returns_a_suggestion_and_no_rows(turn_with_budget) -> None:
    response = turn_with_budget(EXPENSIVE, cost_budget=1.0)

    assert response.result is None
    assert response.narrowing_suggestion is not None
    assert response.validated_sql is not None  # the user sees what was declined


def test_the_same_question_under_a_realistic_budget_executes(turn_with_budget) -> None:
    response = turn_with_budget("how many rows are in the date dimension", cost_budget=1e9)

    assert response.result is not None
    assert response.narrowing_suggestion is None
```

Add a `turn_with_budget` fixture that constructs a `Container` with `cost_budget` overridden and calls `start_turn`. **Part B's Task 17 replaces this fixture's ad-hoc override with `Container.with_overrides`; leave a comment saying so** so the later task knows to come back and collapse the duplication.

- [ ] **Step 5: Run the end-to-end test**

Run: `uv run pytest tests/integration/test_phase7_end_to_end.py -q`
Expected: PASS, or a clean skip without `GENQL_TEST_DSN` / `GENQL_OPENROUTER_API_KEY`

- [ ] **Step 6: Run the whole suite and every static check**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add golden tests/integration
git commit -m "test(phase7): prove rewrite equivalence and the over-budget gate end to end"
```

**Part A review gate.** Run one review of Tasks 1–10 as a whole here, per the execution note in Global Constraints. Do not review per task.

---
# PART B — Phase 8: API and Evaluation

### Task 11: Dependencies, contracts, and the evaluation domain foundation

**Files:**
- Create: `genql/domain/entities/golden_case.py`, `genql/domain/entities/golden_outcome.py`, `genql/domain/entities/golden_run_report.py`, `genql/domain/entities/ablation.py`, `genql/domain/entities/feedback.py`, `genql/domain/entities/stage_event.py`, `genql/domain/ports/golden_set_reader.py`, `genql/domain/ports/turn_runner.py`, `genql/domain/ports/turn_runner_factory.py`, `genql/domain/ports/search_document_recompiler.py`, `genql/domain/ports/feedback_writer.py`, `genql/domain/ports/report_writer.py`
- Modify: `pyproject.toml`, `.importlinter`, `genql/domain/errors.py`, `genql/core/settings.py`
- Test: `tests/unit/test_eval_entities.py`, `tests/unit/test_eval_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `genql.domain.entities.turn_response.TurnResponse` (extended in Task 8)
- Produces: entities `GoldenCase`, `GoldenOutcome`, `GoldenRunReport` (with `passed_count`, `accuracy`, `counts_for`), `Ablation`, `Feedback`, `StageEvent`; ports `GoldenSetReader`, `TurnRunner`, `TurnRunnerFactory`, `SearchDocumentRecompiler`, `FeedbackWriter`, `ReportWriter`; errors `EvaluationError`, `GoldenSetError`, `UnknownAblationError`, `FeedbackError`; eight new settings

- [ ] **Step 1: Add the three dependencies**

Run:

```bash
uv add fastapi 'uvicorn[standard]' sse-starlette
uv run python -c "import fastapi, uvicorn, sse_starlette; print(fastapi.__version__)"
```

- [ ] **Step 2: Forbid them below `genql/api/`**

In `.importlinter`, append to the `forbidden_modules` list of **both** the `domain-is-pure` and `no-sql-in-services` contracts:

```
    fastapi
    starlette
    sse_starlette
```

`starlette` is listed explicitly rather than relying on `fastapi`: a service could import `starlette.concurrency` directly without touching `fastapi` at all, and that is precisely the leak this contract exists to stop.

Run: `uv run lint-imports`
Expected: 3/3 contracts kept (nothing imports them yet)

- [ ] **Step 3: Write the failing entity tests**

Create `tests/unit/test_eval_entities.py`:

```python
"""Six entities. The behaviour worth testing is GoldenRunReport's arithmetic:
every number the ablation harness reports comes out of it, an empty report is
reachable (a fixture directory with no cases), and a ZeroDivisionError in a
reporting property would crash a run that had already done all its work."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.feedback import Feedback
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_outcome import GoldenOutcome
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.entities.stage_event import StageEvent


def _outcome(case_id: str, passed: bool, failure_class: str = "ambiguous_intent") -> GoldenOutcome:
    return GoldenOutcome(
        case_id=case_id,
        failure_class=failure_class,
        passed=passed,
        generated_sql="SELECT 1" if passed else None,
        failure_reason=None if passed else "result mismatch",
        elapsed_ms=10.0,
    )


def test_a_golden_case_carries_its_reference_sql_and_failure_class() -> None:
    case = GoldenCase(
        case_id="c1",
        question="how many customers",
        datasource_name="local",
        reference_sql="SELECT count(*) FROM tpcds.customer",
        failure_class="ambiguous_intent",
    )

    assert case.domain_id is None
    assert case.reference_sql.startswith("SELECT")


def test_a_golden_case_rejects_an_unknown_failure_class() -> None:
    with pytest.raises(ValidationError):
        GoldenCase(
            case_id="c1",
            question="q",
            datasource_name="local",
            reference_sql="SELECT 1",
            failure_class="made_up",
        )


def test_an_empty_report_has_zero_accuracy_and_does_not_divide_by_zero() -> None:
    report = GoldenRunReport(ablation_name="full", outcomes=())

    assert report.accuracy == 0.0
    assert report.passed_count == 0


def test_accuracy_is_passed_over_total() -> None:
    report = GoldenRunReport(
        ablation_name="full",
        outcomes=(_outcome("a", True), _outcome("b", True), _outcome("c", False)),
    )

    assert report.passed_count == 2
    assert report.accuracy == pytest.approx(2 / 3)


def test_counts_for_a_failure_class_returns_passed_and_total() -> None:
    report = GoldenRunReport(
        ablation_name="full",
        outcomes=(
            _outcome("a", True, "ambiguous_intent"),
            _outcome("b", False, "ambiguous_intent"),
            _outcome("c", True, "context_sensitivity"),
        ),
    )

    assert report.counts_for("ambiguous_intent") == (1, 2)
    assert report.counts_for("context_sensitivity") == (1, 1)
    assert report.counts_for("nothing_here") == (0, 0)


def test_an_ablation_carries_its_overrides_and_recompile_flag() -> None:
    ablation = Ablation(
        name="no_domains",
        description="disables domain scoping",
        setting_overrides=(("domain_scoping_enabled", False),),
    )

    assert ablation.requires_recompile is False
    assert ablation.setting_overrides == (("domain_scoping_enabled", False),)


def test_the_baseline_ablation_overrides_nothing() -> None:
    assert Ablation(name="full", description="baseline").setting_overrides == ()


def test_feedback_rejects_a_rating_that_is_not_good_or_bad() -> None:
    with pytest.raises(ValidationError):
        Feedback(thread_id="t-1", rating="meh")


def test_feedback_may_carry_a_correction() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="SELECT 2")

    assert feedback.corrected_sql == "SELECT 2"


def test_a_stage_event_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        StageEvent(stage="planning", status="thinking")


def test_a_stage_event_carries_an_optional_detail_line() -> None:
    assert StageEvent(stage="planning", status="completed").detail is None
```

- [ ] **Step 4: Run to verify it fails**

Run: `uv run pytest tests/unit/test_eval_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.ablation'`

- [ ] **Step 5: Create the six entities**

Create `genql/domain/value_objects/failure_class.py`:

```python
"""The four failure classes the parent spec's §2 names.

A tuple plus a Literal rather than an enum, matching how AMBIGUITY_DIMENSIONS
is already declared: the values are written by hand in YAML fixtures, so they
need to be plain strings at the boundary, and the Literal is what makes a typo
in a fixture a validation error instead of a silently uncounted case.
"""

from __future__ import annotations

from typing import Literal

FailureClass = Literal[
    "ambiguous_intent",
    "absent_business_knowledge",
    "physical_modelling_variation",
    "context_sensitivity",
]

FAILURE_CLASSES: tuple[FailureClass, ...] = (
    "ambiguous_intent",
    "absent_business_knowledge",
    "physical_modelling_variation",
    "context_sensitivity",
)
```

Create `genql/domain/entities/golden_case.py`:

```python
"""One hand-curated question and the statement whose result is its expectation.

The expectation is a reference SQL statement rather than literal rows: thirty
to fifty TPC-DS result sets pasted into YAML would be unreviewable and would
rot the first time the seed data was regenerated. Comparing the *results* of
two statements is still execution-result comparison — the generated SQL's text
is never inspected, which is what §15 actually forbids.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.failure_class import FailureClass


class GoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    datasource_name: str
    reference_sql: str
    failure_class: FailureClass
    domain_id: int | None = None
```

Create `genql/domain/entities/golden_outcome.py`:

```python
"""What one case did.

`failure_class` is copied from the case rather than looked up, so a report can
group by class without holding the fixtures it came from — the JSON report is
readable on its own, which is the point of writing one.

`passed=False` with a `failure_reason` covers every non-matching outcome: a
paused turn, a short-circuited intent, an over-budget narrowing, a raised
error, and an actual result mismatch. They are all "this case did not produce
the expected rows", and flattening them keeps accuracy meaning one thing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.failure_class import FailureClass


class GoldenOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    failure_class: FailureClass
    passed: bool
    generated_sql: str | None = None
    failure_reason: str | None = None
    elapsed_ms: float
```

Create `genql/domain/entities/golden_run_report.py`:

```python
"""One ablation's results over the whole golden set.

`accuracy` returns 0.0 on an empty report rather than raising: an empty
fixture directory is a configuration mistake, and crashing inside a reporting
property would lose a run that had already finished its work. The CLI prints
counts beside every accuracy, so `0.0 (0/0)` is unmistakable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.golden_outcome import GoldenOutcome


class GoldenRunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ablation_name: str
    outcomes: tuple[GoldenOutcome, ...]

    @property
    def passed_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def accuracy(self) -> float:
        if not self.outcomes:
            return 0.0
        return self.passed_count / len(self.outcomes)

    def counts_for(self, failure_class: str) -> tuple[int, int]:
        matching = [o for o in self.outcomes if o.failure_class == failure_class]
        return sum(1 for o in matching if o.passed), len(matching)
```

Create `genql/domain/entities/ablation.py`:

```python
"""A named set of settings overrides that switches one enrichment layer off.

It carries no behaviour on purpose. An ablation that could *do* something
would be a place for a service to branch on being ablated, and a service that
branches on being ablated is not the service being measured.

`requires_recompile` is true only for no_descriptions, because descriptions
reach the online path through compiled search documents rather than through a
query-time read — so switching them off means rebuilding those documents, not
swapping an adapter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Ablation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    setting_overrides: tuple[tuple[str, bool], ...] = ()
    requires_recompile: bool = False
```

Create `genql/domain/entities/feedback.py`:

```python
"""One rating on one turn, optionally with the SQL the user would have wanted.

Kept in GenQL's own Postgres because the parent spec's §2 warns that feedback
living outside the database becomes an ungoverned shadow data repository. It
is captured only — nothing retrieves it yet, and the corrected SQL is stored
so that a later phase can index it without re-collecting anything.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Feedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    rating: Literal["good", "bad"]
    corrected_sql: str | None = None
    comment: str | None = None
```

Create `genql/domain/entities/stage_event.py`:

```python
"""One pipeline stage's completion, as an SSE client sees it.

`detail` is one short human line, never the state delta: a stage's delta can
contain the whole schema-link set or every candidate statement, and shipping
that down an event stream would make the transport the widest interface in the
system.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    status: Literal["completed", "paused", "failed"]
    detail: str | None = None
```

- [ ] **Step 6: Run the entity tests**

Run: `uv run pytest tests/unit/test_eval_entities.py -q`
Expected: PASS (11 tests)

- [ ] **Step 7: Write the failing port tests**

Create `tests/unit/test_eval_ports_are_runtime_checkable.py`, following exactly the shape of `tests/unit/test_optimizer_ports_are_runtime_checkable.py` from Task 1: one minimal fake per port, one `isinstance` assertion each, covering `GoldenSetReader`, `TurnRunner`, `TurnRunnerFactory`, `SearchDocumentRecompiler`, `FeedbackWriter`, and `ReportWriter`.

- [ ] **Step 8: Create the six ports**

Create `genql/domain/ports/golden_set_reader.py`:

```python
"""Reads hand-curated cases from disk.

A port because file I/O is I/O: a service never opens a file, exactly as it
never opens a cursor. That is also what lets GoldenEvaluationService be unit
tested with a tuple of cases and no filesystem.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.golden_case import GoldenCase


@runtime_checkable
class GoldenSetReader(Protocol):
    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]: ...
```

Create `genql/domain/ports/turn_runner.py`:

```python
"""One turn, start to finish, with no clarification loop.

What an evaluation run needs, and deliberately narrower than the CLI's path:
an evaluation cannot answer a clarifying question, so a paused turn is simply
a failed case. The implementation lives in `genql/api/` because it wraps the
compiled graph; the service depends on this protocol so that
`genql/services/` never imports `genql/api/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.turn_response import TurnResponse


@runtime_checkable
class TurnRunner(Protocol):
    def run(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> TurnResponse: ...
```

Create `genql/domain/ports/turn_runner_factory.py`:

```python
"""Builds a TurnRunner over a container constructed with one ablation's
overrides.

AblationService holds this rather than a Container, because a service may not
import the composition root — and because "give me a pipeline with domains
switched off" is the actual thing the service needs, not a DI container.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ablation import Ablation
from genql.domain.ports.turn_runner import TurnRunner


@runtime_checkable
class TurnRunnerFactory(Protocol):
    def for_ablation(self, ablation: Ablation) -> TurnRunner: ...
```

Create `genql/domain/ports/search_document_recompiler.py`:

```python
"""Rebuilds genql_search_document under one ablation's overrides.

Only no_descriptions needs it. Every other ablation leaves the store untouched,
which is why this is a separate port rather than a step in the factory: a
caller reading AblationService can see exactly which ablations mutate shared
state and which do not.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ablation import Ablation


@runtime_checkable
class SearchDocumentRecompiler(Protocol):
    def recompile(self, ablation: Ablation, datasource_name: str) -> int: ...
```

Create `genql/domain/ports/feedback_writer.py`:

```python
"""Persists one rating."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.feedback import Feedback


@runtime_checkable
class FeedbackWriter(Protocol):
    def write(self, feedback: Feedback) -> None: ...
```

Create `genql/domain/ports/report_writer.py`:

```python
"""Serializes evaluation reports to a file, for the same reason
GoldenSetReader reads one: writing a file is I/O."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.golden_run_report import GoldenRunReport


@runtime_checkable
class ReportWriter(Protocol):
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None: ...
```

- [ ] **Step 9: Add the four errors**

Append to `genql/domain/errors.py`:

```python
class EvaluationError(GenqlError):
    """The golden-set runner or the ablation harness could not complete."""


class GoldenSetError(EvaluationError):
    """A fixture file is missing, malformed, or names an unknown failure class."""


class UnknownAblationError(EvaluationError):
    def __init__(self, name: str, known: list[str]) -> None:
        super().__init__(f"unknown ablation {name!r}; registered: {', '.join(known)}")
        self.name = name


class FeedbackError(GenqlError):
    """Feedback could not be accepted or recorded."""
```

Match `UnknownDatasourceError`'s constructor shape — read it first and mirror how it stores its attribute and formats its message.

- [ ] **Step 10: Add the eight settings**

Append to `Settings` in `genql/core/settings.py`:

```python
    # Ablation switches. All True in normal operation. Only the ablation
    # harness sets one False, and it does so through Container.with_overrides
    # rather than the environment — deliberately absent from .env.example,
    # because a stray GENQL_ENRICHMENT_ENABLED=false would silently degrade
    # every real turn with nothing in the output to say so.
    enrichment_enabled: bool = True
    domain_scoping_enabled: bool = True
    join_paths_enabled: bool = True
    probing_enabled: bool = True
    ambiguity_examples_enabled: bool = True

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Where `genql eval` looks for *.yaml fixtures.
    golden_set_dir: str = "golden"
```

- [ ] **Step 11: Run everything**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml uv.lock .importlinter genql/domain genql/core/settings.py tests/unit/test_eval_entities.py tests/unit/test_eval_ports_are_runtime_checkable.py
git commit -m "feat(domain): declare the Phase 8 evaluation and API entities, ports, errors, and settings"
```

---

### Task 12: Feedback, end to end

**Files:**
- Create: `migrations/versions/0010_feedback.py`, `genql/repositories/semantic/feedback_repository.py`, `genql/services/semantic/feedback_service.py`, `tests/unit/test_feedback_service.py`, `tests/integration/test_migration_0010.py`, `tests/integration/test_feedback_repository.py`
- Modify: `genql/repositories/semantic/__init__.py`
- Test: the three test files above

**Interfaces:**
- Consumes: Task 11's `Feedback`, `FeedbackWriter`, `FeedbackError`
- Produces: table `genql.genql_feedback`; `PostgresFeedbackWriter(engine)`; `FeedbackService(writer)` with `record(feedback) -> None`

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0010_feedback.py`, copying `0009`'s conventions exactly (revision `"0010"`, `down_revision = "0009"`, `schema="genql"` on every operation):

```python
def upgrade() -> None:
    op.create_table(
        "genql_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("corrected_sql", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating IN ('good', 'bad')", name="genql_feedback_rating_check"),
        schema="genql",
    )
    op.create_index("genql_feedback_thread_idx", "genql_feedback", ["thread_id"], schema="genql")


def downgrade() -> None:
    op.drop_index("genql_feedback_thread_idx", table_name="genql_feedback", schema="genql")
    op.drop_table("genql_feedback", schema="genql")
```

`thread_id` carries no foreign key on purpose: langgraph's checkpoint tables are created and owned by `PostgresSaver`, not by these migrations, and a constraint against a table another library may reshape is a liability. Feedback on an expired thread is still worth keeping.

Create `tests/integration/test_migration_0010.py` modelled on `test_migration_0009.py`, asserting the column set and that the `rating` check constraint rejects a third value.

- [ ] **Step 2: Write the failing service test**

Create `tests/unit/test_feedback_service.py`:

```python
"""The one line of logic: a correction that is not a SELECT is refused.

The corrected SQL is what a later phase will index as a hint, so garbage
admitted here becomes garbage retrieved later — and unlike the generated SQL,
nothing else validates it."""

from __future__ import annotations

import pytest

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError
from genql.services.semantic.feedback_service import FeedbackService


class _Writer:
    def __init__(self) -> None:
        self.written: list[Feedback] = []

    def write(self, feedback: Feedback) -> None:
        self.written.append(feedback)


def test_a_rating_without_a_correction_is_recorded() -> None:
    writer = _Writer()
    FeedbackService(writer).record(Feedback(thread_id="t-1", rating="good"))

    assert writer.written[0].thread_id == "t-1"


def test_a_correction_that_parses_as_a_select_is_recorded() -> None:
    writer = _Writer()
    feedback = Feedback(
        thread_id="t-1", rating="bad", corrected_sql="SELECT count(*) FROM tpcds.customer"
    )

    FeedbackService(writer).record(feedback)

    assert writer.written[0].corrected_sql is not None


def test_a_correction_that_is_not_a_select_is_refused() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="DROP TABLE customer")

    with pytest.raises(FeedbackError):
        FeedbackService(_Writer()).record(feedback)


def test_a_correction_that_does_not_parse_is_refused() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="SELECT FROM WHERE")

    with pytest.raises(FeedbackError):
        FeedbackService(_Writer()).record(feedback)


def test_a_refused_correction_is_never_written() -> None:
    writer = _Writer()
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="DELETE FROM customer")

    with pytest.raises(FeedbackError):
        FeedbackService(writer).record(feedback)

    assert writer.written == []
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_feedback_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement the service and the repository**

Create `genql/services/semantic/feedback_service.py`:

```python
"""Accepts one rating, refusing a correction that is not a SELECT.

A service rather than the controller calling the port directly, because
"controllers hold no business logic" is a rule this codebase keeps without
exception — and this is business logic: the corrected SQL is the seed of a
future retrieval index, and nothing else in the system will ever validate it.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError
from genql.domain.ports.feedback_writer import FeedbackWriter


class FeedbackService:
    def __init__(self, writer: FeedbackWriter) -> None:
        self._writer = writer

    def record(self, feedback: Feedback) -> None:
        if feedback.corrected_sql is not None:
            self._require_select(feedback.corrected_sql)
        self._writer.write(feedback)

    @staticmethod
    def _require_select(sql: str) -> None:
        try:
            parsed = sqlglot.parse_one(sql, dialect="postgres")
        except sqlglot.errors.ParseError as exc:
            raise FeedbackError(f"the corrected SQL does not parse: {exc}") from exc
        if not isinstance(parsed, exp.Select | exp.Union) and parsed.find(exp.Select) is None:
            raise FeedbackError("the corrected SQL must be a SELECT statement")
```

Create `genql/repositories/semantic/feedback_repository.py` as a plain insert, translating `SQLAlchemyError` into `FeedbackError` — model it on `PostgresRewriteOutcomeWriter` from Task 4.

Export `PostgresFeedbackWriter` from `genql/repositories/semantic/__init__.py`.

Create `tests/integration/test_feedback_repository.py` — one round trip asserting every column persists, and one asserting a rating outside `('good','bad')` is rejected by the database rather than only by Pydantic.

- [ ] **Step 5: Run everything**

Run: `uv run pytest tests/unit -q && uv run pytest tests/integration/test_migration_0010.py tests/integration/test_feedback_repository.py -q; uv run mypy genql && uv run ruff check . && uv run lint-imports`
Expected: unit PASS; integration PASS or clean skip

- [ ] **Step 6: Commit**

```bash
git add migrations genql/repositories/semantic genql/services/semantic/feedback_service.py tests
git commit -m "feat(semantic): capture turn feedback in GenQL's own store"
```

---
### Task 13: `ResultComparator`

**Files:**
- Create: `genql/services/eval/__init__.py`, `genql/services/eval/result_comparator.py`
- Test: `tests/unit/test_result_comparator.py`

**Interfaces:**
- Consumes: existing `genql.domain.entities.execution_result.ExecutionResult`
- Produces: `ResultComparator.compare(reference, generated) -> tuple[bool, str | None]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_result_comparator.py`:

```python
"""The densest unit in Part B, because every accuracy number the ablation
harness reports rests on it. Order insensitivity is required by §15; column
reordering is required because a generated statement may legitimately select
in a different order; numeric normalization is required because a warehouse
returns Decimal and a rewritten aggregate may return float for the same value.

Duplicate counts must be preserved: comparing as sets rather than multisets
would call a query that returns three identical rows equal to one that returns
one, which is exactly the kind of wrong answer a GROUP BY bug produces."""

from __future__ import annotations

from decimal import Decimal

from genql.domain.entities.execution_result import ExecutionResult
from genql.services.eval.result_comparator import ResultComparator


def _result(columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]) -> ExecutionResult:
    return ExecutionResult(
        columns=columns, rows=rows, row_count=len(rows), truncated=False
    )


COMPARATOR = ResultComparator()


def test_identical_results_match() -> None:
    a = _result(("id", "total"), ((1, 10), (2, 20)))

    assert COMPARATOR.compare(a, a) == (True, None)


def test_row_order_does_not_matter() -> None:
    reference = _result(("id",), ((1,), (2,), (3,)))
    generated = _result(("id",), ((3,), (1,), (2,)))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_column_order_does_not_matter() -> None:
    reference = _result(("id", "total"), ((1, 10),))
    generated = _result(("total", "id"), ((10, 1),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_column_names_are_compared_case_insensitively() -> None:
    reference = _result(("Id", "Total"), ((1, 10),))
    generated = _result(("id", "total"), ((1, 10),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_a_missing_column_is_reported_by_name() -> None:
    reference = _result(("id", "total"), ((1, 10),))
    generated = _result(("id",), ((1,),))

    matched, reason = COMPARATOR.compare(reference, generated)

    assert matched is False
    assert reason is not None
    assert "total" in reason


def test_duplicate_rows_are_counted_not_collapsed() -> None:
    reference = _result(("id",), ((1,), (1,), (1,)))
    generated = _result(("id",), ((1,),))

    assert COMPARATOR.compare(reference, generated)[0] is False


def test_a_decimal_equals_the_same_value_as_a_float() -> None:
    reference = _result(("total",), ((Decimal("10.50"),),))
    generated = _result(("total",), ((10.5,),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_an_int_equals_the_same_value_as_a_decimal() -> None:
    reference = _result(("n",), ((Decimal("3"),),))
    generated = _result(("n",), ((3,),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_floats_differing_beyond_tolerance_do_not_match() -> None:
    reference = _result(("total",), ((10.0,),))
    generated = _result(("total",), ((10.5,),))

    assert COMPARATOR.compare(reference, generated)[0] is False


def test_none_matches_none_and_not_zero() -> None:
    assert COMPARATOR.compare(_result(("x",), ((None,),)), _result(("x",), ((None,),)))[0] is True
    assert COMPARATOR.compare(_result(("x",), ((None,),)), _result(("x",), ((0,),)))[0] is False


def test_two_empty_results_with_the_same_columns_match() -> None:
    reference = _result(("id",), ())
    generated = _result(("id",), ())

    assert COMPARATOR.compare(reference, generated) == (True, None)


def test_a_mismatch_reports_the_row_counts() -> None:
    reference = _result(("id",), ((1,), (2,)))
    generated = _result(("id",), ((1,),))

    matched, reason = COMPARATOR.compare(reference, generated)

    assert matched is False
    assert reason is not None
    assert "2" in reason and "1" in reason
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_result_comparator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.eval'`

- [ ] **Step 3: Implement the comparator**

Create `genql/services/eval/__init__.py` (empty docstring module) and `genql/services/eval/result_comparator.py`:

```python
"""Order-insensitive execution-result comparison.

The parent spec's §15: results are compared, never SQL strings. Three
normalizations make that comparison mean what it should:

Columns are matched by lower-cased name and the generated result's columns are
permuted into the reference's order, because a generated statement may
legitimately project in a different order and that is not a wrong answer.

Rows are compared as multisets. Not lists, because ORDER BY is not part of
most questions; not sets, because a query that returns three identical rows is
genuinely different from one that returns one, and collapsing them would hide
exactly the GROUP BY bug this comparison exists to catch.

Numbers are normalized to float within a relative tolerance, because a
warehouse returns Decimal while a rewritten aggregate may return float for the
same value. `None` is never normalized to anything: NULL and 0 are different
answers.
"""

from __future__ import annotations

import math
from collections import Counter
from decimal import Decimal
from typing import Any

from genql.domain.entities.execution_result import ExecutionResult

_RELATIVE_TOLERANCE = 1e-9


def _key(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal | int | float):
        # Rounded to a fixed relative precision so that Decimal("10.50"), 10.5,
        # and 10.500000000000001 all land on the same key. Comparing with
        # math.isclose per pair would be O(n^2) over the whole result set.
        as_float = float(value)
        if not math.isfinite(as_float):
            return as_float
        return round(as_float, 9)
    return str(value)


class ResultComparator:
    def compare(
        self, reference: ExecutionResult, generated: ExecutionResult
    ) -> tuple[bool, str | None]:
        reference_columns = [c.lower() for c in reference.columns]
        generated_columns = [c.lower() for c in generated.columns]

        missing = [c for c in reference_columns if c not in generated_columns]
        extra = [c for c in generated_columns if c not in reference_columns]
        if missing or extra:
            return False, (
                f"column mismatch: missing {missing or 'none'}, unexpected {extra or 'none'}"
            )

        order = [generated_columns.index(c) for c in reference_columns]
        reference_rows = Counter(tuple(_key(v) for v in row) for row in reference.rows)
        generated_rows = Counter(
            tuple(_key(row[i]) for i in order) for row in generated.rows
        )
        if reference_rows == generated_rows:
            return True, None
        return False, (
            f"result mismatch: reference returned {len(reference.rows)} rows, "
            f"generated returned {len(generated.rows)}"
        )
```

Note the `_RELATIVE_TOLERANCE` constant is declared but the implementation rounds instead. Delete the constant — an unused module-level name in a file this central is exactly the kind of drift that misleads the next reader. (`ruff` will not flag it; remove it deliberately.)

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_result_comparator.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add genql/services/eval tests/unit/test_result_comparator.py
git commit -m "feat(eval): add order-insensitive execution-result comparison"
```

---

### Task 14: The golden-set reader, the report writer, and the first fixtures

**Files:**
- Create: `genql/repositories/eval/__init__.py`, `genql/repositories/eval/yaml_golden_set_repository.py`, `genql/repositories/eval/json_report_repository.py`, `golden/tpcds_core.yaml`, `tests/integration/test_yaml_golden_set_repository.py`
- Test: `tests/integration/test_yaml_golden_set_repository.py`

**Interfaces:**
- Consumes: Task 11's `GoldenCase`, `GoldenSetReader`, `ReportWriter`, `GoldenSetError`; Task 10's `golden/phase7_equivalence.yaml`
- Produces: `YamlGoldenSetReader(directory)`; `JsonReportWriter()`; `golden/tpcds_core.yaml`

- [ ] **Step 1: Write the failing reader test**

Create `tests/integration/test_yaml_golden_set_repository.py`:

```python
"""File I/O, so an integration test even though no database is involved.

The malformed-file assertion matters more than the happy path: a reader that
silently skips a broken fixture makes every accuracy number afterwards quietly
optimistic, and nothing downstream can detect it."""

from __future__ import annotations

from pathlib import Path

import pytest

from genql.domain.errors import GoldenSetError
from genql.repositories.eval.yaml_golden_set_repository import YamlGoldenSetReader

VALID = """
cases:
  - case_id: c1
    question: how many customers
    datasource_name: local
    failure_class: ambiguous_intent
    reference_sql: SELECT count(*) FROM tpcds.customer
  - case_id: c2
    question: how many stores
    datasource_name: other
    failure_class: context_sensitivity
    reference_sql: SELECT count(*) FROM tpcds.store
"""


def test_every_case_in_every_file_is_read(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(VALID)

    cases = YamlGoldenSetReader(str(tmp_path)).read_cases()

    assert {c.case_id for c in cases} == {"c1", "c2"}


def test_cases_can_be_filtered_by_datasource(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(VALID)

    cases = YamlGoldenSetReader(str(tmp_path)).read_cases("local")

    assert [c.case_id for c in cases] == ["c1"]


def test_cases_are_returned_in_a_stable_order(tmp_path: Path) -> None:
    """Two runs of the same fixtures must line up case-for-case, or an
    ablation delta is comparing different sets."""
    (tmp_path / "b.yaml").write_text(VALID)
    (tmp_path / "a.yaml").write_text(
        VALID.replace("c1", "c0").replace("c2", "c3").replace("local", "local")
    )

    first = [c.case_id for c in YamlGoldenSetReader(str(tmp_path)).read_cases()]
    second = [c.case_id for c in YamlGoldenSetReader(str(tmp_path)).read_cases()]

    assert first == second == sorted(first)


def test_a_malformed_file_raises_and_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("cases:\n  - case_id: c1\n    question: q\n")

    with pytest.raises(GoldenSetError) as exc:
        YamlGoldenSetReader(str(tmp_path)).read_cases()

    assert "broken.yaml" in str(exc.value)


def test_an_unknown_failure_class_raises(tmp_path: Path) -> None:
    (tmp_path / "bad_class.yaml").write_text(VALID.replace("ambiguous_intent", "invented"))

    with pytest.raises(GoldenSetError):
        YamlGoldenSetReader(str(tmp_path)).read_cases()


def test_a_missing_directory_raises_rather_than_returning_nothing(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError):
        YamlGoldenSetReader(str(tmp_path / "nope")).read_cases()


def test_the_repositorys_own_fixtures_load(tmp_path: Path) -> None:
    """The committed fixtures must parse, or every later task's runs are empty."""
    cases = YamlGoldenSetReader("golden").read_cases()

    assert len(cases) >= 6
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_yaml_golden_set_repository.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the two file repositories**

Create `genql/repositories/eval/yaml_golden_set_repository.py`:

```python
"""Reads golden cases from `*.yaml` under one directory.

Every failure is loud. A missing directory, an unreadable file, a case with a
missing field, and a case naming a failure class that does not exist all raise
GoldenSetError naming the file — because the alternative, skipping quietly,
makes an accuracy number optimistic in a way nothing downstream can detect.

Files are read in sorted filename order and cases keep their in-file order, so
two runs over the same directory produce the same sequence. An ablation delta
compares two runs case-for-case; an unstable order would compare different
sets and report the difference as an effect.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from genql.domain.entities.golden_case import GoldenCase
from genql.domain.errors import GoldenSetError


class YamlGoldenSetReader:
    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]:
        if not self._directory.is_dir():
            raise GoldenSetError(f"no golden-set directory at {self._directory}")

        cases: list[GoldenCase] = []
        for path in sorted(self._directory.glob("*.yaml")):
            cases.extend(self._read_file(path))

        if datasource_name is None:
            return tuple(cases)
        return tuple(c for c in cases if c.datasource_name == datasource_name)

    @staticmethod
    def _read_file(path: Path) -> list[GoldenCase]:
        try:
            payload = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise GoldenSetError(f"{path.name}: could not be read: {exc}") from exc

        raw_cases = (payload or {}).get("cases")
        if not isinstance(raw_cases, list):
            raise GoldenSetError(f"{path.name}: expected a top-level `cases` list")

        parsed: list[GoldenCase] = []
        for index, raw in enumerate(raw_cases):
            try:
                parsed.append(GoldenCase.model_validate(raw))
            except ValidationError as exc:
                raise GoldenSetError(f"{path.name}: case {index} is invalid: {exc}") from exc
        return parsed
```

Create `genql/repositories/eval/json_report_repository.py`:

```python
"""Writes evaluation reports as JSON.

JSON rather than the printed table because the table is for a person reading
one run and this is for comparing runs over time — and because a Pydantic
model already serializes itself correctly, including the computed accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import EvaluationError


class JsonReportWriter:
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None:
        payload = [
            {
                "ablation": report.ablation_name,
                "accuracy": report.accuracy,
                "passed": report.passed_count,
                "total": len(report.outcomes),
                "outcomes": [outcome.model_dump() for outcome in report.outcomes],
            }
            for report in reports
        ]
        try:
            Path(path).write_text(json.dumps(payload, indent=2, default=str))
        except OSError as exc:
            raise EvaluationError(f"could not write the report to {path}: {exc}") from exc
```

- [ ] **Step 4: Write the first curated fixtures**

Create `golden/tpcds_core.yaml` with **at least six** additional cases beyond `golden/phase7_equivalence.yaml`, weighted toward the parent spec's four failure classes per §14. Use the same schema as `phase7_equivalence.yaml`. Every `reference_sql` must be run against real `local.tpcds` and confirmed to return rows before committing — a fixture returning nothing passes vacuously against a generated statement that also returns nothing.

Write cases that actually exercise the failure classes rather than restating easy aggregates:

- `ambiguous_intent` — a question with a defensible second reading ("sales last quarter": calendar or fiscal).
- `absent_business_knowledge` — a question needing a definition that is not in the schema ("net sales", which in TPC-DS means sales less returns).
- `physical_modelling_variation` — a question whose answer depends on how returns are modelled (a separate `store_returns` table rather than negative facts).
- `context_sensitivity` — a question depending on the current date or the fiscal calendar.

- [ ] **Step 5: Run the reader tests**

Run: `uv run pytest tests/integration/test_yaml_golden_set_repository.py -q`
Expected: PASS (7 tests)

- [ ] **Step 6: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run lint-imports`

```bash
git add genql/repositories/eval golden tests/integration/test_yaml_golden_set_repository.py
git commit -m "feat(eval): read golden cases from YAML and write JSON run reports"
```

---

### Task 15: `GoldenEvaluationService`

**Files:**
- Create: `genql/services/eval/golden_evaluation_service.py`
- Test: `tests/unit/test_golden_evaluation_service.py`

**Interfaces:**
- Consumes: Task 13's `ResultComparator`, Task 11's `GoldenCase`/`GoldenOutcome`/`GoldenRunReport`/`TurnRunner`, existing `GuardedExecutionService`
- Produces: `GoldenEvaluationService(execution, comparator)` with `run(ablation_name, cases, runner) -> GoldenRunReport`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_golden_evaluation_service.py`:

```python
"""One property dominates: the run always completes. A paused turn, a
short-circuited intent, an over-budget narrowing, a raised error, and a
truncated reference are each a failed case with a named reason — never an
exception that costs the other forty-nine cases their run."""

from __future__ import annotations

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import SchemaLinkingError
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.result_comparator import ResultComparator

CASE = GoldenCase(
    case_id="c1",
    question="how many customers",
    datasource_name="local",
    reference_sql="SELECT count(*) FROM tpcds.customer",
    failure_class="ambiguous_intent",
)
EXPECTED = ExecutionResult(columns=("n",), rows=((100,),), row_count=1, truncated=False)
OTHER = ExecutionResult(columns=("n",), rows=((7,),), row_count=1, truncated=False)
TRUNCATED = ExecutionResult(columns=("n",), rows=((100,),), row_count=1, truncated=True)


class _Execution:
    def __init__(self, result: ExecutionResult = EXPECTED) -> None:
        self.result = result
        self.calls: list[str] = []

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        self.calls.append(sql)
        return self.result


class _Runner:
    def __init__(self, response: TurnResponse) -> None:
        self.response = response

    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        return self.response


class _RaisingRunner:
    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        raise SchemaLinkingError("no catalogued object matched")


def _service(execution: _Execution) -> GoldenEvaluationService:
    return GoldenEvaluationService(execution=execution, comparator=ResultComparator())


def _finished(result: ExecutionResult) -> TurnResponse:
    return TurnResponse(thread_id="t-1", validated_sql="SELECT count(*) FROM c", result=result)


def test_a_matching_result_passes() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.ablation_name == "full"
    assert report.outcomes[0].passed is True
    assert report.outcomes[0].generated_sql == "SELECT count(*) FROM c"


def test_a_differing_result_fails_with_a_reason() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(OTHER)))

    assert report.outcomes[0].passed is False
    assert "mismatch" in (report.outcomes[0].failure_reason or "")


def test_a_paused_turn_fails_with_a_named_reason_rather_than_hanging() -> None:
    paused = TurnResponse(thread_id="t-1", clarifying_question="which quarter?")

    report = _service(_Execution()).run("full", (CASE,), _Runner(paused))

    assert report.outcomes[0].passed is False
    assert "clarification" in (report.outcomes[0].failure_reason or "")


def test_a_short_circuited_intent_fails_with_a_named_reason() -> None:
    other = TurnResponse(thread_id="t-1", intent="non_sql")

    report = _service(_Execution()).run("full", (CASE,), _Runner(other))

    assert report.outcomes[0].passed is False
    assert "non_sql" in (report.outcomes[0].failure_reason or "")


def test_an_over_budget_turn_fails_with_the_narrowing_suggestion() -> None:
    over = TurnResponse(
        thread_id="t-1", validated_sql="SELECT 1", narrowing_suggestion="too expensive"
    )

    report = _service(_Execution()).run("full", (CASE,), _Runner(over))

    assert report.outcomes[0].passed is False
    assert "budget" in (report.outcomes[0].failure_reason or "").lower()


def test_a_raising_turn_fails_with_the_errors_text_and_the_run_completes() -> None:
    report = _service(_Execution()).run("full", (CASE, CASE), _RaisingRunner())

    assert len(report.outcomes) == 2
    assert all(o.passed is False for o in report.outcomes)
    assert "no catalogued object matched" in (report.outcomes[0].failure_reason or "")


def test_a_truncated_reference_is_a_fixture_error_not_a_verdict() -> None:
    report = _service(_Execution(TRUNCATED)).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.outcomes[0].passed is False
    assert "row cap" in (report.outcomes[0].failure_reason or "")


def test_every_outcome_carries_its_cases_failure_class() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.outcomes[0].failure_class == "ambiguous_intent"


def test_an_empty_case_set_produces_an_empty_report_rather_than_raising() -> None:
    report = _service(_Execution()).run("full", (), _Runner(_finished(EXPECTED)))

    assert report.outcomes == ()
    assert report.accuracy == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_golden_evaluation_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `genql/services/eval/golden_evaluation_service.py`:

```python
"""Runs the golden set and reports what happened, case by case.

Nothing here raises for a case-level problem. A run over fifty cases that
aborts on case three has measured nothing, and the four ways a turn can end
without rows — paused, short-circuited, over budget, failed — are all just
"this case did not produce the expected result", each with its own reason
string so the report says which.

The reference statement runs through the same GuardedExecutionService as the
generated one, so both sides share a row cap. That makes a truncated reference
a fixture error rather than a verdict: truncation is order-dependent, so two
truncated result sets are not comparable even when the underlying queries
agree.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_outcome import GoldenOutcome
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import GenqlError
from genql.domain.ports.turn_runner import TurnRunner
from genql.services.eval.result_comparator import ResultComparator
from genql.services.query.guarded_execution_service import GuardedExecutionService


class GoldenEvaluationService:
    def __init__(
        self, execution: GuardedExecutionService, comparator: ResultComparator
    ) -> None:
        self._execution = execution
        self._comparator = comparator

    def run(
        self, ablation_name: str, cases: Sequence[GoldenCase], runner: TurnRunner
    ) -> GoldenRunReport:
        return GoldenRunReport(
            ablation_name=ablation_name,
            outcomes=tuple(self._run_case(case, runner) for case in cases),
        )

    def _run_case(self, case: GoldenCase, runner: TurnRunner) -> GoldenOutcome:
        started = time.perf_counter()
        try:
            expected = self._execution.execute(case.reference_sql, case.datasource_name)
        except GenqlError as exc:
            return self._failed(case, started, None, f"reference SQL failed: {exc}")
        if expected.truncated:
            return self._failed(
                case,
                started,
                None,
                "reference result exceeds the row cap — narrow the fixture",
            )

        try:
            response = runner.run(case.question, case.datasource_name, case.domain_id)
        except GenqlError as exc:
            return self._failed(case, started, None, str(exc))

        reason = _why_no_result(response)
        if reason is not None:
            return self._failed(case, started, response.validated_sql, reason)

        assert response.result is not None  # guaranteed by _why_no_result
        matched, mismatch = self._comparator.compare(expected, response.result)
        return GoldenOutcome(
            case_id=case.case_id,
            failure_class=case.failure_class,
            passed=matched,
            generated_sql=response.validated_sql,
            failure_reason=None if matched else mismatch,
            elapsed_ms=_elapsed(started),
        )

    @staticmethod
    def _failed(
        case: GoldenCase, started: float, sql: str | None, reason: str
    ) -> GoldenOutcome:
        return GoldenOutcome(
            case_id=case.case_id,
            failure_class=case.failure_class,
            passed=False,
            generated_sql=sql,
            failure_reason=reason,
            elapsed_ms=_elapsed(started),
        )


def _elapsed(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


def _why_no_result(response: TurnResponse) -> str | None:
    """The four ways a turn ends without rows, each named for the report."""
    if response.clarifying_question is not None:
        return f"paused for clarification: {response.clarifying_question}"
    if response.narrowing_suggestion is not None:
        return f"stopped by the cost budget: {response.narrowing_suggestion}"
    if response.intent is not None:
        return f"short-circuited as a {response.intent} question"
    if response.result is None:
        return "the turn produced no result"
    return None
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/unit/test_golden_evaluation_service.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add genql/services/eval/golden_evaluation_service.py tests/unit/test_golden_evaluation_service.py
git commit -m "feat(eval): run the golden set and report every case's outcome"
```

---
### Task 16: The `ABLATIONS` registry, the null adapters, and the compiler flag

**Files:**
- Create: `genql/services/eval/registry.py`, `genql/services/eval/ablations/__init__.py`, `genql/services/eval/ablations/full.py`, `no_descriptions.py`, `no_domains.py`, `no_join_paths.py`, `no_probing.py`, `no_ambiguity_examples.py`, `genql/repositories/null/__init__.py`, `genql/repositories/null/null_join_path_reader.py`, `genql/repositories/null/null_ambiguity_example_reader.py`
- Modify: `genql/repositories/semantic/search_document_repository.py`
- Test: `tests/unit/test_ablations.py`, `tests/unit/test_search_document_compiler_ablation.py`

**Interfaces:**
- Consumes: Task 11's `Ablation`; existing `JoinPathReader`, `AmbiguityExampleReader` ports
- Produces: `ABLATIONS: Registry[Ablation]` with six keys; `NullJoinPathReader`, `NullAmbiguityExampleReader`; `SearchDocumentCompiler(engine, embedder, include_enrichment=True)`

- [ ] **Step 1: Write the failing ablation test**

Create `tests/unit/test_ablations.py`:

```python
"""Each ablation's identity, and the two properties the harness depends on:
`full` changes nothing, and exactly one ablation needs a recompile. A second
recompiling ablation appearing without anyone noticing would double every
ablation run's cost silently."""

from __future__ import annotations

import pytest

from genql.core.settings import Settings
from genql.services.eval.registry import ABLATIONS


def test_the_registry_holds_the_six_ablations() -> None:
    assert ABLATIONS.keys() == [
        "full",
        "no_ambiguity_examples",
        "no_descriptions",
        "no_domains",
        "no_join_paths",
        "no_probing",
    ]


def test_every_ablation_reports_its_own_registry_key_as_its_name() -> None:
    for key in ABLATIONS.keys():
        assert ABLATIONS.create(key).name == key


def test_the_baseline_overrides_nothing_and_needs_no_recompile() -> None:
    full = ABLATIONS.create("full")

    assert full.setting_overrides == ()
    assert full.requires_recompile is False


def test_only_no_descriptions_requires_a_recompile() -> None:
    recompiling = [k for k in ABLATIONS.keys() if ABLATIONS.create(k).requires_recompile]

    assert recompiling == ["no_descriptions"]


@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("no_descriptions", "enrichment_enabled"),
        ("no_domains", "domain_scoping_enabled"),
        ("no_join_paths", "join_paths_enabled"),
        ("no_probing", "probing_enabled"),
        ("no_ambiguity_examples", "ambiguity_examples_enabled"),
    ],
)
def test_each_ablation_switches_off_exactly_its_own_layer(key: str, field: str) -> None:
    ablation = ABLATIONS.create(key)

    assert ablation.setting_overrides == ((field, False),)


def test_every_overridden_field_actually_exists_on_settings() -> None:
    """The override is applied by name, so a typo would be a silent no-op —
    the ablation would report 'no delta' because nothing was switched off."""
    for key in ABLATIONS.keys():
        for field, _ in ABLATIONS.create(key).setting_overrides:
            assert field in Settings.model_fields


def test_every_ablation_carries_a_description_for_the_report_header() -> None:
    for key in ABLATIONS.keys():
        assert ABLATIONS.create(key).description
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ablations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.eval.registry'`

- [ ] **Step 3: Create the registry and the six ablations**

Create `genql/services/eval/registry.py`:

```python
"""The ablation registry, keyed by ablation name.

It lives under `services/` rather than `repositories/` because an Ablation is
a pure value with no I/O — the same reason `genql/services/scope/registry.py`
lives there. Registry stores classes, so each ablation is an Ablation subclass
whose defaults *are* its values, and `ABLATIONS.create(key)` returns the value.

Adding an ablation is one new file plus one decorator. AblationService never
names one, which is what keeps "measure another layer" from being a code
change to the harness.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.registries.registry import Registry

ABLATIONS: Registry[Ablation] = Registry("ablations")
```

Create `genql/services/eval/ablations/full.py`:

```python
"""The baseline every other ablation's delta is measured against."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("full")
class FullAblation(Ablation):
    name: str = "full"
    description: str = "every enrichment layer enabled — the baseline"
```

Create `genql/services/eval/ablations/no_descriptions.py`:

```python
"""Descriptions, aliases, and units removed from the compiled search text.

The only ablation that needs a recompile: enrichment never reaches the online
path through a query-time read. SchemaLinkingService reads structural columns,
join paths, and metrics; descriptions influence a turn only through the BM25
text and the embedding that SearchDocumentCompiler assembles offline. A null
adapter at query time would switch off nothing and report a reassuring "no
delta" that meant only that the wrong thing had been disabled.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_descriptions")
class NoDescriptionsAblation(Ablation):
    name: str = "no_descriptions"
    description: str = "search documents compiled from structural fields only"
    setting_overrides: tuple[tuple[str, bool], ...] = (("enrichment_enabled", False),)
    requires_recompile: bool = True
```

Create the remaining four in the same shape, one file each:

| File | `name` | `description` | `setting_overrides` |
|---|---|---|---|
| `no_domains.py` | `no_domains` | `domain scoping skipped; retrieval sees every object` | `(("domain_scoping_enabled", False),)` |
| `no_join_paths.py` | `no_join_paths` | `mined join paths withheld from schema linking` | `(("join_paths_enabled", False),)` |
| `no_probing.py` | `no_probing` | `no probe queries; selection falls back to critique ranking` | `(("probing_enabled", False),)` |
| `no_ambiguity_examples.py` | `no_ambiguity_examples` | `no synthetic few-shot examples during generation` | `(("ambiguity_examples_enabled", False),)` |

Create `genql/services/eval/ablations/__init__.py` importing all six modules for their registration side effects, exactly as `genql/repositories/query/rewrite_rules/__init__.py` does, and re-exporting `ABLATIONS`.

- [ ] **Step 4: Run the ablation test**

Run: `uv run pytest tests/unit/test_ablations.py -q`
Expected: PASS

- [ ] **Step 5: Create the two null adapters**

Create `genql/repositories/null/__init__.py`:

```python
"""Port implementations that return nothing, used only by the ablation harness.

They live under `repositories/` rather than beside the services because they
stand in for repositories: the composition root swaps one in exactly where the
real repository would have gone, so the service under ablation runs its normal
code against an empty upstream. That is what makes the measurement honest — a
service that branched on being ablated would not be the service being
measured.
"""
```

Create `genql/repositories/null/null_join_path_reader.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.join_path import JoinPath


class NullJoinPathReader:
    """JoinPathReader that has mined nothing."""

    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return ()
```

Create `genql/repositories/null/null_ambiguity_example_reader.py` in the same shape, returning `()` from `search(question, domain_id, top_k)`. Read `genql/domain/ports/ambiguity_example_reader.py` first and match its signature exactly.

Add a test to `tests/unit/test_ablations.py` asserting each null adapter satisfies its port via `isinstance`.

- [ ] **Step 6: Write the failing compiler-flag test**

Create `tests/unit/test_search_document_compiler_ablation.py`:

```python
"""The ablated document keeps every structural field and loses every enriched
one. Asserting both halves matters: a flag that dropped column names too would
ablate far more than 'descriptions' and would make the measured delta mean
something else entirely."""

from __future__ import annotations

from genql.repositories.semantic.search_document_repository import _content_for


def test_the_enriched_content_carries_descriptions_aliases_and_units() -> None:
    content = _content_for(
        object_name="store_sales",
        object_type="TABLE",
        domain_name="sales",
        description="one row per line item sold in a store",
        business_alias="POS line items",
        columns=[("ss_ext_sales_price", "extended sales price", "USD", ["1.00", "2.00"])],
        include_enrichment=True,
    )

    assert "one row per line item sold in a store" in content
    assert "POS line items" in content
    assert "USD" in content
    assert "extended sales price" in content


def test_the_ablated_content_keeps_structure_and_samples_but_drops_enrichment() -> None:
    content = _content_for(
        object_name="store_sales",
        object_type="TABLE",
        domain_name="sales",
        description="one row per line item sold in a store",
        business_alias="POS line items",
        columns=[("ss_ext_sales_price", "extended sales price", "USD", ["1.00", "2.00"])],
        include_enrichment=False,
    )

    assert "store_sales" in content
    assert "TABLE" in content
    assert "sales" in content
    assert "ss_ext_sales_price" in content
    assert "1.00" in content  # profiled samples are data, not LLM enrichment
    assert "one row per line item" not in content
    assert "POS line items" not in content
    assert "extended sales price" not in content
```

- [ ] **Step 7: Add the flag to the compiler**

In `genql/repositories/semantic/search_document_repository.py`:

1. Extract the content assembly currently inlined in `compile` into a module-level function `_content_for(object_name, object_type, domain_name, description, business_alias, columns, include_enrichment)`, where `columns` is a sequence of `(column_name, description, unit, sample_values)` tuples. Extracting it is what makes the behaviour unit-testable without a database, which is why the test above imports it directly.
2. When `include_enrichment` is false, omit the object description, the business alias, and each column's description and unit. Keep the object name, the object type, the domain name, the column names, and the profiled sample values — sample values come from data profiling, not from LLM enrichment, and §15's "no descriptions" names the enrichment layer specifically.
3. Add `include_enrichment: bool = True` to `SearchDocumentCompiler.__init__` and pass it through. Defaulting to `True` means every existing construction site keeps working unchanged.
4. Record in the class docstring that the flag exists for the ablation harness and is never set from the environment.

- [ ] **Step 8: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add genql/services/eval genql/repositories/null genql/repositories/semantic/search_document_repository.py tests/unit/test_ablations.py tests/unit/test_search_document_compiler_ablation.py
git commit -m "feat(eval): register the six ablations and make each layer switchable off"
```

---

### Task 17: `Container.with_overrides`, `GraphTurnRunner`, and the two harness adapters

**Files:**
- Create: `genql/api/graph_turn_runner.py`, `genql/infrastructure/eval/__init__.py`, `genql/infrastructure/eval/turn_runner_factory.py`, `genql/infrastructure/eval/search_document_recompiler.py`, `genql/composition/eval_container.py`
- Modify: `genql/composition_root.py`, `genql/composition/optimizer_container.py`, `tests/integration/test_phase7_end_to_end.py`
- Test: `tests/unit/test_graph_turn_runner.py`, `tests/unit/test_container_overrides.py`

**Interfaces:**
- Consumes: Task 11's `TurnRunner`, `TurnRunnerFactory`, `SearchDocumentRecompiler`, `Ablation`; existing `start_turn`, `ThreadLockFactory`, `CompileService`
- Produces: `Container.with_overrides(**fields) -> Container`; `GraphTurnRunner(graph, locks)`; `TurnRunnerFactoryImpl()`; `SearchDocumentRecompilerImpl()`; `EvalContainer` providing `golden_set_reader`, `report_writer`, `result_comparator`, `golden_evaluation_service`, `turn_runner`, `turn_runner_factory`, `search_document_recompiler`, `feedback_writer`, `feedback_service`

- [ ] **Step 1: Write the failing runner test**

Create `tests/unit/test_graph_turn_runner.py`:

```python
"""A thin adapter, with one behaviour worth pinning: every run gets a fresh
thread id. Reusing one would make the second case in a golden run resume the
first case's checkpoint."""

from __future__ import annotations

from contextlib import contextmanager

from genql.api.graph_turn_runner import GraphTurnRunner
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.turn_runner import TurnRunner


class _Locks:
    @contextmanager
    def for_thread(self, thread_id: str):  # type: ignore[no-untyped-def]
        yield


class _Graph:
    def __init__(self) -> None:
        self.threads: list[str] = []

    def invoke(self, state, config):  # type: ignore[no-untyped-def]
        self.threads.append(config["configurable"]["thread_id"])
        return {**state, "validated_sql": "SELECT 1", "result": None, "optimization": None}


def test_the_runner_satisfies_its_port() -> None:
    assert isinstance(GraphTurnRunner(_Graph(), _Locks()), TurnRunner)


def test_each_run_uses_a_fresh_thread_id() -> None:
    graph = _Graph()
    runner = GraphTurnRunner(graph, _Locks())

    runner.run("q1", "local")
    runner.run("q2", "local")

    assert len(set(graph.threads)) == 2


def test_the_runner_returns_a_turn_response() -> None:
    response = GraphTurnRunner(_Graph(), _Locks()).run("q", "local")

    assert isinstance(response, TurnResponse)
```

- [ ] **Step 2: Create `GraphTurnRunner`**

Create `genql/api/graph_turn_runner.py`:

```python
"""The TurnRunner implementation, in the api layer because that is where the
graph is.

`genql/services/` may not import `genql/api/`, and `start_turn` lives here, so
the adapter lives here too and the composition root injects it into the
evaluation service — the same arrangement used for every repository adapter.
The service depends only on the protocol, which `lint-imports` verifies.

A fresh thread id per run, generated by start_turn's own default: an
evaluation has no follow-up turns, and reusing an id would make the second
case resume the first case's checkpoint.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_turn import start_turn
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.thread_lock import ThreadLockFactory


class GraphTurnRunner:
    def __init__(self, graph: Any, locks: ThreadLockFactory) -> None:
        self._graph = graph
        self._locks = locks

    def run(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> TurnResponse:
        return start_turn(self._graph, self._locks, question, datasource_name, domain_id)
```

- [ ] **Step 3: Write the failing override test**

Create `tests/unit/test_container_overrides.py`:

```python
"""with_overrides is the whole ablation mechanism, so it gets its own test:
the override lands, the base container is untouched, and an unknown field is
refused rather than silently ignored — a typo'd override would produce a
'no delta' result that looks like a finding."""

from __future__ import annotations

import pytest

from genql.composition_root import Container


def test_an_override_reaches_settings() -> None:
    container = Container.with_overrides(domain_scoping_enabled=False)

    assert container.settings().domain_scoping_enabled is False


def test_the_base_container_is_unaffected() -> None:
    Container.with_overrides(domain_scoping_enabled=False)

    assert Container().settings().domain_scoping_enabled is True


def test_several_overrides_apply_together() -> None:
    container = Container.with_overrides(probing_enabled=False, cost_budget=1.0)

    assert container.settings().probing_enabled is False
    assert container.settings().cost_budget == 1.0


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValueError, match="not_a_setting"):
        Container.with_overrides(not_a_setting=False)
```

- [ ] **Step 4: Implement `with_overrides`**

Add to `Container` in `genql/composition_root.py`:

```python
    @classmethod
    def with_overrides(cls, **fields: object) -> "Container":
        """A container whose Settings carry the given field values.

        The whole ablation mechanism. A pre-built Settings passed through
        providers.Object rather than dependency_injector's override() machinery:
        one line, obviously correct, and independent of override-reset semantics
        across seven inherited container classes.

        Unknown fields raise rather than being ignored, because a typo'd
        override switches nothing off and the resulting "no delta" reads as a
        finding about the architecture rather than as a bug in the harness.
        """
        unknown = sorted(set(fields) - set(Settings.model_fields))
        if unknown:
            raise ValueError(f"unknown settings field(s): {', '.join(unknown)}")

        container = cls()
        base = container.settings()
        container.settings.override(providers.Object(base.model_copy(update=dict(fields))))
        return container
```

Import `Settings` from `genql.core.settings` at the top of the module. If `settings` is declared on a base container rather than on `Container`, the override still resolves through inheritance — verify with the test rather than by reasoning.

- [ ] **Step 5: Create the two harness adapters**

Create `genql/infrastructure/eval/turn_runner_factory.py`:

```python
"""Builds a TurnRunner over a container carrying one ablation's overrides.

In `infrastructure/` rather than `services/` because it constructs a Container,
and the composition root is not something a service may reach. AblationService
holds the port; this is the only code that knows an ablation becomes a
container.
"""

from __future__ import annotations

from genql.api.graph_turn_runner import GraphTurnRunner
from genql.domain.entities.ablation import Ablation
from genql.domain.ports.turn_runner import TurnRunner


class TurnRunnerFactoryImpl:
    def for_ablation(self, ablation: Ablation) -> TurnRunner:
        from genql.composition_root import Container

        container = Container.with_overrides(**dict(ablation.setting_overrides))
        return GraphTurnRunner(container.query_graph(), container.thread_lock_factory())
```

The deferred import of `Container` is deliberate and is the one place in the codebase that needs one: `composition_root` imports every container, which imports this module, and a module-level import here would close the cycle. Note it in the docstring.

Create `genql/infrastructure/eval/search_document_recompiler.py`:

```python
"""Rebuilds genql_search_document under one ablation's overrides.

Used only by no_descriptions. Returns the document count so AblationService's
caller can print what it did — a recompile that silently produced zero
documents would make every case in that run fail for the wrong reason.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation


class SearchDocumentRecompilerImpl:
    def recompile(self, ablation: Ablation, datasource_name: str) -> int:
        from genql.composition_root import Container

        container = Container.with_overrides(**dict(ablation.setting_overrides))
        return container.compile_service().compile(datasource_name).documents
```

If the compile provider is named something other than `compile_service`, use the real name — check `genql/composition/semantic_container.py`.

- [ ] **Step 6: Create `EvalContainer`**

Create `genql/composition/eval_container.py` extending `OptimizerContainer`, providing:

```python
    golden_set_reader = providers.Singleton(
        YamlGoldenSetReader, directory=OptimizerContainer.settings.provided.golden_set_dir
    )
    report_writer = providers.Singleton(JsonReportWriter)
    result_comparator = providers.Singleton(ResultComparator)
    golden_evaluation_service = providers.Singleton(
        GoldenEvaluationService,
        execution=OptimizerContainer.guarded_execution_service,
        comparator=result_comparator,
    )
    turn_runner = providers.Singleton(
        GraphTurnRunner,
        graph=OptimizerContainer.query_graph,
        locks=OptimizerContainer.thread_lock_factory,
    )
    turn_runner_factory = providers.Singleton(TurnRunnerFactoryImpl)
    search_document_recompiler = providers.Singleton(SearchDocumentRecompilerImpl)
    feedback_writer = providers.Singleton(
        PostgresFeedbackWriter, engine=OptimizerContainer.semantic_engine
    )
    feedback_service = providers.Singleton(FeedbackService, writer=feedback_writer)
```

Then point `composition_root.Container` at `EvalContainer` instead of `OptimizerContainer`, updating `_step_service_providers`' references the same way Task 9 did.

- [ ] **Step 7: Collapse Task 10's ad-hoc budget override**

In `tests/integration/test_phase7_end_to_end.py`, replace the `turn_with_budget` fixture's hand-rolled container construction with `Container.with_overrides(cost_budget=...)`, and delete the comment Task 10 left pointing here.

- [ ] **Step 8: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS, including the `layers` contract — `GraphTurnRunner` in `genql/api/` importing `genql/services/` is legal; a service importing it would not be.

```bash
git add genql/api/graph_turn_runner.py genql/infrastructure/eval genql/composition genql/composition_root.py tests
git commit -m "feat(composition): add settings overrides, the turn runner, and the ablation adapters"
```

---
### Task 18: `AblationService`

**Files:**
- Create: `genql/services/eval/ablation_service.py`
- Modify: `genql/composition/eval_container.py`
- Test: `tests/unit/test_ablation_service.py`

**Interfaces:**
- Consumes: Tasks 11, 15, 16, 17 — `ABLATIONS`, `TurnRunnerFactory`, `SearchDocumentRecompiler`, `GoldenEvaluationService`, `UnknownAblationError`
- Produces: `AblationService(evaluation, runners, recompiler)` with `run(ablation_names, cases) -> tuple[GoldenRunReport, ...]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ablation_service.py`:

```python
"""Two properties carry the harness. Every ablation must get its own runner —
sharing one would measure the baseline five times and report five identical
"no delta" results. And a recompiling ablation must restore the store even
when its run raises, because a left-behind ablated compile silently degrades
every subsequent turn, including real user turns."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import UnknownAblationError
from genql.services.eval.ablation_service import AblationService

CASE = GoldenCase(
    case_id="c1",
    question="q",
    datasource_name="local",
    reference_sql="SELECT 1",
    failure_class="ambiguous_intent",
)


class _Runner:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        raise AssertionError("the evaluation fake should be driving this")


class _Runners:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def for_ablation(self, ablation: Ablation) -> _Runner:
        self.requested.append(ablation.name)
        return _Runner(ablation.name)


class _Recompiler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def recompile(self, ablation: Ablation, datasource_name: str) -> int:
        self.calls.append(ablation.name)
        return 24


class _Evaluation:
    def __init__(self) -> None:
        self.ablations: list[str] = []

    def run(self, ablation_name: str, cases: Sequence[GoldenCase], runner) -> GoldenRunReport:  # type: ignore[no-untyped-def]
        self.ablations.append(ablation_name)
        return GoldenRunReport(ablation_name=ablation_name, outcomes=())


class _RaisingEvaluation(_Evaluation):
    def run(self, ablation_name, cases, runner):  # type: ignore[no-untyped-def]
        raise RuntimeError("the run exploded")


def _service(evaluation, runners, recompiler) -> AblationService:
    return AblationService(evaluation=evaluation, runners=runners, recompiler=recompiler)


def test_each_named_ablation_produces_one_report() -> None:
    evaluation = _Evaluation()

    reports = _service(evaluation, _Runners(), _Recompiler()).run(
        ("full", "no_domains"), (CASE,)
    )

    assert [r.ablation_name for r in reports] == ["full", "no_domains"]


def test_each_ablation_gets_its_own_runner() -> None:
    runners = _Runners()

    _service(_Evaluation(), runners, _Recompiler()).run(("full", "no_domains"), (CASE,))

    assert runners.requested == ["full", "no_domains"]


def test_an_unknown_ablation_raises_and_names_the_registered_ones() -> None:
    with pytest.raises(UnknownAblationError) as exc:
        _service(_Evaluation(), _Runners(), _Recompiler()).run(("invented",), (CASE,))

    assert "no_domains" in str(exc.value)


def test_a_non_recompiling_ablation_never_touches_the_search_documents() -> None:
    recompiler = _Recompiler()

    _service(_Evaluation(), _Runners(), recompiler).run(("full", "no_domains"), (CASE,))

    assert recompiler.calls == []


def test_a_recompiling_ablation_compiles_before_and_restores_after() -> None:
    recompiler = _Recompiler()

    _service(_Evaluation(), _Runners(), recompiler).run(("no_descriptions",), (CASE,))

    assert recompiler.calls == ["no_descriptions", "full"]


def test_the_store_is_restored_even_when_the_run_raises() -> None:
    recompiler = _Recompiler()

    with pytest.raises(RuntimeError):
        _service(_RaisingEvaluation(), _Runners(), recompiler).run(
            ("no_descriptions",), (CASE,)
        )

    assert recompiler.calls == ["no_descriptions", "full"]


def test_running_no_names_runs_every_registered_ablation() -> None:
    evaluation = _Evaluation()

    _service(evaluation, _Runners(), _Recompiler()).run((), (CASE,))

    assert "full" in evaluation.ablations
    assert len(evaluation.ablations) == 6


def test_an_empty_case_set_still_produces_one_report_per_ablation() -> None:
    reports = _service(_Evaluation(), _Runners(), _Recompiler()).run(("full",), ())

    assert len(reports) == 1
    assert reports[0].outcomes == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ablation_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

Create `genql/services/eval/ablation_service.py`:

```python
"""Runs the golden set once per ablation.

The parent spec's §15 calls this "the only mechanism that demonstrates whether
the semantic store earns its latency, which is the system's entire thesis", so
the service's job is to make the comparison fair rather than to make it come
out a particular way: each ablation gets its own pipeline built from its own
overrides, every ablation sees the same case list in the same order, and
nothing here knows which layers are supposed to matter.

The recompile is wrapped in try/finally rather than run at the end, because
`no_descriptions` mutates state every later turn reads — including real user
turns, if the process is also serving. Restoring on the way out of an
exception is the difference between a failed run and a silently degraded
installation.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import UnknownAblationError
from genql.domain.ports.search_document_recompiler import SearchDocumentRecompiler
from genql.domain.ports.turn_runner_factory import TurnRunnerFactory
from genql.registries.errors import UnknownRegistryKeyError
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.registry import ABLATIONS

_BASELINE = "full"


class AblationService:
    def __init__(
        self,
        evaluation: GoldenEvaluationService,
        runners: TurnRunnerFactory,
        recompiler: SearchDocumentRecompiler,
    ) -> None:
        self._evaluation = evaluation
        self._runners = runners
        self._recompiler = recompiler

    def run(
        self, ablation_names: Sequence[str], cases: Sequence[GoldenCase]
    ) -> tuple[GoldenRunReport, ...]:
        names = list(ablation_names) or ABLATIONS.keys()
        ablations = [self._resolve(name) for name in names]
        return tuple(self._run_one(ablation, cases) for ablation in ablations)

    @staticmethod
    def _resolve(name: str) -> Ablation:
        try:
            return ABLATIONS.create(name)
        except UnknownRegistryKeyError as exc:
            raise UnknownAblationError(name, ABLATIONS.keys()) from exc

    def _run_one(
        self, ablation: Ablation, cases: Sequence[GoldenCase]
    ) -> GoldenRunReport:
        if not ablation.requires_recompile:
            return self._evaluate(ablation, cases)

        datasource = cases[0].datasource_name if cases else "local"
        self._recompiler.recompile(ablation, datasource)
        try:
            return self._evaluate(ablation, cases)
        finally:
            self._recompiler.recompile(ABLATIONS.create(_BASELINE), datasource)

    def _evaluate(
        self, ablation: Ablation, cases: Sequence[GoldenCase]
    ) -> GoldenRunReport:
        return self._evaluation.run(
            ablation.name, cases, self._runners.for_ablation(ablation)
        )
```

Check `genql/registries/errors.py` for the real exception name raised by `Registry.get` on an unknown key, and catch that.

- [ ] **Step 4: Wire it into `EvalContainer`**

```python
    ablation_service = providers.Singleton(
        AblationService,
        evaluation=golden_evaluation_service,
        runners=turn_runner_factory,
        recompiler=search_document_recompiler,
    )
```

Also add `import genql.services.eval.ablations  # noqa: F401` to the container module, so the registry is populated before anything resolves the service — the same registration-side-effect import `composition_root.py` already does for discovery steps.

- [ ] **Step 5: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add genql/services/eval/ablation_service.py genql/composition/eval_container.py tests/unit/test_ablation_service.py
git commit -m "feat(eval): run the golden set once per ablation and restore the store afterwards"
```

---

### Task 19: The `genql eval` command group

**Files:**
- Create: `genql/cli/commands/eval.py`, `tests/integration/test_cli_eval.py`
- Modify: `genql/cli/main.py`
- Test: `tests/integration/test_cli_eval.py`

**Interfaces:**
- Consumes: Tasks 14, 15, 18 — `golden_set_reader`, `golden_evaluation_service`, `turn_runner`, `ablation_service`, `report_writer`
- Produces: `genql eval golden --datasource X [--report P] [--failure-class C]`, `genql eval ablate --datasource X [--ablation N ...] [--report P]`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/integration/test_cli_eval.py`:

```python
"""The two commands' output contracts. Counts beside every accuracy is not
cosmetic: a report showing 0.83 without 5/6 invites a reader to treat six
cases as a measurement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = [pytest.mark.integration, pytest.mark.real_provider]

runner = CliRunner()


def test_golden_prints_accuracy_with_its_counts() -> None:
    result = runner.invoke(app, ["eval", "golden", "--datasource", "local"])

    assert result.exit_code == 0
    assert "/" in result.stdout  # e.g. "accuracy: 0.83 (5/6)"
    assert "accuracy" in result.stdout.lower()


def test_golden_writes_a_json_report_when_asked(tmp_path: Path) -> None:
    report = tmp_path / "report.json"

    result = runner.invoke(
        app, ["eval", "golden", "--datasource", "local", "--report", str(report)]
    )

    assert result.exit_code == 0
    payload = json.loads(report.read_text())
    assert payload[0]["ablation"] == "full"
    assert "outcomes" in payload[0]


def test_ablate_names_the_layer_it_cannot_measure() -> None:
    result = runner.invoke(
        app, ["eval", "ablate", "--datasource", "local", "--ablation", "full"]
    )

    assert result.exit_code == 0
    assert "query log" in result.stdout


def test_ablate_reports_each_ablations_delta_from_the_baseline() -> None:
    result = runner.invoke(
        app,
        ["eval", "ablate", "--datasource", "local", "--ablation", "full",
         "--ablation", "no_domains"],
    )

    assert result.exit_code == 0
    assert "delta" in result.stdout.lower()


def test_an_unknown_ablation_exits_nonzero_and_lists_the_real_ones() -> None:
    result = runner.invoke(
        app, ["eval", "ablate", "--datasource", "local", "--ablation", "invented"]
    )

    assert result.exit_code == 1
    assert "no_domains" in result.stdout
```

- [ ] **Step 2: Create the command group**

Create `genql/cli/commands/eval.py`:

```python
"""`genql eval` — the two mechanisms the parent spec's §15 substitutes for
public benchmarks.

Every accuracy is printed with its counts. Six cases is not a measurement, and
a bare `0.83` reads like one; `0.83 (5/6)` does not. The ablate command also
names the layer it cannot measure, so an absent row is never mistaken for a
measured zero.
"""

from __future__ import annotations

import psycopg
import typer

from genql.composition_root import Container
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import GenqlError
from genql.domain.value_objects.failure_class import FAILURE_CLASSES

app = typer.Typer(help="Run the golden set and the ablation harness")

_UNMEASURED = (
    "not measured: query log — offline query-log mining is not implemented in this "
    "build, so there is no layer to switch off"
)


def _render_cases(report: GoldenRunReport) -> None:
    for outcome in report.outcomes:
        marker = "ok  " if outcome.passed else "FAIL"
        typer.echo(f"  {marker} {outcome.case_id} ({outcome.elapsed_ms:.0f} ms)")
        if not outcome.passed and outcome.failure_reason:
            typer.echo(f"       {outcome.failure_reason}")


def _render_accuracy(report: GoldenRunReport) -> None:
    total = len(report.outcomes)
    typer.echo(f"accuracy: {report.accuracy:.2f} ({report.passed_count}/{total})")
    for failure_class in FAILURE_CLASSES:
        passed, count = report.counts_for(failure_class)
        if count:
            typer.echo(f"  {failure_class}: {passed / count:.2f} ({passed}/{count})")


@app.command("golden")
def golden(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    report_path: str | None = typer.Option(None, "--report", help="Write a JSON report here"),
    failure_class: str | None = typer.Option(
        None, "--failure-class", help="Run only cases of this failure class"
    ),
) -> None:
    """Run every curated case and compare execution results."""
    try:
        # record_execution_actuals is on for evaluation runs so that
        # `genql optimizer recommend-indexes` has evidence on a fresh install.
        container = Container.with_overrides(record_execution_actuals=True)
        cases = container.golden_set_reader().read_cases(datasource)
        if failure_class is not None:
            cases = tuple(c for c in cases if c.failure_class == failure_class)
        result = container.golden_evaluation_service().run(
            "full", cases, container.turn_runner()
        )
        if report_path is not None:
            container.report_writer().write(report_path, (result,))
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _render_cases(result)
    typer.echo("")
    _render_accuracy(result)


@app.command("ablate")
def ablate(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    ablation: list[str] = typer.Option(
        [], "--ablation", help="Ablation to run; repeatable. Default: all registered."
    ),
    report_path: str | None = typer.Option(None, "--report", help="Write a JSON report here"),
) -> None:
    """Run the golden set once per ablation and print each delta from the baseline."""
    try:
        container = Container()
        cases = container.golden_set_reader().read_cases(datasource)
        reports = container.ablation_service().run(tuple(ablation), cases)
        if report_path is not None:
            container.report_writer().write(report_path, reports)
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    baseline = next((r.accuracy for r in reports if r.ablation_name == "full"), None)
    typer.echo("ablation | accuracy | delta")
    for report in reports:
        total = len(report.outcomes)
        delta = "—" if baseline is None else f"{report.accuracy - baseline:+.2f}"
        typer.echo(
            f"{report.ablation_name} | {report.accuracy:.2f} "
            f"({report.passed_count}/{total}) | {delta}"
        )
    typer.echo("")
    typer.echo(_UNMEASURED)
    typer.echo(
        "an ablation measures a layer's absence, not its quality: it says what happens "
        "with none of that layer, not what better input would buy"
    )
```

- [ ] **Step 3: Register the sub-app**

In `genql/cli/main.py`, add `app.add_typer(eval_commands.app, name="eval")`. Import it as `from genql.cli.commands import eval as eval_commands` — `eval` shadows a builtin, so the alias is not optional.

- [ ] **Step 4: Run everything and commit**

Run: `uv run pytest tests/unit -q && uv run pytest tests/integration/test_cli_eval.py -q; uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: unit PASS; CLI test PASS or clean skip

```bash
git add genql/cli tests/integration/test_cli_eval.py
git commit -m "feat(cli): add genql eval golden and genql eval ablate"
```

---
### Task 20: The HTTP surface

**Files:**
- Create: `genql/api/dtos/__init__.py`, `genql/api/dtos/query_dtos.py`, `genql/api/dtos/feedback_dtos.py`, `genql/api/dtos/datasource_dtos.py`, `genql/api/deps.py`, `genql/api/controllers/__init__.py`, `genql/api/controllers/query_controller.py`, `genql/api/controllers/feedback_controller.py`, `genql/api/controllers/datasource_controller.py`, `genql/api/app.py`, `genql/cli/commands/serve.py`
- Modify: `genql/cli/main.py`
- Test: `tests/unit/test_api_dtos.py`, `tests/integration/test_api_routes.py`

**Interfaces:**
- Consumes: existing `start_turn`, `resume_turn`, `TurnResponse`, `DatasourceRepository`; Task 12's `FeedbackService`
- Produces: `create_app(container) -> FastAPI`; `get_container(request) -> Container`; `TurnResponseDto.from_domain(response)`; `genql serve`

- [ ] **Step 1: Write the failing DTO test**

Create `tests/unit/test_api_dtos.py`:

```python
"""The DTO is the wire contract Phase 9's frontend will be written against, so
the mapping from the domain entity is pinned here rather than left implicit.

`rows` becomes a list of lists because JSON has no tuples, and a client that
round-trips the payload must get the same shape back."""

from __future__ import annotations

from genql.api.dtos.query_dtos import TurnResponseDto
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_response import TurnResponse


def test_a_finished_turn_maps_its_rows_and_columns() -> None:
    response = TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT 1",
        result=ExecutionResult(
            columns=("n",), rows=((1,), (2,)), row_count=2, truncated=False
        ),
    )

    dto = TurnResponseDto.from_domain(response)

    assert dto.columns == ["n"]
    assert dto.rows == [[1], [2]]
    assert dto.row_count == 2
    assert dto.truncated is False


def test_a_paused_turn_carries_its_question_and_no_rows() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(thread_id="t-1", clarifying_question="which quarter?")
    )

    assert dto.clarifying_question == "which quarter?"
    assert dto.rows == []
    assert dto.row_count == 0


def test_an_over_budget_turn_carries_its_suggestion_and_the_declined_sql() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(
            thread_id="t-1", validated_sql="SELECT 1", narrowing_suggestion="too expensive"
        )
    )

    assert dto.narrowing_suggestion == "too expensive"
    assert dto.validated_sql == "SELECT 1"
    assert dto.rows == []


def test_applied_defaults_become_a_list_of_pairs() -> None:
    dto = TurnResponseDto.from_domain(
        TurnResponse(thread_id="t-1", applied_defaults=(("time_range", "fiscal_year"),))
    )

    assert dto.applied_defaults == [["time_range", "fiscal_year"]]
```

- [ ] **Step 2: Create the DTOs**

Create `genql/api/dtos/query_dtos.py`:

```python
"""The wire contract. Phase 9's frontend is written against this, so it is a
declared shape rather than whatever `TurnResponse.model_dump()` happens to
produce — and so that adding a field to the entity does not silently change
the API.

Tuples become lists because JSON has none, and a client round-tripping the
payload must get the same shape back.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from genql.domain.entities.turn_response import TurnResponse


class StartTurnRequest(BaseModel):
    question: str
    datasource: str
    domain_id: int | None = None
    thread_id: str | None = None


class ResumeTurnRequest(BaseModel):
    answer: str


class TurnResponseDto(BaseModel):
    thread_id: str
    clarifying_question: str | None = None
    intent: str | None = None
    validated_sql: str | None = None
    narrowing_suggestion: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    applied_defaults: list[list[str]] = []
    rewrite_rules_applied: list[str] = []
    plan_text: str | None = None
    referenced_objects: list[str] = []
    selection_method: str | None = None
    selection_rationale: str | None = None
    candidate_count: int = 0
    probe_count: int = 0

    @classmethod
    def from_domain(cls, response: TurnResponse) -> "TurnResponseDto":
        result = response.result
        return cls(
            thread_id=response.thread_id,
            clarifying_question=response.clarifying_question,
            intent=response.intent,
            validated_sql=response.validated_sql,
            narrowing_suggestion=response.narrowing_suggestion,
            columns=list(result.columns) if result else [],
            rows=[list(row) for row in result.rows] if result else [],
            row_count=result.row_count if result else 0,
            truncated=result.truncated if result else False,
            applied_defaults=[list(pair) for pair in response.applied_defaults],
            rewrite_rules_applied=list(response.rewrite_rules_applied),
            plan_text=response.plan_text,
            referenced_objects=list(response.referenced_objects),
            selection_method=response.selection_method,
            selection_rationale=response.selection_rationale,
            candidate_count=response.candidate_count,
            probe_count=response.probe_count,
        )
```

The six provenance fields are read here but only added to `TurnResponse` in Task 22. Add them to the entity **now**, with defaults, so this task's tests pass; Task 22 fills them in from state.

Create `genql/api/dtos/feedback_dtos.py` (`FeedbackRequest` with `rating: Literal["good","bad"]`, `corrected_sql: str | None`, `comment: str | None`) and `genql/api/dtos/datasource_dtos.py` (`DatasourceDto` with the fields `Datasource` exposes minus any secret — read the entity first and **omit every credential field**).

- [ ] **Step 3: Create `deps.py` and the app factory**

Create `genql/api/deps.py`:

```python
"""One container per process, reached through the app rather than a module
global, so a test can build an app around a container with a fake graph."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def get_container(request: Request) -> Any:
    return request.app.state.container
```

Create `genql/api/app.py`:

```python
"""The FastAPI application.

Endpoints are synchronous `def`, so FastAPI runs each on a worker thread. The
whole pipeline below is synchronous — SQLAlchemy, psycopg, httpx, neo4j — and
making the transport async would not make any of it concurrent; it would only
move the blocking off the loop by rewriting every layer.

All error translation happens here, in one handler, so no controller contains a
`try`. UnknownDatasourceError and UnknownThreadError are 404 because the client
named something that does not exist; every other GenqlError is 400 because the
request could not be served as asked; anything else is a bug and is 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from genql.api.controllers import (
    datasource_controller,
    feedback_controller,
    query_controller,
    stream_controller,
)
from genql.domain.errors import GenqlError, UnknownDatasourceError, UnknownThreadError

_NOT_FOUND = (UnknownDatasourceError, UnknownThreadError)


def create_app(container: Any) -> FastAPI:
    app = FastAPI(title="GenQL", version="0.1.0")
    app.state.container = container

    @app.exception_handler(GenqlError)
    def _handle_genql_error(request: Request, exc: GenqlError) -> JSONResponse:
        status = 404 if isinstance(exc, _NOT_FOUND) else 400
        return JSONResponse(
            status_code=status,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(query_controller.router, prefix="/v1")
    app.include_router(stream_controller.router, prefix="/v1")
    app.include_router(feedback_controller.router, prefix="/v1")
    app.include_router(datasource_controller.router, prefix="/v1")
    return app
```

`stream_controller` is created in Task 21. Until then, comment out its import and router registration and leave a `# Task 21` marker — or implement Tasks 20 and 21 in one sitting, since they are batched together.

- [ ] **Step 4: Create the three controllers**

Create `genql/api/controllers/query_controller.py`:

```python
"""Two routes, no logic. DTO in, service call, DTO out — every failure is
translated by the app's single exception handler, so there is no `try` here."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container
from genql.api.dtos.query_dtos import ResumeTurnRequest, StartTurnRequest, TurnResponseDto
from genql.api.query_turn import resume_turn, start_turn

router = APIRouter(tags=["queries"])


@router.post("/queries", response_model=TurnResponseDto)
def start(
    request: StartTurnRequest,
    container: Annotated[Any, Depends(get_container)],
) -> TurnResponseDto:
    response = start_turn(
        container.query_graph(),
        container.thread_lock_factory(),
        request.question,
        request.datasource,
        request.domain_id,
        request.thread_id,
    )
    return TurnResponseDto.from_domain(response)


@router.post("/queries/{thread_id}/resume", response_model=TurnResponseDto)
def resume(
    thread_id: str,
    request: ResumeTurnRequest,
    container: Annotated[Any, Depends(get_container)],
) -> TurnResponseDto:
    response = resume_turn(
        container.query_graph(), container.thread_lock_factory(), request.answer, thread_id
    )
    return TurnResponseDto.from_domain(response)
```

Create `genql/api/controllers/feedback_controller.py` — one `POST /queries/{thread_id}/feedback` returning `204`, building a `Feedback` entity from the DTO and the path parameter and calling `container.feedback_service().record(...)`.

Create `genql/api/controllers/datasource_controller.py` — one `GET /datasources` returning `[DatasourceDto]` from `container.datasource_repository().list()`. Check the repository's real listing method name first.

- [ ] **Step 5: Write the route tests**

Create `tests/integration/test_api_routes.py`:

```python
"""The routes against a container whose graph is a fake, so the assertions are
about transport — status codes, shapes, error mapping — and not about the
pipeline, which every other test already covers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from genql.api.app import create_app
from genql.domain.errors import UnknownDatasourceError, UnknownThreadError


class _FakeContainer:
    """Enough of a container for the routes. Built by hand rather than by
    overriding a real one: the real container opens a checkpointer pool on
    first resolution, and these tests must not need a database."""

    def __init__(self, graph) -> None:  # type: ignore[no-untyped-def]
        self._graph = graph

    def query_graph(self):  # type: ignore[no-untyped-def]
        return self._graph

    def thread_lock_factory(self):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager

        class _Locks:
            @contextmanager
            def for_thread(self, thread_id: str):  # type: ignore[no-untyped-def]
                yield

        return _Locks()


class _Graph:
    def __init__(self, raw) -> None:  # type: ignore[no-untyped-def]
        self._raw = raw

    def invoke(self, state, config):  # type: ignore[no-untyped-def]
        if isinstance(self._raw, Exception):
            raise self._raw
        return {**state, **self._raw}


def _client(raw) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(_FakeContainer(_Graph(raw))), raise_server_exceptions=False)


FINISHED = {
    "validated_sql": "SELECT 1",
    "result": None,
    "intent": "analytical_sql",
    "optimization": None,
}


def test_healthz_is_ok() -> None:
    assert _client(FINISHED).get("/healthz").json() == {"status": "ok"}


def test_starting_a_turn_returns_the_dto() -> None:
    response = _client(FINISHED).post(
        "/v1/queries", json={"question": "how many customers", "datasource": "local"}
    )

    assert response.status_code == 200
    assert response.json()["validated_sql"] == "SELECT 1"
    assert response.json()["thread_id"]


def test_a_request_missing_a_required_field_is_422() -> None:
    assert _client(FINISHED).post("/v1/queries", json={"question": "q"}).status_code == 422


def test_an_unknown_datasource_is_404() -> None:
    client = _client(UnknownDatasourceError("nope", ["local"]))

    response = client.post("/v1/queries", json={"question": "q", "datasource": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "UnknownDatasourceError"


def test_an_unknown_thread_is_404() -> None:
    client = _client(UnknownThreadError("t-missing"))

    response = client.post("/v1/queries/t-missing/resume", json={"answer": "q3"})

    assert response.status_code == 404


def test_any_other_typed_failure_is_400_with_its_type_name() -> None:
    from genql.domain.errors import SchemaLinkingError

    client = _client(SchemaLinkingError("no catalogued object matched"))

    response = client.post("/v1/queries", json={"question": "q", "datasource": "local"})

    assert response.status_code == 400
    assert response.json()["error"] == "SchemaLinkingError"
    assert "no catalogued object" in response.json()["detail"]
```

Match `UnknownDatasourceError` and `UnknownThreadError`'s real constructor signatures — read `genql/domain/errors.py`. `resume_turn` calls `graph.get_state(...)` before invoking, so `_Graph` needs a `get_state` returning an object with an `interrupts` attribute; add it.

- [ ] **Step 6: Add `genql serve`**

Create `genql/cli/commands/serve.py`:

```python
"""`genql serve` — uvicorn over the app factory, one process.

Defaults bind 127.0.0.1: this is a development server for a single-user system,
and a default of 0.0.0.0 would expose an unauthenticated query API to the
network the first time someone ran it.
"""

from __future__ import annotations

import typer
import uvicorn

from genql.api.app import create_app
from genql.composition_root import Container

app_command = typer.Typer()


def serve(
    host: str | None = typer.Option(None, "--host", help="Bind address"),
    port: int | None = typer.Option(None, "--port", help="Bind port"),
) -> None:
    """Serve the GenQL HTTP API."""
    container = Container()
    settings = container.settings()
    uvicorn.run(
        create_app(container),
        host=host or settings.api_host,
        port=port or settings.api_port,
    )
```

Register it in `genql/cli/main.py` as a top-level command: `app.command("serve")(serve_commands.serve)`, matching how `query` is registered.

- [ ] **Step 7: Run everything and commit**

Run: `uv run pytest tests/unit tests/integration/test_api_routes.py -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS, and `lint-imports` still 3/3 — `fastapi` is imported only from `genql/api/` and `genql/cli/`

```bash
git add genql/api genql/cli tests
git commit -m "feat(api): serve turns, feedback, and datasources over HTTP"
```

---

### Task 21: Per-stage SSE streaming

**Files:**
- Create: `genql/api/sse/__init__.py`, `genql/api/sse/stage_events.py`, `genql/api/sse/event_stream.py`, `genql/api/controllers/stream_controller.py`
- Modify: `genql/api/query_graph.py`, `genql/api/app.py`
- Test: `tests/unit/test_stage_events.py`, `tests/integration/test_api_stream.py`

**Interfaces:**
- Consumes: Task 11's `StageEvent`; existing `initial_state`, `_to_response`
- Produces: `stream_query(graph, question, datasource_name, thread_id, domain_id)`, `stream_resume(graph, answer, thread_id)`; `to_stage_event(node, delta) -> StageEvent`; `stage_event_stream(...) -> Iterator[dict[str, str]]`; `GET /v1/queries/stream`

- [ ] **Step 1: Write the failing stage-event test**

Create `tests/unit/test_stage_events.py`:

```python
"""A stage delta becomes one short line, never the delta itself: a delta can
carry every schema link or every candidate statement, and putting that on the
wire would make the event stream the widest interface in the system."""

from __future__ import annotations

from genql.api.sse.stage_events import to_stage_event
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink


def test_a_completed_node_becomes_a_completed_event_named_for_the_node() -> None:
    event = to_stage_event("planning", {"plan": QueryPlan(
        question="q", plan_text="sum sales by month", referenced_objects=("local.a.b",)
    )})

    assert event.stage == "planning"
    assert event.status == "completed"


def test_a_schema_linking_delta_is_summarized_by_count_not_by_content() -> None:
    links = tuple(
        SchemaLink(object_qualified_name=f"local.s.o{i}") for i in range(12)
    )

    event = to_stage_event("schema_linking", {"links": links})

    assert event.detail is not None
    assert "12" in event.detail
    assert "o11" not in event.detail


def test_an_interrupt_becomes_a_paused_event() -> None:
    class _Interrupt:
        value = "which quarter did you mean?"

    event = to_stage_event("__interrupt__", (_Interrupt(),))

    assert event.status == "paused"
    assert event.detail == "which quarter did you mean?"


def test_a_node_with_no_summariser_still_produces_an_event() -> None:
    """A stage added by a later phase must stream without editing this file."""
    event = to_stage_event("a_future_stage", {"whatever": 1})

    assert event.stage == "a_future_stage"
    assert event.status == "completed"


def test_a_detail_line_is_never_longer_than_the_cap() -> None:
    event = to_stage_event("planning", {"plan": QueryPlan(
        question="q", plan_text="x" * 5_000, referenced_objects=()
    )})

    assert event.detail is not None
    assert len(event.detail) <= 200
```

- [ ] **Step 2: Add the two streaming functions to `query_graph.py`**

```python
def stream_query(
    graph: Any,
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one mapping per completed node.

    `stream_mode="updates"` gives `{node_name: delta}` after each node, which
    is exactly one SSE event per pipeline stage. Kept here beside run_query for
    the same reason run_query is here: every fact about langgraph's invocation
    convention lives in one file, so a release that changes it breaks once.
    """
    yield from graph.stream(
        initial_state(question, datasource_name, thread_id, domain_id),
        _config(thread_id),
        stream_mode="updates",
    )


def stream_resume(graph: Any, answer: str, thread_id: str) -> Iterator[dict[str, Any]]:
    config = _config(thread_id)
    if not graph.get_state(config).interrupts:
        raise UnknownThreadError(thread_id)
    yield from graph.stream(Command(resume=answer), config, stream_mode="updates")
```

Import `Iterator` from `collections.abc`.

- [ ] **Step 3: Create the stage-event renderer**

Create `genql/api/sse/stage_events.py`:

```python
"""One completed node becomes one short line.

The summarisers are a lookup keyed by node name, and a node with no entry
still produces an event — so a stage added by a later phase streams without
anyone editing this file, which is the same open/closed property the
registries give the rest of the system.

Every detail is capped. A plan can be a thousand tokens and a candidate set can
be several statements; the stream exists to say *what is happening*, and the
full state is available from the terminal event.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from genql.domain.entities.stage_event import StageEvent

_MAX_DETAIL = 200
_INTERRUPT = "__interrupt__"


def _links(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('links') or ())} objects linked"


def _plan(delta: dict[str, Any]) -> str:
    plan = delta.get("plan")
    return plan.plan_text if plan is not None else "planned"


def _candidates(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('candidates') or ())} candidates generated"


def _validated(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('validated_sqls') or ())} candidates cleared validation"


def _probes(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('probe_results') or ())} probes executed"


def _selection(delta: dict[str, Any]) -> str:
    selection = delta.get("selection")
    return f"selected by {selection.method}" if selection is not None else "selected"


def _optimization(delta: dict[str, Any]) -> str:
    optimization = delta.get("optimization")
    if optimization is None:
        return "cost gate cleared"
    rules = ", ".join(optimization.rules_applied) or "no rewrites"
    verdict = "within budget" if optimization.within_budget else "over budget"
    return f"{rules}; estimated cost {optimization.estimated_cost:.0f} ({verdict})"


def _execution(delta: dict[str, Any]) -> str:
    result = delta.get("result")
    return f"{result.row_count} rows" if result is not None else "executed"


_SUMMARISERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "schema_linking": _links,
    "planning": _plan,
    "candidate_generation": _candidates,
    "static_validation": _validated,
    "ambiguity_probing": _probes,
    "candidate_selection": _selection,
    "rewrite_and_cost_gate": _optimization,
    "guarded_execution": _execution,
}


def to_stage_event(node: str, delta: Any) -> StageEvent:
    if node == _INTERRUPT:
        question = str(delta[0].value) if delta else ""
        return StageEvent(stage="ambiguity_gate", status="paused", detail=question[:_MAX_DETAIL])

    summarise = _SUMMARISERS.get(node)
    detail = summarise(delta) if summarise and isinstance(delta, dict) else None
    return StageEvent(
        stage=node, status="completed", detail=detail[:_MAX_DETAIL] if detail else None
    )
```

- [ ] **Step 4: Create the event stream**

Create `genql/api/sse/event_stream.py`:

```python
"""The generator behind GET /v1/queries/stream.

Three guarantees a client depends on, in this order: one `stage` event per
completed pipeline node; exactly one terminal event, which is always `result`,
`clarification`, or `error`; and nothing after the terminal event. A stream
that just stops is indistinguishable from a dropped connection, which is why
even a failure is delivered as an event rather than as a closed socket.

The deltas are accumulated into a merged state as they pass, so the terminal
event can be built by the same `to_response` the blocking path uses. Without
that, the streaming and blocking endpoints could report a turn differently.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from genql.api.query_graph import stream_query, stream_resume
from genql.api.query_state import initial_state
from genql.api.query_turn import new_thread_id, to_response
from genql.api.sse.stage_events import to_stage_event
from genql.domain.errors import GenqlError
from genql.domain.ports.thread_lock import ThreadLockFactory


def _event(name: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload, default=str)}


def _terminal(thread_id: str, merged: dict[str, Any]) -> dict[str, str]:
    from genql.api.dtos.query_dtos import TurnResponseDto

    response = to_response(thread_id, merged)
    payload = TurnResponseDto.from_domain(response).model_dump()
    if response.clarifying_question is not None:
        return _event("clarification", payload)
    return _event("result", payload)


def stage_event_stream(  # noqa: PLR0913, PLR0917 - mirrors the graph's start parameters
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
    answer: str | None = None,
) -> Iterator[dict[str, str]]:
    resolved = thread_id or new_thread_id()
    merged: dict[str, Any] = dict(
        initial_state(question, datasource_name, resolved, domain_id)
    )
    try:
        with locks.for_thread(resolved):
            chunks = (
                stream_resume(graph, answer, resolved)
                if answer is not None
                else stream_query(graph, question, datasource_name, resolved, domain_id)
            )
            for chunk in chunks:
                for node, delta in chunk.items():
                    if isinstance(delta, dict):
                        merged.update(delta)
                    else:
                        merged["__interrupt__"] = delta
                    yield _event("stage", to_stage_event(node, delta).model_dump())
    except GenqlError as exc:
        yield _event("error", {"error": type(exc).__name__, "detail": str(exc)})
        return

    yield _terminal(resolved, merged)
```

`_to_response` is currently private in `query_turn.py`. Rename it to `to_response` (dropping the underscore) and update its one existing caller, rather than importing a private name across modules.

- [ ] **Step 5: Create the stream controller**

Create `genql/api/controllers/stream_controller.py`:

```python
"""GET, not POST, because the browser EventSource API cannot issue a POST and
the first client for this route is Phase 9's frontend.

`iterate_in_threadpool` is what bridges the synchronous generator into the
event loop. It costs one worker thread for the duration of a turn — documented
in the spec's risks, and acceptable for the single-user target.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from genql.api.deps import get_container
from genql.api.sse.event_stream import stage_event_stream

router = APIRouter(tags=["queries"])


@router.get("/queries/stream")
def stream(  # noqa: PLR0913, PLR0917 - one query parameter per turn input
    question: str,
    datasource: str,
    container: Annotated[Any, Depends(get_container)],
    domain_id: int | None = None,
    thread_id: str | None = None,
    answer: str | None = None,
) -> EventSourceResponse:
    generator = stage_event_stream(
        container.query_graph(),
        container.thread_lock_factory(),
        question,
        datasource,
        domain_id,
        thread_id,
        answer,
    )
    return EventSourceResponse(iterate_in_threadpool(generator))
```

Uncomment `stream_controller`'s import and registration in `genql/api/app.py`.

- [ ] **Step 6: Write the stream test**

Create `tests/integration/test_api_stream.py`, using `TestClient` against the same `_FakeContainer` shape as Task 20 (extract it into `tests/integration/conftest.py` rather than duplicating it), with a fake graph whose `stream` yields a fixed sequence of `{node: delta}` chunks. Assert, by parsing the raw `text/event-stream` body:

- one `stage` event per chunk, in the order the graph yielded them;
- exactly one terminal event, and it is last;
- an interrupt chunk produces a `stage` event with `"status": "paused"` followed by a terminal `clarification` event;
- a graph that raises `SchemaLinkingError` mid-stream produces the `stage` events that preceded it, then a terminal `error` event carrying `SchemaLinkingError` — and no `result` event.

- [ ] **Step 7: Run everything and commit**

Run: `uv run pytest tests/unit tests/integration/test_api_stream.py -q && uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add genql/api tests
git commit -m "feat(api): stream one SSE event per pipeline stage"
```

---

### Task 22: Provenance, and proving Part B end to end

**Files:**
- Modify: `genql/domain/entities/turn_response.py`, `genql/api/query_turn.py`, `genql/cli/commands/query.py`
- Create: `tests/golden/__init__.py`, `tests/golden/test_golden_runner.py`, `tests/integration/test_ablation_harness.py`
- Test: all of the above, plus the existing turn tests

**Interfaces:**
- Consumes: everything from Tasks 11–21
- Produces: a `TurnResponse` carrying the provenance §9's stage 14 names; a golden run and an ablation run that both execute against real data

- [ ] **Step 1: Fill in the provenance fields**

The six fields were added to `TurnResponse` with defaults in Task 20. Now populate them in `to_response` in `genql/api/query_turn.py`:

```python
    plan = state.get("plan")
    selection = state.get("selection")
    return TurnResponse(
        ...,
        plan_text=plan.plan_text if plan is not None else None,
        referenced_objects=plan.referenced_objects if plan is not None else (),
        selection_method=selection.method if selection is not None else None,
        selection_rationale=selection.rationale if selection is not None else None,
        candidate_count=len(state.get("candidates") or ()),
        probe_count=len(state.get("probe_results") or ()),
    )
```

Add a `--verbose` flag to `genql query` that prints the plan, the referenced objects, the candidate and probe counts, and the selection rationale beneath the SQL. Without a flag the CLI's output is unchanged — provenance is for someone auditing an answer, and printing it on every turn would bury the answer.

Extend the existing turn tests to assert each field is populated on a finished contested turn and is empty on a short-circuited one.

- [ ] **Step 2: Write the golden-runner test**

Create `tests/golden/__init__.py` and `tests/golden/test_golden_runner.py`:

```python
"""The runner against real data, over the fixtures Phase 7 already validated.

This is the first test in the project whose *result* is a finding rather than
a pass/fail contract, so it asserts mechanics only: every case produces an
outcome, and every outcome names a reason when it failed. It deliberately does
not assert a minimum accuracy — a threshold here would either be so low it
proved nothing or would turn a real regression in the model provider into a
red suite with no code change.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.real_provider]


def test_every_golden_case_produces_an_outcome(golden_runner, golden_cases) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    assert len(report.outcomes) == len(golden_cases)
    assert {o.case_id for o in report.outcomes} == {c.case_id for c in golden_cases}


def test_every_failed_case_names_why(golden_runner, golden_cases) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    for outcome in report.outcomes:
        if not outcome.passed:
            assert outcome.failure_reason


def test_the_report_prints_counts_alongside_accuracy(golden_runner, golden_cases) -> None:
    report = golden_runner.run("full", golden_cases, golden_turn_runner())

    assert 0.0 <= report.accuracy <= 1.0
    assert report.passed_count <= len(report.outcomes)
```

Add `golden_runner`, `golden_cases`, and `golden_turn_runner` fixtures to a new `tests/golden/conftest.py` resolving them from a real `Container`. Configure `pytest` to collect `tests/golden` — `testpaths = ["tests"]` already covers it.

**Record the accuracy this run produces in the commit message.** It is the project's first end-to-end measurement, and it is the number Phase 9 and every later fixture addition will be compared against.

- [ ] **Step 3: Write the ablation harness test**

Create `tests/integration/test_ablation_harness.py`:

```python
"""Two ablations over the same cases, asserting the instrument rather than the
result.

There is deliberately no assertion that `full` outscores `no_domains`. That is
the empirical question the harness exists to answer; encoding the expected
answer as a test assertion would make the instrument agree with the hypothesis
by construction, which is the one failure mode an evaluation harness cannot
recover from.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.real_provider]


def test_two_ablations_cover_the_same_cases(ablation_service, golden_cases) -> None:
    reports = ablation_service.run(("full", "no_domains"), golden_cases)

    assert len(reports) == 2
    assert {o.case_id for o in reports[0].outcomes} == {
        o.case_id for o in reports[1].outcomes
    }


def test_each_ablation_is_scored_independently(ablation_service, golden_cases) -> None:
    reports = ablation_service.run(("full", "no_domains"), golden_cases)

    for report in reports:
        assert 0.0 <= report.accuracy <= 1.0
        assert len(report.outcomes) == len(golden_cases)


def test_a_recompiling_ablation_leaves_the_store_restored(
    ablation_service, golden_cases, search_document_content
) -> None:
    """After a no_descriptions run, the compiled documents must carry
    enrichment again — an ablated compile left behind would silently degrade
    every later turn, including a real user's."""
    ablation_service.run(("no_descriptions",), golden_cases[:1])

    assert search_document_content("local") != ""
```

Add an `ablation_service` fixture and a `search_document_content(datasource)` helper fixture reading one `genql_search_document.content` row through the semantic engine.

- [ ] **Step 4: Run the whole suite**

Run:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest tests/golden -q
uv run mypy genql && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

Expected: unit PASS; integration and golden PASS or clean skip; all static checks clean, 3/3 contracts kept.

- [ ] **Step 5: Commit**

```bash
git add genql tests
git commit -m "feat(api): surface turn provenance and prove the golden and ablation runs

Golden-set accuracy on this run: <N>/<M> (<accuracy>)."
```

**Part B review gate.** Run one review of Tasks 11–22 as a whole here.

---

## Done When

**Part A:**

- `genql query` on an affordable question executes as before, and prints the rewrites that fired.
- `genql query` on a question estimated over `cost_budget` prints the statement, prints why it was not run, and exits 0 — no rows, no traceback, no execution.
- Each of the four rewrite rules preserves the result set of all six fixtures in `golden/phase7_equivalence.yaml`, verified one rule at a time against real `local.tpcds`.
- With `record_execution_actuals=True`, a served turn writes one `genql_rewrite_outcome` row; with it false, none, and the recorder is never constructed.
- A recorder that raises never fails a turn whose query returned rows.
- `genql optimizer recommend-indexes --datasource local` prints either a ranked table or the line naming both reasons it can be empty.

**Part B:**

- `genql serve` starts, `GET /healthz` returns `{"status": "ok"}`, and `POST /v1/queries` answers a question.
- `GET /v1/queries/stream` emits one `stage` event per pipeline node and exactly one terminal event, which is always `result`, `clarification`, or `error`.
- `POST /v1/queries/{thread_id}/feedback` writes a `genql_feedback` row, and refuses a `corrected_sql` that is not a SELECT.
- `genql eval golden --datasource local` runs every fixture and prints accuracy with counts, overall and per failure class.
- `genql eval ablate --datasource local` prints one row per registered ablation with its delta from `full`, and names query-log mining as the layer this build cannot measure.
- A `no_descriptions` run leaves `genql_search_document` compiled with enrichment, including when the run raises.
- `uv run lint-imports` reports 3/3 contracts kept, with `fastapi`, `starlette`, and `sse_starlette` forbidden below `genql/api/`.
- `uv run mypy genql` is clean, `uv run ruff check .` and `uv run ruff format --check .` are clean, and the unit suite is green.

## Deliberately Not Done

- **FK-driven redundant-join elimination.** sqlglot's `eliminate_joins` proves non-filtering from the query's own structure, not from `SchemaLink.join_paths` or GenQL's foreign-key metadata, so the rule declines on a plain FK join. Hand-writing the FK version is exactly the semantics risk Deviation 1 exists to avoid; it needs the larger fixture set before it is worth attempting.
- **A fixpoint rewrite loop.** One pass, in registry order. Phase 7's spec argues the four rules converge in one pass by construction; a loop would need its own termination argument.
- **Correlating `cost_budget` against wall-clock time.** It stays a planner-unit proxy. The data to correlate it — `genql_rewrite_outcome` rows carrying estimate beside actual — is what this plan builds; the correlation itself is a later analysis, not a code change.
- **A feedback vector index.** The corrected SQL is captured so a later phase can index it, but nothing retrieves it and no embedding is computed. Building a retrieval index with no reader is speculative infrastructure.
- **The "no query log" ablation.** Query-log mining is not implemented in this codebase, so there is no layer to switch off. The harness names it as un-measured rather than reporting a zero that would read as a finding.
- **Async pipeline execution.** Every endpoint is synchronous `def` and the SSE endpoint holds one worker thread per stream. The fix, if concurrency ever matters, is confined to `query_graph.py`.
- **Authentication, authorization, rate limiting, and CORS on the HTTP surface.** `genql serve` binds `127.0.0.1` by default and is a development server. Exposing it needs all four, and none of them is in this phase's scope.
- **Thirty to fifty golden cases.** This plan commits twelve or so — six from Phase 7's equivalence fixtures plus the cases Task 14 adds. §14's target is the ongoing work the harness now enables; every accuracy is printed with its counts precisely because twelve cases is not yet a measurement.
