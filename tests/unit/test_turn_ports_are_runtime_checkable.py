"""Phase 6's ports get their own file rather than joining Phase 5's, keeping
both comfortably under the 250-line cap.

ThreadLock is asserted differently from the rest: a Protocol whose only members
are __enter__/__exit__ is satisfied by almost anything, so isinstance() on it
proves nothing. What actually matters is that a conforming object works as a
`with` block, so that is what is asserted.
"""

from __future__ import annotations

from types import TracebackType

import pytest

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.business_domain import BusinessDomain
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

    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]:
        return ()


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

    with pytest.raises(RuntimeError), lock:
        raise RuntimeError("boom")

    assert lock.exited
