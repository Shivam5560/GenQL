"""Reversible encryption for the one secret GenQL now stores.

Registering a warehouse by host and port means the password has to live
somewhere, and the semantic store is where. A port rather than a direct
dependency for the usual reason — DatasourceService may not import
infrastructure — and a reversible cipher rather than a hash because the DSN
has to be reconstructed at connect time, which is the difference between this
and how user passwords are handled.

The key itself never appears in this package. The composition root reads it
from the environment and hands the implementation a configured instance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretCipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...
