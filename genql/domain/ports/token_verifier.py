"""Verifies a GoTrue-issued access token and extracts the caller's
identity. GenQL never issues a token — only verifies one — so this port has
no issue()/refresh() methods; token lifecycle is entirely GoTrue's."""

from __future__ import annotations

from typing import Protocol

from genql.domain.value_objects.authenticated_user import AuthenticatedUser


class TokenVerifier(Protocol):
    def verify(self, access_token: str) -> AuthenticatedUser: ...
