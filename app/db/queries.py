"""Database engine and cross-cutting query helpers."""

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from app.db.schema import metadata, wallet_principals


def create_database_engine(database_url: str) -> Engine:
    """Create a Postgres SQLAlchemy engine from an explicit URL."""
    return create_engine(database_url)


def verify_database(engine: Engine) -> None:
    """Verify connectivity and that migrations have created expected tables."""
    expected_tables = set(metadata.tables.keys())
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                """
            )
        )
        existing_tables = {str(row["table_name"]) for row in rows.mappings()}
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(f"Database is missing tables: {missing_tables}")


def upsert_wallet_principal(engine: Engine, address: str) -> None:
    """Insert a wallet principal if it does not already exist.

    Args:
        engine: SQLAlchemy engine.
        address: Lowercase wallet address.
    """
    with engine.begin() as connection:
        connection.execute(
            insert(wallet_principals)
            .values(wallet_address=address, created_at=text("now()"))
            .on_conflict_do_nothing(index_elements=[wallet_principals.c.wallet_address])
        )
