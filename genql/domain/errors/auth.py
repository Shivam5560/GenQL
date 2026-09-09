"""Failures verifying a caller's identity. GenQL issues nothing here — this
is entirely about rejecting a bad GoTrue-issued token."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class InvalidAccessTokenError(GenqlError):
    """The presented access token is missing, malformed, expired, or fails
    signature verification against Settings.gotrue_jwt_secret."""
