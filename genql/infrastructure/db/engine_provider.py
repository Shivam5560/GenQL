"""Maps a Datasource to a pooled Engine, one per datasource name and role.

The environment is injected rather than read from `os.environ` directly, so
unit tests describe a datasource whose secret is missing without mutating
process state.

Two bindings exist per datasource, keyed ("admin", name) and
("readonly", name). Only `readonly_engine_for` is reachable from the guarded
execution path, so the admin engine is structurally out of reach there rather
than merely unused by convention. Both are cached for the process lifetime,
which is right for a CLI invocation and for a long-lived API process;
`invalidate` drops both so removing a datasource cannot leave a stale
connection behind inside one process.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, MissingReadonlySecretError
from genql.infrastructure.db.engine import create_engine_from_dsn

READONLY_ROLE = "genql_readonly"

_ADMIN = "admin"
_READONLY = "readonly"


class DatasourceEngineProvider:
    def __init__(
        self,
        env: Mapping[str, str],
        engine_factory: Callable[[str], Engine] = create_engine_from_dsn,
        readonly_role: str = READONLY_ROLE,
        readonly_password: str = "",
    ) -> None:
        self._env = env
        self._engine_factory = engine_factory
        self._readonly_role = readonly_role
        self._readonly_password = readonly_password
        self._engines: dict[tuple[str, str], Engine] = {}

    def engine_for(self, datasource: Datasource) -> Engine:
        return self._cached(_ADMIN, datasource, self._dsn_for(datasource))

    def readonly_engine_for(self, datasource: Datasource) -> Engine:
        if not self._readonly_password.strip():
            raise MissingReadonlySecretError(datasource.name)
        url = make_url(self._dsn_for(datasource)).set(
            username=self._readonly_role, password=self._readonly_password
        )
        return self._cached(_READONLY, datasource, url.render_as_string(hide_password=False))

    def invalidate(self, name: str) -> None:
        self._engines.pop((_ADMIN, name), None)
        self._engines.pop((_READONLY, name), None)

    def _cached(self, role: str, datasource: Datasource, dsn: str) -> Engine:
        key = (role, datasource.name)
        cached = self._engines.get(key)
        if cached is not None:
            return cached
        engine = self._engine_factory(dsn)
        self._engines[key] = engine
        return engine

    def _dsn_for(self, datasource: Datasource) -> str:
        dsn = self._env.get(datasource.dsn_env_var, "").strip()
        if not dsn:
            raise MissingDatasourceSecretError(datasource.name, datasource.dsn_env_var)
        return dsn
