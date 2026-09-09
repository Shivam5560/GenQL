"""GoTrueJwtVerifier's whole job: accept a token signed with the right
secret carrying the right claims, reject everything else."""

from __future__ import annotations

import time

import jwt
import pytest

from genql.domain.errors import InvalidAccessTokenError
from genql.infrastructure.auth.gotrue_jwt_verifier import GoTrueJwtVerifier

_SECRET = "test-secret-do-not-use-in-production"


def _token(secret: str = _SECRET, **overrides: object) -> str:
    now = int(time.time())
    payload = {
        "sub": "u-1",
        "email": "shivam@example.com",
        "iat": now,
        "exp": now + 900,
        **overrides,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_a_validly_signed_token_verifies() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)

    user = verifier.verify(_token())

    assert user.user_id == "u-1"
    assert user.email == "shivam@example.com"


def test_a_token_signed_with_the_wrong_secret_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(_token(secret="wrong-secret"))


def test_an_expired_token_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)
    expired = _token(exp=int(time.time()) - 60)

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(expired)


def test_a_token_with_no_email_claim_is_rejected() -> None:
    verifier = GoTrueJwtVerifier(_SECRET)
    now = int(time.time())
    no_email = jwt.encode({"sub": "u-1", "iat": now, "exp": now + 900}, _SECRET, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        verifier.verify(no_email)
