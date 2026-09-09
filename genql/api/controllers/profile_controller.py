"""Two routes, no logic: read the caller's profile, or update its theme.
Email and display name are not here — they come from the JWT, which the
frontend already has from GoTrue's own session response, so there is
nothing this route would add for them."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.profile_dtos import ProfileDto, UpdateThemeRequest
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileDto)
def get_profile(
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileDto:
    profile = container.profile_service().get_profile(user.user_id)
    return ProfileDto.from_domain(profile)


@router.patch("/profile", response_model=ProfileDto)
def update_theme(
    request: UpdateThemeRequest,
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ProfileDto:
    container.profile_service().update_theme(user.user_id, request.theme_preference)
    profile = container.profile_service().get_profile(user.user_id)
    return ProfileDto.from_domain(profile)
