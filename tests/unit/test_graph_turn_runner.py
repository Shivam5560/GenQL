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
