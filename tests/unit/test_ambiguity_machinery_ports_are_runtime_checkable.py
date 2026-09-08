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
from genql.domain.ports.candidate_strategy_factory import CandidateStrategyFactory
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


class StrategyFactory:
    def default(self, chat: object) -> CandidateGenerationStrategy:
        return Strategy()

    def all(self, chat: object) -> list[CandidateGenerationStrategy]:
        return [Strategy()]


def test_candidate_strategy_factory_is_satisfied_structurally() -> None:
    """The port CandidateGenerationService depends on instead of importing the
    registry directly — the seam that keeps the services layer free of any
    `genql.repositories` import."""
    assert isinstance(StrategyFactory(), CandidateStrategyFactory)
