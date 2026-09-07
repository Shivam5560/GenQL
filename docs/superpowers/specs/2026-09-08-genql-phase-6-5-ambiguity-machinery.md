# GenQL Phase 6.5 — Ambiguity Machinery

## 1. Purpose

Phase 6's own spec (§1) carved itself out of the parent spec's original Phase 6 and named exactly
what it deferred: "multi-candidate generation, critique, probing, and data-driven selection move to
Phase 6.5, because nothing consumes candidate disagreement until critique exists." That is this
phase. It is SOMA-SQL's distinguishing idea (parent spec §2): offline synthetic ambiguity-aware
examples retrieved as few-shot context; structured planning producing multiple candidate SQLs
representing alternative interpretations; a critique phase emitting a structured defect report; and
ambiguity-driven probing — diffing candidates, mapping differences to intent/schema/value
dimensions, and issuing targeted probe queries whose results let the *data* arbitrate, rather than a
learned selector picking a favorite the way CHASE-SQL and XiYan-SQL do.

**Scope, decided explicitly:**

- **Multi-candidate generation is demand-driven, not unconditional.** Parent spec §20's "stage
  activation must be demand-driven" is the load-bearing constraint: a well-specified question that
  never touched the ambiguity gate must keep paying exactly Phase 5/6's $0.046 simple-path cost.
  Whether a turn is "contested" is derived from state Phase 6 already produces — `clarifications`
  (a resumed answer was needed) or the final `AmbiguityAssessment.applied_defaults` (a rule default
  was applied) — not a new gate score. A turn is contested if either is non-empty; nothing else
  changes about how the gate decides to interrupt.
- **Candidate diversity comes from two generator strategies, not resampling.** Per §20: "diversity in
  multi-candidate text-to-SQL comes from different generator prompts (divide-and-conquer
  decomposition versus execution-plan chain of thought), not from resampling one prompt." These are
  registered strategies (`CANDIDATE_STRATEGIES`), each returning two structured SQL variants from one
  `ChatProvider.complete` call — two calls, four candidates, matching §20's "two generator calls
  returning two structured variants each yield four candidates through two calls" exactly. A future
  third strategy (e.g. bottom-up join assembly) registers without touching
  `CandidateGenerationService`.
- **Critique combines a deterministic check with one LLM judgment call, not two LLM calls.** The
  "database signals" §9 asks for — column existence, type compatibility — are already fully
  determined by `SchemaLink.column_names`, the same list static validation's guardrails already
  enforce; checking a candidate's referenced columns against that list needs sqlglot, not a model
  call. Join validity and plan-alignment are judgment calls a script can't make, so one
  `ChatProvider.complete` scores every surviving candidate at once, folding in the deterministic
  findings as part of its input rather than issuing a second round trip.
- **Probing is gated on candidates actually disagreeing, and capped.** Per §19's risk mitigation: "gated
  on candidates actually disagreeing, runs under a strict budget, and is individually ablatable so its
  value is measurable." Zero or one surviving candidate skips probing entirely — there is nothing to
  arbitrate. A configurable cap (`probing_max_probes`, default 3) bounds worst-case latency and cost
  regardless of how many dimensions a critique disagreement touches.
- **Selection is a pure function, not a model call.** Per §20: "Selection ... is deterministic by
  default. When probing resolves every contested dimension, selection is a lookup rather than a
  judgement." `CandidateSelectionService` takes no `ChatProvider` at all — it is a lookup over probe
  results, falling back to the highest critique score when probing is inconclusive or was skipped.
- **The offline synthetic ambiguity log is a new discovery step and its own table**, not an extension
  of `genql_search_document`. That table's shape is schema-object retrieval by BM25/HNSW over object
  descriptions; ambiguity examples are question→interpretations→resolution triples retrieved by
  similarity to the *current question*, a different key and a different consumer (the generation
  prompt, not schema linking). A dedicated `genql_ambiguity_example` table keeps the two concerns from
  tangling, at the cost of one more small reader/writer pair — the same tradeoff Phase 6 already made
  for `genql_rule` against `genql_search_document`.
