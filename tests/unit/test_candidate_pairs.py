"""Only pairs without a direct FK edge are worth mining a path between —
direct edges need no mined path."""

from __future__ import annotations

from genql.repositories.graph.join_path_miner_repository import _candidate_pairs


def test_directly_connected_pairs_are_excluded() -> None:
    pairs = _candidate_pairs(["a", "b"], [("a", "b")])
    assert pairs == []


def test_unconnected_pairs_are_included() -> None:
    pairs = _candidate_pairs(["a", "b", "c"], [("a", "b")])
    assert set(pairs) == {("a", "c"), ("b", "c")}


def test_edge_direction_does_not_matter_for_exclusion() -> None:
    pairs = _candidate_pairs(["a", "b"], [("b", "a")])
    assert pairs == []


def test_no_pair_is_produced_against_itself() -> None:
    pairs = _candidate_pairs(["a"], [])
    assert pairs == []
