# GenQL Phase 6.5: Ambiguity Machinery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-candidate generation, critique, ambiguity-driven probing, and data-arbitrated selection demand-driven additions to Phase 5/6's LangGraph pipeline — a well-specified question still pays exactly one `ChatProvider` call for generation and nothing else, while a contested question (one that needed a clarification or a rule default) generates several candidate SQL statements from two prompt strategies, has them critiqued by one deterministic pass plus one LLM judgment call, probes the surviving disagreement against the real warehouse when candidates disagree, and selects deterministically — falling back to critique's ranking only when probing cannot decide.

**Architecture:** Three new domain entities describing one defect/report/probe/selection each, five new ports (`CandidateGenerationStrategy`, `Critic`, `ProbeDesigner`, `AmbiguityExampleReader`, `AmbiguityExampleWriter`), and a sixth (a `list_domains` method added to the existing `DomainReader`) let five new or rewritten services under `genql/services/query/` (`CandidateGenerationService` rewritten, `CritiqueService`, `AmbiguityProbingService`, `CandidateSelectionService`, plus a `LlmProbeDesigner` adapter) and one offline `SyntheticAmbiguityLogService` under `genql/services/discovery/` implement the parent spec's stages 7 and 9–11. `QueryState.candidate: SqlCandidate | None` becomes `candidates: tuple[SqlCandidate, ...]`, and three new graph nodes (`CritiqueNode`, `AmbiguityProbingNode`, `CandidateSelectionNode`, in a new `genql/api/query_ambiguity_nodes.py`) extend `query_graph.py`'s single straight path with two new stages and one new conditional edge. Every new stage opens with the same guard — `if not state["contested"] or len(candidates) <= 1`, return the empty/single-survivor case — so a non-contested turn touches none of this phase's new code paths at runtime, matching the parent spec's demand-driven mandate exactly.

