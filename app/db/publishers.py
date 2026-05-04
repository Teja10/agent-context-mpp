"""Publisher query functions."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.records import PublisherRecord
from app.db.schema import publishers


def create_publisher(
    engine: Engine,
    publisher_id: UUID,
    handle: str,
    display_name: str,
    description: str,
    owner_address: str,
    recipient_address: str,
    default_article_price: Decimal,
    default_subscription_price: Decimal,
) -> Optional[PublisherRecord]:
    """Insert a new publisher with on_conflict_do_nothing on handle.

    Args:
        engine: SQLAlchemy engine.
        publisher_id: UUID for the new publisher.
        handle: Unique publisher handle.
        display_name: Display name.
        description: Publisher description.
        owner_address: Wallet address of the owner.
        recipient_address: Payment recipient address.
        default_article_price: Default price for articles.
        default_subscription_price: Default price for subscriptions.

    Returns:
        PublisherRecord if inserted, None if handle conflict.
    """
    with engine.begin() as connection:
        row = connection.execute(
            insert(publishers)
            .values(
                id=publisher_id,
                handle=handle,
                display_name=display_name,
                owner_address=owner_address,
                description=description,
                status="active",
                recipient_address=recipient_address,
                default_article_price=default_article_price,
                default_subscription_price=default_subscription_price,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing(index_elements=[publishers.c.handle])
            .returning(publishers.c.id)
        ).scalar_one_or_none()
    if row is None:
        return None
    return PublisherRecord(
        id=publisher_id,
        handle=handle,
        display_name=display_name,
        owner_address=owner_address,
        description=description,
        status="active",
        recipient_address=recipient_address,
        default_article_price=default_article_price,
        default_subscription_price=default_subscription_price,
    )


def get_publisher_by_handle(engine: Engine, handle: str) -> Optional[PublisherRecord]:
    """Return a publisher by its unique handle.

    Args:
        engine: SQLAlchemy engine.
        handle: Publisher handle.

    Returns:
        PublisherRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(select(publishers).where(publishers.c.handle == handle))
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _publisher_record(row)


def get_publisher_by_id(
    engine: Engine, publisher_id: UUID
) -> Optional[PublisherRecord]:
    """Return a publisher by its primary key.

    Args:
        engine: SQLAlchemy engine.
        publisher_id: Publisher UUID.

    Returns:
        PublisherRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(publishers).where(publishers.c.id == publisher_id)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _publisher_record(row)


def update_publisher(engine: Engine, handle: str, values: dict[str, object]) -> None:
    """Update publisher fields by handle.

    Args:
        engine: SQLAlchemy engine.
        handle: Publisher handle.
        values: Column-value pairs to update.
    """
    with engine.begin() as connection:
        connection.execute(
            update(publishers).where(publishers.c.handle == handle).values(**values)
        )


def _publisher_record(row: RowMapping) -> PublisherRecord:
    return PublisherRecord(
        id=row["id"],
        handle=row["handle"],
        display_name=row["display_name"],
        owner_address=row["owner_address"],
        description=row["description"],
        status=row["status"],
        recipient_address=row["recipient_address"],
        default_article_price=row["default_article_price"],
        default_subscription_price=row["default_subscription_price"],
    )
