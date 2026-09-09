# GenQL Phase 8 — API and Evaluation

## 1. Purpose

The parent spec's §18 gives this phase four deliverables: "FastAPI controllers, SSE streaming,
golden set runner, ablation harness." Two of them expose the engine (an HTTP surface, and per-stage
streaming so a caller watches a turn progress rather than waiting on one blocking call), and two of
them measure it. §15 is blunt about why the measuring half exists: the ablation harness "is the only
mechanism that demonstrates whether the semantic store earns its latency, which is the system's
entire thesis." Every phase up to now has asserted that enrichment helps. This is the phase that can
be wrong about it.

It also closes §9's stage 14 — "answer, the SQL, the NL plan, the applied defaults, provenance for
every semantic element used ... and a feedback handle" — which no earlier phase had a transport to
deliver.

**Scope, decided explicitly:**

- **Nothing becomes async.** Every service, repository, and driver in this codebase is synchronous,
  and FastAPI serves synchronous `def` endpoints on a threadpool without complaint. The one endpoint
  that genuinely streams bridges a synchronous generator into the event loop with Starlette's
  `iterate_in_threadpool`. Converting the pipeline to `async def` would touch SQLAlchemy, psycopg,
  httpx, neo4j, and langgraph invocation in every layer, for no benefit on the single-user
  development machine §20's cost model describes. The blocking call is the model provider, and it
  blocks a worker thread rather than the loop either way.
- **The golden set's expected result is a reference SQL statement, executed at evaluation time — not
  literal rows stored in YAML.** §15 requires comparing "execution results with order-insensitive set
  equality, never SQL string matching," and this satisfies that literally: two result sets are
  compared and the generated statement's text is never inspected. Storing thirty to fifty TPC-DS
  result sets as inline YAML would be unmaintainable, would rot the first time the seed data is
  regenerated, and would make a fixture unreviewable. A reference statement is reviewable in one
  screen. The cost is that a wrong reference produces a wrong verdict — which is why the runner
  prints both statements on a mismatch.
- **Both sides of a comparison run through `GuardedExecutionService`, so a case whose reference
  result is truncated is a fixture error, not a failure.** The row cap applies to the reference and
  the generated statement alike, and truncation is order-dependent, so two truncated result sets are
  not comparable even when the underlying queries agree. `GoldenEvaluationService` fails such a case
  with the reason "reference result exceeds the row cap — narrow the fixture," which is an
  instruction to the fixture author rather than a verdict about the pipeline.
- **Ablation works by disabling a layer at the composition root, never by branching inside a
  service.** No service acquires an `if ablated`. A service under ablation runs its normal code
  against an empty or absent upstream, which is what makes the measurement mean what it claims to
  mean. Four of the five ablations are pure settings overrides applied when the container is built;
  one is not, and that asymmetry is real rather than hidden — see the next bullet.
- **`no_descriptions` requires recompiling `genql_search_document`, because that is where
  descriptions actually live at query time.** Enrichment text does not reach the online path through
  a query-time read — `SchemaLinkingService` reads structural columns, join paths, and metrics, and
  never touches `EnrichmentReader`. Descriptions influence a turn only through the BM25 text and the
  embedding that `SearchDocumentCompiler` assembles offline. Ablating them therefore means compiling
  documents from structural fields alone, running the golden set, and recompiling normally
  afterwards. A null adapter at query time would ablate nothing and would report a reassuring
  "no delta" that meant only that the wrong thing had been switched off.
- **The "no query log" ablation is out of scope, and the harness says so rather than reporting a
  meaningless zero.** Query-log mining is offline step 10 in §3's pipeline and is not implemented:
  there is no `query_log_mining` discovery step, no `genql_query_log` table, and nothing downstream
  reads one. An ablation disabling a layer that was never enabled would report no delta and be
  misread as evidence that query logs do not help. The registry omits it; the report names it as an
  un-measured layer.
- **Feedback is captured, not retrieved.** §9's stage 14 promises "a feedback handle," and §2's
  fourth source warns that feedback living outside the database becomes an ungoverned shadow data
  repository — so the handle writes to GenQL's own Postgres. But §2's "feedback vector index in which
  corrected SQL is retrieved by similarity as a hint" is *not* built here: nothing in the generation
  path would consume it, and a retrieval index with no reader is speculative infrastructure. The
  table carries the corrected SQL so a later phase can index it without re-collecting anything.
