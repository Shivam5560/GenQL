"""The root of every typed failure. Every stage returns one of these so
callers can route."""

from __future__ import annotations


class GenqlError(Exception):
    """Base class for every GenQL failure."""