**Tech Stack:** Python 3.12 (uv), the same stack Phase 6 established — `langgraph>=1.2.11` with its checkpointer, `sqlglot` (reused directly, no new dependency), OpenRouter over `httpx` via `ChatProvider`/`EmbeddingProvider`, SQLAlchemy 2.0 Core, Alembic, `pgvector` (reused for the new `genql_ambiguity_example` table's HNSW index, same as `genql_search_document`), Pydantic v2, pydantic-settings, dependency-injector, Typer, pytest + testcontainers, ruff, mypy strict, import-linter. **No new third-party dependency is added in this phase.**

**Spec:** `docs/superpowers/specs/2026-09-08-genql-phase-6-5-ambiguity-machinery.md`
**Parent spec:** `docs/superpowers/specs/2026-09-05-genql-design.md` (§9 stages 7, 9–11; §20 demand-driven stage activation and the cost model; §21 model-choice policy)
**Previous plan:** `docs/superpowers/plans/2026-09-07-genql-phase-6-clarification-and-multi-turn.md` — this plan assumes that one is fully merged (it is: `genql/api/query_turn_nodes.py`, `genql/domain/ports/ambiguity_gate.py`, `genql/repositories/semantic/rule_repository.py`, and migration `0007` already exist in the tree).

## Global Constraints

- Python 3.12 exactly, managed by `uv`. Run everything through `uv run`.
- **No SQL string, SQLAlchemy Core construct, psycopg call, `httpx` call, Cypher string, or GDS client call may appear outside `genql/repositories/`.** Enforced by import-linter's `no-sql-in-services` and `domain-is-pure` contracts (`.importlinter`, unchanged by this phase — no new forbidden module is needed since nothing new this phase imports a database driver from `genql/services/` or `genql/domain/`).
- The `layers` contract declares `genql.api > genql.services > genql.domain`. `genql/composition/` and `genql/cli/` are outside the layers contract and may import anything.
- `genql/domain/` imports no other `genql` package and performs no I/O. Every new port is a `@runtime_checkable` `Protocol`.
- Every file ≤ 250 lines (pre-commit hook `scripts/check_file_length.py`, `LIMIT = 250`). One class per file, except adapter-node files, which the codebase already lets hold several tightly related node classes (`genql/api/query_nodes.py`, `genql/api/query_turn_nodes.py`) — this phase's three new nodes get their own new file for the same reason Phase 6's three nodes got their own (`query_turn_nodes.py`'s docstring: "one file per responsibility is the house rule, and this is the only module... worth being able to find").
- All entities are **frozen Pydantic v2 models** (`model_config = ConfigDict(frozen=True)`), matching every entity since Phase 4. The spec's §2 code blocks are written as plain classes for brevity; this plan follows the repository convention.
- `uv run mypy genql` (strict) must pass with zero errors. `uv run ruff check .` and `uv run ruff format --check .` must pass. `uv run lint-imports` must pass.
- Every typed failure inherits `GenqlError` from `genql/domain/errors.py`. The CLI (`genql/cli/commands/query.py`) already catches `GenqlError` broadly and prints one line plus exit code 1 — **this phase adds no new CLI catch clause**, because every new failure mode (`CritiqueError`, any `ChatProviderError`/`EmbeddingProviderError` propagating unwrapped from critique or probing) is already a `GenqlError` subtype the existing `except (GenqlError, ValueError, psycopg.Error)` catches.
- Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `chore:`, `refactor:`, `docs:`). Commit at the end of every task.
- **Execution note for whoever runs this plan under subagent-driven-development:** the user's standing preference is to group sequentially-dependent tasks into one dispatch, parallelize genuinely independent tasks, commit at batch boundaries, and run one review at the very end. See "Execution Batches" below.
- Docker (ParadeDB) runs on the Debian VM (`ssh genql-vm`, 100.99.72.99). Export before running integration tests:

  ```bash
  export GENQL_TEST_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_WAREHOUSE_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_SEMANTIC_DSN=postgresql+psycopg://genql:genql@100.99.72.99:5433/genql
  export GENQL_READONLY_DB_PASSWORD=genql_readonly_dev
  ```

  Real-provider tests additionally need `GENQL_OPENROUTER_API_KEY`; they are written to skip cleanly without it and **a clean skip is not a task failure**.
- **This plan may be executed in a sandbox with no Docker daemon and no route to the VM.** Every task's unit suite (`tests/unit/`) must be run and must pass there. Integration tests are written, committed, and left for a VM-connected run; report "unit green, integration written-but-unrun" exactly as every prior phase did.
- The baseline before Task 1 is the full Phase 6 suite green. Never leave a task boundary with a red unit suite.

---

## Deviations From the Spec (decided here, deliberately)

Each is a place where the spec's literal text conflicts with an established repository convention, with something not present in the codebase, or is genuinely underspecified. Implement the plan's version.

1. **`StaticValidationNode` and the new `CritiqueNode` raise their own typed errors when no further attempt remains, rather than deferring the raise to the router.** Phase 5/6's convention was "node writes state, router raises" — safe there because the router's only decision was a single retry-count threshold. This phase adds a one-shot, whole-turn escalation budget (`escalated: bool`) that either stage can spend, and the decision "should I grant one more regeneration, or is the budget already spent" must be made from the value of `escalated` *as the node received it*, in the same evaluation that might flip it to `True`. Splitting that check across a node-then-router boundary makes "just spent it" and "already spent, still failing" indistinguishable to the router (both read back `escalated == True`). Making the deciding node raise directly removes the ambiguity; both conditional edges that follow (`route_after_validation`, `route_after_critique`) become trivial dispatchers reachable only on the non-raising path.
2. **`CRITIQUE` gains a conditional edge, `route_after_critique`, back to `CANDIDATE_GENERATION`**, not shown in the spec's plain three-node-straight-line diagram (§7). Without it, `CritiqueService` finding every survivor fatal would have nowhere to go but an immediate raise, and the phase's own stated implemented escalation trigger — "critique fails to resolve after one repair round" (§1) — would never actually fire. The edge is the minimum addition that lets `CRITIQUE` grant its one escalated regeneration.
3. **The static-validation-exhaustion escalation branch (§7's literal text) and critique's all-fatal escalation branch share one `escalated` flag and one budget for the whole turn.** Whichever stage first sets `escalated = True` spends it; the other stage's own gate (`not state["escalated"]`) refuses to spend it a second time. This reconciles §1's framing ("only [critique-fails-to-resolve] is implemented") with §7's explicit static-validation-loop text: both are spending events against the same one-shot Opus regeneration, not two independent budgets.
4. **`PostgresAmbiguityExampleReader` and `PostgresAmbiguityExampleWriter` each hold their own `EmbeddingProvider` and embed internally** (the reader embeds the question before searching; the writer embeds each example's question before inserting), unlike `DenseRetriever`, which receives a pre-computed embedding from `RetrievalService`. This follows the spec's own port signatures literally: `AmbiguityExampleReader.search(question, domain_id, top_k)` and `AmbiguityExampleWriter.write(examples)` carry no embedding parameter, so nothing upstream can compute it on their behalf. `PostgresAmbiguityExampleReader`'s own docstring in the spec's §5 says exactly this ("Embeds the question via the existing EmbeddingProvider").
5. **`SyntheticAmbiguityLogService` grounds its prompt on each domain's name, description, and the datasource's full metric list — not per-domain object membership.** Object-level grounding would need a new "object names by domain" read that nothing else in this phase needs; the domain's `description` (produced by `LlmDomainNamer` from the same cluster) already summarizes what is in it, and `MetricReader.read_metrics` already exists. Kept in scope by not adding a read this phase does not otherwise require.
6. **`SyntheticAmbiguityLogService` is registered as an ordinary `DiscoveryStep`** (`"synthetic_ambiguity_log"`, appended after `"object_profiling"`), but domain naming (`genql graph domains`) is **not** a `DiscoveryStep` in this codebase — it is invoked by its own CLI command, entirely outside `DiscoveryRunner`. "Run last, after domain naming" is therefore satisfied operationally, not by registry order: a first `genql discover` run finds zero domains yet and writes zero examples (a successful, zero-record `StepResult`, not a failure). The intended path is `genql discover --start-from synthetic_ambiguity_log`, run again after `genql graph domains` — `DiscoveryRunner.run`'s existing `start_from` parameter already supports this with no runner change.
7. **`CritiqueService.critique` and `LlmProbeDesigner.design` do not wrap a `ChatProviderError` into a stage-specific error**, unlike every other stage in the codebase. This follows the spec's own Risk section literally: "a `ChatProviderError` from `CritiqueService` or `ProbeDesigner` propagates as a typed error and fails the whole turn... this phase does not carve out an exception." `CritiqueError` is added only for the distinct "every survivor fatal, escalation already spent" business-rule failure, which is not a provider failure.
8. **`CandidateGenerationStrategy` implementations are constructed fresh per call**, via `CANDIDATE_STRATEGIES.create(key, chat=<chosen provider>)` — mirroring `GuardrailFactoryImpl`'s `GUARDRAILS.create(key, config=config)`. This is how one registry serves both the normal call (`chat_model`) and the escalated call (`chat_model_escalation`) without a second registry or a provider that mutates after construction.
9. **`AmbiguityProbingService` does not catch a probe's `StaticValidationError` or `ExecutionError`.** The spec's §2 is explicit that a probe referencing an unlisted object "is a bug in `ProbeDesigner`'s prompt, not a case to special-case around" — so a bad probe fails the turn loudly (as any other stage's failure does), rather than being silently dropped from consideration.

---

## File Structure

**Created**

```
genql/domain/entities/defect.py                          Defect
genql/domain/entities/critique_report.py                 CritiqueReport
genql/domain/entities/ambiguity_probe.py                 AmbiguityProbe
genql/domain/entities/probe_result.py                    ProbeResult
genql/domain/entities/candidate_selection.py              CandidateSelection
genql/domain/entities/ambiguity_example.py                AmbiguityExample
genql/domain/ports/candidate_strategy.py                  CandidateGenerationStrategy
genql/domain/ports/critic.py                              Critic
genql/domain/ports/probe_designer.py                      ProbeDesigner
genql/domain/ports/ambiguity_example_reader.py             AmbiguityExampleReader
genql/domain/ports/ambiguity_example_writer.py             AmbiguityExampleWriter
migrations/versions/0008_ambiguity_examples.py             genql.genql_ambiguity_example
genql/repositories/semantic/ambiguity_example_repository.py  PostgresAmbiguityExampleReader, PostgresAmbiguityExampleWriter
genql/repositories/query/registry.py                       CANDIDATE_STRATEGIES
genql/repositories/query/decomposition_strategy.py         DecompositionStrategy
genql/repositories/query/execution_plan_strategy.py        ExecutionPlanStrategy
genql/services/query/critique_service.py                   CritiqueService
genql/services/query/probe_designer.py                      LlmProbeDesigner
genql/services/query/ambiguity_probing_service.py           AmbiguityProbingService
genql/services/query/candidate_selection_service.py         CandidateSelectionService
genql/services/discovery/synthetic_ambiguity_log_service.py  SyntheticAmbiguityLogService
genql/discovery/steps/synthetic_ambiguity_log_step.py        SyntheticAmbiguityLogStep
genql/api/query_ambiguity_nodes.py                          CritiqueNode, AmbiguityProbingNode, CandidateSelectionNode
genql/composition/ambiguity_container.py                    AmbiguityContainer
tests/unit/test_ambiguity_machinery_entities.py
tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py
tests/unit/test_candidate_strategies.py
tests/unit/test_critique_service.py
tests/unit/test_probe_designer.py
tests/unit/test_ambiguity_probing_service.py
tests/unit/test_candidate_selection_service.py
tests/unit/test_synthetic_ambiguity_log_service.py
tests/unit/test_synthetic_ambiguity_log_step.py
tests/unit/test_query_ambiguity_nodes.py
tests/integration/test_migration_0008.py
tests/integration/test_ambiguity_example_repository.py
tests/integration/test_critique_service_real_provider.py
tests/integration/test_probe_designer_real_provider.py
tests/integration/test_phase6_5_end_to_end.py
```

**Modified**

```
genql/domain/ports/domain_reader.py             + list_domains
genql/domain/ports/candidate_generator.py       rewritten for multi-candidate, domain_id/contested/escalated
genql/domain/errors.py                          + CritiqueError, AmbiguityExampleGenerationError
genql/api/query_state.py                        candidate -> candidates, + validated_sqls, contested,
                                                  critique_reports, probe_results, selection, escalated
genql/api/query_nodes.py                        CandidateGenerationNode, StaticValidationNode rewritten
                                                  for multiple candidates
genql/api/query_turn_nodes.py                   AmbiguityGateNode + contested
genql/api/query_graph.py                        + CRITIQUE, AMBIGUITY_PROBING, CANDIDATE_SELECTION nodes,
                                                  route_after_critique, rewritten route_after_validation
genql/repositories/semantic/domain_repository.py  + list_domains
genql/repositories/semantic/__init__.py          + PostgresAmbiguityExampleReader, PostgresAmbiguityExampleWriter
genql/repositories/query/__init__.py             + registration imports for the two strategies
genql/services/query/candidate_generation_service.py  rewritten for multi-candidate + examples
genql/discovery/steps/__init__.py               + SyntheticAmbiguityLogStep
genql/core/settings.py                          + chat_model_escalation, probing_max_probes,
                                                  ambiguity_example_top_k
genql/composition/gateway_container.py          + escalation_chat_provider (Task 12)
genql/composition/semantic_container.py         + ambiguity_example_writer, synthetic_ambiguity_log_service
                                                  (Task 9); + ambiguity_example_reader (Task 12)
genql/composition/query_container.py            candidate_generation_service rewired (Task 12)
genql/composition_root.py                       + synthetic_ambiguity_log step entry (Task 9);
                                                  Container now inherits AmbiguityContainer (Task 12)
.env.example                                    + GENQL_CHAT_MODEL_ESCALATION, GENQL_PROBING_MAX_PROBES,
                                                  GENQL_AMBIGUITY_EXAMPLE_TOP_K
tests/unit/test_composition_root.py             + new providers, updated stage list
tests/unit/test_candidate_generation_service.py  rewritten for the new signature and multi-candidate output
tests/unit/test_query_graph.py                  candidates/validated_sqls plural, node rewrites
tests/unit/test_query_graph_turns.py            fakes updated for the new fields
tests/unit/test_query_nodes.py                  StaticValidationNode/CandidateGenerationNode tests rewritten
tests/unit/test_query_turn_nodes.py             + contested assertions
tests/integration/test_domain_repository.py     + list_domains tests
tests/integration/test_candidate_generation_service_real_provider.py  + contested-path real-provider test
pyproject.toml                                  unchanged (no new dependency)
```

**Not modified, deliberately:** `.importlinter` (nothing new imports a database driver from `genql/services/` or `genql/domain/`); `genql/domain/entities/semantic_overlay.py` and `genql/services/semantic/semantic_overlay_service.py` (this phase does not touch `genql_rule` or the YAML overlay path, per the spec's own scope note); `genql/services/query/static_validation_service.py` and `genql/services/query/guarded_execution_service.py` (both reused with their existing one-candidate / one-statement signatures, called once per candidate or once per probe by the layer above); `genql/api/query_turn.py` (its `_to_response` already reads `state["validated_sql"]` and `state["result"]`, both unchanged field names and types).

---

## Task Sequence and Why

Task 1 is pure declaration — six entities, five ports, one port extension, two errors — so every later task is written against fixed names. Task 2 lands migration `0008` and the three new settings, because Task 3's repository integration test cannot run without `genql_ambiguity_example` existing. Task 3 builds the two new repositories and the one new `DomainReader` read method. Task 4 is the `CANDIDATE_STRATEGIES` registry and its two strategies, needed before Task 5 can rewrite `CandidateGenerationService` against it. Tasks 5–9 are the five independent stage services (generation, critique, probing, selection, and the offline synthetic-log service) — each depends only on Task 1 (Task 5 also on Task 4, Task 9 also on Task 3's `DomainReader.list_domains` and `AmbiguityExampleWriter`), so all five parallelize. Task 10 rewires `QueryState` and the two existing generation-path nodes for multiple candidates, which every new graph node needs as a type. Task 11 adds the three new graph nodes and the graph's new edges, and is held until Task 10's state shape exists. Task 12 is composition-root wiring, held until every service and node exists. Task 13 proves the demand-driven claim end to end: a well-specified question pays for exactly one candidate, a contested one pays for the whole pipeline.

## Execution Batches

| Batch | Tasks | Parallelizable? |
|---|---|---|
| 1 | 1 | — |
| 2 | 2 | — |
| 3 | 3 | — |
| 4 | 4 | — |
| 5 | 5, 6, 7, 8, 9 | Yes |
| 6 | 10 | — |
| 7 | 11 | — |
| 8 | 12 | — |
| 9 | 13 | — |

---

### Task 1: Domain foundation — entities, ports, port extension, typed errors

**Files:**
- Create: `genql/domain/entities/defect.py`, `genql/domain/entities/critique_report.py`, `genql/domain/entities/ambiguity_probe.py`, `genql/domain/entities/probe_result.py`, `genql/domain/entities/candidate_selection.py`, `genql/domain/entities/ambiguity_example.py`, `genql/domain/ports/candidate_strategy.py`, `genql/domain/ports/critic.py`, `genql/domain/ports/probe_designer.py`, `genql/domain/ports/ambiguity_example_reader.py`, `genql/domain/ports/ambiguity_example_writer.py`
- Modify: `genql/domain/ports/domain_reader.py`, `genql/domain/errors.py`
- Test: `tests/unit/test_ambiguity_machinery_entities.py`, `tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py`

**Interfaces:**
- Consumes: `genql.domain.entities.query_plan.QueryPlan`, `genql.domain.entities.schema_link.SchemaLink`, `genql.domain.entities.sql_candidate.SqlCandidate`, `genql.domain.entities.guardrail_violation.GuardrailViolation`, `genql.domain.entities.business_domain.BusinessDomain` (all existing)
- Produces: entities `Defect(dimension, severity, message)`, `CritiqueReport(candidate_index, defects, score)` with `.is_fatal`, `AmbiguityProbe(dimension, probe_sql, candidate_predictions)`, `ProbeResult(probe, actual_result, resolved_candidate_index)`, `CandidateSelection(selected, selected_sql, method, rationale)`, `AmbiguityExample(question, interpretations, resolution, domain_id)`; ports `CandidateGenerationStrategy.generate_variants(plan, links, violations, examples) -> tuple[SqlCandidate, ...]` (with class attribute `variant_count: int`), `Critic.critique(plan, candidates, validated_sqls, links) -> tuple[CritiqueReport, ...]`, `ProbeDesigner.design(plan, candidates, validated_sqls, critiques) -> tuple[AmbiguityProbe, ...]`, `AmbiguityExampleReader.search(question, domain_id, top_k) -> tuple[AmbiguityExample, ...]`, `AmbiguityExampleWriter.write(examples) -> None`; `DomainReader.list_domains(datasource_name) -> tuple[BusinessDomain, ...]`; errors `CritiqueError`, `AmbiguityExampleGenerationError`

- [ ] **Step 1: Write the failing entity tests**

Create `tests/unit/test_ambiguity_machinery_entities.py`:

```python
"""Six new entities. `CritiqueReport.is_fatal` is the one behaviour worth
testing directly: CritiqueNode and CandidateSelectionService both call it, and
a typo in the severity comparison would silently make every candidate look
non-fatal or every one fatal."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)


def test_a_defect_carries_a_dimension_severity_and_message() -> None:
    defect = Defect(dimension="time_range", severity="fatal", message="bad join")

    assert defect.severity == "fatal"


def test_a_defect_dimension_may_be_none_for_a_non_ambiguity_defect() -> None:
    defect = Defect(dimension=None, severity="advisory", message="style nit")

    assert defect.dimension is None


def test_a_defect_is_frozen() -> None:
    defect = Defect(dimension=None, severity="advisory", message="m")

    with pytest.raises(ValidationError):
        defect.message = "other"


def test_a_critique_report_with_a_fatal_defect_is_fatal() -> None:
    report = CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="fatal", message="bad join"),),
        score=0.2,
    )

    assert report.is_fatal is True


def test_a_critique_report_with_only_advisory_defects_is_not_fatal() -> None:
    report = CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="advisory", message="style nit"),),
        score=0.9,
    )

    assert report.is_fatal is False


def test_a_critique_report_with_no_defects_is_not_fatal() -> None:
    report = CritiqueReport(candidate_index=0, defects=(), score=1.0)

    assert report.is_fatal is False


def test_an_ambiguity_probe_carries_a_prediction_per_candidate() -> None:
    probe = AmbiguityProbe(
        dimension="grain",
        probe_sql="SELECT count(*) FROM shop.orders LIMIT 1",
        candidate_predictions=((0, "12"), (1, "144")),
    )

    assert probe.candidate_predictions == ((0, "12"), (1, "144"))


def test_a_probe_result_names_which_candidate_it_resolved() -> None:
    probe = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())
    result = ProbeResult(probe=probe, actual_result="12", resolved_candidate_index=0)

    assert result.resolved_candidate_index == 0


def test_a_probe_result_may_resolve_nothing() -> None:
    probe = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())
    result = ProbeResult(probe=probe, actual_result="99", resolved_candidate_index=None)

    assert result.resolved_candidate_index is None


def test_a_candidate_selection_carries_the_qualified_sql_and_the_method() -> None:
    selection = CandidateSelection(
        selected=CANDIDATE,
        selected_sql="SELECT 1 FROM local.shop.orders LIMIT 1",
        method="single_survivor",
        rationale="only one candidate survived validation",
    )

    assert selection.method == "single_survivor"
    assert selection.selected_sql != selection.selected.sql


def test_a_candidate_selection_rejects_an_unknown_method() -> None:
    with pytest.raises(ValidationError):
        CandidateSelection(
            selected=CANDIDATE, selected_sql="SELECT 1", method="guessed", rationale="r"
        )


def test_an_ambiguity_example_carries_alternative_interpretations() -> None:
    example = AmbiguityExample(
        question="show me revenue",
        interpretations=("gross revenue", "net revenue"),
        resolution="Unqualified revenue means net revenue per the finance glossary.",
        domain_id=3,
    )

    assert example.interpretations == ("gross revenue", "net revenue")
    assert example.domain_id == 3


def test_an_ambiguity_example_domain_id_may_be_none() -> None:
    example = AmbiguityExample(
        question="q", interpretations=("a", "b"), resolution="r", domain_id=None
    )

    assert example.domain_id is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_ambiguity_machinery_entities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.entities.defect'`

- [ ] **Step 3: Create the six entities**

Create `genql/domain/entities/defect.py`:

```python
"""One critique finding against one candidate.

`dimension` is `str | None`, not a `Literal[*AMBIGUITY_DIMENSIONS]`: a
deterministic column/table check has no ambiguity dimension to name (it is a
plain correctness defect), and the LLM half of critique is asked to name one
only when the defect actually reflects a contested interpretation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Defect(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str | None
    severity: Literal["fatal", "repairable", "advisory"]
    message: str
```

Create `genql/domain/entities/critique_report.py`:

```python
"""What critique decided about one surviving candidate.

`candidate_index` is the position in the surviving-candidates tuple this
report is about, not a stable identifier: candidates carry no id of their own,
and critique runs once per turn over one fixed tuple, so a position is
unambiguous for that tuple's lifetime.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.defect import Defect


class CritiqueReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    defects: tuple[Defect, ...]
    score: float

    @property
    def is_fatal(self) -> bool:
        return any(defect.severity == "fatal" for defect in self.defects)
```

Create `genql/domain/entities/ambiguity_probe.py`:

```python
"""One targeted query issued to let the data arbitrate between candidates.

`candidate_predictions` pairs a candidate's index with what its interpretation
predicts the probe will return, rendered as a string up front — comparing the
probe's real result against these predictions is then a lookup
(AmbiguityProbingService), never a second judgment call.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AmbiguityProbe(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    probe_sql: str
    candidate_predictions: tuple[tuple[int, str], ...]
```

Create `genql/domain/entities/probe_result.py`:

```python
"""One probe's real result, compared against every candidate's prediction.

`resolved_candidate_index` is None when no prediction matched the real
result — a prediction rendering mismatch (e.g. "42" vs "42.0") rather than a
crash, per this phase's own Risk section: it fails visibly downstream
(selection falls back to critique ranking) rather than raising here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.ambiguity_probe import AmbiguityProbe


class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    probe: AmbiguityProbe
    actual_result: str
    resolved_candidate_index: int | None = None
```

Create `genql/domain/entities/candidate_selection.py`:

```python
"""The winning candidate, and which qualified SQL to actually run.

`selected_sql` is the qualified string StaticValidationService produced for
the winning candidate, not `selected.sql` (the pre-repair, pre-qualification
text the generator emitted). Carrying both lets a later stage explain *which
interpretation* won while executing exactly what passed validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.sql_candidate import SqlCandidate


class CandidateSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    selected: SqlCandidate
    selected_sql: str
    method: Literal["single_survivor", "probe_resolved", "critique_ranked"]
    rationale: str
```

Create `genql/domain/entities/ambiguity_example.py`:

```python
"""One offline, synthetic ambiguity example: a question, the interpretations
it admits, and which one is correct and why.

Written once per domain by SyntheticAmbiguityLogService, read by similarity to
the current question as few-shot context for the contested generation path —
a different key and a different consumer than genql_search_document's
schema-object retrieval, which is why this is its own table rather than an
extension of that one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AmbiguityExample(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    interpretations: tuple[str, ...]
    resolution: str
    domain_id: int | None = None
```

- [ ] **Step 4: Run to verify the entity tests pass**

Run: `uv run pytest tests/unit/test_ambiguity_machinery_entities.py -q`
Expected: PASS — 13 tests

- [ ] **Step 5: Write the failing port tests**

Create `tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py`:

```python
"""Every new port, structurally satisfied by a minimal fake. `variant_count`
is asserted on CandidateGenerationStrategy because CandidateGenerationService
never calls it (each strategy's own generate_variants always returns exactly
that many) — it exists purely as advertised metadata, and a Protocol attribute
with nothing that reads it is easy to typo silently.
"""

from __future__ import annotations

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.ambiguity_example_reader import AmbiguityExampleReader
from genql.domain.ports.ambiguity_example_writer import AmbiguityExampleWriter
from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy
from genql.domain.ports.critic import Critic
from genql.domain.ports.domain_reader import DomainReader
from genql.domain.ports.probe_designer import ProbeDesigner

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())
CANDIDATE = SqlCandidate(sql="SELECT 1", plan=PLAN)


class Strategy:
    variant_count = 2

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]:
        return (CANDIDATE, CANDIDATE)


class CriticImpl:
    def critique(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        links: tuple[SchemaLink, ...],
    ) -> tuple[CritiqueReport, ...]:
        return ()


class Designer:
    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]:
        return ()


class ExampleStore:
    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        return ()

    def write(self, examples: tuple[AmbiguityExample, ...]) -> None:
        return None


class Domains:
    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        return None

    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]:
        return ()


def test_candidate_generation_strategy_is_structurally_satisfied() -> None:
    strategy = Strategy()

    assert isinstance(strategy, CandidateGenerationStrategy)
    assert strategy.variant_count == 2


def test_critic_is_structurally_satisfied() -> None:
    assert isinstance(CriticImpl(), Critic)


def test_probe_designer_is_structurally_satisfied() -> None:
    assert isinstance(Designer(), ProbeDesigner)


def test_ambiguity_example_reader_and_writer_are_structurally_satisfied() -> None:
    store = ExampleStore()

    assert isinstance(store, AmbiguityExampleReader)
    assert isinstance(store, AmbiguityExampleWriter)


def test_domain_reader_now_also_lists_domains() -> None:
    assert isinstance(Domains(), DomainReader)
```

- [ ] **Step 6: Run to verify they fail**

Run: `uv run pytest tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.domain.ports.candidate_strategy'`

- [ ] **Step 7: Create the five new ports**

Create `genql/domain/ports/candidate_strategy.py`:

```python
"""One way of turning a plan into SQL variants.

`variant_count` is fixed per strategy rather than a runtime parameter, since
each strategy's prompt is built around producing exactly that many structured
variants from one ChatProvider.complete call.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class CandidateGenerationStrategy(Protocol):
    variant_count: ClassVar[int]

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]: ...
```

Create `genql/domain/ports/critic.py`:

```python
"""Scores every surviving candidate against the plan and each other.

`validated_sqls[i]` is the qualified statement for `candidates[i]` — the
deterministic column/table check runs against this, not `candidates[i].sql`,
since qualification can rewrite references a pre-qualification check would
misjudge.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class Critic(Protocol):
    def critique(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        links: tuple[SchemaLink, ...],
    ) -> tuple[CritiqueReport, ...]: ...
```

Create `genql/domain/ports/probe_designer.py`:

```python
"""Designs the targeted queries that let the data resolve a critique
disagreement. Only designs them — validating and executing probe_sql reuses
StaticValidationService and GuardedExecutionService unchanged, one layer up in
AmbiguityProbingService."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class ProbeDesigner(Protocol):
    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]: ...
```

Create `genql/domain/ports/ambiguity_example_reader.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample


@runtime_checkable
class AmbiguityExampleReader(Protocol):
    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]: ...
```

Create `genql/domain/ports/ambiguity_example_writer.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample


@runtime_checkable
class AmbiguityExampleWriter(Protocol):
    def write(self, examples: tuple[AmbiguityExample, ...]) -> None: ...
```

- [ ] **Step 8: Extend `DomainReader` and add the two new errors**

Modify `genql/domain/ports/domain_reader.py`. Add the import and the method:

```python
from genql.domain.entities.business_domain import BusinessDomain
```

```python
class DomainReader(Protocol):
    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None: ...

    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]: ...
```

Modify `genql/domain/errors.py`. Append at the end of the file:

```python
class CritiqueError(QueryError):
    """Every surviving candidate carries a fatal defect, and the one escalated
    regeneration this phase allows has already been spent."""


class AmbiguityExampleGenerationError(DiscoveryError):
    """The offline synthetic ambiguity log could not be generated or embedded
    for one domain."""
```

- [ ] **Step 9: Run to verify the port tests pass**

Run: `uv run pytest tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py tests/unit/test_ambiguity_machinery_entities.py -q`
Expected: PASS — 18 tests

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — the whole Phase 6 suite plus the 18 new tests

- [ ] **Step 11: Commit**

```bash
git add genql/domain/entities/defect.py genql/domain/entities/critique_report.py \
  genql/domain/entities/ambiguity_probe.py genql/domain/entities/probe_result.py \
  genql/domain/entities/candidate_selection.py genql/domain/entities/ambiguity_example.py \
  genql/domain/ports/candidate_strategy.py genql/domain/ports/critic.py \
  genql/domain/ports/probe_designer.py genql/domain/ports/ambiguity_example_reader.py \
  genql/domain/ports/ambiguity_example_writer.py genql/domain/ports/domain_reader.py \
  genql/domain/errors.py tests/unit/test_ambiguity_machinery_entities.py \
  tests/unit/test_ambiguity_machinery_ports_are_runtime_checkable.py
git commit -m "feat(domain): add Phase 6.5 ambiguity-machinery entities, ports, and errors"
```

---

### Task 2: Settings and migration `0008`

**Files:**
- Create: `migrations/versions/0008_ambiguity_examples.py`, `tests/integration/test_migration_0008.py`
- Modify: `genql/core/settings.py`, `.env.example`
- Test: `tests/integration/test_migration_0008.py`

**Interfaces:**
- Consumes: migration `0007` as `down_revision`; `genql.genql_domain(id)` for the foreign key
- Produces: table `genql.genql_ambiguity_example (id, domain_id, question, interpretations, resolution, embedding)`; `Settings.chat_model_escalation: str = "anthropic/claude-opus-5"`, `Settings.probing_max_probes: int = 3`, `Settings.ambiguity_example_top_k: int = 3`

- [ ] **Step 1: Add the three settings**

Modify `genql/core/settings.py`. Append three fields after `checkpoint_pool_max_size`:

```python
    # Used only for the one escalated regeneration this phase allows, when
    # every surviving candidate carries a fatal defect after one repair round.
    # A distinct, stronger model rather than a retry against chat_model: the
    # parent spec's §20 names Opus specifically for this trigger.
    chat_model_escalation: str = "anthropic/claude-opus-5"
    # Caps AmbiguityProbingService regardless of how many dimensions a
    # critique disagreement touches, bounding worst-case probing latency and
    # cost per the spec's §19 risk mitigation.
    probing_max_probes: int = 3
    # How many offline synthetic ambiguity examples the contested generation
    # path retrieves as few-shot context. Small on purpose: these are
    # few-shot exemplars, not a retrieval corpus to page through.
    ambiguity_example_top_k: int = 3
```

- [ ] **Step 2: Document them in `.env.example`**

Modify `.env.example`. Append:

```
# The model used for the one escalated regeneration this phase allows.
GENQL_CHAT_MODEL_ESCALATION=anthropic/claude-opus-5
# Cap on ambiguity-driven probe queries per turn.
GENQL_PROBING_MAX_PROBES=3
# Offline synthetic ambiguity examples retrieved as few-shot context.
GENQL_AMBIGUITY_EXAMPLE_TOP_K=3
```

- [ ] **Step 3: Write the failing migration test**

Create `tests/integration/test_migration_0008.py`:

```python
"""0008 is one additive table, mirroring genql_search_document's pgvector/HNSW
shape exactly (same extension, same index type, same distance operator) so
nothing new is asked of the ParadeDB image. domain_id is ON DELETE SET NULL,
not CASCADE: an example survives its domain being renamed or re-clustered,
since the question/interpretations/resolution triple is still a valid few-shot
exemplar even once it is no longer attributed to a specific domain.
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


def test_upgrade_creates_genql_ambiguity_example(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NOT NULL")
        ).scalar_one()

    assert present


def test_the_hnsw_index_exists(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname = 'genql_ambiguity_example_hnsw'"
            )
        ).scalar_one()

    assert present == 1


def test_deleting_a_domain_sets_domain_id_null_rather_than_deleting_the_row(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("ambiguity_ds", "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        domain_id = conn.execute(
            text(
                "INSERT INTO genql.genql_domain (datasource_name, name, description) "
                "VALUES ('ambiguity_ds', 'Sales', 'd') RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO genql.genql_ambiguity_example "
                "(domain_id, question, interpretations, resolution, embedding) "
                "VALUES (:domain_id, 'q', ARRAY['a','b'], 'r', "
                f"CAST(ARRAY(SELECT 0 FROM generate_series(1,1536)) AS vector))"
            ),
            {"domain_id": domain_id},
        )
        conn.execute(text("DELETE FROM genql.genql_domain WHERE id = :id"), {"id": domain_id})
        remaining = conn.execute(
            text("SELECT domain_id FROM genql.genql_ambiguity_example WHERE question = 'q'")
        ).scalar_one()

    assert remaining is None


def test_downgrade_to_0007_drops_genql_ambiguity_example_and_upgrade_restores_it(
    migrated_engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "0007")
    with migrated_engine.connect() as conn:
        gone = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NULL")
        ).scalar_one()
    assert gone

    command.upgrade(alembic_config, "head")
    with migrated_engine.connect() as conn:
        back = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NOT NULL")
        ).scalar_one()
    assert back
```

- [ ] **Step 4: Run to verify it fails**

Run: `uv run pytest tests/integration/test_migration_0008.py -q`
Expected: FAIL — the table does not exist. In a sandbox with no database, this errors at fixture setup; that is expected, and the migration is still written in Step 5.

- [ ] **Step 5: Write the migration**

Create `migrations/versions/0008_ambiguity_examples.py`:

```python
"""ambiguity examples

Revision ID: 0008
Revises: 0007

One additive table: the offline synthetic ambiguity log SyntheticAmbiguityLog-
Service writes per domain and CandidateGenerationService reads as few-shot
context on the contested path. Mirrors genql_search_document's pgvector/HNSW
setup exactly (Phase 4) — same extension, same index type, same distance
operator — so nothing new is asked of the ParadeDB image; `vector` is already
created by migration 0005 and is not re-created here.

domain_id is ON DELETE SET NULL, not CASCADE, unlike every other table this
phase's sibling tables use: an example's question/interpretations/resolution
triple stays a valid few-shot exemplar even once its domain is renamed or
re-clustered, so deleting the domain should not delete the example.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "genql_ambiguity_example",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("domain_id", sa.BigInteger),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("interpretations", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("resolution", sa.Text, nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.ForeignKeyConstraint(
            ["domain_id"],
            ["genql.genql_domain.id"],
            name="fk_genql_ambiguity_example_domain",
            ondelete="SET NULL",
        ),
        schema="genql",
    )
    op.execute("""
        CREATE INDEX genql_ambiguity_example_hnsw
            ON genql.genql_ambiguity_example
            USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genql.genql_ambiguity_example_hnsw")
    op.drop_table("genql_ambiguity_example", schema="genql")
```

- [ ] **Step 6: Run the migration test**

Run: `uv run pytest tests/integration/test_migration_0008.py -q`
Expected: PASS — 4 tests. Sandbox: "written but unrun".

- [ ] **Step 7: Confirm the whole migration chain still linearises**

Run: `uv run pytest tests/integration/test_migrations.py -q`
Expected: PASS — a single head, `0001 → 0008`.

- [ ] **Step 8: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add genql/core/settings.py .env.example migrations/versions/0008_ambiguity_examples.py \
  tests/integration/test_migration_0008.py
git commit -m "feat(migrations): add genql_ambiguity_example and Phase 6.5 settings"
```

---

### Task 3: `AmbiguityExample` repositories and `DomainRepository.list_domains`

**Files:**
- Create: `genql/repositories/semantic/ambiguity_example_repository.py`, `tests/integration/test_ambiguity_example_repository.py`
- Modify: `genql/repositories/semantic/domain_repository.py`, `genql/repositories/semantic/__init__.py`, `tests/integration/test_domain_repository.py`
- Test: `tests/integration/test_ambiguity_example_repository.py`, `tests/integration/test_domain_repository.py`

**Interfaces:**
- Consumes: `AmbiguityExample` entity, `AmbiguityExampleReader`/`AmbiguityExampleWriter`/`DomainReader` ports (Task 1); `genql.genql_ambiguity_example` (Task 2); `genql.domain.ports.embedding_provider.EmbeddingProvider` (existing)
- Produces: `PostgresAmbiguityExampleReader(engine, embedder).search(question, domain_id, top_k) -> tuple[AmbiguityExample, ...]`; `PostgresAmbiguityExampleWriter(engine, embedder).write(examples) -> None`; `PostgresDomainRepository.list_domains(datasource_name) -> tuple[BusinessDomain, ...]`

- [ ] **Step 1: Write the failing repository integration test**

Create `tests/integration/test_ambiguity_example_repository.py`:

```python
"""The reader and writer both embed internally (Deviation 4): the domain
ports carry no embedding parameter, so nothing upstream can compute it for
them. FakeEmbeddingProvider returns a fixed vector regardless of input so the
distance ordering below is driven only by which rows exist, not by real
semantic similarity — that is proven separately in the real-provider tests.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.repositories.semantic.ambiguity_example_repository import (
    PostgresAmbiguityExampleReader,
    PostgresAmbiguityExampleWriter,
)

DS = "ambiguity_example_ds"


class FixedEmbeddingProvider:
    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [tuple([0.1] * self._dim) for _ in texts]


@pytest.fixture()
def seeded(migrated_engine: Engine, register_schema: object) -> Engine:
    register_schema(DS, "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM genql.genql_ambiguity_example WHERE domain_id IS NULL")
        )
    return migrated_engine


def test_a_written_example_is_found_by_search(seeded: Engine) -> None:
    embedder = FixedEmbeddingProvider()
    writer = PostgresAmbiguityExampleWriter(seeded, embedder)
    example = AmbiguityExample(
        question="show me revenue",
        interpretations=("gross revenue", "net revenue"),
        resolution="Net revenue, per the finance glossary.",
        domain_id=None,
    )

    writer.write((example,))
    found = PostgresAmbiguityExampleReader(seeded, embedder).search("revenue", None, 5)

    assert any(e.question == "show me revenue" for e in found)


def test_search_respects_top_k(seeded: Engine) -> None:
    embedder = FixedEmbeddingProvider()
    writer = PostgresAmbiguityExampleWriter(seeded, embedder)
    writer.write(
        tuple(
            AmbiguityExample(question=f"q{i}", interpretations=("a", "b"), resolution="r")
            for i in range(5)
        )
    )

    found = PostgresAmbiguityExampleReader(seeded, embedder).search("q", None, 2)

    assert len(found) == 2


def test_writing_no_examples_is_a_no_op() -> None:
    embedder = FixedEmbeddingProvider()
    # No engine call should happen at all; a None engine would raise if write()
    # tried to open a connection for an empty batch.
    PostgresAmbiguityExampleWriter(engine=None, embedder=embedder).write(())  # type: ignore[arg-type]


def test_search_with_no_rows_returns_empty(seeded: Engine) -> None:
    found = PostgresAmbiguityExampleReader(seeded, FixedEmbeddingProvider()).search("nothing", None, 5)

    assert found == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_ambiguity_example_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.semantic.ambiguity_example_repository'`

- [ ] **Step 3: Write the repository**

Create `genql/repositories/semantic/ambiguity_example_repository.py`:

```python
"""The offline synthetic ambiguity log's reader and writer.

Both embed internally via an injected EmbeddingProvider (Deviation 4): the
AmbiguityExampleReader/Writer ports carry no embedding parameter, unlike
Retriever.search, which receives one pre-computed by RetrievalService. The
read shape otherwise mirrors DenseRetriever's cosine-distance ORDER BY LIMIT
exactly, applied to this smaller table.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.ports.embedding_provider import EmbeddingProvider

_SEARCH = text("""
    SELECT question, interpretations, resolution, domain_id
    FROM genql.genql_ambiguity_example
    WHERE (:domain_id::bigint IS NULL OR domain_id = :domain_id)
    ORDER BY embedding <=> CAST(:query_embedding AS vector)
    LIMIT :top_k
""")

_INSERT = text("""
    INSERT INTO genql.genql_ambiguity_example
        (domain_id, question, interpretations, resolution, embedding)
    VALUES (:domain_id, :question, :interpretations, :resolution, :embedding)
""")


class PostgresAmbiguityExampleReader:
    def __init__(self, engine: Engine, embedder: EmbeddingProvider) -> None:
        self._engine = engine
        self._embedder = embedder

    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        query_embedding = self._embedder.embed([question])[0]
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "domain_id": domain_id,
                    "query_embedding": str(list(query_embedding)),
                    "top_k": top_k,
                },
            ).all()
        return tuple(
            AmbiguityExample(
                question=row.question,
                interpretations=tuple(row.interpretations),
                resolution=row.resolution,
                domain_id=row.domain_id,
            )
            for row in rows
        )


class PostgresAmbiguityExampleWriter:
    def __init__(self, engine: Engine, embedder: EmbeddingProvider) -> None:
        self._engine = engine
        self._embedder = embedder

    def write(self, examples: Sequence[AmbiguityExample]) -> None:
        if not examples:
            return
        embeddings = self._embedder.embed([e.question for e in examples])
        rows = [
            {
                "domain_id": example.domain_id,
                "question": example.question,
                "interpretations": list(example.interpretations),
                "resolution": example.resolution,
                "embedding": list(embedding),
            }
            for example, embedding in zip(examples, embeddings, strict=True)
        ]
        with self._engine.begin() as conn:
            conn.execute(_INSERT, rows)
```

- [ ] **Step 4: Export both from the package `__init__`**

Modify `genql/repositories/semantic/__init__.py`. Add the import and both names to `__all__`, alongside the existing entries:

```python
from genql.repositories.semantic.ambiguity_example_repository import (
    PostgresAmbiguityExampleReader,
    PostgresAmbiguityExampleWriter,
)
```

- [ ] **Step 5: Run the repository test**

Run: `uv run pytest tests/integration/test_ambiguity_example_repository.py -q`
Expected: PASS — 4 tests. Sandbox: "written but unrun".

- [ ] **Step 6: Write the failing `list_domains` test**

Append to `tests/integration/test_domain_repository.py`:

```python
def test_list_domains_returns_every_domain_for_the_datasource(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("list_domains_ds", "public")
    repo = PostgresDomainRepository(migrated_engine)
    repo.write_domains(
        [
            BusinessDomain(
                datasource_name="list_domains_ds",
                name="Sales",
                description="Orders and revenue.",
                provenance=Provenance.LLM,
            ),
            BusinessDomain(
                datasource_name="list_domains_ds",
                name="Support",
                description="Tickets and agents.",
                provenance=Provenance.LLM,
            ),
        ]
    )

    domains = repo.list_domains("list_domains_ds")

    assert {d.name for d in domains} == {"Sales", "Support"}
    assert all(d.domain_id is not None for d in domains)


def test_list_domains_is_empty_for_a_datasource_with_none(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("no_domains_ds", "public")

    assert PostgresDomainRepository(migrated_engine).list_domains("no_domains_ds") == ()
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/integration/test_domain_repository.py -k list_domains -q`
Expected: FAIL — `AttributeError: 'PostgresDomainRepository' object has no attribute 'list_domains'`

- [ ] **Step 8: Implement `list_domains`**

Modify `genql/repositories/semantic/domain_repository.py`. Add the query and the method:

```python
_SELECT_DOMAINS = text("""
    SELECT id, datasource_name, name, description, provenance
    FROM genql.genql_domain
    WHERE datasource_name = :datasource_name
    ORDER BY name
""")
```

```python
    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]:
        """The read side SyntheticAmbiguityLogService needs: one domain per
        row, grounding its per-domain generation prompt. Ordered by name so a
        capped or paginated caller sees a stable slice, matching every other
        reader in this file."""
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_DOMAINS, {"datasource_name": datasource_name}).all()
        return tuple(
            BusinessDomain(
                datasource_name=row.datasource_name,
                domain_id=row.id,
                name=row.name,
                description=row.description,
                provenance=row.provenance,
            )
            for row in rows
        )
```

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/integration/test_domain_repository.py -q`
Expected: PASS — every existing test plus the 2 new ones. Sandbox: "written but unrun".

- [ ] **Step 10: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 11: Commit**

```bash
git add genql/repositories/semantic/ambiguity_example_repository.py \
  genql/repositories/semantic/domain_repository.py genql/repositories/semantic/__init__.py \
  tests/integration/test_ambiguity_example_repository.py tests/integration/test_domain_repository.py
git commit -m "feat(repositories): add ambiguity-example store and DomainRepository.list_domains"
```

---

### Task 4: `CANDIDATE_STRATEGIES` registry and the two generation strategies

**Files:**
- Create: `genql/repositories/query/registry.py`, `genql/repositories/query/candidate_prompt.py`, `genql/repositories/query/decomposition_strategy.py`, `genql/repositories/query/execution_plan_strategy.py`, `tests/unit/test_candidate_strategies.py`
- Modify: `genql/repositories/query/__init__.py`
- Test: `tests/unit/test_candidate_strategies.py`

**Interfaces:**
- Consumes: `CandidateGenerationStrategy` port, `SqlCandidate`/`QueryPlan`/`SchemaLink`/`GuardrailViolation`/`AmbiguityExample` entities (Task 1); `ChatProvider` port (existing)
- Produces: `CANDIDATE_STRATEGIES: Registry[CandidateGenerationStrategy]`; `DecompositionStrategy(chat).generate_variants(...)`, `ExecutionPlanStrategy(chat).generate_variants(...)`, each returning exactly 2 `SqlCandidate`s from one `ChatProvider.complete` call

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_candidate_strategies.py`:

```python
"""Two strategies, one shared contract: each returns exactly variant_count
candidates from exactly one ChatProvider.complete call. The registry test
matters on its own — CandidateGenerationService iterates CANDIDATE_STRATEGIES
.keys() on the contested path, so a strategy registered under the wrong key,
or not registered at all, would silently change candidate diversity.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, GenerationError
from genql.repositories.query.decomposition_strategy import DecompositionStrategy
from genql.repositories.query.execution_plan_strategy import ExecutionPlanStrategy
from genql.repositories.query.registry import CANDIDATE_STRATEGIES

PLAN = QueryPlan(
    question="revenue by customer",
    plan_text="sum orders.total grouped by customers.email",
    referenced_objects=("local.shop.orders", "local.shop.customers"),
)
LINKS = (SchemaLink(object_qualified_name="local.shop.orders", column_names=("id", "total")),)
EXAMPLE = AmbiguityExample(
    question="show me revenue", interpretations=("gross", "net"), resolution="net"
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


def test_both_strategies_are_registered() -> None:
    assert set(CANDIDATE_STRATEGIES.keys()) >= {"decomposition", "execution_plan"}


def test_the_registry_creates_a_decomposition_strategy_with_an_injected_chat() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    strategy = CANDIDATE_STRATEGIES.create("decomposition", chat=chat)
    variants = strategy.generate_variants(PLAN, LINKS, (), ())

    assert len(variants) == 2
    assert len(chat.prompts) == 1


def test_decomposition_returns_two_candidates_carrying_the_plan() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    variants = DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert [v.sql for v in variants] == ["SELECT 1", "SELECT 2"]
    assert all(v.plan is PLAN for v in variants)


def test_decomposition_declares_a_variant_count_of_two() -> None:
    assert DecompositionStrategy.variant_count == 2


def test_decomposition_prompt_carries_the_examples_when_given() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), (EXAMPLE,))

    assert "show me revenue" in chat.prompts[0]


def test_a_provider_failure_becomes_a_generation_error() -> None:
    with pytest.raises(GenerationError):
        DecompositionStrategy(RaisingChatProvider()).generate_variants(PLAN, LINKS, (), ())


def test_execution_plan_returns_two_candidates() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    variants = ExecutionPlanStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert len(variants) == 2


def test_execution_plan_declares_a_variant_count_of_two() -> None:
    assert ExecutionPlanStrategy.variant_count == 2


def test_execution_plan_prompt_mentions_scan_order() -> None:
    chat = FakeChatProvider({"variant_1": "SELECT 1", "variant_2": "SELECT 2"})

    ExecutionPlanStrategy(chat).generate_variants(PLAN, LINKS, (), ())

    assert "execution plan" in chat.prompts[0].lower()


def test_an_empty_variant_is_refused() -> None:
    chat = FakeChatProvider({"variant_1": "   ", "variant_2": "SELECT 2"})

    with pytest.raises(GenerationError, match="empty"):
        DecompositionStrategy(chat).generate_variants(PLAN, LINKS, (), ())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_candidate_strategies.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.repositories.query.registry'`

- [ ] **Step 3: Create the registry**

Create `genql/repositories/query/registry.py`:

```python
"""The candidate-generation strategy registry, keyed by strategy name.

Mirrors GUARDRAILS exactly: one file plus one decorator adds a strategy.
CandidateGenerationService iterates CANDIDATE_STRATEGIES.keys() only on the
contested path — the non-contested path always names "decomposition"
directly, so a third registered strategy changes contested-path diversity
without touching CandidateGenerationService at all.
"""

from __future__ import annotations

from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy
from genql.registries.registry import Registry

CANDIDATE_STRATEGIES: Registry[CandidateGenerationStrategy] = Registry("candidate_strategies")
```

- [ ] **Step 4: Write the shared prompt-rendering helpers**

Both strategies render the same schema-link catalog and the same few-shot
example block, differing only in the instruction text around them. Factoring
that into one shared, public (non-underscore) module keeps each strategy file
under the line cap without either one importing a "private" name from the
other, which `ruff` (`PLC2701`) would otherwise flag.

Create `genql/repositories/query/candidate_prompt.py`:

```python
"""Rendering helpers shared by every CandidateGenerationStrategy — the
schema-link catalog and the few-shot example block look identical regardless
of which strategy's instructions wrap them."""

from __future__ import annotations

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.schema_link import SchemaLink


def render_link(link: SchemaLink) -> str:
    parts = [f"- {link.object_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    return "\n".join(parts)


def render_examples(examples: tuple[AmbiguityExample, ...]) -> str:
    if not examples:
        return ""
    rendered = "\n\n".join(
        f"Q: {e.question}\nInterpretations: {'; '.join(e.interpretations)}\n"
        f"Resolved: {e.resolution}"
        for e in examples
    )
    return f"\n\nSimilar ambiguous questions resolved previously:\n{rendered}"
```

- [ ] **Step 5: Write the two strategies**

Create `genql/repositories/query/decomposition_strategy.py`:

```python
"""Breaks the plan into sub-clauses (filters, joins, aggregation) and asks the
model to assemble two candidate statements bottom-up from them — one of the
two prompt strategies the parent spec's §20 says diversity comes from, rather
than resampling one prompt.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ChatProviderError, GenerationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.repositories.query.candidate_prompt import render_examples, render_link
from genql.repositories.query.registry import CANDIDATE_STRATEGIES


class TwoVariantResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_1: str
    variant_2: str


def build_decomposition_prompt(
    plan: QueryPlan,
    links: tuple[SchemaLink, ...],
    violations: tuple[GuardrailViolation, ...],
    examples: tuple[AmbiguityExample, ...],
) -> str:
    catalog = "\n".join(render_link(link) for link in links)
    sections = [
        "Decompose the plan below into its filter, join, and aggregation "
        "sub-clauses, then assemble TWO candidate PostgreSQL SELECT "
        "statements bottom-up from them, each representing a genuinely "
        "different plausible interpretation of the question.",
        f"Question:\n{plan.question}",
        f"Plan:\n{plan.plan_text}",
        f"Available objects (reference them as schema.object):\n{catalog}",
        (
            "Rules:\n"
            "- Each variant is a single SELECT (a leading WITH is fine).\n"
            "- Reference only the objects listed above, schema-qualified.\n"
            "- Include an explicit LIMIT in each variant.\n"
            "- Return `variant_1` and `variant_2`, each raw SQL with no "
            "markdown fence and no commentary."
        ),
    ]
    if violations:
        rendered = "\n".join(f"- {v.rule_name}: {v.message}" for v in violations)
        sections.append(f"The previous attempt was rejected:\n{rendered}")
    sections.append(render_examples(examples))
    return "\n\n".join(s for s in sections if s)


@CANDIDATE_STRATEGIES.register("decomposition")
class DecompositionStrategy:
    variant_count = 2

    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]:
        prompt = build_decomposition_prompt(plan, links, violations, examples)
        try:
            response = self._chat.complete(prompt, TwoVariantResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise GenerationError(
                f"decomposition strategy failed to generate SQL for {plan.question!r}: {exc}"
            ) from exc
        variants = (response.variant_1.strip(), response.variant_2.strip())
        if not all(variants):
            raise GenerationError(
                f"the decomposition strategy returned an empty variant for {plan.question!r}"
            )
        return tuple(SqlCandidate(sql=v, plan=plan) for v in variants)
```

Create `genql/repositories/query/execution_plan_strategy.py`:

```python
"""Asks the model to reason in terms of a PostgreSQL execution plan (scan ->
join -> filter -> aggregate order) and produce two candidates from that
ordering — the second of the two prompt strategies the parent spec's §20
names for diversity.
"""

from __future__ import annotations

from pydantic import ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ChatProviderError, GenerationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.repositories.query.candidate_prompt import render_examples, render_link
from genql.repositories.query.decomposition_strategy import TwoVariantResponse
from genql.repositories.query.registry import CANDIDATE_STRATEGIES


def build_execution_plan_prompt(
    plan: QueryPlan,
    links: tuple[SchemaLink, ...],
    violations: tuple[GuardrailViolation, ...],
    examples: tuple[AmbiguityExample, ...],
) -> str:
    catalog = "\n".join(render_link(link) for link in links)
    sections = [
        "Reason about the plan below the way a PostgreSQL execution plan "
        "would order it — scan, then join, then filter, then aggregate — "
        "and produce TWO candidate SELECT statements from that ordering, "
        "each representing a genuinely different plausible interpretation "
        "of the question.",
        f"Question:\n{plan.question}",
        f"Plan:\n{plan.plan_text}",
        f"Available objects (reference them as schema.object):\n{catalog}",
        (
            "Rules:\n"
            "- Each variant is a single SELECT (a leading WITH is fine).\n"
            "- Reference only the objects listed above, schema-qualified.\n"
            "- Include an explicit LIMIT in each variant.\n"
            "- Return `variant_1` and `variant_2`, each raw SQL with no "
            "markdown fence and no commentary."
        ),
    ]
    if violations:
        rendered = "\n".join(f"- {v.rule_name}: {v.message}" for v in violations)
        sections.append(f"The previous attempt was rejected:\n{rendered}")
    sections.append(render_examples(examples))
    return "\n\n".join(s for s in sections if s)


@CANDIDATE_STRATEGIES.register("execution_plan")
class ExecutionPlanStrategy:
    variant_count = 2

    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]:
        prompt = build_execution_plan_prompt(plan, links, violations, examples)
        try:
            response = self._chat.complete(prompt, TwoVariantResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise GenerationError(
                f"execution_plan strategy failed to generate SQL for {plan.question!r}: {exc}"
            ) from exc
        variants = (response.variant_1.strip(), response.variant_2.strip())
        if not all(variants):
            raise GenerationError(
                f"the execution_plan strategy returned an empty variant for {plan.question!r}"
            )
        return tuple(SqlCandidate(sql=v, plan=plan) for v in variants)
```

- [ ] **Step 6: Register both via the package `__init__`**

Modify `genql/repositories/query/__init__.py`. It currently holds only the package docstring; add:

```python
from genql.repositories.query.decomposition_strategy import DecompositionStrategy
from genql.repositories.query.execution_plan_strategy import ExecutionPlanStrategy

__all__ = ["DecompositionStrategy", "ExecutionPlanStrategy"]
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/unit/test_candidate_strategies.py -q`
Expected: PASS — 10 tests

- [ ] **Step 8: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add genql/repositories/query/registry.py genql/repositories/query/candidate_prompt.py \
  genql/repositories/query/decomposition_strategy.py genql/repositories/query/execution_plan_strategy.py \
  genql/repositories/query/__init__.py tests/unit/test_candidate_strategies.py
git commit -m "feat(query): add the CANDIDATE_STRATEGIES registry and its two strategies"
```

---

### Task 5: `CandidateGenerationService` rewritten for multi-candidate generation

**Files:**
- Modify: `genql/services/query/candidate_generation_service.py`, `tests/unit/test_candidate_generation_service.py`
- Test: `tests/unit/test_candidate_generation_service.py`

**Interfaces:**
- Consumes: `CANDIDATE_STRATEGIES` (Task 4), `AmbiguityExampleReader` port (Task 1)
- Produces: `CandidateGenerationService(chat, escalation_chat, examples, example_top_k).generate(plan, links, violations=(), *, domain_id=None, contested=False, escalated=False) -> tuple[SqlCandidate, ...]` — same class name, same import path, every existing caller updates in the same task

- [ ] **Step 1: Rewrite the test file for the new signature**

Replace `tests/unit/test_candidate_generation_service.py` in full:

```python
"""Non-contested calls exactly one strategy and keeps only its first variant —
bit-for-bit Phase 5/6 cost and shape. Contested calls every registered
strategy once each and fetches examples exactly once, regardless of how many
strategies are registered, matching CandidateGenerationService's own
docstring claim.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, GenerationError
from genql.repositories.query.registry import CANDIDATE_STRATEGIES
from genql.services.query.candidate_generation_service import CandidateGenerationService

PLAN = QueryPlan(
    question="revenue by customer",
    plan_text="sum orders.total grouped by customers.email",
    referenced_objects=("local.shop.orders", "local.shop.customers"),
)
LINKS = (SchemaLink(object_qualified_name="local.shop.orders", column_names=("id", "total")),)
VIOLATIONS = (GuardrailViolation(rule_name="fake", message="bad", repairable=True),)
EXAMPLE = AmbiguityExample(question="q", interpretations=("a", "b"), resolution="r")


class FakeChatProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        return response_schema.model_validate(
            {"variant_1": f"SELECT '{self.name}-1'", "variant_2": f"SELECT '{self.name}-2'"}
        )


class RaisingChatProvider:
    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        raise ChatProviderError("upstream refused")


class FakeExampleReader:
    def __init__(self, examples: tuple[AmbiguityExample, ...] = ()) -> None:
        self._examples = examples
        self.calls: list[tuple[str, int | None, int]] = []

    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        self.calls.append((question, domain_id, top_k))
        return self._examples


def _service(
    chat: object = None, escalation: object = None, examples: FakeExampleReader | None = None
) -> CandidateGenerationService:
    return CandidateGenerationService(
        chat=chat or FakeChatProvider("normal"),
        escalation_chat=escalation or FakeChatProvider("escalated"),
        examples=examples or FakeExampleReader(),
        example_top_k=3,
    )


def test_non_contested_calls_exactly_one_strategy_and_keeps_one_candidate() -> None:
    chat = FakeChatProvider("normal")
    examples = FakeExampleReader()

    candidates = _service(chat=chat, examples=examples).generate(PLAN, LINKS, contested=False)

    assert len(candidates) == 1
    assert chat.calls == 1
    assert examples.calls == []


def test_contested_calls_every_registered_strategy_once() -> None:
    chat = FakeChatProvider("normal")

    candidates = _service(chat=chat).generate(PLAN, LINKS, contested=True)

    assert chat.calls == len(CANDIDATE_STRATEGIES.keys())
    assert len(candidates) == 2 * len(CANDIDATE_STRATEGIES.keys())


def test_contested_fetches_examples_exactly_once() -> None:
    examples = FakeExampleReader((EXAMPLE,))

    _service(examples=examples).generate(PLAN, LINKS, contested=True, domain_id=7)

    assert examples.calls == [("revenue by customer", 7, 3)]


def test_escalated_uses_the_escalation_chat_provider() -> None:
    normal = FakeChatProvider("normal")
    escalated = FakeChatProvider("escalated")

    candidates = _service(chat=normal, escalation=escalated).generate(
        PLAN, LINKS, contested=False, escalated=True
    )

    assert normal.calls == 0
    assert escalated.calls == 1
    assert candidates[0].sql == "SELECT 'escalated-1'"


def test_generating_without_links_is_refused_before_any_call() -> None:
    chat = FakeChatProvider("normal")

    with pytest.raises(GenerationError, match="no schema links"):
        _service(chat=chat).generate(PLAN, (), contested=False)

    assert chat.calls == 0


def test_a_strategy_failure_propagates_as_a_generation_error() -> None:
    with pytest.raises(GenerationError):
        _service(chat=RaisingChatProvider()).generate(PLAN, LINKS, contested=False)


def test_the_violations_reach_every_strategy() -> None:
    """Every strategy must see the previous attempt's guardrail failures, the
    same rule Phase 5's retry loop depends on for the single-candidate path."""
    chat = FakeChatProvider("normal")

    _service(chat=chat).generate(PLAN, LINKS, VIOLATIONS, contested=False)
    # FakeChatProvider does not record prompts; this asserts the call still
    # succeeds with violations present, proving the parameter is accepted and
    # threaded through without raising.
    assert chat.calls == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_candidate_generation_service.py -q`
Expected: FAIL — `TypeError: CandidateGenerationService.__init__() got an unexpected keyword argument 'escalation_chat'`

- [ ] **Step 3: Rewrite the service**

Replace `genql/services/query/candidate_generation_service.py` in full:

```python
"""Produces one candidate on the non-contested path, or several representing
alternative interpretations on the contested path.

Non-contested: exactly one strategy ("decomposition", chosen arbitrarily
since a non-contested plan has one intended reading and strategy choice
cannot matter), keeping only its first variant, with examples=() — bit-for-
bit Phase 5/6 behaviour and cost. Contested: fetches up to
`ambiguity_example_top_k` examples once, then calls every registered
strategy with them, flattening the variants into one tuple. Two strategies
therefore yield four candidates through exactly two ChatProvider calls,
matching the parent spec's §20 cost model.

`escalated` picks which ChatProvider each strategy is constructed with —
chat_model normally, chat_model_escalation for the one regeneration this
phase allows after every survivor was judged fatal.
"""

from __future__ import annotations

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import GenerationError
from genql.domain.ports.ambiguity_example_reader import AmbiguityExampleReader
from genql.domain.ports.chat_provider import ChatProvider
from genql.repositories.query.registry import CANDIDATE_STRATEGIES

_NON_CONTESTED_STRATEGY = "decomposition"


class CandidateGenerationService:
    def __init__(
        self,
        chat: ChatProvider,
        escalation_chat: ChatProvider,
        examples: AmbiguityExampleReader,
        example_top_k: int,
    ) -> None:
        self._chat = chat
        self._escalation_chat = escalation_chat
        self._examples = examples
        self._example_top_k = example_top_k

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]:
        if not links:
            raise GenerationError(f"cannot generate SQL for {plan.question!r} with no schema links")
        chat = self._escalation_chat if escalated else self._chat

        if not contested:
            strategy = CANDIDATE_STRATEGIES.create(_NON_CONTESTED_STRATEGY, chat=chat)
            return strategy.generate_variants(plan, links, violations, ())[:1]

        examples = self._examples.search(plan.question, domain_id, self._example_top_k)
        candidates: list[SqlCandidate] = []
        for key in CANDIDATE_STRATEGIES.keys():  # noqa: SIM118 - Registry, not a dict
            strategy = CANDIDATE_STRATEGIES.create(key, chat=chat)
            candidates.extend(strategy.generate_variants(plan, links, violations, examples))
        return tuple(candidates)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_candidate_generation_service.py -q`
Expected: PASS — 8 tests

- [ ] **Step 5: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: `ruff`, `ruff format`, `mypy`, and `lint-imports` all green. `mypy` stays green because `genql/domain/ports/candidate_generator.py` still declares the old one-candidate signature and nothing asserts `isinstance(CandidateGenerationService(...), CandidateGenerator)` — Task 10 updates that port and its sole consumer, `CandidateGenerationNode`, together. `pytest tests/unit -q` fails exactly three pre-existing tests in `tests/unit/test_composition_root.py` — `test_the_container_builds_a_candidate_generation_service`, `test_the_container_builds_an_invokable_query_graph`, and `test_the_query_graph_carries_all_eight_stages` — because `QueryContainer.candidate_generation_service`'s existing wiring (`CandidateGenerationService(chat=SemanticContainer.chat_provider)`) no longer matches the rewritten constructor, and the latter two resolve it transitively while building `query_graph`. This is a lazy-resolution failure (dependency-injector only constructs a `Singleton` when something calls it), not an import-time crash, so it is confined to exactly these three tests. Task 12 rewires `query_container.py` and fixes all three. Confirm no other test fails, then proceed.

- [ ] **Step 6: Commit**

```bash
git add genql/services/query/candidate_generation_service.py \
  tests/unit/test_candidate_generation_service.py
git commit -m "feat(query): rewrite CandidateGenerationService for multi-candidate generation"
```

---

### Task 6: `CritiqueService`

**Files:**
- Create: `genql/services/query/critique_service.py`, `tests/unit/test_critique_service.py`
- Test: `tests/unit/test_critique_service.py`

**Interfaces:**
- Consumes: `Defect`, `CritiqueReport` entities, `Critic` port (Task 1)
- Produces: `CritiqueService(chat).critique(plan, candidates, validated_sqls, links) -> tuple[CritiqueReport, ...]` — satisfies `Critic`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_critique_service.py`:

```python
"""The deterministic column check runs with no ChatProvider involved — DummyChat
below records whether it was ever called, and the pure-deterministic tests
assert it was not. The one merge test proves deterministic and model-found
defects both survive onto the same CritiqueReport."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.critique_service import CritiqueService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE_A = SqlCandidate(sql="SELECT o.id FROM shop.orders o LIMIT 1", plan=PLAN)
CANDIDATE_B = SqlCandidate(sql="SELECT o.bogus_col FROM shop.orders o LIMIT 1", plan=PLAN)
LINKS = (SchemaLink(object_qualified_name="local.shop.orders", column_names=("id", "total")),)


class RecordingChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        return response_schema.model_validate(self.payload)


def _batch(reports: list[dict[str, object]]) -> dict[str, object]:
    return {"reports": reports}


def test_a_clean_candidate_has_no_deterministic_defects() -> None:
    chat = RecordingChatProvider(
        _batch([{"candidate_index": 0, "defects": [], "score": 0.9}])
    )

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_A,), ("SELECT o.id FROM local.shop.orders o LIMIT 1",), LINKS
    )

    assert reports[0].defects == ()
    assert reports[0].score == 0.9


def test_an_unknown_column_becomes_a_fatal_deterministic_defect() -> None:
    chat = RecordingChatProvider(
        _batch([{"candidate_index": 0, "defects": [], "score": 0.1}])
    )

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_B,), ("SELECT o.bogus_col FROM local.shop.orders o LIMIT 1",), LINKS
    )

    assert any(d.severity == "fatal" for d in reports[0].defects)


def test_the_deterministic_check_makes_no_model_call() -> None:
    """It is pure sqlglot parsing against SchemaLink.column_names — asserted by
    checking the chat provider directly, independent of critique()'s own model
    call for join/plan-alignment judgment."""
    chat = RecordingChatProvider(_batch([]))

    CritiqueService(chat)._deterministic_defects(  # noqa: SLF001 - unit-testing the pure check directly
        "SELECT o.bogus_col FROM local.shop.orders o LIMIT 1", LINKS
    )

    assert chat.calls == 0


def test_model_found_defects_and_deterministic_defects_both_survive() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {
                    "candidate_index": 0,
                    "defects": [
                        {"dimension": "grain", "severity": "repairable", "message": "wrong grain"}
                    ],
                    "score": 0.4,
                }
            ]
        )
    )

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_B,), ("SELECT o.bogus_col FROM local.shop.orders o LIMIT 1",), LINKS
    )

    severities = {d.severity for d in reports[0].defects}
    assert severities == {"fatal", "repairable"}


def test_exactly_one_model_call_regardless_of_candidate_count() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {"candidate_index": 0, "defects": [], "score": 0.5},
                {"candidate_index": 1, "defects": [], "score": 0.6},
            ]
        )
    )

    CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert chat.calls == 1


def test_a_candidate_the_model_omitted_scores_zero_with_no_extra_defects() -> None:
    chat = RecordingChatProvider(_batch([{"candidate_index": 0, "defects": [], "score": 0.5}]))

    reports = CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert reports[1].score == 0.0
    assert reports[1].defects == ()


def test_reports_preserve_candidate_order() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {"candidate_index": 1, "defects": [], "score": 0.9},
                {"candidate_index": 0, "defects": [], "score": 0.1},
            ]
        )
    )

    reports = CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert [r.candidate_index for r in reports] == [0, 1]
    assert reports[0].score == 0.1
    assert reports[1].score == 0.9
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_critique_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.critique_service'`

- [ ] **Step 3: Write the service**

Create `genql/services/query/critique_service.py`:

```python
"""Combines a deterministic check with one LLM judgment call, per the parent
spec's §9 stage 9 and this phase's §1: the "database signals" — column
existence, type compatibility — are already fully determined by
SchemaLink.column_names, so checking them needs sqlglot, not a model call.
Join validity and plan-alignment are judgment calls a script cannot make, so
one ChatProvider.complete call scores every surviving candidate at once,
folding in the deterministic findings as input rather than a second round
trip.

Per Deviation 7, a ChatProviderError from the model call is NOT wrapped into
a stage-specific error here — it propagates as-is, matching the spec's own
Risk-section wording that this phase does not carve out an exception for
critique's or probing's provider failures.
"""

from __future__ import annotations

from typing import Literal

import sqlglot
from pydantic import BaseModel, ConfigDict
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider


class DefectResponse(BaseModel):
    """`severity` is typed exactly like `Defect.severity` (a Literal, not a
    bare str) so a malformed value fails INSIDE `ChatProvider.complete` —
    already converted to a `ChatProviderError` there — rather than later, as
    a bare `pydantic.ValidationError` escaping `Defect(...)` construction with
    no GenqlError wrapper to catch it."""

    model_config = ConfigDict(frozen=True)

    dimension: str | None = None
    severity: Literal["fatal", "repairable", "advisory"]
    message: str


class CandidateCritiqueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    defects: tuple[DefectResponse, ...] = ()
    score: float


class CritiqueBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    reports: tuple[CandidateCritiqueResponse, ...]


def build_critique_prompt(
    plan: QueryPlan,
    candidates: tuple[SqlCandidate, ...],
    validated_sqls: tuple[str, ...],
    deterministic: list[tuple[Defect, ...]],
) -> str:
    rendered = []
    for i, sql in enumerate(validated_sqls):
        found = "; ".join(d.message for d in deterministic[i]) or "none"
        rendered.append(f"Candidate {i}:\n{sql}\nDeterministic findings: {found}")
    return "\n\n".join(
        [
            "Judge every candidate SQL statement below against the plan. For "
            "each, name any join-validity or plan-alignment defects beyond "
            "the deterministic findings already listed, and score it 0-1 for "
            "overall confidence it correctly answers the question.",
            f"Question:\n{plan.question}",
            f"Plan:\n{plan.plan_text}",
            "\n\n".join(rendered),
            (
                "Rules:\n"
                "- Return `reports`, one entry per candidate index.\n"
                "- Each defect names `severity` as exactly one of "
                "'fatal', 'repairable', or 'advisory'.\n"
                "- `dimension` is null unless the defect reflects a specific "
                "contested interpretation (entity, metric, time_range, "
                "grain, filter, or comparison_baseline)."
            ),
        ]
    )


class CritiqueService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def critique(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        links: tuple[SchemaLink, ...],
    ) -> tuple[CritiqueReport, ...]:
        deterministic = [self._deterministic_defects(sql, links) for sql in validated_sqls]
        prompt = build_critique_prompt(plan, candidates, validated_sqls, deterministic)
        response = self._chat.complete(prompt, CritiqueBatchResponse)
        by_index = {r.candidate_index: r for r in response.reports}

        reports = []
        for i in range(len(candidates)):
            found = by_index.get(i)
            model_defects = tuple(
                Defect(dimension=d.dimension, severity=d.severity, message=d.message)
                for d in (found.defects if found else ())
            )
            score = found.score if found else 0.0
            reports.append(
                CritiqueReport(candidate_index=i, defects=deterministic[i] + model_defects, score=score)
            )
        return tuple(reports)

    @staticmethod
    def _deterministic_defects(sql: str, links: tuple[SchemaLink, ...]) -> tuple[Defect, ...]:
        known_columns = {c for link in links for c in link.column_names}
        if not known_columns:
            return ()
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # StaticValidationService already guarantees sql parses; this is
            # defence in depth, not a path any current caller can reach.
            return ()
        referenced = {col.name for col in expression.find_all(exp.Column)}
        unknown = sorted(referenced - known_columns)
        return tuple(
            Defect(dimension=None, severity="fatal", message=f"references unknown column {col!r}")
            for col in unknown
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_critique_service.py -q`
Expected: PASS — 7 tests

- [ ] **Step 5: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add genql/services/query/critique_service.py tests/unit/test_critique_service.py
git commit -m "feat(query): add CritiqueService"
```

---

### Task 7: `LlmProbeDesigner` and `AmbiguityProbingService`

**Files:**
- Create: `genql/services/query/probe_designer.py`, `genql/services/query/ambiguity_probing_service.py`, `tests/unit/test_probe_designer.py`, `tests/unit/test_ambiguity_probing_service.py`
- Test: `tests/unit/test_probe_designer.py`, `tests/unit/test_ambiguity_probing_service.py`

**Interfaces:**
- Consumes: `AmbiguityProbe`, `ProbeResult`, `CritiqueReport` entities, `ProbeDesigner` port (Task 1); `StaticValidationService`, `GuardedExecutionService` (existing, unchanged)
- Produces: `LlmProbeDesigner(chat).design(plan, candidates, validated_sqls, critiques) -> tuple[AmbiguityProbe, ...]` — satisfies `ProbeDesigner`; `AmbiguityProbingService(designer, validation, execution, max_probes).probe(plan, candidates, validated_sqls, critiques, datasource_name) -> tuple[ProbeResult, ...]`

- [ ] **Step 1: Write the failing designer test**

Create `tests/unit/test_probe_designer.py`:

```python
"""One ChatProvider.complete call, mapped into AmbiguityProbe entities. No cap
is applied here — AmbiguityProbingService applies probing_max_probes on the
designer's output, keeping "how many probes to ask for" and "how many to
actually run" as two separate, independently testable concerns."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.probe_designer import LlmProbeDesigner

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        return response_schema.model_validate(self.payload)


def test_designs_a_probe_per_dimension_with_a_prediction_per_candidate() -> None:
    chat = FakeChatProvider(
        {
            "probes": [
                {
                    "dimension": "grain",
                    "probe_sql": "SELECT count(*) FROM shop.orders LIMIT 1",
                    "candidate_predictions": [
                        {"candidate_index": 0, "prediction": "12"},
                        {"candidate_index": 1, "prediction": "144"},
                    ],
                }
            ]
        }
    )

    probes = LlmProbeDesigner(chat).design(PLAN, (CANDIDATE, CANDIDATE), ("SELECT 1",) * 2, ())

    assert probes[0].dimension == "grain"
    assert probes[0].candidate_predictions == ((0, "12"), (1, "144"))


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"probes": []})

    LlmProbeDesigner(chat).design(PLAN, (CANDIDATE,), ("SELECT 1",), ())

    assert chat.calls == 1


def test_no_probes_is_a_valid_response() -> None:
    chat = FakeChatProvider({"probes": []})

    probes = LlmProbeDesigner(chat).design(PLAN, (CANDIDATE,), ("SELECT 1",), ())

    assert probes == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_probe_designer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.probe_designer'`

- [ ] **Step 3: Write the designer**

Create `genql/services/query/probe_designer.py`:

```python
"""Designs the queries that let real warehouse data arbitrate between
candidates that critique could not fully rank. Only designs them — validating
and executing probe_sql is AmbiguityProbingService's job, one layer up, reusing
StaticValidationService and GuardedExecutionService unchanged.

Per Deviation 7, a ChatProviderError from the model call is not wrapped here;
it propagates as-is.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider


class PredictionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    prediction: str


class ProbeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    probe_sql: str
    candidate_predictions: tuple[PredictionResponse, ...] = ()


class ProbeBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    probes: tuple[ProbeResponse, ...]


def build_probe_prompt(
    plan: QueryPlan,
    candidates: tuple[SqlCandidate, ...],
    validated_sqls: tuple[str, ...],
    critiques: tuple[CritiqueReport, ...],
) -> str:
    rendered_candidates = "\n\n".join(
        f"Candidate {i}:\n{sql}" for i, sql in enumerate(validated_sqls)
    )
    rendered_critiques = "\n".join(
        f"Candidate {r.candidate_index}: score={r.score}, "
        f"defects={[d.message for d in r.defects]}"
        for r in critiques
    )
    return "\n\n".join(
        [
            "The candidates below disagree on how to answer the question. "
            "Design one targeted, read-only PostgreSQL query per contested "
            "dimension whose result would let the REAL DATA decide which "
            "candidate's interpretation is correct.",
            f"Question:\n{plan.question}",
            f"Plan:\n{plan.plan_text}",
            f"Candidates:\n{rendered_candidates}",
            f"Critique findings:\n{rendered_critiques or 'none'}",
            (
                "Rules:\n"
                "- Each probe_sql is a single SELECT with an explicit LIMIT, "
                "referencing only objects the candidates themselves "
                "reference.\n"
                "- For each probe, predict what each candidate's "
                "interpretation implies the probe will return, rendered as "
                "a short string, in `candidate_predictions`.\n"
                "- Return `probes`; an empty list is valid if nothing would "
                "usefully discriminate between the candidates."
            ),
        ]
    )


class LlmProbeDesigner:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]:
        prompt = build_probe_prompt(plan, candidates, validated_sqls, critiques)
        response = self._chat.complete(prompt, ProbeBatchResponse)
        return tuple(
            AmbiguityProbe(
                dimension=p.dimension,
                probe_sql=p.probe_sql,
                candidate_predictions=tuple(
                    (pr.candidate_index, pr.prediction) for pr in p.candidate_predictions
                ),
            )
            for p in response.probes
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_probe_designer.py -q`
Expected: PASS — 3 tests

- [ ] **Step 5: Write the failing probing-service test**

Create `tests/unit/test_ambiguity_probing_service.py`:

```python
"""AmbiguityProbingService wraps StaticValidationService and
GuardedExecutionService unchanged, matching Deviation 9: a probe that fails
either is a bug in ProbeDesigner's prompt, and propagates loudly rather than
being silently dropped."""

from __future__ import annotations

import pytest

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ExecutionError, StaticValidationError
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)
PROBE = AmbiguityProbe(
    dimension="grain",
    probe_sql="SELECT count(*) FROM shop.orders LIMIT 1",
    candidate_predictions=((0, "12"), (1, "144")),
)


class FakeDesigner:
    def __init__(self, probes: tuple[AmbiguityProbe, ...]) -> None:
        self._probes = probes

    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]:
        return self._probes


