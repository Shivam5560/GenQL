"""_choose_k and _l2_normalize are plain functions — no Neo4j, no Postgres."""

from __future__ import annotations

import numpy as np

from genql.repositories.graph.fused_clustering_algorithm_repository import (
    _choose_k,
    _l2_normalize,
)


def test_l2_normalize_produces_unit_length_vectors() -> None:
    vector = np.array([3.0, 4.0])

    normalized = _l2_normalize(vector)

    assert np.isclose(np.linalg.norm(normalized), 1.0)


def test_l2_normalize_leaves_a_zero_vector_untouched() -> None:
    assert np.array_equal(_l2_normalize(np.zeros(3)), np.zeros(3))


def test_choose_k_finds_two_well_separated_clusters() -> None:
    cluster_a = np.random.default_rng(0).normal(loc=0.0, scale=0.1, size=(10, 4))
    cluster_b = np.random.default_rng(1).normal(loc=10.0, scale=0.1, size=(10, 4))
    vectors = np.concatenate([cluster_a, cluster_b])

    k, labels = _choose_k(vectors, k_min=2, k_max=5)

    assert k == 2
    assert len(set(labels[:10])) == 1
    assert len(set(labels[10:])) == 1
    assert labels[0] != labels[10]


def test_choose_k_falls_back_to_one_cluster_when_too_few_objects() -> None:
    vectors = np.array([[1.0, 2.0], [3.0, 4.0]])

    k, labels = _choose_k(vectors, k_min=2, k_max=20)

    assert k == 1
    assert set(labels) == {0}
