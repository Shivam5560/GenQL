"""Defers GraphDataScience client construction past composition-root build
time.

Unlike the driver, the GDS client checks server compatibility as soon as it
is constructed. Building it eagerly in the composition root would make
`test_composition_root.py`'s container-builds-without-real-infra invariant
false the moment this file is wired in. `.client()` builds it once, on first
use, and caches it.
"""

from __future__ import annotations

from neo4j import Driver


class GdsClientProvider:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._client: object | None = None

    def client(self) -> object:
        if self._client is None:
            from graphdatascience import GraphDataScience  # noqa: PLC0415

            self._client = GraphDataScience.from_neo4j_driver(self._driver)
        return self._client
