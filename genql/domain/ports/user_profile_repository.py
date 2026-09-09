from __future__ import annotations

from typing import Protocol

from genql.domain.entities.user_profile import UserProfile


class UserProfileRepository(Protocol):
    def get_or_default(self, user_id: str) -> UserProfile: ...
    def update_theme(self, user_id: str, theme: str) -> None: ...
