from __future__ import annotations

from sqlalchemy import Engine, text


def test_postgres_is_version_18(engine: Engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SHOW server_version_num")).scalar_one()
    assert int(version) >= 180000


def test_paradedb_extensions_are_available(engine: Engine) -> None:
    with engine.connect() as conn:
        installed = {
            row[0]
            for row in conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('pg_search', 'vector')")
            )
        }
    assert installed == {"pg_search", "vector"}
