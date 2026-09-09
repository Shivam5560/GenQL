# genql/infrastructure/auth/gotrue_jwt_verifier.py
"""Verifies HS256 access tokens issued by the self-hosted GoTrue service
(docker/compose.yaml's `gotrue`), using the same shared secret GoTrue signs
with (Settings.gotrue_jwt_secret == the gotrue service's GOTRUE_JWT_SECRET).

GenQL never issues a token here — this class only ever calls jwt.decode.
`sub` and `email` are the claims GoTrue's own tokens always carry; reading
them is not a guess about GoTrue's token shape, it is GoTrue's documented
JWT contract.
"""

from __future__ import annotations

import jwt

from genql.domain.errors import InvalidAccessTokenError
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

_ALGORITHM = "HS256"


class GoTrueJwtVerifier:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify(self, access_token: str) -> AuthenticatedUser:
        try:
            payload = jwt.decode(
                access_token,
                self._secret,
                algorithms=[_ALGORITHM],
                options={"require": ["sub", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidAccessTokenError(f"access token is invalid or expired: {exc}") from exc

        email = payload.get("email")
        if not email:
            raise InvalidAccessTokenError("access token carries no email claim")
        return AuthenticatedUser(user_id=str(payload["sub"]), email=str(email))