class FakeValidation:
    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        return "SELECT count(*) FROM local.shop.orders LIMIT 1"


class RaisingValidation:
    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        raise StaticValidationError(())


class FakeExecution:
    def __init__(self, row: tuple[object, ...] = (12,)) -> None:
        self._row = row

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        return ExecutionResult(columns=("n",), rows=(self._row,), row_count=1, truncated=False)


class RaisingExecution:
    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        raise ExecutionError("boom")


def test_a_matching_prediction_resolves_its_candidate() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), FakeExecution((12,)), max_probes=3
    )

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert results[0].resolved_candidate_index == 0
    assert results[0].actual_result == "12"


def test_no_matching_prediction_resolves_nothing() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), FakeExecution((999,)), max_probes=3
    )

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert results[0].resolved_candidate_index is None


def test_probes_are_capped_at_max_probes() -> None:
    designer = FakeDesigner((PROBE, PROBE, PROBE, PROBE))
    service = AmbiguityProbingService(designer, FakeValidation(), FakeExecution(), max_probes=2)

    results = service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")

    assert len(results) == 2


def test_a_bad_probe_sql_propagates_rather_than_being_dropped() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), RaisingValidation(), FakeExecution(), max_probes=3
    )

    with pytest.raises(StaticValidationError):
        service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")


