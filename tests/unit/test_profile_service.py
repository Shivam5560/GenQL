"""ProfileService is a thin pass-through — the one thing worth testing is
that an unseen user_id still gets a usable default rather than an error."""

from __future__ import annotations

from genql.domain.entities.user_profile import UserProfile
from genql.services.auth.profile_service import ProfileService


class _Profiles:
    def __init__(self) -> None:
        self._rows: dict[str, UserProfile] = {}

    def get_or_default(self, user_id: str) -> UserProfile:
        return self._rows.get(user_id, UserProfile(user_id=user_id))

    def update_theme(self, user_id: str, theme: str) -> None:
        self._rows[user_id] = UserProfile(user_id=user_id, theme_preference=theme)


def test_get_profile_defaults_to_system_theme_for_an_unseen_user() -> None:
    profile = ProfileService(_Profiles()).get_profile("u-new")

    assert profile.theme_preference == "system"


def test_update_theme_persists_and_is_readable() -> None:
    service = ProfileService(_Profiles())

    service.update_theme("u-1", "dark")

    assert service.get_profile("u-1").theme_preference == "dark"