- **Opus escalation, scoped to what this phase actually controls.** §20 names two escalation
  triggers: a gate score of "genuinely hard" (the gate has no such score today — adding one is Phase
  6 surface, out of this phase's touch scope, and is flagged in §11 rather than half-built here) and
  "critique fails to resolve after one repair round" (fully within this phase). Only the second is
  implemented: if every surviving candidate carries a fatal defect after one regeneration attempt, one
  escalated regeneration runs against `chat_model_escalation` (Opus 5) before the turn raises.

**What this phase does not touch:** the ambiguity gate's interrupt/resume mechanics, `genql_rule`,
domain scoping (all Phase 6, unchanged), rewrite/optimization (Phase 7), the API/SSE layer and the
golden-set/ablation harness that would make this phase's cost model *measured* rather than modeled
(Phase 8).

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/defect.py
class Defect(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str | None  # one of AMBIGUITY_DIMENSIONS, or None for a non-ambiguity defect
    severity: Literal["fatal", "repairable", "advisory"]
    message: str

# domain/entities/critique_report.py
class CritiqueReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int  # position in the surviving-candidates tuple this reports on
    defects: tuple[Defect, ...]
    score: float  # 0-1, the critique_ranked selection fallback's sort key

    @property
    def is_fatal(self) -> bool:
        return any(d.severity == "fatal" for d in self.defects)

# domain/entities/ambiguity_probe.py
class AmbiguityProbe(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str  # one of AMBIGUITY_DIMENSIONS
    probe_sql: str
    # what each candidate's interpretation predicts the probe returns, so a
    # later comparison against the real result is a lookup, not a judgment.
    candidate_predictions: tuple[tuple[int, str], ...]

# domain/entities/probe_result.py
class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    probe: AmbiguityProbe
    actual_result: str  # the probe's real scalar/short result, rendered for comparison
    resolved_candidate_index: int | None  # None when no prediction matched

# domain/entities/candidate_selection.py
class CandidateSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    selected: SqlCandidate
    method: Literal["single_survivor", "probe_resolved", "critique_ranked"]
    rationale: str

# domain/entities/ambiguity_example.py — offline, the synthetic ambiguity log
class AmbiguityExample(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    interpretations: tuple[str, ...]  # alternative readings the question admits
    resolution: str  # which interpretation is correct and why, in prose
    domain_id: int | None
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/candidate_strategy.py
class CandidateGenerationStrategy(Protocol):
    """One way of turning a plan into SQL variants. `variant_count` is fixed
    per strategy rather than a parameter, since each strategy's prompt is
    built around producing exactly that many structured variants in one call."""
    variant_count: int
    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]: ...

# domain/ports/critic.py
class Critic(Protocol):
    def critique(
        self, plan: QueryPlan, candidates: tuple[SqlCandidate, ...], links: tuple[SchemaLink, ...]
    ) -> tuple[CritiqueReport, ...]: ...

# domain/ports/probe_designer.py
class ProbeDesigner(Protocol):
    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]: ...

# domain/ports/ambiguity_example_reader.py
class AmbiguityExampleReader(Protocol):
    def search(self, question: str, domain_id: int | None, top_k: int) -> tuple[AmbiguityExample, ...]: ...

# domain/ports/ambiguity_example_writer.py
class AmbiguityExampleWriter(Protocol):
    def write(self, examples: tuple[AmbiguityExample, ...]) -> None: ...
```

Probe execution and probe-SQL safety reuse existing ports unchanged: `StaticValidationService`
validates `probe_sql` exactly like a candidate (a probe that references an unlisted object is a bug
in `ProbeDesigner`'s prompt, not a case to special-case around), and `GuardedExecutionService` runs it
under the same row cap and read-only binding. No new execution port.

`QueryState` (`genql/api/query_state.py`) changes:

```python
# `candidate: SqlCandidate | None` becomes `candidates: tuple[SqlCandidate, ...]` — Phase 5/6's
# simple path is now the len(candidates) == 1 case, not a structurally different type. Every node
# and test that touched `candidate` singular updates in the same batch; there is no compatibility
# shim, matching how Phase 6 itself changed Phase 5's graph file without one.
candidates: tuple[SqlCandidate, ...]
contested: bool  # clarifications or applied_defaults were non-empty when the gate last cleared
critique_reports: tuple[CritiqueReport, ...]
probe_results: tuple[ProbeResult, ...]
selection: CandidateSelection | None
escalated: bool  # whether the one Opus regeneration attempt has already been spent
```

`validated_sql: str | None` keeps its existing meaning and type: the field is populated from
`selection.selected` once selection runs, so `GuardedExecutionNode` (Phase 5) needs no change at all.

---

## 3. Registries

**New: `CANDIDATE_STRATEGIES: Registry[CandidateGenerationStrategy]`**, in
`genql/repositories/query/registry.py` alongside the existing pattern. Two implementations register
on import, same shape as every other registry in the codebase:

- `"decomposition"` — breaks the plan into sub-clauses (filters, joins, aggregation) and asks the
  model to assemble two candidate statements bottom-up from them.
- `"execution_plan"` — asks the model to reason in terms of a PostgreSQL execution plan (scan → join
  → filter → aggregate order) and produce two candidates from that ordering.

`CandidateGenerationService` iterates `CANDIDATE_STRATEGIES.all()` only on the contested path; the
non-contested path calls exactly one fixed strategy (`"decomposition"`, chosen arbitrarily since a
non-contested plan has one intended reading and strategy choice cannot matter) and keeps only its
first variant — preserving Phase 5/6's exact one-call, one-candidate shape and cost for that path.

No other new registry. `GUARDRAILS` (Phase 5) is reused unchanged for probe-SQL validation; critique,
probing, and selection are not designed as swappable — the parent spec names one deterministic
selection rule and one critique approach, and a registry with a single forced member is an
abstraction this phase doesn't need yet.

---

## 4. Infrastructure

**Migration `0008_ambiguity_examples.py`:**

```sql
CREATE TABLE genql_ambiguity_example (
    id BIGSERIAL PRIMARY KEY,
    domain_id BIGINT REFERENCES genql_domain(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    interpretations TEXT[] NOT NULL,
    resolution TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL
);
CREATE INDEX genql_ambiguity_example_embedding_hnsw
    ON genql_ambiguity_example USING hnsw (embedding vector_cosine_ops);
```

Mirrors `genql_search_document`'s existing pgvector/HNSW setup (Phase 4) exactly — same extension,
same index type, same distance operator — so nothing new is asked of the ParadeDB/Postgres image.

**`Settings` gains** (`genql/core/settings.py`):

```python
chat_model_escalation: str = "anthropic/claude-opus-5"
probing_max_probes: int = 3
ambiguity_example_top_k: int = 3
```

---

## 5. Repositories

```python
# repositories/semantic/ambiguity_example_repository.py
class PostgresAmbiguityExampleReader:  # AmbiguityExampleReader
    """Embeds the question via the existing EmbeddingProvider, then a
    cosine-distance ORDER BY LIMIT — the same read shape
    SemanticCatalogReader's hybrid retrieval already uses for
    genql_search_document, applied to the smaller table."""
    ...
class PostgresAmbiguityExampleWriter:  # AmbiguityExampleWriter, plain insert
    ...
```

---

## 6. Services

New, under `genql/services/query/`:

- **`CandidateGenerationService`** (replaces Phase 5/6's version; same class name, same import
  path — every existing caller updates in place) — takes `CANDIDATE_STRATEGIES` and an
  `AmbiguityExampleReader`. On `contested=False`: one strategy, first variant, `examples=()` — bit-
  for-bit Phase 5/6 behavior. On `contested=True`: fetches up to `ambiguity_example_top_k` examples
  once, calls every registered strategy with them, flattens the variants into the candidate tuple.
- **`CritiqueService`** — deterministically checks each candidate's referenced columns/tables against
  `SchemaLink` (sqlglot, no model call, mirrors `StaticValidationService`'s parsing) to seed a
  `Defect` per unlisted reference, then makes one `ChatProvider.complete` call carrying the plan, all
  candidates, and the deterministic defects already found, asking the model to add join-validity and
  plan-alignment defects and to score each candidate 0–1. Only invoked when `contested` and more than
  one candidate survived static validation.
- **`AmbiguityProbingService`** — wraps a `ProbeDesigner` (one `ChatProvider.complete` call given the
  plan, surviving candidates, and critique reports, returning up to `probing_max_probes` probes each
  naming a dimension and a prediction per candidate), then for each probe: validates `probe_sql`
  through `StaticValidationService`, executes it through `GuardedExecutionService`, and compares the
  real result against each candidate's prediction to produce a `ProbeResult`. Skipped when ≤1
  candidate survives critique.
- **`CandidateSelectionService`** — no `ChatProvider` dependency. `select(candidates, critiques,
  probe_results) -> CandidateSelection`: one survivor → `single_survivor`; else, if every probe in
  `probe_results` resolved and agrees on one index → `probe_resolved`; else → `critique_ranked`,
  the highest `CritiqueReport.score` among non-fatal survivors, ties broken by the lowest
  `candidate_index`.
- **Offline, under `genql/services/discovery/`: `SyntheticAmbiguityLogService`** — a new
  `DiscoveryStep` (registered in the existing `DISCOVERY_STEPS` registry as
  `"synthetic_ambiguity_log"`, run last, after domain naming): for each domain, one `ChatProvider`
  call grounded on that domain's object/metric names asks for several genuinely ambiguous example
  questions with their interpretations and resolution, embeds each question via the existing
  `EmbeddingProvider`, and writes them via `AmbiguityExampleWriter`.

Modified: `StaticValidationNode`'s underlying loop moves from the graph layer (see §7) — the service
itself, `StaticValidationService.validate`, keeps its existing one-candidate signature and is simply
called once per surviving candidate.

---

## 7. Controller: graph extension

`genql/api/query_graph.py`'s existing edges (`CANDIDATE_GENERATION → STATIC_VALIDATION → [retry |
GUARDED_EXECUTION]`) become:

```
CANDIDATE_GENERATION → STATIC_VALIDATION → CRITIQUE → AMBIGUITY_PROBING → CANDIDATE_SELECTION
                                                                                    → GUARDED_EXECUTION
```

`StaticValidationNode` now validates every candidate in `state["candidates"]` independently (one
repair attempt each, exactly Phase 5's per-candidate rule), collecting survivors; if none survive and
`retry_count == 0`, it routes back to `CANDIDATE_GENERATION` exactly as Phase 5 already does. If none
survive and `retry_count == 1` and `contested` and not yet `escalated`, it routes back to
`CANDIDATE_GENERATION` once more with `escalated=True` (the node signals this by returning it in
state; `CandidateGenerationService` reads `escalated` to pick `chat_model_escalation` instead of
`chat_model` for that one call). Otherwise it raises `StaticValidationError`, unchanged.

`CRITIQUE`, `AMBIGUITY_PROBING`, and `CANDIDATE_SELECTION` each open with the same guard: `if not
state["contested"] or len(candidates) <= 1: return {<their output field>: ()}` (or, for selection,
`{"selection": CandidateSelection(selected=candidates[0], method="single_survivor", rationale="only
one candidate survived validation")}`). This is a state check inside the node, not a new conditional
edge — the graph's shape stays three added nodes on one added straight path, and the well-specified
turn pays zero extra `ChatProvider` calls and zero extra warehouse round trips, matching §20's
demand-driven mandate without branching the graph itself.

If `CritiqueService` finds every survivor fatal and the escalation described above has already been
spent (or the turn is not `contested`), `CRITIQUE` raises a new `CritiqueError` — surfaced by the CLI
exactly like `StaticValidationError` is today.

---

## 8. Configuration

Covered in §4: `chat_model_escalation`, `probing_max_probes`, `ambiguity_example_top_k`.

`GatewayContainer` gains an `escalation_chat_provider` singleton built the same way as
`chat_provider`, through the same `CHAT_PROVIDERS` registry, keyed by `chat_model_escalation` instead
of `chat_model` — no new registry entry, since `"openrouter"` already accepts any model string.

---

## 9. Testing

**Unit** — `CandidateGenerationService` against a fake `CANDIDATE_STRATEGIES` registry entry, asserting
the non-contested path calls exactly one strategy and the contested path calls every registered one;
`CritiqueService`'s deterministic column-check against fake `SchemaLink`s, independent of any fake
`ChatProvider`; `CandidateSelectionService`'s three branches (single survivor, probe-resolved,
critique-ranked-with-a-tie) as pure-function tests with no fakes at all, since it takes none.
`SyntheticAmbiguityLogService` against a fake `ChatProvider`/`EmbeddingProvider`/writer.

**Integration (testcontainers)** — migration `0008` upgrade/downgrade; `PostgresAmbiguityExampleReader`
similarity search against real seeded rows; a real probe round trip (`StaticValidationService` +
`GuardedExecutionService`) against `local.tpcds`.

**Real-provider integration (gated)** — one real two-strategy `CandidateGenerationService.generate`
call, one real `CritiqueService.critique` call, one real `ProbeDesigner.design` call, each skipped
without `GENQL_OPENROUTER_API_KEY`, matching every prior phase's convention.

**End-to-end** — a well-specified question (`genql query "how many stores do we have"`) is asserted to
produce exactly one `CandidateGenerationStrategy` invocation and an unchanged validated statement,
proving the simple path is untouched. A deliberately ambiguous question that resolves through a rule
default or a clarification answer is asserted to produce ≥2 candidates, a non-empty
`critique_reports`, and a `CandidateSelection` whose `method` is `probe_resolved` when the seeded
`local.tpcds` data actually decides the contested dimension, `critique_ranked` otherwise — both
outcomes are legitimate and the test asserts on whichever the real data produces, not a hardcoded one.

---

## 10. Consequences for later phases

**Phase 7 (optimizer)** inserts between `CANDIDATE_SELECTION`'s output (`validated_sql`, unchanged
name and type) and `GUARDED_EXECUTION` — this phase does not move where that boundary is.

**Phase 8 (API and evaluation)** is where this phase's cost-model assumptions get checked against
reality: the golden-set runner reports realized cost per query "so the candidate count, the probing
threshold, and the Opus escalation threshold [are] tunable against evidence instead of intuition"
(parent spec §20). It is also where `genql_query_log`/`genql_query_feature`, deferred out of every
phase so far, finally gets real traffic — including, now, real `contested` vs simple-path traffic
this phase's own routing produces — to learn the frequency-weighted join-path strategy from.

---

## 11. Risks

**The gate-driven "genuinely hard" Opus escalation trigger is not built.** §20 names two triggers;
this phase implements only "critique fails to resolve after one repair round." Adding a difficulty
score to `AmbiguityGateService` is Phase 6 surface and was deliberately left alone rather than
reopened here. Mitigation: the cost-row assumption this leaves unmeasured ("Hard" vs "Opus escalation"
in §20's table) is exactly what Phase 8's golden-set runner exists to check — tracked there, not
hidden.

**`AmbiguityProbingService`'s prediction-matching is a string comparison (`actual_result` against each
`candidate_predictions` entry), not a typed numeric comparison.** A probe whose SQL returns `42` and a
prediction rendered as `"42.0"` would spuriously fail to resolve. Mitigation: this is the same
"fail visibly downstream, not upfront" tradeoff Phase 4 accepted for `Metric.sql_expression` and Phase
6 accepted for `genql_rule.dimension` — normalizing numeric rendering is a small, well-scoped
follow-up once real probe traffic in Phase 8 shows whether it actually matters, not a blocker here.

**Critique and probing both cost a `ChatProvider` call whose failure has no repair loop of its own** —
a `ChatProviderError` from `CritiqueService` or `ProbeDesigner` propagates as a typed error and fails
the whole turn, even though the candidates it was judging already passed static validation and could,
in principle, fall back to `critique_ranked` selection over an empty critique set. Mitigation: not
built, because degrading gracefully on a partial critique failure risks silently selecting a candidate
nothing has actually checked — failing loudly here is the same choice Phase 5 made for a
`ChatProviderError` anywhere else in the pipeline, and this phase does not carve out an exception.
