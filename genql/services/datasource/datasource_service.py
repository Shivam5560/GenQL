"""Registers, lists, and removes datasources.

Both validations happen at registration rather than at first use. A dialect
nobody implemented and an environment variable nobody set are the two ways a
datasource row can be born useless, and both are cheap to detect here.

`dialects` is a plain list of registered keys rather than the registry itself:
a service may not import from `genql.repositories`, so the composition root
passes the keys in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.registries.errors import UnknownRegistryKeyError


class DatasourceService:
    def __init__(
        self,
        datasources: DatasourceRepository,
        dialects: Sequence[str],
        env: Mapping[str, str],
    ) -> None:
        self._datasources = datasources
        self._dialects = list(dialects)
        self._env = env

    def register(
        self, name: str, dialect: str, dsn_env_var: str, description: str | None
    ) -> Datasource:
        if dialect not in self._dialects:
            raise UnknownRegistryKeyError("catalog_readers", dialect, self._dialects)
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
