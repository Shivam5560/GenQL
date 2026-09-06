"""Registers, lists, and removes datasources.

Both validations happen at registration rather than at first use. A dialect
nobody implemented and an environment variable nobody set are the two ways a
datasource row can be born useless, and both are cheap to detect here.

`dialects` is a plain list of registered keys rather than the registry itself,
and `dialect_registry` is that registry's own name: a service may not import
from `genql.repositories`, so the composition root passes both in rather than
this module naming the registry by a duplicated literal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.engine_invalidator import EngineInvalidator
from genql.registries.errors import UnknownRegistryKeyError


class DatasourceService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        dialects: Sequence[str],
        dialect_registry: str,
        env: Mapping[str, str],
        engines: EngineInvalidator,
    ) -> None:
        self._datasources = datasources
        self._dialects = list(dialects)
        self._dialect_registry = dialect_registry
        self._env = env
        self._engines = engines

    def register(
        self, name: str, dialect: str, dsn_env_var: str, description: str | None
    ) -> Datasource:
        if dialect not in self._dialects:
            raise UnknownRegistryKeyError(self._dialect_registry, dialect, self._dialects)
        if not self._env.get(dsn_env_var, "").strip():
            raise MissingDatasourceSecretError(name, dsn_env_var)
        datasource = Datasource(
            name=name, dialect=dialect, dsn_env_var=dsn_env_var, description=description
        )
        self._datasources.add(datasource)
        return datasource

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return self._datasources.list_all(enabled_only=enabled_only)

    def remove(self, name: str) -> None:
        self._datasources.remove(name)
        # Only after the delete succeeds: a removal that was refused (unknown
        # name) must leave a live datasource's pooled engine alone.
        self._engines.invalidate(name)