- **Provenance is assembled from state the pipeline already produces.** The turn already holds the
  plan, the applied defaults, the schema links retrieval returned, the candidate count, the probe
  outcomes, the selection method and rationale, and (after Phase 7) the rewrite rules applied. The
  response DTO surfaces those. No stage gains a provenance-recording side channel.

**What this phase does not touch:** the offline discovery pipeline's behaviour, the ambiguity
machinery's behaviour (Phase 6.5, only observed here), the optimizer's behaviour (Phase 7, only
observed and reported here), and the React frontend (Phase 9).

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/golden_case.py
class GoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    datasource_name: str
    reference_sql: str          # executed to produce the expected result set
    failure_class: str          # one of §2's four: ambiguous_intent, absent_business_knowledge,
                                # physical_modelling_variation, context_sensitivity
    domain_id: int | None = None

# domain/entities/golden_outcome.py
class GoldenOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    failure_class: str          # copied from the case so a report groups without re-reading fixtures
    passed: bool
    generated_sql: str | None   # None when the turn produced no SQL at all
    failure_reason: str | None  # "paused for clarification", "result mismatch: ...", an error's text
    elapsed_ms: float

# domain/entities/golden_run_report.py
class GoldenRunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ablation_name: str          # "full" for an un-ablated run
    outcomes: tuple[GoldenOutcome, ...]

    @property
    def passed_count(self) -> int: ...
    @property
    def accuracy(self) -> float: ...                  # 0.0 on an empty report, never ZeroDivisionError
    def counts_for(self, failure_class: str) -> tuple[int, int]: ...   # (passed, total)

# domain/entities/ablation.py
class Ablation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    setting_overrides: tuple[tuple[str, bool], ...]   # Settings field name -> value
    # True only for no_descriptions: the layer lives in compiled search
    # documents, so switching it off means rebuilding them first.
    requires_recompile: bool = False

# domain/entities/feedback.py
class Feedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    rating: Literal["good", "bad"]
    corrected_sql: str | None = None
    comment: str | None = None

# domain/entities/stage_event.py
class StageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str                  # a node name from query_graph.py's constants
    status: Literal["completed", "paused", "failed"]
    detail: str | None = None   # one short human line; never the whole state
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/golden_set_reader.py
class GoldenSetReader(Protocol):
    """Reads hand-curated cases from `golden/*.yaml`. A port because file I/O
    is I/O: services never open a file, exactly as they never open a cursor."""
    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]: ...

# domain/ports/turn_runner.py
class TurnRunner(Protocol):
    """One turn, start to finish, with no clarification loop — what an
    evaluation run needs. GoldenEvaluationService depends on this rather than
    on `genql.api.query_turn`, because `services/` may not import `api/`."""
    def run(self, question: str, datasource_name: str, domain_id: int | None) -> TurnResponse: ...

# domain/ports/turn_runner_factory.py
class TurnRunnerFactory(Protocol):
    """Builds a TurnRunner over a container constructed with one ablation's
    setting overrides. The composition root implements it; AblationService
    holds it, and so never imports the composition root itself."""
    def for_ablation(self, ablation: Ablation) -> TurnRunner: ...

# domain/ports/search_document_recompiler.py
class SearchDocumentRecompiler(Protocol):
    """Rebuilds genql_search_document under one ablation's overrides. Only
    no_descriptions needs it; every other ablation leaves the store untouched."""
    def recompile(self, ablation: Ablation, datasource_name: str) -> int: ...

# domain/ports/feedback_writer.py
class FeedbackWriter(Protocol):
    def write(self, feedback: Feedback) -> None: ...

