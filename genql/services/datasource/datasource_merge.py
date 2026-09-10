"""Applies a DatasourceUpdate onto the row it edits.

Kept apart from DatasourceService because it is the one piece of update that
is pure: given a datasource, a patch and a cipher it yields the row to write,
and it decides nothing about environment variables, pooled engines or
persistence. That makes the rule it enforces — a datasource says where its
warehouse is in exactly one of two ways — testable on its own.

The two ways are mutually exclusive, so an edit that names any endpoint field
drops the environment variable, and an edit that names an environment variable
drops the endpoint *and* the stored password. Mentioning both is resolved in
favour of the endpoint: it is the more specific instruction, and it is the one
the connect form sends.
"""

from __future__ import annotations

from typing import Any

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import IncompleteDatasourceConnectionError
from genql.domain.ports.secret_cipher import SecretCipher
from genql.domain.value_objects.datasource_update import ENDPOINT_FIELDS, DatasourceUpdate


def merge(datasource: Datasource, patch: DatasourceUpdate, cipher: SecretCipher) -> Datasource:
    changes: dict[str, Any] = patch.changes()
    if patch.touches_endpoint():
        changes["dsn_env_var"] = None
    elif changes.get("dsn_env_var"):
        changes.update({field: None for field in ENDPOINT_FIELDS})
        changes["password_ciphertext"] = None
    if patch.password is not None:
        # "" is the instruction to forget the credential, not to store an
        # empty one: a datasource with an empty ciphertext would decrypt to a
        # blank password and fail with a permission error instead of a clear one.
        changes["password_ciphertext"] = cipher.encrypt(patch.password) if patch.password else None
    merged = datasource.model_copy(update=changes)
    _require_connectable(merged)
    return merged


def _require_connectable(datasource: Datasource) -> None:
    if datasource.dsn_env_var:
        return
    missing = [field for field in ENDPOINT_FIELDS if not getattr(datasource, field)]
    if missing:
        raise IncompleteDatasourceConnectionError(datasource.name, missing)
