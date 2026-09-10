"""Registers, lists, and removes datasources.

Registration takes a host, a port, a database and a user — the form a person
can actually fill in — and turns them into the DSN the engine provider will
connect with. The password is encrypted here, on the way in, and is the only
field that is: everything else is printable and is what the datasources page
shows.

`register_from_env` is the older path, kept for the CLI and for the `local`
row the Phase 2.5 migration created. Both validations still happen at
registration rather than at first use: a dialect nobody implemented and an
environment variable nobody set are the two ways a datasource row can be born
useless, and both are cheap to detect here.

`dialects` is a plain list of registered keys rather than the registry itself,
and `dialect_registry` is that registry's own name: a service may not import
from `genql.repositories`, so the composition root passes both in rather than
this module naming the registry by a duplicated literal. `dsn_schemes` arrives
the same way and for the same reason — which SQLAlchemy driver a dialect
connects through is configuration, not a fact this service should own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.engine_invalidator import EngineInvalidator
from genql.domain.ports.secret_cipher import SecretCipher
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.registries.errors import UnknownRegistryKeyError


class DatasourceService:
    def __init__(  # noqa: PLR0913, PLR0917 - one per collaborator, all required
        self,
        datasources: DatasourceRepository,
        dialects: Sequence[str],
        dialect_registry: str,
        dsn_schemes: Mapping[str, str],
        cipher: SecretCipher,
        env: Mapping[str, str],
        engines: EngineInvalidator,
    ) -> None:
        self._datasources = datasources
        self._dialects = list(dialects)
        self._dialect_registry = dialect_registry
        self._dsn_schemes = dict(dsn_schemes)
        self._cipher = cipher
        self._env = env
        self._engines = engines

    def register(
        self,
        name: str,
        dialect: str,
        connection: DatasourceConnection,
        description: str | None,
    ) -> Datasource:
        self._require_known_dialect(dialect)
        # Proves the DSN is renderable — an unknown dialect has no driver
        # scheme — before anything is encrypted or written.
        self._scheme_for(dialect)
        datasource = Datasource(
            name=name,
            dialect=dialect,
            host=connection.host,
            port=connection.port,
            database=connection.database,
            username=connection.username,
            password_ciphertext=(
                self._cipher.encrypt(connection.password) if connection.password else None
            ),
            options=connection.options,
            description=description,
        )
        self._datasources.add(datasource)
        return datasource

    def register_from_env(
        self, name: str, dialect: str, dsn_env_var: str, description: str | None
    ) -> Datasource:
        self._require_known_dialect(dialect)
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

    def _require_known_dialect(self, dialect: str) -> None:
        if dialect not in self._dialects:
            raise UnknownRegistryKeyError(self._dialect_registry, dialect, self._dialects)

    def _scheme_for(self, dialect: str) -> str:
        try:
            return self._dsn_schemes[dialect]
        except KeyError:
            raise UnknownRegistryKeyError(
                "dsn_schemes", dialect, sorted(self._dsn_schemes)
            ) from None