# domain/ports/report_writer.py
class ReportWriter(Protocol):
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None: ...
```

`TurnResponse` (`genql/domain/entities/turn_response.py`) gains the provenance fields §9's stage 14
names, each defaulting so no existing construction site breaks: `plan_text: str | None`,
`referenced_objects: tuple[str, ...]`, `selection_method: str | None`,
`selection_rationale: str | None`, `candidate_count: int`, `probe_count: int`, and
`rewrite_rules_applied: tuple[str, ...]` beside the `narrowing_suggestion` Phase 7 adds.

New errors (`genql/domain/errors.py`): `EvaluationError(GenqlError)`,
`GoldenSetError(EvaluationError)`, `UnknownAblationError(EvaluationError)`,
`FeedbackError(GenqlError)`.

---

## 3. Registries

**New: `ABLATIONS: Registry[Ablation]`**, in `genql/services/eval/registry.py` — beside
`genql/services/scope/registry.py`, which set the precedent that a registry of pure, I/O-free values
may live under `services/`. An `Ablation` carries no behaviour and touches nothing; it is a named set
of settings overrides.

`Registry[T]` stores classes, so each registration is a zero-argument class whose instance is the
`Ablation` value — the shape every other registry uses. Six initial registrations, one file each
under `genql/services/eval/ablations/`:

| Key | Disables | Override | Recompile |
|---|---|---|---|
| `full` | nothing — the baseline every other run is compared against | (none) | no |
| `no_descriptions` | LLM descriptions, aliases, and units in the compiled search text | `enrichment_enabled=False` | **yes** |
| `no_domains` | domain scoping before retrieval | `domain_scoping_enabled=False` | no |
| `no_join_paths` | mined join paths in schema linking | `join_paths_enabled=False` | no |
| `no_probing` | ambiguity probing; selection falls back to critique ranking | `probing_enabled=False` | no |
| `no_ambiguity_examples` | the offline synthetic few-shot examples | `ambiguity_examples_enabled=False` | no |

`no_ambiguity_examples` is one layer beyond §15's five; it is in the online path, costs one null
adapter, and Phase 6.5 built it on the explicit claim that it helps. Adding an ablation is one new
file plus one decorator — `AblationService` never names one.

---

## 4. Infrastructure

**Migration `0010_feedback.py`:**

```sql
CREATE TABLE genql_feedback (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    rating TEXT NOT NULL CHECK (rating IN ('good', 'bad')),
    corrected_sql TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX genql_feedback_thread_idx ON genql_feedback (thread_id);
```

`thread_id` carries no foreign key: langgraph's checkpoint tables are owned by `PostgresSaver`, not
by GenQL's migrations, and a constraint against a table another library creates and may reshape is a
liability. Feedback on an expired thread is still evidence worth keeping.

**`Settings` gains** (`genql/core/settings.py`):

```python
# Ablation switches. All True in normal operation; only the ablation harness
# sets one False, and it does so through Container overrides rather than the
# environment, so a stray .env entry cannot silently degrade a real turn.
enrichment_enabled: bool = True          # read by SearchDocumentCompiler, at compile time
domain_scoping_enabled: bool = True
join_paths_enabled: bool = True
probing_enabled: bool = True
ambiguity_examples_enabled: bool = True

api_host: str = "127.0.0.1"
api_port: int = 8000
golden_set_dir: str = "golden"           # where `genql eval` looks for *.yaml fixtures
```

**New dependencies:** `fastapi`, `uvicorn[standard]`, `sse-starlette`. `httpx` is already present, so
`fastapi.testclient.TestClient` needs nothing new. `fastapi`, `starlette`, and `sse_starlette` join
the forbidden lists of the `domain-is-pure` and `no-sql-in-services` contracts in `.importlinter`, so
the HTTP framework cannot leak below `genql/api/`.

**`Container.with_overrides`** (`genql/composition_root.py`): builds a `Container` whose `settings`
provider yields a `Settings` copy with the given fields replaced. This is the only mechanism the
ablation harness uses, and the only new composition-root capability this phase adds.

---

## 5. Repositories

```python
# repositories/eval/yaml_golden_set_repository.py
class YamlGoldenSetReader:  # GoldenSetReader
    """Reads every `*.yaml` under the configured directory. A malformed file
    raises GoldenSetError naming the file and the field: a silently skipped
    fixture makes an accuracy number quietly optimistic."""
    ...

# repositories/eval/json_report_repository.py
class JsonReportWriter:  # ReportWriter
    ...

# repositories/semantic/feedback_repository.py
class PostgresFeedbackWriter:  # FeedbackWriter, plain insert
    ...
```

**`SearchDocumentCompiler` gains a constructor flag** `include_enrichment: bool = True`. When false,
the assembled content omits the object description, the business alias, and each column's description
and unit, keeping the structural fields — object name, object type, domain name, column names, and
profiled sample values. Sample values stay because they come from data profiling, not from LLM
enrichment, and §15's "no descriptions" names the enrichment layer specifically. The flag lives on
the compiler rather than in the SQL, so the two `SELECT` statements are unchanged and the ablated
document is provably the same rows with less text.

**Null adapters** for the online ablations, under `genql/repositories/null/` — one file each:
`NullJoinPathReader` and `NullAmbiguityExampleReader`. Each satisfies its port and returns an empty
sequence. They live under `repositories/` rather than beside the services because they are port
implementations standing in for repositories, and the composition root swaps them in exactly where
the real repository would have gone. `no_domains` and `no_probing` need no null adapter: the
composition root binds a pass-through `DomainScopingNode` for the first (it returns `{}`, leaving
`domain_id` as the caller supplied it), and for the second an `AmbiguityProbingService` constructed
with `max_probes=0`, whose existing cap already yields no probe results.

---

## 6. Services

New, under `genql/services/eval/`:

- **`ResultComparator`** (`services/eval/result_comparator.py`) — pure, no ports, no I/O. Given the
  reference `ExecutionResult` and the generated one, returns `(bool, str | None)`. Columns are
  matched by name case-insensitively and reordered to the reference's order, because a generated
  statement may legitimately select in a different order. Rows are compared as multisets of tuples,
  so both ordering and duplicate counts are handled correctly. `Decimal`, `float`, and `int` are
  normalized before comparison, because a warehouse returns `Decimal` and a rewritten aggregate may
  return `float` for the same number. A column-set mismatch reports which columns differ rather than
  just `False`.
- **`GoldenEvaluationService`** — `run(ablation_name, cases, runner) -> GoldenRunReport`. Per case:
  execute the reference SQL through `GuardedExecutionService`, run one turn through the supplied
  `TurnRunner`, then compare. A turn that pauses for clarification, short-circuits on intent, returns
  a Phase 7 narrowing suggestion, or raises a `GenqlError` is a **failure with a named reason**, never
  an exception that aborts the run — one bad case must not cost the other forty-nine. A truncated
  reference result fails the case with the fixture-error reason from §1.
- **`AblationService`** — `run(ablation_names, cases) -> tuple[GoldenRunReport, ...]`. Resolves each
  name against `ABLATIONS` (an unregistered name raises `UnknownAblationError` naming the registered
  alternatives), asks `TurnRunnerFactory` for a runner bound to that ablation's overrides, and
  delegates to `GoldenEvaluationService`. For an ablation with `requires_recompile`, it calls
  `SearchDocumentRecompiler.recompile(ablation, ...)` before the run and, in a `finally`,
  `recompile(FULL, ...)` afterwards — so an interrupted ablation restores the store on its way out.
- **`FeedbackService`** — `record(feedback) -> None`, delegating to `FeedbackWriter`. A service rather
  than a controller calling the port directly, for the same reason Phase 7's
  `IndexRecommendationService` is one: controllers hold no logic, including the single line of it here
  — rejecting a `corrected_sql` that does not parse as a `SELECT`, so the eventual feedback index is
  not seeded with garbage.

---

## 7. Controllers: HTTP, SSE, and CLI

`genql/api/` gains the structure §16 already specifies, plus the one adapter that closes the layering:

```
genql/api/app.py                    FastAPI app factory, exception handler, router registration
genql/api/deps.py                   Container resolution per request
genql/api/graph_turn_runner.py      GraphTurnRunner — the TurnRunner implementation
genql/api/dtos/query_dtos.py        StartTurnRequest, ResumeTurnRequest, TurnResponseDto
genql/api/dtos/feedback_dtos.py     FeedbackRequest
genql/api/dtos/datasource_dtos.py   DatasourceDto
genql/api/controllers/query_controller.py       POST /v1/queries, POST /v1/queries/{id}/resume
genql/api/controllers/stream_controller.py      GET  /v1/queries/stream
genql/api/controllers/feedback_controller.py    POST /v1/queries/{id}/feedback
genql/api/controllers/datasource_controller.py  GET  /v1/datasources
genql/api/sse/stage_events.py       a graph delta -> StageEvent
genql/api/sse/event_stream.py       StageEvent -> ServerSentEvent, plus the terminal event
```

**`GraphTurnRunner` lives in `genql/api/`, not in `genql/services/`.** It wraps the compiled graph
and `start_turn`, both of which live in `genql/api/`, and `genql/services/` may not import
`genql.api`. Placing the implementation in the api layer while `GoldenEvaluationService` depends only
on the `TurnRunner` protocol keeps the layers contract intact with no indirection: the composition
root injects the api-layer adapter into the service, exactly as it injects repository adapters.

| Route | Body / params | Response |
|---|---|---|
| `POST /v1/queries` | `{question, datasource, domain_id?, thread_id?}` | `TurnResponseDto` |
| `POST /v1/queries/{thread_id}/resume` | `{answer}` | `TurnResponseDto` |
| `GET /v1/queries/stream` | `?question=&datasource=&domain_id=&thread_id=` | `text/event-stream` |
| `POST /v1/queries/{thread_id}/feedback` | `{rating, corrected_sql?, comment?}` | `204` |
| `GET /v1/datasources` | — | `[DatasourceDto]` |
| `GET /healthz` | — | `{"status": "ok"}` |

The stream endpoint is `GET` because the browser `EventSource` API cannot issue a `POST`, and its
first client is Phase 9's frontend.

**Streaming mechanics.** `genql/api/query_graph.py` gains `stream_query` and `stream_resume` beside
the existing `run_query`/`resume_query`, so every fact about langgraph's invocation convention stays
in the one file that already owns it. Both wrap `graph.stream(..., stream_mode="updates")`, which
yields one `{node_name: delta}` mapping per completed node. `stage_events.py` renders each mapping as
one `StageEvent`; a mapping carrying langgraph's `__interrupt__` key becomes a `paused` event
followed by a terminal `clarification` event; a `GenqlError` raised mid-stream becomes a terminal
`error` event rather than a dropped connection, because a half-delivered SSE stream is
indistinguishable from a broken one on the client. The generator is synchronous and is bridged with
`starlette.concurrency.iterate_in_threadpool`. The per-thread advisory lock wraps the whole stream,
exactly as `start_turn` wraps the blocking invoke.

**Errors.** One exception handler on the app maps `UnknownDatasourceError` and `UnknownThreadError`
to `404`, every other `GenqlError` to `400` as `{"error": type_name, "detail": str(exc)}`, and
anything else to `500`. Controllers contain no `try`.

**CLI** — `genql/cli/commands/serve.py` and `genql/cli/commands/eval.py`:

```
genql serve [--host H] [--port P]
    → uvicorn over the app factory, one process

genql eval golden --datasource X [--report out.json] [--failure-class C]
    → runs every fixture; prints a per-case pass/fail table, then overall and
      per-failure-class accuracy with counts beside every number

genql eval ablate --datasource X [--ablation N ...] [--report out.json]
    → runs the golden set once per ablation (all registered ones by default),
      printing each ablation's accuracy and its delta from `full`, and naming
      "query log" as a layer this build cannot measure
```

`genql eval golden` sets `record_execution_actuals=True` through the same override mechanism the
ablations use, so Phase 7's `genql optimizer recommend-indexes` has evidence to report on a fresh
installation — the hand-off Phase 7's §10 describes.

---

## 8. Configuration

Covered in §4: the five ablation switches, `api_host`, `api_port`, `golden_set_dir`.

---

## 9. Testing

**Unit** — `ResultComparator` is the densest target: identical results, reordered rows, reordered
columns, differing column sets, duplicate rows differing in count, `Decimal`/`float` equivalence, and
empty-versus-empty. `GoldenEvaluationService` against a fake `TurnRunner` and a fake execution path,
covering a pass, a result mismatch, a paused turn, a narrowing suggestion, a truncated reference, and
a raising turn — asserting the run completes and reports in every case. `AblationService` against
fake factories, asserting each ablation gets its own runner, that an unregistered name raises
`UnknownAblationError`, and — the one ordering that matters — that a `requires_recompile` ablation
recompiles before the run and restores afterwards **even when the run raises**. `GoldenRunReport`
arithmetic on an empty report. `FeedbackService`'s corrected-SQL rejection. `stage_events.py` against
hand-built delta mappings, including the `__interrupt__` one. Every ablation's registration and
override shape. `SearchDocumentCompiler`'s ablated content assembly, asserting descriptions and units
are absent while column names and samples remain.

**Integration (testcontainers)** — migration `0010` upgrade/downgrade; `PostgresFeedbackWriter` round
trip; `YamlGoldenSetReader` against real fixture files, including a malformed one asserting
`GoldenSetError` names the offending file.

**API** — `fastapi.testclient.TestClient` against an app whose container is overridden with a fake
graph: each route's happy path, the exception handler's three status mappings, and the SSE endpoint's
event *order* — one event per node, terminal event last — parsed from the raw stream rather than
asserted on the generator, because the ordering guarantee is what a client depends on.

**Golden** — `tests/golden/test_golden_runner.py` runs the runner over the four-to-six fixtures Phase
7 authored for its rewrite-equivalence tests, promoted into `golden/*.yaml` and reused rather than
re-invented, against real `local.tpcds`. Gated on `GENQL_TEST_DSN` and `GENQL_OPENROUTER_API_KEY`,
with a clean skip without them.

**Ablation** — one integration test asserting that `no_domains` and `full` produce two reports over
the same case ids with independently computed accuracies. It deliberately does **not** assert that
`full` scores higher: that is the empirical question the harness exists to answer, and encoding the
expected answer as an assertion would make the instrument agree with the hypothesis by construction.

**Contract** — `lint-imports` continues to pass with `fastapi`, `starlette`, and `sse_starlette`
added to the forbidden lists for `genql.domain` and `genql.services`.

---

## 10. Consequences for later phases

**Phase 9 (frontend)** consumes `GET /v1/queries/stream` as its primary surface. The SSE contract
this phase fixes — one event per pipeline stage, and a terminal event that is always one of `result`,
`clarification`, or `error` — is the contract §18 says the frontend was deferred until stabilizing.

The ablation report is the first artifact that can falsify the project's premise. If
`no_descriptions` or `no_domains` scores within noise of `full`, that is a finding about the
architecture rather than a bug in the harness, which is why §9's ablation test asserts mechanics and
not an outcome.

---

## 11. Risks

**A wrong reference statement produces a confidently wrong verdict.** The runner cannot distinguish
"the generated SQL is wrong" from "the reference SQL is wrong." Mitigation: references are
hand-written and reviewed as fixtures; the per-case report prints both statements on a mismatch so a
reviewer sees them side by side; and the first six fixtures are promoted from Phase 7's equivalence
set, which was already validated against real execution.

**Golden-set size bounds every conclusion the ablation harness supports.** §14 calls for thirty to
fifty cases; the first run will have six. A four-point accuracy difference over six cases is one
case. Mitigation: the report prints counts beside every accuracy, per failure class, so a reader
cannot see `0.83` without also seeing `5/6`. Growing the fixture set is the ongoing work this phase
enables rather than completes.

**An interrupted `no_descriptions` run can leave `genql_search_document` compiled without
enrichment.** The restore is a `finally`, so an exception is covered, but a killed process is not.
Mitigation: the degraded state is fully repaired by `genql semantic compile`, a single idempotent
command — the same posture §19 already takes toward Neo4j projection drift — and the CLI prints that
instruction when it starts a recompiling ablation, before the risk exists rather than after.

**Ablation measures a layer's *absence*, not its *quality*.** `no_descriptions` says what happens
with no descriptions at all; it says nothing about what better descriptions would buy. Mitigation:
stated in the report header rather than left for a reader to infer, and it matches what §15 actually
claims the harness demonstrates — whether the semantic store earns its latency, not how much more it
could earn.

**A synchronous SSE endpoint holds a worker thread for a whole turn.** A turn is seconds to tens of
seconds and FastAPI's threadpool defaults to forty workers, so a few dozen concurrent streams
exhaust it and later requests queue invisibly. Mitigation: documented, and acceptable for the
single-user development target §20's cost model describes; the fix, if it is ever needed, is an async
graph invocation, which is a change to one file rather than to the pipeline.
