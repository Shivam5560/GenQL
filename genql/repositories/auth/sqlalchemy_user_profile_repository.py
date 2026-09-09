"""Reads and writes genql_user_profile — the one piece of per-user state
GoTrue has no concept of. No foreign key into auth.users, same reasoning as
genql_thread.user_id: GoTrue owns that table's lifecycle, not this
migration set."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.user_profile import UserProfile
from genql.domain.errors import QueryError

_SELECT = text("""
    SELECT user_id, theme_preference FROM genql.genql_user_profile WHERE user_id = :user_id
""")
_UPSERT = text("""
    INSERT INTO genql.genql_user_profile (user_id, theme_preference)
    VALUES (:user_id, :theme)
    ON CONFLICT (user_id) DO UPDATE SET theme_preference = EXCLUDED.theme_preference
""")


class SqlAlchemyUserProfileRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_or_default(self, user_id: str) -> UserProfile:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT, {"user_id": user_id}).mappings().first()
        return UserProfile.model_validate(dict(row)) if row else UserProfile(user_id=user_id)

    def update_theme(self, user_id: str, theme: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(_UPSERT, {"user_id": user_id, "theme": theme})
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to update theme for {user_id!r}: {exc}") from exc