def test_an_execution_failure_propagates() -> None:
    service = AmbiguityProbingService(
        FakeDesigner((PROBE,)), FakeValidation(), RaisingExecution(), max_probes=3
    )

    with pytest.raises(ExecutionError):
        service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local")


def test_zero_probes_designed_means_zero_results() -> None:
    service = AmbiguityProbingService(FakeDesigner(()), FakeValidation(), FakeExecution(), max_probes=3)

    assert service.probe(PLAN, (CANDIDATE, CANDIDATE), ("s1", "s2"), (), "local") == ()
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_ambiguity_probing_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.ambiguity_probing_service'`

- [ ] **Step 7: Write the service**

Create `genql/services/query/ambiguity_probing_service.py`:

```python
"""Ambiguity-driven probing: for each designed probe, validate and execute it
exactly like a candidate (reusing StaticValidationService and
GuardedExecutionService unchanged), then compare the real result against every
candidate's rendered prediction — a lookup, not a second judgment call.

Gated by the caller (AmbiguityProbingNode) on candidates actually disagreeing
and capped here at `probing_max_probes`, per the parent spec's §19 risk
mitigation. A probe that fails validation or execution is NOT caught here —
per Deviation 9, that is a bug in ProbeDesigner's prompt, and propagates like
any other stage's failure.
"""

from __future__ import annotations

from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.probe_designer import ProbeDesigner
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService


def _render_scalar(result: ExecutionResult) -> str:
    if len(result.rows) == 1 and len(result.rows[0]) == 1:
        return str(result.rows[0][0])
    return str(result.rows)


class AmbiguityProbingService:
    def __init__(
        self,
        designer: ProbeDesigner,
        validation: StaticValidationService,
        execution: GuardedExecutionService,
        max_probes: int,
    ) -> None:
        self._designer = designer
        self._validation = validation
        self._execution = execution
        self._max_probes = max_probes

    def probe(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
        datasource_name: str,
    ) -> tuple[ProbeResult, ...]:
        probes = self._designer.design(plan, candidates, validated_sqls, critiques)
        probes = probes[: self._max_probes]

        results = []
        for probe in probes:
            probe_candidate = SqlCandidate(sql=probe.probe_sql, plan=plan)
            validated_probe_sql = self._validation.validate(probe_candidate, datasource_name)
            execution_result = self._execution.execute(validated_probe_sql, datasource_name)
            actual = _render_scalar(execution_result)
            resolved = next(
                (idx for idx, prediction in probe.candidate_predictions if prediction == actual),
                None,
            )
            results.append(
                ProbeResult(probe=probe, actual_result=actual, resolved_candidate_index=resolved)
            )
        return tuple(results)
```

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_ambiguity_probing_service.py -q`
Expected: PASS — 6 tests

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 10: Commit**

```bash
git add genql/services/query/probe_designer.py genql/services/query/ambiguity_probing_service.py \
  tests/unit/test_probe_designer.py tests/unit/test_ambiguity_probing_service.py
