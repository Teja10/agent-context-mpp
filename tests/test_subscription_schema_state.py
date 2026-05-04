"""Schema-level assertions for the AGE-16 migration cutover."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _column_type(engine: Engine, table: str, column: str) -> str:
    """Return the udt_name (e.g. 'timestamptz') for a given column."""
    with engine.connect() as connection:
        return str(
            connection.execute(
                text(
                    """
                    select udt_name
                      from information_schema.columns
                     where table_schema = 'public'
                       and table_name = :t
                       and column_name = :c
                    """
                ),
                {"t": table, "c": column},
            ).scalar_one()
        )


def _index_exists(engine: Engine, name: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.execute(
                text("select 1 from pg_indexes where indexname = :n"),
                {"n": name},
            ).scalar_one_or_none()
        )


def _table_exists(engine: Engine, name: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.execute(
                text(
                    """
                    select 1 from information_schema.tables
                     where table_schema = 'public' and table_name = :n
                    """
                ),
                {"n": name},
            ).scalar_one_or_none()
        )


def test_subscriptions_period_columns_are_timestamptz(engine: Engine) -> None:
    assert _column_type(engine, "subscriptions", "period_start") == "timestamptz"
    assert _column_type(engine, "subscriptions", "period_end") == "timestamptz"


def test_subscription_authorizations_table_exists(engine: Engine) -> None:
    assert _table_exists(engine, "subscription_authorizations")
    assert _table_exists(engine, "subscription_authorization_keys")
    assert _table_exists(engine, "subscription_renewal_attempts")


def test_partial_unique_index_on_active_authorization(engine: Engine) -> None:
    assert _index_exists(engine, "subscription_authorizations_one_active")
