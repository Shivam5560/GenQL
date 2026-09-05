"""SQLAlchemy engine construction.

Engines are created here and injected. No module builds its own.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine


def create_engine_from_dsn(dsn: str) -> Engine:
    return create_engine(dsn, pool_pre_ping=True, future=True)