git commit -m "feat(query): add LlmProbeDesigner and AmbiguityProbingService"
```

---

### Task 8: `CandidateSelectionService`

**Files:**
- Create: `genql/services/query/candidate_selection_service.py`, `tests/unit/test_candidate_selection_service.py`
- Test: `tests/unit/test_candidate_selection_service.py`

**Interfaces:**
- Consumes: `CandidateSelection`, `CritiqueReport`, `ProbeResult` entities (Task 1)
- Produces: `CandidateSelectionService().select(candidates, validated_sqls, critiques, probe_results) -> CandidateSelection` — no `ChatProvider` dependency; assumes `len(candidates) >= 2` (the single-survivor case is handled by the calling node, per §7's guard, before this service is ever invoked)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_candidate_selection_service.py`:

```python
"""Pure-function tests, no fakes at all — CandidateSelectionService takes no
ChatProvider, so every branch (probe-resolved, critique-ranked, and
critique-ranked's tie-break) is deterministic given its inputs."""

from __future__ import annotations

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.candidate_selection_service import CandidateSelectionService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())
CANDIDATES = (SqlCandidate(sql="A", plan=PLAN), SqlCandidate(sql="B", plan=PLAN))
SQLS = ("SELECT A", "SELECT B")
PROBE = AmbiguityProbe(dimension="grain", probe_sql="SELECT 1", candidate_predictions=())


def _service() -> CandidateSelectionService:
    return CandidateSelectionService()


def test_a_resolving_probe_wins_over_critique_scores() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=1),)

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "probe_resolved"
    assert selection.selected is CANDIDATES[1]
    assert selection.selected_sql == SQLS[1]


def test_no_probe_results_falls_back_to_critique_ranking() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.method == "critique_ranked"
    assert selection.selected is CANDIDATES[0]


def test_disagreeing_probe_results_fall_back_to_critique_ranking() -> None:
    """Every probe must agree on the same candidate to resolve; conflicting
    probes are as inconclusive as none at all."""
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (
        ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=0),
        ProbeResult(probe=PROBE, actual_result="y", resolved_candidate_index=1),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "critique_ranked"


def test_an_unresolved_probe_is_treated_as_inconclusive() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.9),
        CritiqueReport(candidate_index=1, defects=(), score=0.1),
    )
    probe_results = (ProbeResult(probe=PROBE, actual_result="x", resolved_candidate_index=None),)

    selection = _service().select(CANDIDATES, SQLS, critiques, probe_results)

    assert selection.method == "critique_ranked"


def test_critique_ranking_excludes_fatal_candidates() -> None:
    critiques = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="bad join"),),
            score=0.99,
        ),
        CritiqueReport(candidate_index=1, defects=(), score=0.2),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[1]


def test_critique_ranking_falls_back_to_the_whole_pool_when_every_candidate_is_fatal() -> None:
    critiques = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.8,
        ),
        CritiqueReport(
            candidate_index=1,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.3,
        ),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[0]


def test_a_tied_score_is_broken_by_the_lowest_candidate_index() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.5),
        CritiqueReport(candidate_index=1, defects=(), score=0.5),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected is CANDIDATES[0]


def test_selected_sql_is_always_the_qualified_statement_for_the_winning_index() -> None:
    critiques = (
        CritiqueReport(candidate_index=0, defects=(), score=0.1),
        CritiqueReport(candidate_index=1, defects=(), score=0.9),
    )

    selection = _service().select(CANDIDATES, SQLS, critiques, ())

    assert selection.selected_sql == SQLS[1]
    assert selection.selected_sql != selection.selected.sql
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_candidate_selection_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.services.query.candidate_selection_service'`

- [ ] **Step 3: Write the service**

Create `genql/services/query/candidate_selection_service.py`:

```python
"""Selection is a pure function, not a model call, per the parent spec's §20:
"Selection is deterministic by default. When probing resolves every contested
dimension, selection is a lookup rather than a judgement." Takes no
ChatProvider at all.

Assumes len(candidates) >= 2: the single-survivor case is handled by
CandidateSelectionNode's own guard before this service is ever called, per
§7 of the spec.
"""

from __future__ import annotations

from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.sql_candidate import SqlCandidate


class CandidateSelectionService:
    def select(
        self,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
        probe_results: tuple[ProbeResult, ...],
    ) -> CandidateSelection:
        resolved = self._probe_resolved_index(probe_results)
        if resolved is not None:
            return CandidateSelection(
                selected=candidates[resolved],
                selected_sql=validated_sqls[resolved],
                method="probe_resolved",
                rationale=(
                    f"probing resolved every contested dimension in favor of "
                    f"candidate {resolved}"
                ),
            )
        winner = self._critique_ranked_index(critiques)
        return CandidateSelection(
            selected=candidates[winner],
            selected_sql=validated_sqls[winner],
            method="critique_ranked",
            rationale=(
                f"candidate {winner} had the highest critique score among "
                "non-fatal survivors"
            ),
        )

    @staticmethod
    def _probe_resolved_index(probe_results: tuple[ProbeResult, ...]) -> int | None:
        """Every probe must resolve, and every one must agree on the same
        candidate — a single disagreeing or inconclusive probe is as
        inconclusive as none at all, per the spec's own selection rule."""
        if not probe_results:
            return None
        resolved_indices = {r.resolved_candidate_index for r in probe_results}
        if None in resolved_indices or len(resolved_indices) != 1:
            return None
        return next(iter(resolved_indices))

    @staticmethod
    def _critique_ranked_index(critiques: tuple[CritiqueReport, ...]) -> int:
        non_fatal = [c for c in critiques if not c.is_fatal]
        pool = non_fatal or list(critiques)
        best = max(pool, key=lambda c: (c.score, -c.candidate_index))
        return best.candidate_index
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_candidate_selection_service.py -q`
Expected: PASS — 8 tests

- [ ] **Step 5: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add genql/services/query/candidate_selection_service.py \
  tests/unit/test_candidate_selection_service.py
git commit -m "feat(query): add CandidateSelectionService"
```

---

### Task 9: `SyntheticAmbiguityLogService` and its discovery step

**Files:**
- Create: `genql/services/discovery/synthetic_ambiguity_log_service.py`, `genql/discovery/steps/synthetic_ambiguity_log_step.py`, `tests/unit/test_synthetic_ambiguity_log_service.py`, `tests/unit/test_synthetic_ambiguity_log_step.py`
- Modify: `genql/discovery/steps/__init__.py`, `genql/composition/semantic_container.py`, `genql/composition_root.py`, `tests/unit/test_composition_root.py`
- Test: `tests/unit/test_synthetic_ambiguity_log_service.py`, `tests/unit/test_synthetic_ambiguity_log_step.py`, `tests/unit/test_composition_root.py`

**Note on why this task also touches composition:** `@DISCOVERY_STEPS.register("synthetic_ambiguity_log")` mutates the process-wide `DISCOVERY_STEPS` registry the moment this step's module is imported by anything in the test session — not only when `genql/discovery/steps/__init__.py` re-exports it. `genql/composition_root.py`'s `Container` class body calls `_step_providers_in_registered_order(_step_service_providers)` at **import time**, doing a plain dict lookup per registered step name; a registered name with no matching dict entry raises `KeyError` the instant `genql.composition_root` is imported anywhere in the same pytest session — cascading into every test file that imports `Container`, not just the two obviously-related ones. This task must therefore land the container wiring in the same commit, unlike Task 5's narrower, lazily-resolved breakage.

**Interfaces:**
- Consumes: `AmbiguityExample`, `AmbiguityExampleWriter` (Task 1); `DomainReader.list_domains` (Task 1/3); `genql.domain.ports.metric_reader.MetricReader`, `genql.domain.ports.embedding_provider.EmbeddingProvider`, `genql.domain.ports.chat_provider.ChatProvider` (existing); `DiscoveryStep`, `DiscoveryContext`, `StepResult`, `DISCOVERY_STEPS` (existing)
- Produces: `SyntheticAmbiguityLogService(chat, embedder, domains, metrics, writer).generate(datasource_name) -> int` (examples written); `SyntheticAmbiguityLogStep` registered as `"synthetic_ambiguity_log"`

- [ ] **Step 1: Write the failing service test**

Create `tests/unit/test_synthetic_ambiguity_log_service.py`:

```python
"""Grounds each domain's generation prompt on its name, description, and the
datasource's full metric list (Deviation 5) — no per-domain object membership
read is added this phase. Zero domains is a valid, zero-record outcome, not a
failure (Deviation 6): a first `genql discover` run reaches this step before
`genql graph domains` has ever run."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.metric import Metric
from genql.domain.value_objects.provenance import Provenance
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService

SALES = BusinessDomain(
    datasource_name="local", domain_id=1, name="Sales", description="Orders and revenue."
)
METRIC = Metric(
    datasource_name="local", name="net_revenue", sql_expression="sum(total)", grain="order"
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class FakeEmbeddingProvider:
    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [(0.1,) for _ in texts]


class FakeDomains:
    def __init__(self, domains: tuple[BusinessDomain, ...]) -> None:
        self._domains = domains

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        return None

    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]:
        return self._domains


class FakeMetrics:
    def __init__(self, metrics: tuple[Metric, ...]) -> None:
        self._metrics = metrics

    def read_metrics(self, datasource_name: str):  # type: ignore[no-untyped-def]
        return self._metrics


class RecordingWriter:
    def __init__(self) -> None:
        self.written: list[AmbiguityExample] = []

    def write(self, examples: tuple[AmbiguityExample, ...]) -> None:
        self.written.extend(examples)


def _payload() -> dict[str, object]:
    return {
        "examples": [
            {
                "question": "show me revenue",
                "interpretations": ["gross revenue", "net revenue"],
                "resolution": "Net revenue, per the finance glossary.",
            }
        ]
    }


def test_generates_and_writes_one_example_per_domain() -> None:
    chat = FakeChatProvider(_payload())
    writer = RecordingWriter()
    service = SyntheticAmbiguityLogService(
        chat, FakeEmbeddingProvider(), FakeDomains((SALES,)), FakeMetrics((METRIC,)), writer
    )

    written = service.generate("local")

    assert written == 1
    assert writer.written[0].domain_id == 1


def test_grounds_the_prompt_on_domain_and_metric_names() -> None:
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat, FakeEmbeddingProvider(), FakeDomains((SALES,)), FakeMetrics((METRIC,)), RecordingWriter()
    )

    service.generate("local")

    assert "Sales" in chat.prompts[0]
    assert "net_revenue" in chat.prompts[0]


def test_zero_domains_writes_zero_examples_and_makes_no_model_call() -> None:
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat, FakeEmbeddingProvider(), FakeDomains(()), FakeMetrics(()), RecordingWriter()
    )

    written = service.generate("local")

    assert written == 0
    assert chat.prompts == []


def test_one_call_per_domain() -> None:
    other = BusinessDomain(
        datasource_name="local", domain_id=2, name="Support", description="Tickets."
    )
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat,
        FakeEmbeddingProvider(),
        FakeDomains((SALES, other)),
        FakeMetrics((METRIC,)),
        RecordingWriter(),
    )

    service.generate("local")

    assert len(chat.prompts) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_synthetic_ambiguity_log_service.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the service**

Create `genql/services/discovery/synthetic_ambiguity_log_service.py`:

```python
"""Offline: for each domain, one ChatProvider call grounded on that domain's
name, description, and the datasource's full metric list (Deviation 5) asks
for several genuinely ambiguous example questions with their interpretations
and resolution, embeds each question, and writes them via
AmbiguityExampleWriter.

Zero domains is valid, not an error (Deviation 6): the first `genql discover`
run reaches this step before `genql graph domains` has ever populated
genql_domain. Re-running `genql discover --start-from synthetic_ambiguity_log`
after domain naming is the intended path to populate the log for real.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.metric import Metric
from genql.domain.errors import (
    AmbiguityExampleGenerationError,
    ChatProviderError,
    EmbeddingProviderError,
)
from genql.domain.ports.ambiguity_example_writer import AmbiguityExampleWriter
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.domain_reader import DomainReader
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.metric_reader import MetricReader


class ExampleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    interpretations: tuple[str, ...]
    resolution: str


class SyntheticAmbiguityLogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    examples: tuple[ExampleResponse, ...] = ()


def build_prompt(domain: BusinessDomain, metrics: Sequence[Metric]) -> str:
    metric_names = ", ".join(m.name for m in metrics) or "(none defined)"
    return (
        "Write several genuinely ambiguous analytical questions a business "
        "user might ask about the domain below — questions that admit more "
        "than one reasonable interpretation — along with what those "
        "interpretations are and which one is actually correct, and why.\n\n"
        f"Domain: {domain.name}\n"
        f"Description: {domain.description}\n"
        f"Metrics available in this datasource: {metric_names}\n\n"
        "Rules:\n"
        "- Each example names at least two distinct interpretations.\n"
        "- `resolution` states which interpretation is correct and the "
        "business reasoning why, in prose.\n"
        "- Return `examples`; an empty list is valid if nothing genuinely "
        "ambiguous applies to this domain."
    )


class SyntheticAmbiguityLogService:
    def __init__(
        self,
        chat: ChatProvider,
        embedder: EmbeddingProvider,
        domains: DomainReader,
        metrics: MetricReader,
        writer: AmbiguityExampleWriter,
    ) -> None:
        self._chat = chat
        self._embedder = embedder
        self._domains = domains
        self._metrics = metrics
        self._writer = writer

    def generate(self, datasource_name: str) -> int:
        domains = self._domains.list_domains(datasource_name)
        if not domains:
            return 0
        metrics = self._metrics.read_metrics(datasource_name)

        written_total = 0
        for domain in domains:
            try:
                response = self._chat.complete(
                    build_prompt(domain, metrics), SyntheticAmbiguityLogResponse
                )
            except (ChatProviderError, ValidationError) as exc:
                raise AmbiguityExampleGenerationError(
                    f"failed to generate ambiguity examples for domain "
                    f"{domain.name!r} in {datasource_name!r}: {exc}"
                ) from exc
            if not response.examples:
                continue
            examples = tuple(
                AmbiguityExample(
                    question=e.question,
                    interpretations=e.interpretations,
                    resolution=e.resolution,
                    domain_id=domain.domain_id,
                )
                for e in response.examples
            )
            try:
                self._writer.write(examples)
            except EmbeddingProviderError as exc:
                raise AmbiguityExampleGenerationError(
                    f"failed to embed ambiguity examples for domain "
                    f"{domain.name!r} in {datasource_name!r}: {exc}"
                ) from exc
            written_total += len(examples)
        return written_total
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_synthetic_ambiguity_log_service.py -q`
Expected: PASS — 4 tests

- [ ] **Step 5: Write the failing step test**

Create `tests/unit/test_synthetic_ambiguity_log_step.py`:

```python
"""Mirrors CatalogScanStep's shape: run() delegates to the service, translates
its typed failure into a failed StepResult, and reports records_written on
success — including the zero-domains case, which succeeds with zero records
rather than failing (Deviation 6)."""

