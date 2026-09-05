"""Maps a Datasource to a pooled Engine, one per datasource name.

The environment is injected rather than read from `os.environ` directly, so
unit tests describe a datasource whose secret is missing without mutating
process state.

Engines are cached for the process lifetime, which is right for a CLI
invocation and for a long-lived API process. `invalidate` exists so removing a
datasource cannot leave a stale connection behind inside one process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy import Engine

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.infrastructure.db.engine import create_engine_from_dsn


class DatasourceEngineProvider:
    def __init__(
        self,
        env: Mapping[str, str],
        engine_factory: Callable[[str], Engine] = create_engine_from_dsn,
    ) -> None:
        self._env = env
        self._engine_factory = engine_factory
        self._engines: dict[str, Engine] = {}

    def engine_for(self, datasource: Datasource) -> Engine:
        cached = self._engines.get(datasource.name)
        if cached is not None:
            return cached
        engine = self._engine_factory(self._dsn_for(datasource))
        self._engines[datasource.name] = engine
        return engine

    def invalidate(self, name: str) -> None:
        self._engines.pop(name, None)

    def _dsn_for(self, datasource: Datasource) -> str:
        dsn = self._env.get(datasource.dsn_env_var, "").strip()
        if not dsn:
            raise MissingDatasourceSecretError(datasource.name, datasource.dsn_env_var)
        return dsn
