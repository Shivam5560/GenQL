"""The runner's step list must be built FROM the registry, not hand-listed.

Before this fix, genql/composition_root.py hardcoded
`providers.List(Factory(CatalogScanStep, ...), Factory(DataProfilingStep, ...))`,
so a newly `@DISCOVERY_STEPS.register(...)`-ed step could be silently left out of
the pipeline. This asserts the constructed runner's step order always equals
DISCOVERY_STEPS's registered order, caught here instead of in production. See final-review.md I4.
"""

from __future__ import annotations

from dependency_injector import providers
from langgraph.checkpoint.memory import InMemorySaver

from genql.api.query_graph import (
    AMBIGUITY_GATE,
    AMBIGUITY_PROBING,
    CANDIDATE_GENERATION,
    CANDIDATE_SELECTION,
    CRITIQUE,
    DOMAIN_SCOPING,
    GUARDED_EXECUTION,
    INTENT_CLASSIFICATION,
    PLANNING,
    REWRITE_AND_COST_GATE,
    SCHEMA_LINKING,
    STATIC_VALIDATION,
)
from genql.composition_root import Container
from genql.discovery.registry import DISCOVERY_STEPS
from genql.repositories.guardrails.registry import GUARDRAILS


def test_runner_step_names_equal_the_registered_order(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert step_names == DISCOVERY_STEPS.keys()


def test_every_registered_step_has_a_service_provider(container: Container) -> None:
    """A step registered without a service-provider entry fails fast (KeyError)."""
    runner = container.discovery_runner()

    assert len(runner._steps) == len(DISCOVERY_STEPS.keys())  # noqa: SLF001


def test_the_container_builds_a_catalog_reader_factory(container: Container) -> None:
    factory = container.catalog_reader_factory()

    assert hasattr(factory, "for_datasource")


def test_the_runner_includes_graph_projection(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "graph_projection" in step_names


def test_the_container_builds_a_graph_analysis_service(container: Container) -> None:
    service = container.graph_analysis_service()

    assert hasattr(service, "analyze")


def test_the_container_builds_a_graph_projection_service(container: Container) -> None:
    service = container.graph_projection_service()

    assert hasattr(service, "project")


def test_the_runner_includes_object_profiling(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "object_profiling" in step_names


def test_the_container_builds_a_chat_provider(container: Container) -> None:
    assert hasattr(container.chat_provider(), "complete")


def test_the_container_builds_an_embedding_provider(container: Container) -> None:
    assert hasattr(container.embedding_provider(), "embed")


def test_the_container_builds_a_rerank_provider_when_enabled(container: Container) -> None:
    assert hasattr(container.rerank_provider(), "rerank")


def test_the_container_builds_an_object_profiling_service(container: Container) -> None:
    assert hasattr(container.object_profiling_service(), "profile")


def test_the_container_builds_a_domain_discovery_service(container: Container) -> None:
    assert hasattr(container.domain_discovery_service(), "discover")


def test_the_container_builds_a_semantic_overlay_service(container: Container) -> None:
    assert hasattr(container.semantic_overlay_service(), "apply")


def test_the_container_builds_a_compile_service(container: Container) -> None:
    assert hasattr(container.compile_service(), "compile")


def test_the_container_builds_a_retrieval_service(container: Container) -> None:
    assert hasattr(container.retrieval_service(), "search")


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
    assert len(GUARDRAILS.keys()) == 5
    assert hasattr(container.guardrail_factory(), "for_datasource")


def test_the_container_builds_an_invokable_query_graph(container: Container) -> None:
    with container.checkpointer.override(providers.Object(InMemorySaver())):
        assert hasattr(container.query_graph(), "invoke")


def test_the_container_builds_a_rule_reader_and_writer(container: Container) -> None:
    assert hasattr(container.rule_reader(), "read_rules")
    assert hasattr(container.rule_writer(), "write_rules")


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


def test_the_query_graph_carries_all_twelve_stages(container: Container) -> None:
    """The graph provider is overridden in OptimizerContainer, so this is where a
    forgotten node would show up — an eleven-node graph compiled from a
    partial provider would still be `invoke`-able and silently skip a stage.

    The checkpointer is overridden with InMemorySaver because building the real
    one opens a psycopg pool and runs setup() against it, and this fixture's DSN
    points at a host that does not exist. Overriding it is not weakening the
    test: what is under test is which nodes the provider wires, and that is
    saver-independent. The real saver is proven in
    tests/integration/test_postgres_checkpointer.py.
    """
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
        REWRITE_AND_COST_GATE,
        GUARDED_EXECUTION,
    ):
        assert stage in nodes


def test_the_runner_includes_synthetic_ambiguity_log(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert "synthetic_ambiguity_log" in step_names


def test_the_container_builds_a_synthetic_ambiguity_log_service(container: Container) -> None:
    assert hasattr(container.synthetic_ambiguity_log_service(), "generate")


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