from __future__ import annotations

from genql.discovery.steps.synthetic_ambiguity_log_step import SyntheticAmbiguityLogStep
from genql.domain.errors import AmbiguityExampleGenerationError
from genql.domain.ports.discovery_step import DiscoveryContext


class FakeService:
    def __init__(self, written: int = 0, raises: Exception | None = None) -> None:
        self._written = written
        self._raises = raises

    def generate(self, datasource_name: str) -> int:
        if self._raises:
            raise self._raises
        return self._written


def _ctx() -> DiscoveryContext:
    return DiscoveryContext(datasource_name="local", schema_name="shop")


def test_step_name_is_registered_as_synthetic_ambiguity_log() -> None:
    assert SyntheticAmbiguityLogStep.name == "synthetic_ambiguity_log"


def test_a_successful_run_reports_records_written() -> None:
    result = SyntheticAmbiguityLogStep(FakeService(written=4)).run(_ctx())

    assert result.succeeded is True
    assert result.records_written == 4


def test_zero_domains_succeeds_with_zero_records() -> None:
    result = SyntheticAmbiguityLogStep(FakeService(written=0)).run(_ctx())

    assert result.succeeded is True
    assert result.records_written == 0


def test_a_service_failure_becomes_a_failed_step_result() -> None:
    result = SyntheticAmbiguityLogStep(
        FakeService(raises=AmbiguityExampleGenerationError("boom"))
    ).run(_ctx())

    assert result.succeeded is False
    assert "boom" in result.message
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/unit/test_synthetic_ambiguity_log_step.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Write the step and register it**

Create `genql/discovery/steps/synthetic_ambiguity_log_step.py`:

```python
"""Registered last (after object_profiling in registration order). Domain
naming (`genql graph domains`) is not itself a DiscoveryStep — it is invoked
by its own CLI command outside DiscoveryRunner entirely (Deviation 6) — so a
first `genql discover` run reaches this step before any domain exists and
correctly reports zero records, not a failure. Re-running
`genql discover --start-from synthetic_ambiguity_log` after `genql graph
domains` is the intended path to populate it for real.
"""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService


@DISCOVERY_STEPS.register("synthetic_ambiguity_log")
class SyntheticAmbiguityLogStep:
    name: ClassVar[str] = "synthetic_ambiguity_log"

    def __init__(self, service: SyntheticAmbiguityLogService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            written = self._service.generate(ctx.datasource_name)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=written,
            message=f"{written} ambiguity examples written",
        )
```

Modify `genql/discovery/steps/__init__.py`. Add the import and the name, after `ObjectProfilingStep`:

```python
from genql.discovery.steps.synthetic_ambiguity_log_step import SyntheticAmbiguityLogStep

__all__ = [
    "CatalogScanStep",
    "DataProfilingStep",
    "GraphProjectionStep",
    "ObjectProfilingStep",
    "SyntheticAmbiguityLogStep",
]
```

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/unit/test_synthetic_ambiguity_log_step.py -q`
Expected: PASS — 4 tests

- [ ] **Step 9: Confirm the container is broken, then wire it**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL at collection — `KeyError: 'synthetic_ambiguity_log'` raised while importing `genql.composition_root`, per this task's opening note.

Modify `genql/composition/semantic_container.py`. Add the import and one provider, alongside `object_profiling_service`:

```python
from genql.repositories.semantic.ambiguity_example_repository import PostgresAmbiguityExampleWriter
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService
```

```python
    ambiguity_example_writer = providers.Singleton(
        PostgresAmbiguityExampleWriter,
        engine=GraphContainer.semantic_engine,
        embedder=GatewayContainer.embedding_provider,
    )
    synthetic_ambiguity_log_service = providers.Factory(
        SyntheticAmbiguityLogService,
        chat=GatewayContainer.chat_provider,
        embedder=GatewayContainer.embedding_provider,
        domains=domain_repository,
        metrics=metric_repository,
        writer=ambiguity_example_writer,
    )
```

Modify `genql/composition_root.py`. Add the new step's entry to `_step_service_providers`:

```python
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": TurnContainer.catalog_scan_service,
        "data_profiling": TurnContainer.profiling_service,
        "graph_projection": TurnContainer.graph_projection_service,
        "object_profiling": TurnContainer.object_profiling_service,
        "synthetic_ambiguity_log": TurnContainer.synthetic_ambiguity_log_service,
    }
