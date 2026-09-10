"""Fernet, keyed once at startup, for the warehouse passwords the store holds.

Fernet rather than a hand-rolled AES-GCM wrapper: it is authenticated (a
tampered ciphertext raises rather than decrypting to garbage), it carries its
own version byte and timestamp so a future key rotation has something to hang
off, and it is one line to use correctly. The alternative here is not a
stronger cipher, it is a subtly wrong one.

A blank or malformed key raises at the point of use rather than at
construction: `Settings.secret_key` defaults to empty exactly like
`openrouter_api_key` so that `migrations/env.py` and every container unit test
can build a container without one, and the typed failure belongs where a
credential is actually being written or read.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from genql.domain.errors import MissingEncryptionKeyError


class FernetSecretCipher:
    def __init__(self, key: str) -> None:
        self._key = key.strip()

    def encrypt(self, plaintext: str) -> str:
        return self._fernet().encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        # InvalidToken is deliberately not caught here: the caller knows which
        # datasource it was reading and can name it, and this class cannot.
        return self._fernet().decrypt(ciphertext.encode()).decode()

    def _fernet(self) -> Fernet:
        if not self._key:
            raise MissingEncryptionKeyError
        try:
            return Fernet(self._key.encode())
        except (ValueError, TypeError) as exc:
            raise MissingEncryptionKeyError from exc
