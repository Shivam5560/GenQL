"""Maps a Datasource to a pooled Engine, one per datasource name and role.

A datasource resolves to a DSN one of two ways and this is where that choice
is made. A row carrying a host connects through the driver scheme registered
for its dialect, with its password decrypted here and nowhere else; a row
carrying only `dsn_env_var` — `local`, and anything the CLI registered — reads
a whole DSN out of the process environment as it always did. A row carrying
neither is a registration that never completed, and says so.

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

from cryptography.fernet import InvalidToken
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import (
    MissingDatasourceSecretError,
    MissingReadonlySecretError,
    UndecryptableDatasourceSecretError,
)
from genql.domain.ports.secret_cipher import SecretCipher
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.infrastructure.db.dsn_schemes import DSN_SCHEMES
from genql.infrastructure.db.engine import create_engine_from_dsn

READONLY_ROLE = "genql_readonly"

_ADMIN = "admin"
_READONLY = "readonly"


class DatasourceEngineProvider:
    def __init__(  # noqa: PLR0913, PLR0917 - all six are one provider's configuration
        self,
        env: Mapping[str, str],
        cipher: SecretCipher | None = None,
        engine_factory: Callable[[str], Engine] = create_engine_from_dsn,
        readonly_role: str = READONLY_ROLE,
        readonly_password: str = "",
        dsn_schemes: Mapping[str, str] = DSN_SCHEMES,
    ) -> None:
        self._env = env
        self._cipher = cipher
        self._engine_factory = engine_factory
        self._readonly_role = readonly_role
        self._readonly_password = readonly_password
        self._dsn_schemes = dict(dsn_schemes)
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
        if datasource.host:
            return self._stored_dsn(datasource)
        if datasource.dsn_env_var:
            dsn = self._env.get(datasource.dsn_env_var, "").strip()
            if not dsn:
                raise MissingDatasourceSecretError(datasource.name, datasource.dsn_env_var)
            return dsn
        raise MissingDatasourceSecretError(datasource.name)

    def _stored_dsn(self, datasource: Datasource) -> str:
        assert datasource.host is not None  # guarded by the caller
        connection = DatasourceConnection(
            host=datasource.host,
            # A row with a host always has a port: registration writes both or
            # neither. The default is the Postgres one so a hand-edited row
            # still connects rather than failing validation.
            port=datasource.port or 5432,
            database=datasource.database or "",
            username=datasource.username or "",
            password=self._password_for(datasource),
            options=datasource.options,
        )
        scheme = self._dsn_schemes.get(datasource.dialect)
        if scheme is None:
            raise MissingDatasourceSecretError(datasource.name)
        return connection.render_dsn(scheme)

    def _password_for(self, datasource: Datasource) -> str:
        if not datasource.password_ciphertext:
            return ""
        if self._cipher is None:
            raise MissingDatasourceSecretError(datasource.name)
        try:
            return self._cipher.decrypt(datasource.password_ciphertext)
        except InvalidToken as exc:
            raise UndecryptableDatasourceSecretError(datasource.name) from exc