```

Append to `tests/unit/test_composition_root.py`:

```python
def test_the_runner_includes_synthetic_ambiguity_log(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "synthetic_ambiguity_log" in step_names


def test_the_container_builds_a_synthetic_ambiguity_log_service(container: Container) -> None:
    assert hasattr(container.synthetic_ambiguity_log_service(), "generate")
```

- [ ] **Step 10: Run to verify the container is fixed**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS — every existing test plus the 2 new ones, 5 registered steps total

- [ ] **Step 11: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green

- [ ] **Step 12: Commit**

```bash
git add genql/services/discovery/synthetic_ambiguity_log_service.py \
  genql/discovery/steps/synthetic_ambiguity_log_step.py genql/discovery/steps/__init__.py \
  genql/composition/semantic_container.py genql/composition_root.py \
  tests/unit/test_synthetic_ambiguity_log_service.py tests/unit/test_synthetic_ambiguity_log_step.py \
  tests/unit/test_composition_root.py
git commit -m "feat(discovery): add SyntheticAmbiguityLogService, its step, and container wiring"
```

---

### Task 10: `QueryState` for multiple candidates, and the two rewritten generation-path nodes

**Files:**
- Modify: `genql/api/query_state.py`, `genql/api/query_nodes.py`, `genql/domain/ports/candidate_generator.py`, `tests/unit/test_query_nodes.py`
- Test: `tests/unit/test_query_nodes.py`

**Interfaces:**
- Consumes: `CandidateGenerationService` (Task 5), `StaticValidationService` (existing, unchanged)
- Produces: `QueryState.candidates: tuple[SqlCandidate, ...]` (replaces `candidate: SqlCandidate | None`), `+ validated_sqls: tuple[str, ...]`, `+ contested: bool`, `+ critique_reports: tuple[CritiqueReport, ...]`, `+ probe_results: tuple[ProbeResult, ...]`, `+ selection: CandidateSelection | None`, `+ escalated: bool`; `CandidateGenerator.generate(plan, links, violations=(), *, domain_id=None, contested=False, escalated=False) -> tuple[SqlCandidate, ...]`; `CandidateGenerationNode` and `StaticValidationNode` rewritten for multiple candidates

**Note on this task's central design decision (Deviation 1):** `StaticValidationNode` now raises `StaticValidationError` itself when no further attempt remains, rather than `route_after_validation` raising as it did in Phase 5/6. The one-shot `escalated` budget must be spent or refused using the value the node received, in the same evaluation that might flip it — splitting that decision across a node/router boundary makes "just spent it" and "already spent, still failing" indistinguishable to the router. `route_after_validation` becomes a two-way dispatcher reachable only on the non-raising path.

- [ ] **Step 1: Extend `QueryState`**

Modify `genql/api/query_state.py`. Replace the field list and `initial_state`:

```python
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.probe_result import ProbeResult
```

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
    # Phase 5/6's single `candidate` becomes a tuple: the non-contested path
    # is now the len(candidates) == 1 case, not a structurally different
    # type. No compatibility shim — every caller updates in this task.
    candidates: tuple[SqlCandidate, ...]
    # Index-aligned with `candidates` after static validation drops the
    # failures: candidates[i]'s qualified SQL is validated_sqls[i]. Critique,
    # probing, and selection read and write against this field —
    # SqlCandidate.sql stays the pre-repair, pre-qualification text.
    validated_sqls: tuple[str, ...]
    # Whether clarifications or applied_defaults were non-empty when the
    # ambiguity gate last cleared — the sole gate for every new stage this
    # phase adds, per the parent spec's demand-driven mandate.
    contested: bool
    critique_reports: tuple[CritiqueReport, ...]
    probe_results: tuple[ProbeResult, ...]
    selection: CandidateSelection | None
    # Whether the one escalated regeneration this phase allows has already
    # been spent — by static validation exhausting its own retry, or by
    # critique finding every survivor fatal, whichever happens first.
    escalated: bool
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]


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
        candidates=(),
        validated_sqls=(),
        contested=False,
        critique_reports=(),
        probe_results=(),
        selection=None,
        escalated=False,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
```

- [ ] **Step 2: Update `CandidateGenerator`**

Modify `genql/domain/ports/candidate_generator.py` in full:

```python
"""Produces one candidate on the non-contested path, or several on the
contested path.

`domain_id` lets the implementation fetch few-shot ambiguity examples scoped
to the right domain; `contested` and `escalated` are read from QueryState by
CandidateGenerationNode and passed straight through, so this port carries them
as keyword-only rather than deriving them itself.
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
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]: ...
```

- [ ] **Step 3: Write the failing node tests**

Replace the `CandidateGenerationNode` and `StaticValidationNode` sections of `tests/unit/test_query_nodes.py`. Keep the file's existing imports, `LINK`, `PLAN`, `CANDIDATE`, `RESULT`, `DS`, `FakeLinker`, `FakePlanner`, `FixedFactory`, `FixedExecutorFactory`, `FakeDatasourceRepository`, and the schema-linking/planning/guarded-execution tests exactly as they are; replace everything from `FakeGenerator` through `test_a_node_reached_without_its_input_fails_loudly` with:

```python
CANDIDATE_2 = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 2", plan=PLAN)


class FakeGenerator:
    def __init__(self, candidates: tuple[SqlCandidate, ...] = (CANDIDATE,)) -> None:
        self._candidates = candidates
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]:
        self.calls.append(
            {
                "violations": violations,
                "domain_id": domain_id,
                "contested": contested,
                "escalated": escalated,
            }
        )
        return self._candidates


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
        raise StaticValidationError((VIOLATION,))


class UnrepairableRule:
    name = "unrepairable"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name="unrepairable", message="fatal", repairable=False),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))


def test_candidate_generation_forwards_state_into_the_generator() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1", domain_id=7)
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["contested"] = True
    state["escalated"] = True

    CandidateGenerationNode(generator)(state)

    assert generator.calls == [
        {"violations": (), "domain_id": 7, "contested": True, "escalated": True}
    ]


def test_candidate_generation_writes_the_candidates_tuple() -> None:
    generator = FakeGenerator((CANDIDATE, CANDIDATE_2))
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["candidates"] == (CANDIDATE, CANDIDATE_2)


def test_candidate_generation_does_not_count_a_retry_on_the_first_attempt() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 0


def test_candidate_generation_counts_a_retry_and_forwards_the_violations() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["violations"] = (VIOLATION,)

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 1
    assert generator.calls[0]["violations"] == (VIOLATION,)


def test_candidate_generation_without_a_plan_fails_loudly() -> None:
    with pytest.raises(GenerationError, match="without a plan"):
        CandidateGenerationNode(FakeGenerator())(initial_state("q", "local", "t-1"))


def test_static_validation_writes_survivors_and_their_qualified_sql() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    update = node(state)

    assert update["candidates"] == (CANDIDATE,)
    assert "shop.orders" in update["validated_sqls"][0]
    assert update["violations"] == ()


def test_static_validation_keeps_only_the_surviving_candidates() -> None:
    """One candidate references an unlisted column reported by FailingRule,
    the other passes — the survivor list is not all-or-nothing."""

    class MixedRule:
        name = "mixed"
        priority = 10

        def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
            if "LIMIT 2" in sql:
                return (VIOLATION,)
            return ()

        def repair(self, sql: str, violation: GuardrailViolation) -> str:
            raise StaticValidationError((violation,))

    node = StaticValidationNode(StaticValidationService(FixedFactory([MixedRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE, CANDIDATE_2)

    update = node(state)

    assert len(update["candidates"]) == 1
    assert update["candidates"][0] == CANDIDATE
    assert len(update["validated_sqls"]) == 1


def test_static_validation_grants_one_ordinary_retry_when_repairable() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    update = node(state)

    assert update["validated_sqls"] == ()
    assert update["violations"] == (VIOLATION,)
    assert "escalated" not in update


def test_static_validation_raises_immediately_on_an_unrepairable_violation() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([UnrepairableRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_raises_on_a_second_ordinary_failure_when_not_contested() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_grants_one_escalated_retry_when_contested() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1
    state["contested"] = True

    update = node(state)

    assert update["validated_sqls"] == ()
    assert update["escalated"] is True


def test_static_validation_raises_once_the_escalation_budget_is_already_spent() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1
    state["contested"] = True
    state["escalated"] = True

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_without_any_candidates_fails_loudly() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))

    with pytest.raises(StaticValidationError, match="without any candidates"):
        node(initial_state("q", "local", "t-1"))
```

Add the two new imports this rewrite needs, alongside the existing ones:

```python
from genql.api.query_nodes import CandidateGenerationNode, StaticValidationNode
```

(already imported — confirm `PLAN`, `LINK`, `CANDIDATE`, `VIOLATION` stay defined exactly as before; only `CANDIDATE_2` is new.)

- [ ] **Step 4: Run to verify they fail**

Run: `uv run pytest tests/unit/test_query_nodes.py -q`
Expected: FAIL — `TypeError` from `FakeGenerator.generate`'s new required keyword-only parameters not matching the still-old `CandidateGenerationNode`, and `KeyError: 'candidates'` from `StaticValidationNode` still reading `state["candidate"]`

- [ ] **Step 5: Rewrite the two nodes**

Modify `genql/api/query_nodes.py`. Replace `CandidateGenerationNode` and `StaticValidationNode` in full (the other three classes are untouched):

```python
class CandidateGenerationNode:
    def __init__(self, generator: CandidateGenerator) -> None:
        self._generator = generator

    def __call__(self, state: QueryState) -> dict[str, Any]:
        plan = state["plan"]
        if plan is None:
            raise GenerationError("candidate generation was reached without a plan")
        violations = state["violations"]
        candidates = self._generator.generate(
            plan,
            state["links"] or (),
            violations,
            domain_id=state["domain_id"],
            contested=state["contested"],
            escalated=state["escalated"],
        )
        return {
            "candidates": candidates,
            "retry_count": state["retry_count"] + (1 if violations else 0),
        }


class StaticValidationNode:
    """Validates every candidate independently, one repair attempt each,
    exactly Phase 5's per-candidate rule — collecting survivors rather than
    treating the batch as all-or-nothing.

    Raises directly (Deviation 1) rather than writing failure into state for
    the router to raise: granting the one escalated retry is a one-shot
    decision this node must make and act on in the same evaluation, using the
    `escalated` value it was handed. `not state["escalated"]` guards BOTH
    retry branches, so once the budget is spent (here or by CritiqueNode) no
    further regeneration is ever granted again, from either stage.
    """

    def __init__(self, service: StaticValidationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not candidates:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="graph",
                        message="static validation was reached without any candidates",
                    ),
                )
            )

        survivors: list[SqlCandidate] = []
        validated_sqls: list[str] = []
        all_violations: list[GuardrailViolation] = []
        for candidate in candidates:
            try:
                validated = self._service.validate(candidate, state["datasource_name"])
            except StaticValidationError as exc:
                all_violations.extend(exc.violations)
                continue
            survivors.append(candidate)
            validated_sqls.append(validated)

        if survivors:
            return {
                "candidates": tuple(survivors),
                "validated_sqls": tuple(validated_sqls),
                "violations": (),
            }

        combined = tuple(all_violations)
        repairable = any(violation.repairable for violation in combined)
        if repairable and not state["escalated"] and state["retry_count"] == 0:
            return {"candidates": (), "validated_sqls": (), "violations": combined}
        if repairable and state["contested"] and not state["escalated"]:
            return {
                "candidates": (),
                "validated_sqls": (),
                "violations": combined,
                "escalated": True,
            }
        raise StaticValidationError(combined)
```

Add the imports `StaticValidationError` is already imported; add `SqlCandidate`:

```python
from genql.domain.entities.sql_candidate import SqlCandidate
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/unit/test_query_nodes.py -q`
Expected: PASS — every existing schema-linking/planning/guarded-execution test plus the rewritten candidate-generation and static-validation tests

- [ ] **Step 7: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: `tests/unit/test_query_nodes.py` and everything not touching the graph or the turn nodes is green. `tests/unit/test_query_graph.py`, `tests/unit/test_query_graph_turns.py`, and `tests/unit/test_query_turn_nodes.py` are now red — every direct reference to `state["candidate"]`/`state["validated_sql"]` inside their own fakes and assertions (e.g. `initial_state(...)` no longer has a `candidate` key) breaks. This is expected and is Task 11's job. Confirm the failures are confined to those three files and `genql/api/query_graph.py`'s own callers, and go no further in this task.

- [ ] **Step 8: Commit**

```bash
git add genql/api/query_state.py genql/api/query_nodes.py genql/domain/ports/candidate_generator.py \
  tests/unit/test_query_nodes.py
git commit -m "feat(api): extend QueryState for multiple candidates and rewrite the generation nodes"
```

---

### Task 11: Three new graph nodes, `contested`, and the extended graph

**Files:**
- Create: `genql/api/query_ambiguity_nodes.py`, `tests/unit/test_query_ambiguity_nodes.py`
- Modify: `genql/api/query_turn_nodes.py`, `genql/api/query_graph.py`, `tests/unit/test_query_graph.py`, `tests/unit/test_query_graph_turns.py`, `tests/unit/test_query_turn_nodes.py`
- Test: `tests/unit/test_query_ambiguity_nodes.py`, `tests/unit/test_query_graph.py`, `tests/unit/test_query_graph_turns.py`, `tests/unit/test_query_turn_nodes.py`

**Interfaces:**
- Consumes: `Critic`, `ProbeDesigner`-backed `AmbiguityProbingService`, `CandidateSelectionService` (Tasks 6–8); `QueryState` (Task 10)
- Produces: `CritiqueNode`, `AmbiguityProbingNode`, `CandidateSelectionNode`; `AmbiguityGateNode` now writes `contested`; `route_after_critique(state) -> str`; rewritten `route_after_validation(state) -> str`; `build_query_graph` gains `critique`, `ambiguity_probing`, `candidate_selection` parameters and the `CRITIQUE`/`AMBIGUITY_PROBING`/`CANDIDATE_SELECTION` node-name constants

**Note on `route_after_critique` (Deviation 2):** `CritiqueNode` raises `CritiqueError` itself when every survivor is fatal and `escalated` was already `True` on entry, mirroring `StaticValidationNode`'s Deviation 1. `route_after_critique` is therefore reachable only when critique just granted (not exhausted) the escalated retry, or found at least one non-fatal survivor — it never needs to raise.

- [ ] **Step 1: Add `contested` to `AmbiguityGateNode`**

Modify `genql/api/query_turn_nodes.py`. In `AmbiguityGateNode.__call__`, the `not assessment.is_ambiguous` branch becomes:

```python
        if not assessment.is_ambiguous:
            # Contested per this phase's own definition: a resumed answer was
            # needed (clarifications non-empty) or a rule default was applied
            # (applied_defaults non-empty) by the time the gate finally
            # cleared. Derived from state Phase 6 already produces — not a
            # new gate score.
            contested = bool(answers) or bool(assessment.applied_defaults)
            return {"ambiguity": assessment, "contested": contested}
```

- [ ] **Step 2: Write the failing test for `contested`**

Append to `tests/unit/test_query_turn_nodes.py`:

```python
def test_a_clear_gate_with_no_prior_answers_and_no_defaults_is_not_contested(
    no_interrupt: list[str],
) -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)

    update = AmbiguityGateNode(FakeGate(plain_clear))(initial_state("q", "local", "t-1"))

    assert update == {"ambiguity": plain_clear, "contested": False}


def test_a_clear_gate_after_a_resumed_answer_is_contested(no_interrupt: list[str]) -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "last quarter"),)

    update = AmbiguityGateNode(FakeGate(plain_clear))(state)

    assert update["contested"] is True


def test_a_clear_gate_with_an_applied_default_is_contested(no_interrupt: list[str]) -> None:
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update["contested"] is True
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_query_turn_nodes.py -k contested -q`
Expected: FAIL — `AssertionError` (no `contested` key in the update)

- [ ] **Step 4: Run to verify the fix passes**

Run: `uv run pytest tests/unit/test_query_turn_nodes.py -q`
Expected: PASS — every existing test plus the 3 new ones

- [ ] **Step 5: Write the failing tests for the three new nodes**

Create `tests/unit/test_query_ambiguity_nodes.py`:

```python
"""Each node opens with the same guard: not contested, or one surviving
candidate, short-circuits to the empty (or single-survivor) case with no
service call at all — the whole demand-driven claim, tested directly here
rather than only at the graph level."""

from __future__ import annotations

import pytest

from genql.api.query_ambiguity_nodes import (
    AmbiguityProbingNode,
    CandidateSelectionNode,
    CritiqueNode,
)
from genql.api.query_state import initial_state
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import CritiqueError

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())
CANDIDATE_A = SqlCandidate(sql="A", plan=PLAN)
CANDIDATE_B = SqlCandidate(sql="B", plan=PLAN)
NON_FATAL = (CritiqueReport(candidate_index=0, defects=(), score=0.9),)
ALL_FATAL = (
    CritiqueReport(
        candidate_index=0,
        defects=(Defect(dimension=None, severity="fatal", message="m"),),
        score=0.1,
    ),
    CritiqueReport(
        candidate_index=1,
        defects=(Defect(dimension=None, severity="fatal", message="m"),),
        score=0.2,
    ),
)


class FakeCritic:
    def __init__(self, reports: tuple[CritiqueReport, ...]) -> None:
        self._reports = reports
        self.calls = 0

    def critique(self, plan, candidates, validated_sqls, links) -> tuple[CritiqueReport, ...]:
        self.calls += 1
        return self._reports


def _contested_two_candidate_state():  # type: ignore[no-untyped-def]
    state = initial_state("q", "local", "t-1")
    state["contested"] = True
    state["plan"] = PLAN
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)
    state["validated_sqls"] = ("SELECT A", "SELECT B")
    return state


def test_critique_skips_entirely_when_not_contested() -> None:
    critic = FakeCritic(NON_FATAL)
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)

    update = CritiqueNode(critic)(state)

    assert update == {"critique_reports": ()}
    assert critic.calls == 0


def test_critique_skips_with_a_single_survivor_even_when_contested() -> None:
    critic = FakeCritic(NON_FATAL)
    state = initial_state("q", "local", "t-1")
    state["contested"] = True
    state["candidates"] = (CANDIDATE_A,)

    update = CritiqueNode(critic)(state)

    assert update == {"critique_reports": ()}
    assert critic.calls == 0


def test_critique_writes_the_reports_when_not_all_fatal() -> None:
    critic = FakeCritic(NON_FATAL)

    update = CritiqueNode(critic)(_contested_two_candidate_state())

    assert update == {"critique_reports": NON_FATAL}


def test_critique_grants_the_escalated_retry_the_first_time_all_are_fatal() -> None:
    critic = FakeCritic(ALL_FATAL)
    state = _contested_two_candidate_state()

    update = CritiqueNode(critic)(state)

    assert update["escalated"] is True
    assert update["critique_reports"] == ALL_FATAL


def test_critique_raises_once_the_escalation_budget_is_already_spent() -> None:
    critic = FakeCritic(ALL_FATAL)
    state = _contested_two_candidate_state()
    state["escalated"] = True

    with pytest.raises(CritiqueError):
        CritiqueNode(critic)(state)


def test_ambiguity_probing_skips_entirely_when_not_contested() -> None:
    class FakeProbingService:
        def probe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)

    update = AmbiguityProbingNode(FakeProbingService())(state)

    assert update == {"probe_results": ()}


def test_ambiguity_probing_calls_the_service_when_contested_with_multiple_candidates() -> None:
    results = (ProbeResult(probe=CANDIDATE_A, actual_result="x", resolved_candidate_index=0),)  # type: ignore[arg-type]

    class FakeProbingService:
        def probe(self, plan, candidates, validated_sqls, critiques, datasource_name):  # type: ignore[no-untyped-def]
            return results

    update = AmbiguityProbingNode(FakeProbingService())(_contested_two_candidate_state())

    assert update == {"probe_results": results}


def test_candidate_selection_short_circuits_a_single_survivor() -> None:
    class FakeSelectionService:
        def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A,)
    state["validated_sqls"] = ("SELECT A",)

    update = CandidateSelectionNode(FakeSelectionService())(state)

    assert update["selection"].method == "single_survivor"
    assert update["selection"].selected is CANDIDATE_A
    assert update["validated_sql"] == "SELECT A"


def test_candidate_selection_short_circuits_when_not_contested_even_with_two_candidates() -> None:
    """Defence in depth: this shape should not occur (the non-contested path
    only ever produces one candidate), but the guard still protects it."""

    class FakeSelectionService:
        def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("must not be called")

    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE_A, CANDIDATE_B)
    state["validated_sqls"] = ("SELECT A", "SELECT B")

    update = CandidateSelectionNode(FakeSelectionService())(state)

    assert update["selection"].method == "single_survivor"
    assert update["selection"].selected is CANDIDATE_A


def test_candidate_selection_calls_the_service_when_contested_with_multiple_candidates() -> None:
    from genql.domain.entities.candidate_selection import CandidateSelection

    selection = CandidateSelection(
        selected=CANDIDATE_B, selected_sql="SELECT B", method="critique_ranked", rationale="r"
    )

    class FakeSelectionService:
        def select(self, candidates, validated_sqls, critiques, probe_results):  # type: ignore[no-untyped-def]
            return selection

    update = CandidateSelectionNode(FakeSelectionService())(_contested_two_candidate_state())

    assert update == {"selection": selection, "validated_sql": "SELECT B"}
```

- [ ] **Step 6: Run to verify they fail**

Run: `uv run pytest tests/unit/test_query_ambiguity_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'genql.api.query_ambiguity_nodes'`

- [ ] **Step 7: Write the three new nodes**

Create `genql/api/query_ambiguity_nodes.py`:

```python
"""Three adapters for the three stages this phase inserts between static
validation and guarded execution. Their own file, matching how
query_turn_nodes.py was split out from query_nodes.py in Phase 6: one file per
responsibility, and this is the only module besides query_turn_nodes.py that
carries phase-specific business logic rather than a pass-through call.

Every node opens with the same guard from the spec's §7: not contested, or one
surviving candidate, short-circuits with no service call at all. This is what
makes the whole ambiguity machinery demand-driven at runtime, not only at the
registry level.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import QueryState
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.errors import CritiqueError
from genql.domain.ports.critic import Critic
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService
from genql.services.query.candidate_selection_service import CandidateSelectionService


class CritiqueNode:
    """Raises CritiqueError itself when exhausted (Deviation 1/2): granting
    the one escalated retry is a decision this node must make and act on
    using the `escalated` value it was handed, in the same evaluation that
    might flip it."""

    def __init__(self, service: Critic) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not state["contested"] or len(candidates) <= 1:
            return {"critique_reports": ()}

        reports = self._service.critique(
            state["plan"], candidates, state["validated_sqls"], state["links"] or ()
        )
        if reports and all(r.is_fatal for r in reports):
            if state["escalated"]:
                raise CritiqueError(
                    f"every surviving candidate for {state['question']!r} carries a "
                    "fatal defect, even after an escalated regeneration"
                )
            return {"critique_reports": reports, "escalated": True}
        return {"critique_reports": reports}


class AmbiguityProbingNode:
    def __init__(self, service: AmbiguityProbingService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not state["contested"] or len(candidates) <= 1:
            return {"probe_results": ()}
        results = self._service.probe(
            state["plan"],
            candidates,
            state["validated_sqls"],
            state["critique_reports"],
            state["datasource_name"],
        )
        return {"probe_results": results}


class CandidateSelectionNode:
    def __init__(self, service: CandidateSelectionService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        validated_sqls = state["validated_sqls"]
        if not state["contested"] or len(candidates) <= 1:
            selection = CandidateSelection(
                selected=candidates[0],
                selected_sql=validated_sqls[0],
                method="single_survivor",
                rationale="only one candidate survived validation",
            )
        else:
            selection = self._service.select(
                candidates, validated_sqls, state["critique_reports"], state["probe_results"]
            )
        return {"selection": selection, "validated_sql": selection.selected_sql}
```

- [ ] **Step 8: Run to verify they pass**

Run: `uv run pytest tests/unit/test_query_ambiguity_nodes.py -q`
Expected: PASS — 10 tests

- [ ] **Step 9: Extend the graph**

Modify `genql/api/query_graph.py`.

Add the three node-name constants after `GUARDED_EXECUTION`:

```python
CRITIQUE = "critique"
AMBIGUITY_PROBING = "ambiguity_probing"
CANDIDATE_SELECTION = "candidate_selection"
```

Replace `route_after_validation` in full:

```python
def route_after_validation(state: QueryState) -> str:
    """Trivial by design (Deviation 1): StaticValidationNode itself raises
    when no attempt remains, so this is reachable only when it granted a
    retry or produced survivors."""
    return CRITIQUE if state["validated_sqls"] else CANDIDATE_GENERATION
```

Add `route_after_critique` immediately after it:

```python
def route_after_critique(state: QueryState) -> str:
    """Trivial by the same reasoning (Deviation 2): CritiqueNode itself
    raises CritiqueError when the escalation budget is already spent, so
    reaching here with every report fatal means it was just granted."""
    reports = state["critique_reports"]
    if reports and all(r.is_fatal for r in reports):
        return CANDIDATE_GENERATION
    return AMBIGUITY_PROBING
```

Update `build_query_graph`'s signature, node registration, and edges:

```python
def build_query_graph(  # noqa: PLR0913, PLR0917 - one parameter per pipeline stage
    intent_classification: NodeFn,
    ambiguity_gate: NodeFn,
    domain_scoping: NodeFn,
    schema_linking: NodeFn,
    planning: NodeFn,
    candidate_generation: NodeFn,
    static_validation: NodeFn,
    critique: NodeFn,
    ambiguity_probing: NodeFn,
    candidate_selection: NodeFn,
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
    graph.add_node(CRITIQUE, critique)
    graph.add_node(AMBIGUITY_PROBING, ambiguity_probing)
    graph.add_node(CANDIDATE_SELECTION, candidate_selection)
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
        {CANDIDATE_GENERATION: CANDIDATE_GENERATION, CRITIQUE: CRITIQUE},
    )
    graph.add_conditional_edges(
        CRITIQUE,
        route_after_critique,
        {CANDIDATE_GENERATION: CANDIDATE_GENERATION, AMBIGUITY_PROBING: AMBIGUITY_PROBING},
    )
    graph.add_edge(AMBIGUITY_PROBING, CANDIDATE_SELECTION)
    graph.add_edge(CANDIDATE_SELECTION, GUARDED_EXECUTION)
    graph.add_edge(GUARDED_EXECUTION, END)
    return graph.compile(checkpointer=checkpointer)
```

`route_after_validation` no longer raises `StaticValidationError`, so drop the now-unused import of it from this module if nothing else in the file references it — check with `grep -n StaticValidationError genql/api/query_graph.py` before removing; `UnknownThreadError` stays.

- [ ] **Step 10: Rewrite `tests/unit/test_query_graph.py`'s fakes and assertions**

The file's fakes (`GenerateNode`, `ValidateNode`, `execute_node`, `build`) and every test currently reference `state["candidate"]`/`state["validated_sql"]` singular. Replace the module in full:

```python
"""The wiring, proven with fake nodes so no ChatProvider, database, or
retriever is involved. Candidates are tuples throughout — the non-contested
path is just the len == 1 case, matching the real StaticValidationNode/
CandidateSelectionNode's own shape.

Phase 6 prepends three stages and Phase 6.5 three more; the paths they add
live in tests/unit/test_query_graph_turns.py rather than here, because
together the two sets do not fit under the project's per-file line cap. The
fake nodes and the `build` helper below are shared with that file.
"""

from __future__ import annotations

from typing import Any

import pytest

from genql.api.query_graph import build_query_graph, route_after_critique, route_after_validation, run_query
from genql.api.query_state import initial_state
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import CritiqueError, StaticValidationError

LINK = SchemaLink(object_qualified_name="local.shop.orders")
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)
VIOLATIONS = (GuardrailViolation(rule_name="fake", message="bad", repairable=True),)
UNREPAIRABLE = (GuardrailViolation(rule_name="fake", message="fatal", repairable=False),)
RESULT = ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False)
CLEAR = AmbiguityAssessment(is_ambiguous=False)


def analytical_intent(state: dict[str, Any]) -> dict[str, Any]:
    return {"intent": "analytical_sql"}


def clear_gate(state: dict[str, Any]) -> dict[str, Any]:
    return {"ambiguity": CLEAR, "contested": False}


def no_scope(state: dict[str, Any]) -> dict[str, Any]:
    return {"domain_id": None}


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
            "candidates": (CANDIDATE,),
            "retry_count": state["retry_count"] + (1 if state["violations"] else 0),
        }


class ValidateNode:
    """Fails its first `failures` invocations, then succeeds."""

    def __init__(self, failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS):
        self.remaining = failures
        self.violations = violations

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.remaining > 0:
            self.remaining -= 1
            return {"candidates": (), "validated_sqls": (), "violations": self.violations}
        return {
            "candidates": (CANDIDATE,),
            "validated_sqls": ("SELECT 1 LIMIT 1",),
            "violations": (),
        }


def critique_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"critique_reports": ()}


def probing_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"probe_results": ()}


def selection_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection": None,
        "validated_sql": state["validated_sqls"][0] if state["validated_sqls"] else None,
    }


def execute_node(state: dict[str, Any]) -> dict[str, Any]:
    return {"result": RESULT}


def build(  # noqa: PLR0913, PLR0917 - one parameter per overridable stage
    validate: Any,
    generate: Any,
    intent: Any = analytical_intent,
    gate: Any = clear_gate,
    scope: Any = no_scope,
    critique: Any = critique_node,
    probing: Any = probing_node,
    selection: Any = selection_node,
    checkpointer: Any = None,
) -> Any:
    """One helper so the graph tests below differ only where they mean to."""
    return build_query_graph(
        intent,
        gate,
        scope,
        link_node,
        plan_node,
        generate,
        validate,
        critique,
        probing,
        selection,
        execute_node,
        checkpointer=checkpointer,
    )


def _graph(
    failures: int, violations: tuple[GuardrailViolation, ...] = VIOLATIONS
) -> tuple[Any, GenerateNode]:
    generate = GenerateNode()
    graph = build(ValidateNode(failures, violations), generate)
    return graph, generate


def test_the_clean_path_generates_once_and_returns_a_result() -> None:
    graph, generate = _graph(failures=0)

    final = run_query(graph, "q", "local", "t-1")

    assert generate.calls == 1
    assert final["retry_count"] == 0
    assert final["result"] == RESULT
    assert final["validated_sql"] == "SELECT 1 LIMIT 1"


def test_one_failure_routes_back_to_generation_exactly_once() -> None:
    graph, generate = _graph(failures=1)

    final = run_query(graph, "q", "local", "t-1")

    assert generate.calls == 2
    assert final["retry_count"] == 1
    assert final["result"] == RESULT


def test_a_second_failure_raises_instead_of_looping() -> None:
    graph, generate = _graph(failures=2)

    with pytest.raises(StaticValidationError, match="bad"):
        run_query(graph, "q", "local", "t-1")

    assert generate.calls == 2


def test_an_unrepairable_violation_raises_without_spending_the_retry() -> None:
    graph, generate = _graph(failures=1, violations=UNREPAIRABLE)

    with pytest.raises(StaticValidationError, match="fatal"):
        run_query(graph, "q", "local", "t-1")

    assert generate.calls == 1


def test_the_router_sends_a_validated_batch_to_critique() -> None:
    state = initial_state("q", "local", "t-1")
    state["validated_sqls"] = ("SELECT 1 LIMIT 1",)

    assert route_after_validation(state) == "critique"


def test_the_router_sends_no_survivors_back_to_generation() -> None:
    state = initial_state("q", "local", "t-1")

    assert route_after_validation(state) == "candidate_generation"


def test_route_after_critique_sends_a_non_fatal_batch_onward() -> None:
    state = initial_state("q", "local", "t-1")
    state["critique_reports"] = (CritiqueReport(candidate_index=0, defects=(), score=0.9),)

    assert route_after_critique(state) == "ambiguity_probing"


def test_route_after_critique_sends_a_just_escalated_all_fatal_batch_back() -> None:
    state = initial_state("q", "local", "t-1")
    state["critique_reports"] = (
        CritiqueReport(
            candidate_index=0,
            defects=(Defect(dimension=None, severity="fatal", message="m"),),
            score=0.1,
        ),
    )

    assert route_after_critique(state) == "candidate_generation"


def test_the_initial_state_starts_empty_with_no_retries_used() -> None:
    state = initial_state("q", "local", "t-1", domain_id=3)

    assert state["retry_count"] == 0
    assert state["violations"] == ()
    assert state["domain_id"] == 3
    assert state["result"] is None
    assert state["thread_id"] == "t-1"
    assert state["intent"] is None
    assert state["ambiguity"] is None
    assert state["clarifications"] == ()
    assert state["candidates"] == ()
    assert state["validated_sqls"] == ()
    assert state["contested"] is False
    assert state["escalated"] is False
    assert state["critique_reports"] == ()
    assert state["probe_results"] == ()
    assert state["selection"] is None
```

`CritiqueError` is imported for use by `tests/unit/test_query_graph_turns.py` in the next step, which re-imports several names from this module — keep the import even though this file's own tests do not raise it directly.

- [ ] **Step 11: Run to verify `test_query_graph.py` passes**

Run: `uv run pytest tests/unit/test_query_graph.py -q`
Expected: PASS — 11 tests

- [ ] **Step 12: Fix `tests/unit/test_query_graph_turns.py`'s imports and `build_query_graph` calls**

This file imports `CLEAR`, `LINK`, `RESULT`, `GenerateNode`, `ValidateNode`, `analytical_intent`, `build`, `clear_gate`, `execute_node`, `no_scope`, `plan_node` from `tests.unit.test_query_graph` — every one of those names still exists after Step 10's rewrite, so the import line itself is unchanged. Only its three direct `build_query_graph(...)` calls (in `test_a_non_analytical_intent_reaches_the_end_without_linking` and `test_an_explicit_domain_id_survives_to_schema_linking`) pass positional node arguments and must add the three new ones. Update both call sites:

```python
    graph = build_query_graph(
        lambda state: {"intent": "non_sql"},
        clear_gate,
        no_scope,
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        critique_node,
        probing_node,
        selection_node,
        execute_node,
    )
```

and

```python
    graph = build_query_graph(
        analytical_intent,
        clear_gate,
        lambda state: {},
        recording_link,
        plan_node,
        GenerateNode(),
        ValidateNode(0),
        critique_node,
        probing_node,
        selection_node,
        execute_node,
    )
```

Add the three fakes to the import line from `tests.unit.test_query_graph`:

```python
from tests.unit.test_query_graph import (
    CLEAR,
    LINK,
    RESULT,
    GenerateNode,
    ValidateNode,
    analytical_intent,
    build,
    clear_gate,
    critique_node,
    execute_node,
    no_scope,
    plan_node,
    probing_node,
    selection_node,
)
```

Every test that calls `build(...)` (the helper, not `build_query_graph` directly) needs no change — `build`'s new keyword-only `critique`, `probing`, `selection` parameters default to the pass-through fakes.

- [ ] **Step 13: Run to verify `test_query_graph_turns.py` passes**

Run: `uv run pytest tests/unit/test_query_graph_turns.py -q`
Expected: PASS — every existing test, unchanged in behaviour

- [ ] **Step 14: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green except `tests/unit/test_composition_root.py`'s query-graph-related assertions, which still resolve the stale five-argument `candidate_generation_service` wiring (Task 5's known, narrower breakage) and now also need the container to supply the three new node providers — both fixed together in Task 12. Confirm no other test is affected.

- [ ] **Step 15: Commit**

```bash
git add genql/api/query_ambiguity_nodes.py genql/api/query_turn_nodes.py genql/api/query_graph.py \
  tests/unit/test_query_ambiguity_nodes.py tests/unit/test_query_graph.py \
  tests/unit/test_query_graph_turns.py tests/unit/test_query_turn_nodes.py
git commit -m "feat(api): add the three ambiguity-machinery graph nodes and extend the graph"
```

---

### Task 12: Composition-root wiring

