"""Failures raised reading thread history."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class ThreadOwnershipError(GenqlError):
    """A thread exists but does not belong to the requesting user.

    Controllers translate this to 404, not 403 — thread existence is not
    leaked to a non-owner.
    """
