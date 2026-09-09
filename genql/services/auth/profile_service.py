"""A thin pass-through over UserProfileRepository. Exists as its own service
(rather than the controller calling the repository directly) only to match
the codebase's controller-never-touches-a-repository convention."""

from __future__ import annotations

from genql.domain.entities.user_profile import UserProfile
from genql.domain.ports.user_profile_repository import UserProfileRepository


class ProfileService:
    def __init__(self, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    def get_profile(self, user_id: str) -> UserProfile:
        return self._profiles.get_or_default(user_id)

    def update_theme(self, user_id: str, theme: str) -> None:
        self._profiles.update_theme(user_id, theme)