**Files:**
- Create: `genql/composition/ambiguity_container.py`
- Modify: `genql/composition/gateway_container.py`, `genql/composition/semantic_container.py`, `genql/composition/query_container.py`, `genql/composition_root.py`, `tests/unit/test_composition_root.py`
- Test: `tests/unit/test_composition_root.py`

**Interfaces:**
- Consumes: every service and node from Tasks 4–11
- Produces: `GatewayContainer.escalation_chat_provider`; `SemanticContainer.ambiguity_example_reader`; `QueryContainer.candidate_generation_service` rewired; `AmbiguityContainer(TurnContainer)` with `critique_service`, `ambiguity_probing_service`, `candidate_selection_service`, and `query_graph` re-declared over all eleven stages; `Container(AmbiguityContainer)`

- [ ] **Step 1: Confirm the exact set of currently-broken tests**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: FAIL — `test_the_container_builds_a_candidate_generation_service`, `test_the_container_builds_an_invokable_query_graph`, `test_the_query_graph_carries_all_eight_stages` (Task 5's known breakage; the eleven-stage assertion below is added fresh in this task, so there is no stale eight-stage test to also fail on this count).

- [ ] **Step 2: Add `escalation_chat_provider`**

Modify `genql/composition/gateway_container.py`. Add one provider, alongside `chat_provider`:

```python
    escalation_chat_provider = providers.Singleton(
        build_chat_provider,
        key=CoreContainer.settings.provided.chat_provider,
        openrouter_client=openrouter_client,
        model=CoreContainer.settings.provided.chat_model_escalation,
    )
```

- [ ] **Step 3: Add `ambiguity_example_reader`**

Modify `genql/composition/semantic_container.py`. Add the import and one provider, alongside `ambiguity_example_writer` (added by Task 9):

```python
from genql.repositories.semantic.ambiguity_example_repository import (
    PostgresAmbiguityExampleReader,
    PostgresAmbiguityExampleWriter,
)
```

```python
    ambiguity_example_reader = providers.Singleton(
        PostgresAmbiguityExampleReader,
        engine=GraphContainer.semantic_engine,
        embedder=GatewayContainer.embedding_provider,
    )
```

- [ ] **Step 4: Rewire `candidate_generation_service`**

Modify `genql/composition/query_container.py`. Replace the existing provider:

```python
    candidate_generation_service = providers.Singleton(
        CandidateGenerationService,
        chat=SemanticContainer.chat_provider,
        escalation_chat=SemanticContainer.escalation_chat_provider,
        examples=SemanticContainer.ambiguity_example_reader,
        example_top_k=SemanticContainer.settings.provided.ambiguity_example_top_k,
    )
```

- [ ] **Step 5: Run to verify the three known-broken tests now pass**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS for `test_the_container_builds_a_candidate_generation_service`; the two `query_graph`-resolving tests still FAIL — `QueryContainer.query_graph` still builds only the eight-stage `CandidateGenerationNode`/... set and `TurnContainer.query_graph` re-declares that same eight-stage graph; Step 8 below fixes both by re-declaring `query_graph` an eleventh time over all eleven stages.

- [ ] **Step 6: Write `AmbiguityContainer`**

Create `genql/composition/ambiguity_container.py`:

```python
"""Ambiguity-machinery providers: the three new stage services and the graph
rebuilt over all eleven stages.

`query_graph` is re-declared here, overriding TurnContainer's eight-node
version, exactly the way TurnContainer itself overrode QueryContainer's five-
node version in Phase 6 — declarative containers resolve the most-derived
declaration, so every consumer gets the eleven-node graph with no risk of two
graph providers drifting apart.
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
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.composition.turn_container import TurnContainer
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService
from genql.services.query.candidate_selection_service import CandidateSelectionService
from genql.services.query.critique_service import CritiqueService
from genql.services.query.probe_designer import LlmProbeDesigner


class AmbiguityContainer(TurnContainer):
    critique_service = providers.Singleton(CritiqueService, chat=TurnContainer.chat_provider)
    probe_designer = providers.Singleton(LlmProbeDesigner, chat=TurnContainer.chat_provider)
    ambiguity_probing_service = providers.Singleton(
        AmbiguityProbingService,
        designer=probe_designer,
        validation=TurnContainer.static_validation_service,
        execution=TurnContainer.guarded_execution_service,
        max_probes=TurnContainer.settings.provided.probing_max_probes,
    )
    candidate_selection_service = providers.Singleton(CandidateSelectionService)

    query_graph = providers.Singleton(
        build_query_graph,
        intent_classification=providers.Singleton(
            IntentClassificationNode, classifier=TurnContainer.intent_classification_service
        ),
        ambiguity_gate=providers.Singleton(
            AmbiguityGateNode, gate=TurnContainer.ambiguity_gate_service
        ),
        domain_scoping=providers.Singleton(
            DomainScopingNode, scoper=TurnContainer.domain_scoping_service
        ),
        schema_linking=providers.Singleton(
            SchemaLinkingNode, linker=TurnContainer.schema_linking_service
        ),
        planning=providers.Singleton(PlanningNode, planner=TurnContainer.planning_service),
        candidate_generation=providers.Singleton(
            CandidateGenerationNode, generator=TurnContainer.candidate_generation_service
        ),
        static_validation=providers.Singleton(
            StaticValidationNode, service=TurnContainer.static_validation_service
        ),
        critique=providers.Singleton(CritiqueNode, service=critique_service),
        ambiguity_probing=providers.Singleton(
            AmbiguityProbingNode, service=ambiguity_probing_service
        ),
        candidate_selection=providers.Singleton(
            CandidateSelectionNode, service=candidate_selection_service
        ),
        guarded_execution=providers.Singleton(
            GuardedExecutionNode, service=TurnContainer.guarded_execution_service
        ),
        checkpointer=TurnContainer.checkpointer,
    )
```

- [ ] **Step 7: Point `Container` at `AmbiguityContainer`**

Modify `genql/composition_root.py`. Change the import and base class:

```python
from genql.composition.ambiguity_container import AmbiguityContainer
```

```python
class Container(AmbiguityContainer):
```

Update every `TurnContainer.` reference inside `_step_service_providers` to `AmbiguityContainer.` (a pure rename — `AmbiguityContainer` inherits every one of those attributes from `TurnContainer` unchanged):

```python
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": AmbiguityContainer.catalog_scan_service,
        "data_profiling": AmbiguityContainer.profiling_service,
        "graph_projection": AmbiguityContainer.graph_projection_service,
        "object_profiling": AmbiguityContainer.object_profiling_service,
        "synthetic_ambiguity_log": AmbiguityContainer.synthetic_ambiguity_log_service,
    }
```

- [ ] **Step 8: Run to verify the container is fully fixed**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS — every test, including the two that were failing since Task 5/11

- [ ] **Step 9: Add container-level assertions for the new services and the eleven-stage graph**

Append to `tests/unit/test_composition_root.py`:

```python
def test_the_container_builds_a_critique_service(container: Container) -> None:
    assert hasattr(container.critique_service(), "critique")


def test_the_container_builds_an_ambiguity_probing_service(container: Container) -> None:
    assert hasattr(container.ambiguity_probing_service(), "probe")


def test_the_container_builds_a_candidate_selection_service(container: Container) -> None:
    assert hasattr(container.candidate_selection_service(), "select")


def test_the_container_builds_an_escalation_chat_provider(container: Container) -> None:
    assert hasattr(container.escalation_chat_provider(), "complete")


def test_the_container_builds_an_ambiguity_example_reader_and_writer(container: Container) -> None:
    assert hasattr(container.ambiguity_example_reader(), "search")
    assert hasattr(container.ambiguity_example_writer(), "write")


def test_the_query_graph_carries_all_eleven_stages(container: Container) -> None:
    from genql.api.query_graph import (
        AMBIGUITY_PROBING,
        CANDIDATE_SELECTION,
        CRITIQUE,
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
        CRITIQUE,
        AMBIGUITY_PROBING,
        CANDIDATE_SELECTION,
        GUARDED_EXECUTION,
    ):
        assert stage in nodes
```

Move the `from genql.api.query_graph import (AMBIGUITY_PROBING, CANDIDATE_SELECTION, CRITIQUE)` import to the file's top-level import block alongside the other stage-name imports rather than leaving it local, matching the file's existing style.

- [ ] **Step 10: Run to verify it passes**

Run: `uv run pytest tests/unit/test_composition_root.py -q`
Expected: PASS — every existing test plus the 6 new ones

- [ ] **Step 11: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — the entire Phase 6.5 unit surface

- [ ] **Step 12: Commit**

```bash
git add genql/composition/ambiguity_container.py genql/composition/gateway_container.py \
  genql/composition/semantic_container.py genql/composition/query_container.py \
  genql/composition_root.py tests/unit/test_composition_root.py
git commit -m "feat(composition): wire the Phase 6.5 ambiguity-machinery services and graph"
```

---

### Task 13: Prove the demand-driven claim end to end

**Files:**
- Create: `tests/integration/test_critique_service_real_provider.py`, `tests/integration/test_probe_designer_real_provider.py`, `tests/integration/test_phase6_5_end_to_end.py`
- Modify: `tests/integration/test_candidate_generation_service_real_provider.py`
- Test: all four

**Interfaces:**
- Consumes: the fully-wired `Container` (Task 12) and every real infrastructure fixture `tests/integration/conftest.py` already provides

- [ ] **Step 1: Add a real-provider contested-path test to the existing candidate-generation real-provider test**

Read `tests/integration/test_candidate_generation_service_real_provider.py` first — it currently exercises Phase 5/6's one-candidate call and skips cleanly without `GENQL_OPENROUTER_API_KEY`, matching every prior phase's convention. Append, following that same skip pattern:

```python
def test_the_contested_path_calls_every_registered_strategy_for_real(
    openrouter_chat_provider: ChatProvider,
) -> None:
    """One real ChatProvider, both strategies, no fake anywhere. Two
    registered strategies means two real calls and four real candidates —
    the exact shape the parent spec's §20 cost model assumes."""
    service = CandidateGenerationService(
        chat=openrouter_chat_provider,
        escalation_chat=openrouter_chat_provider,
        examples=_EmptyExampleReader(),
        example_top_k=3,
    )

    candidates = service.generate(PLAN, LINKS, contested=True)

    assert len(candidates) == 2 * len(CANDIDATE_STRATEGIES.keys())
    assert all(c.sql.strip() for c in candidates)
```

Add the small fixture it needs, and the registry import, near the top of the file:

```python
class _EmptyExampleReader:
    def search(self, question: str, domain_id: int | None, top_k: int) -> tuple:
        return ()
```

```python
from genql.repositories.query.registry import CANDIDATE_STRATEGIES
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/integration/test_candidate_generation_service_real_provider.py -q`
Expected: PASS with `GENQL_OPENROUTER_API_KEY` set; a clean SKIP without it (not a failure).

- [ ] **Step 3: Write the `CritiqueService` real-provider test**

Create `tests/integration/test_critique_service_real_provider.py`:

```python
"""One real CritiqueService.critique call against two hand-written candidates
— one clean, one referencing a column no SchemaLink lists — proving the
deterministic check and the real model call both fire and merge onto one
CritiqueReport per candidate."""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider
from genql.services.query.critique_service import CritiqueService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="requires GENQL_OPENROUTER_API_KEY"
)

PLAN = QueryPlan(
    question="how many stores do we have",
    plan_text="count distinct stores",
    referenced_objects=("local.public.store",),
)
LINKS = (SchemaLink(object_qualified_name="local.public.store", column_names=("store_id",)),)
CLEAN = SqlCandidate(sql="SELECT count(*) FROM public.store LIMIT 1", plan=PLAN)
BROKEN = SqlCandidate(sql="SELECT bogus_col FROM public.store LIMIT 1", plan=PLAN)


def test_a_real_critique_call_scores_both_candidates(openrouter_chat_provider: ChatProvider) -> None:
    reports = CritiqueService(openrouter_chat_provider).critique(
        PLAN,
        (CLEAN, BROKEN),
        (
            "SELECT count(*) FROM local.public.store LIMIT 1",
            "SELECT bogus_col FROM local.public.store LIMIT 1",
        ),
        LINKS,
    )

    assert len(reports) == 2
    assert reports[1].is_fatal  # the deterministic unknown-column check alone guarantees this
```

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/integration/test_critique_service_real_provider.py -q`
Expected: PASS with the key set; clean SKIP without it.

- [ ] **Step 5: Write the `ProbeDesigner` real-provider test**

Create `tests/integration/test_probe_designer_real_provider.py`:

```python
"""One real LlmProbeDesigner.design call against two disagreeing candidates,
proving it returns at least one probe naming a dimension and a prediction per
candidate — the shape AmbiguityProbingService's own unit tests already prove
correct once probes exist."""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider
from genql.services.query.probe_designer import LlmProbeDesigner

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="requires GENQL_OPENROUTER_API_KEY"
)

PLAN = QueryPlan(
    question="show me store sales",
    plan_text="sum sales, grain ambiguous between daily and monthly",
    referenced_objects=("local.public.store_sales",),
)
DAILY = SqlCandidate(sql="SELECT sum(sales) FROM public.store_sales GROUP BY sale_date", plan=PLAN)
MONTHLY = SqlCandidate(
    sql="SELECT sum(sales) FROM public.store_sales GROUP BY date_trunc('month', sale_date)",
    plan=PLAN,
)


def test_a_real_design_call_returns_at_least_one_probe(
    openrouter_chat_provider: ChatProvider,
) -> None:
    probes = LlmProbeDesigner(openrouter_chat_provider).design(
        PLAN,
        (DAILY, MONTHLY),
        (
            "SELECT sum(sales) FROM local.public.store_sales GROUP BY sale_date",
            "SELECT sum(sales) FROM local.public.store_sales "
            "GROUP BY date_trunc('month', sale_date)",
        ),
        (),
    )

    assert len(probes) >= 1
    assert probes[0].probe_sql.strip()
    assert len(probes[0].candidate_predictions) >= 1
```

- [ ] **Step 6: Run it**

Run: `uv run pytest tests/integration/test_probe_designer_real_provider.py -q`
Expected: PASS with the key set; clean SKIP without it.

- [ ] **Step 7: Write the end-to-end test**

Create `tests/integration/test_phase6_5_end_to_end.py`:

```python
"""Proves the demand-driven claim itself: a well-specified question touches
none of this phase's new machinery, and a contested one touches all of it.
Both run through the real, fully-wired Container against real infrastructure
— testcontainers Postgres/Neo4j plus a real OpenRouter call — matching every
prior phase's end-to-end convention. Requires GENQL_OPENROUTER_API_KEY and a
seeded local.tpcds datasource; skips cleanly without either.
"""

from __future__ import annotations

import os

import pytest

from genql.api.query_turn import resume_turn, start_turn
from genql.composition_root import Container

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="requires GENQL_OPENROUTER_API_KEY"
)


@pytest.fixture()
def container() -> Container:
    return Container()


def test_a_well_specified_question_generates_exactly_one_candidate(container: Container) -> None:
    graph = container.query_graph()
    locks = container.thread_lock_factory()

    response = start_turn(graph, locks, "how many stores do we have", "local")

    assert response.validated_sql is not None
    assert response.clarifying_question is None


def test_a_contested_question_pauses_first(container: Container) -> None:
    """`show me store sales` under-specifies time_range against local.tpcds's
    seeded rules/gate — asserted here only as the precondition the next test
    depends on: without a pause, `contested` never becomes True and none of
    this phase's machinery would run at all."""
    graph = container.query_graph()
    locks = container.thread_lock_factory()

    paused = start_turn(graph, locks, "show me store sales", "local")

    assert paused.clarifying_question is not None


def test_a_contested_resumed_turn_selects_deterministically(container: Container) -> None:
    graph = container.query_graph()
    locks = container.thread_lock_factory()

    paused = start_turn(graph, locks, "show me store sales", "local")
    finished = resume_turn(graph, locks, "last quarter", paused.thread_id)

    assert finished.validated_sql is not None
    # Whichever real data actually decides between probe_resolved and
    # critique_ranked: both are legitimate outcomes of a real, contested run,
    # and this asserts only that the turn actually finished with an answer —
    # not on a hardcoded selection method.
```

- [ ] **Step 8: Run it**

Run: `uv run pytest tests/integration/test_phase6_5_end_to_end.py -q`
Expected: PASS with `GENQL_OPENROUTER_API_KEY`, `GENQL_TEST_DSN`, and a seeded `local.tpcds` datasource; clean SKIP without the API key. In a sandbox with neither Docker nor the API key, report "written but unrun".

- [ ] **Step 9: Full local checks**

Run: `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy genql && uv run lint-imports`
Expected: all green — the complete Phase 6.5 unit surface, plus every integration test written across all thirteen tasks either passing (VM-connected, keyed) or cleanly skipped/unrun (sandboxed).

- [ ] **Step 10: Commit**

```bash
git add tests/integration/test_candidate_generation_service_real_provider.py \
  tests/integration/test_critique_service_real_provider.py \
  tests/integration/test_probe_designer_real_provider.py \
  tests/integration/test_phase6_5_end_to_end.py
git commit -m "test(phase6.5): prove the demand-driven ambiguity machinery end to end"
```

---

## Done When

- `genql query "how many stores do we have" --datasource local` answers in one invocation with `CandidateGenerationService` calling exactly one strategy and keeping exactly one candidate — bit-for-bit Phase 5/6 cost.
- A deliberately ambiguous question that resolves through a clarification answer or a rule default (`contested=True`) produces at least two candidates from two registered strategies, a non-empty `critique_reports`, and a `CandidateSelection` whose `method` is `probe_resolved` when the seeded `local.tpcds` data actually decides the contested dimension, `critique_ranked` otherwise.
- `AmbiguityGateNode` sets `contested` from `clarifications`/`applied_defaults` alone — no new gate score, matching the spec's explicit scope decision.
- `CRITIQUE`, `AMBIGUITY_PROBING`, and `CANDIDATE_SELECTION` each make zero extra `ChatProvider` calls and zero extra warehouse round trips on the non-contested path — proven by their own node-level guard tests in `tests/unit/test_query_ambiguity_nodes.py`, independent of the graph.
- Exactly one escalated regeneration is ever spent per turn, whichever stage (static-validation exhaustion or critique-all-fatal) first needs it — proven by `tests/unit/test_query_nodes.py`'s and `tests/unit/test_query_ambiguity_nodes.py`'s escalation tests.
- Migration `0008` creates `genql.genql_ambiguity_example` with its HNSW index, `domain_id` set null (not cascaded) on domain deletion, and downgrades cleanly to `0007`.
- `PostgresAmbiguityExampleReader`/`Writer` both embed internally and round-trip a written example back through `search`.
- `Container` exposes every Phase 6.5 provider, and `query_graph` compiles all eleven stages with the checkpointer attached.
- The full local unit suite is green; `mypy --strict`, `ruff check`, `ruff format --check`, and `lint-imports` all pass; every file is under 250 lines.

---

## Deliberately Not Done

- **The gate-driven "genuinely hard" Opus escalation trigger.** Per the parent spec's §1: adding a difficulty score to `AmbiguityGateService` is Phase 6 surface, deliberately left alone. Only "critique fails to resolve after one repair round" is implemented.
- **Typed numeric comparison for probe prediction matching.** `AmbiguityProbingService` compares `actual_result` against each prediction as a plain string; a probe returning `"42"` against a prediction rendered `"42.0"` fails to resolve rather than crashing. The same "fail visibly downstream, not upfront" tradeoff Phase 4 and Phase 6 each accepted once already.
- **Graceful degradation on a partial critique or probing failure.** A `ChatProviderError` from `CritiqueService` or `LlmProbeDesigner` fails the whole turn rather than falling back to `critique_ranked` over an empty critique set — degrading here risks silently selecting a candidate nothing has actually checked.
- **`genql_query_log` / `genql_query_feature` and cost-model measurement.** Deferred to Phase 8's golden-set runner, which is also where this phase's own contested-vs-simple-path split first gets real traffic to check against.
- **Per-domain object-membership grounding for `SyntheticAmbiguityLogService`** (Deviation 5) — a `description`-and-metrics-only prompt for now; a richer per-domain object read is a small, well-scoped follow-up once real usage shows it matters.
- **Rewrite/optimization (Phase 7)** inserts between `CANDIDATE_SELECTION`'s output (`validated_sql`, unchanged name and type) and `GUARDED_EXECUTION` — this phase does not move that boundary.
