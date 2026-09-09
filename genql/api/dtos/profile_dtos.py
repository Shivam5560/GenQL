"""The wire contract for GET/PATCH /profile."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from genql.domain.entities.user_profile import UserProfile


class ProfileDto(BaseModel):
    theme_preference: Literal["light", "dark", "system"]

    @classmethod
    def from_domain(cls, profile: UserProfile) -> ProfileDto:
        return cls(theme_preference=profile.theme_preference)


class UpdateThemeRequest(BaseModel):
    theme_preference: Literal["light", "dark", "system"]
