"""The fields an edit to a registered datasource may change.

Every field is optional and `None` means "leave this alone", which is the only
representation that lets one shape serve both `PATCH /datasources/{name}` and
`genql datasource update --host ...`: a caller that says nothing about the
password must not clear it, and a caller cannot say "keep the password" by
sending it back, because no endpoint ever hands it out.

Clearing is therefore spelled with an empty string rather than with `None`:
`password=""` removes the stored credential, `options=""` removes the driver
query string. `enabled` needs no such spelling — `False` is already the
instruction.

`changes` deliberately reports only what was mentioned. The service applies it
onto the row it read, so an edit is never a whole-row overwrite and two people
editing different fields of the same datasource do not clobber each other.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

#: Columns that only render a DSN together, so they are validated together.
ENDPOINT_FIELDS: tuple[str, ...] = ("host", "port", "database", "username")


class DatasourceUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    dialect: str | None = None
    dsn_env_var: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, gt=0, le=65535)
    database: str | None = None
    username: str | None = None
    #: Plaintext, inbound only. Encrypted by the service; "" clears it.
    password: str | None = None
    options: str | None = None
    description: str | None = None
    enabled: bool | None = None

    #: Text columns an empty string clears rather than sets.
    CLEARABLE: ClassVar[tuple[str, ...]] = ("dsn_env_var", "options", "description")

    def changes(self) -> dict[str, Any]:
        """The mentioned fields only, password excluded.

        The password is left out because it is the one field whose stored form
        is not its given form — the service encrypts it and writes
        `password_ciphertext` instead. A clearable field mentioned as `""`
        comes back as `None`: present in the mapping, so it is applied, with
        the value that empties the column.
        """
        mentioned = {
            field: value
            for field, value in self.model_dump(exclude={"password"}).items()
            if value is not None
        }
        return {
            field: (None if field in self.CLEARABLE and value == "" else value)
            for field, value in mentioned.items()
        }

    def touches_endpoint(self) -> bool:
        return any(getattr(self, field) is not None for field in ENDPOINT_FIELDS)
