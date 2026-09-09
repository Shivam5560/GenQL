"""The one piece of per-user state GoTrue has no concept of. `user_id` is
GoTrue's auth.users.id, carried as plain text — GenQL never writes to or
joins against auth.* directly, only stores this id as an opaque key."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    theme_preference: Literal["light", "dark", "system"] = "system"
