"""One container per process, reached through the app rather than a module
global, so a test can build an app around a container with a fake graph."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, Request

from genql.domain.errors import InvalidAccessTokenError
from genql.domain.value_objects.authenticated_user import AuthenticatedUser


def get_container(request: Request) -> Any:
    return request.app.state.container


def get_current_user(
    container: Annotated[Any, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if authorization is None or not authorization.startswith("Bearer "):
        raise InvalidAccessTokenError("missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ")
    verified: AuthenticatedUser = container.token_verifier().verify(token)
    return verified
