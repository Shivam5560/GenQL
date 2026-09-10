"""Failures raised while resolving or registering a datasource."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class DatasourceError(GenqlError):
    """A datasource or schema registration could not be resolved."""


class UnknownDatasourceError(DatasourceError):
    def __init__(self, name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{name!r} is not a registered datasource. Available: {options}")
        self.name = name


class DuplicateDatasourceError(DatasourceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"datasource {name!r} is already registered")
        self.name = name


class MissingDatasourceSecretError(DatasourceError):
    """A datasource carries neither a stored credential nor a readable one.

    `env_var` is the variable that was consulted, when one was named at all.
    A datasource registered through the API stores its own credential and
    names no variable, so the two cases produce different sentences.
    """

    def __init__(self, datasource_name: str, env_var: str | None = None) -> None:
        if env_var:
            message = (
                f"datasource {datasource_name!r} names environment variable {env_var!r}, "
                "which is unset or empty"
            )
        else:
            message = (
                f"datasource {datasource_name!r} has no stored connection credential. "
                "Reconnect the warehouse from the datasources page."
            )
        super().__init__(message)
        self.datasource_name = datasource_name
        self.env_var = env_var


class MissingEncryptionKeyError(DatasourceError):
    """GENQL_SECRET_KEY is unset, so no warehouse password can be stored.

    Raised at registration rather than at connect time: a datasource whose
    password could not be encrypted must never reach the row, because the row
    would then be a warehouse nobody can connect to and nobody can repair
    without re-entering credentials this API deliberately cannot read back.
    """

    def __init__(self) -> None:
        super().__init__(
            "GENQL_SECRET_KEY is unset or empty, so warehouse credentials cannot be "
            "encrypted. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and set it on the server.'
        )


class UndecryptableDatasourceSecretError(DatasourceError):
    """The stored credential does not decrypt under the current key.

    Almost always a rotated or mistyped GENQL_SECRET_KEY rather than a corrupt
    row, which is why the message says so: the fix is the key, or re-entering
    the connection.
    """

    def __init__(self, datasource_name: str) -> None:
        super().__init__(
            f"the stored credential for datasource {datasource_name!r} could not be "
            "decrypted with the current GENQL_SECRET_KEY. Restore the original key, "
            "or reconnect the warehouse to store its credential again."
        )
        self.datasource_name = datasource_name


class EmptySchemaError(DatasourceError):
    """Registration found no readable objects in the named schema.

    Distinct from UnknownSchemaRegistrationError, which means "no such row in
    the semantic store". A reader that returns nothing cannot tell an empty
    schema apart from an absent one or one this role cannot see, so the
    message names all three rather than asserting the wrong one.
    """

    def __init__(self, qualified_name: str) -> None:
        super().__init__(
            f"{qualified_name!r} exposes no readable objects: it is empty, does not "
            "exist, or is not visible to the role this datasource connects as"
        )
        self.qualified_name = qualified_name


class UnknownSchemaRegistrationError(DatasourceError):
    def __init__(self, qualified_name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{qualified_name!r} is not a registered schema. Available: {options}")
        self.qualified_name = qualified_name


class AmbiguousScopeError(DatasourceError):
    """No datasource was given and more than one is enabled."""

    def __init__(self, candidates: list[str]) -> None:
        options = ", ".join(candidates)
        super().__init__(
            f"no datasource given and {len(candidates)} are enabled ({options}). "
            "Pass --datasource, or set GENQL_DEFAULT_DATASOURCE."
        )
        self.candidates = candidates


class MissingReadonlySecretError(DatasourceError):
    """GENQL_READONLY_DB_PASSWORD is unset, so no read-only engine can be built.

    Separate from MissingDatasourceSecretError: that one means a datasource's
    own DSN variable is missing, this one means the process-wide read-only
    role password is, and the fix is different in each case.
    """

    def __init__(self, datasource_name: str) -> None:
        super().__init__(
            f"no read-only engine can be built for datasource {datasource_name!r}: "
            "GENQL_READONLY_DB_PASSWORD is unset or empty"
        )
        self.datasource_name = datasource_name
