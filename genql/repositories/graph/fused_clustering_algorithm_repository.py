"""FastRP structural embeddings (Neo4j, written by Phase 3's FastRpNodeEmbedder)
fused with LLM-description text embeddings (Postgres, written by
ObjectProfilingService) into business-domain clusters. Reads/writes plain
node properties via the Neo4j driver directly — not through
GraphCatalogSession's GDS graph catalog, which exists for GDS algorithms,
not for this Python-side k-means."""

from __future__ import annotations

import numpy as np
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from genql.domain.errors import DomainNamingError
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.repositories.graph.registry import CLUSTERING_ALGORITHMS

_FUSED_PROPERTY = "domain_cluster"
_READ_EMBEDDINGS = (
    "MATCH (o:Object {datasource_name: $datasource_name}) WHERE o.embedding IS NOT NULL "
    "RETURN o.qualified_name AS qualified_name, o.embedding AS embedding"
)
_WRITE_CLUSTERS = (
    "UNWIND $rows AS row MATCH (o:Object {qualified_name: row.qualified_name}) "
    f"SET o.{_FUSED_PROPERTY} = row.cluster_id"
)


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector if norm == 0 else vector / norm


def _choose_k(vectors: np.ndarray, k_min: int, k_max: int) -> tuple[int, np.ndarray]:
    n_samples = vectors.shape[0]
    upper = min(k_max, n_samples - 1)
    if upper < k_min:
        return 1, np.zeros(n_samples, dtype=int)
    best_k, best_score, best_labels = k_min, -1.0, np.zeros(n_samples, dtype=int)
    for k in range(k_min, upper + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(vectors)
        score = silhouette_score(vectors, labels)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels
    return best_k, best_labels


@CLUSTERING_ALGORITHMS.register("fused")
class FusedClusteringAlgorithm:
    def __init__(
        self, driver: Driver, enrichment_reader: EnrichmentReader, k_min: int = 2, k_max: int = 20
    ) -> None:
        self._driver = driver
        self._enrichment_reader = enrichment_reader
        self._k_min = k_min
        self._k_max = k_max

    def detect(self, datasource_name: str) -> int:
        try:
            with self._driver.session() as session:
                structural_rows = list(
                    session.run(_READ_EMBEDDINGS, datasource_name=datasource_name)
                )
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to read structural embeddings for {datasource_name!r}: {exc}"
            ) from exc

        structural = {
            r["qualified_name"]: np.array(r["embedding"], dtype=float) for r in structural_rows
        }
        textual = {
            e.qualified_name: np.array(e.embedding, dtype=float)
            for e in self._enrichment_reader.read_object_enrichments(datasource_name)
            if e.embedding is not None
        }
        shared = sorted(set(structural) & set(textual))
        if not shared:
            raise DomainNamingError(
                f"no object has both a structural and a text embedding for {datasource_name!r}; "
                "run graph analyze and discover (object_profiling) first"
            )

        fused = np.stack(
            [
                np.concatenate([_l2_normalize(structural[qn]), _l2_normalize(textual[qn])])
                for qn in shared
            ]
        )
        k, labels = _choose_k(fused, self._k_min, self._k_max)

        rows = [
            {"qualified_name": qn, "cluster_id": int(label)}
            for qn, label in zip(shared, labels, strict=True)
        ]
        try:
            with self._driver.session() as session:
                session.run(_WRITE_CLUSTERS, rows=rows)
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to write fused clusters for {datasource_name!r}: {exc}"
            ) from exc
        return k
