"""Database query and engine functions."""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.records import ArticleRecord, OneTimePurchase, PublisherRecord
from app.db.schema import (
    articles,
    metadata,
    one_time_purchases,
    publishers,
    wallet_principals,
)
from app.models import ArticleMetadata


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


def list_article_metadata(engine: Engine) -> list[ArticleMetadata]:
    """Return public metadata for all published articles ordered by slug."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles.c.title,
                articles.c.author,
                articles.c.published_at,
                articles.c.price,
                articles.c.slug,
            )
            .where(articles.c.status == "published")
            .order_by(articles.c.slug)
        )
        return [
            ArticleMetadata(
                title=row["title"],
                author=row["author"],
                published_date=row["published_at"],
                price=str(row["price"]),
                slug=row["slug"],
            )
            for row in rows.mappings()
        ]


def list_articles(engine: Engine) -> list[ArticleRecord]:
    """Return all articles ordered by slug."""
    with engine.connect() as connection:
        rows = connection.execute(select(articles).order_by(articles.c.slug))
        return [_article_record(row) for row in rows.mappings()]


def get_article_by_slug(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one published article by its slug."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(articles)
                .where(articles.c.slug == slug)
                .where(articles.c.status == "published")
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def get_article_by_slug_for_owner(engine: Engine, slug: str) -> Optional[ArticleRecord]:
    """Return one article by slug regardless of status.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.

    Returns:
        ArticleRecord if found, None otherwise.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(select(articles).where(articles.c.slug == slug))
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


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


def insert_one_time_purchase(
    engine: Engine,
    purchase: OneTimePurchase,
    article_id: UUID,
) -> OneTimePurchase:
    """Persist a wallet principal and one-time purchase."""
    upsert_wallet_principal(engine, purchase.wallet_address)
    with engine.begin() as connection:
        result = connection.execute(
            insert(one_time_purchases)
            .values(
                id=text("gen_random_uuid()"),
                wallet_address=purchase.wallet_address,
                article_id=article_id,
                payment_reference=purchase.payment_reference,
                amount=purchase.amount,
                currency=purchase.currency,
                network=purchase.network,
                receipt=purchase.receipt,
                created_at=text("now()"),
            )
            .on_conflict_do_nothing(
                index_elements=[one_time_purchases.c.payment_reference]
            )
        )
    if result.rowcount == 1:
        return purchase
    existing_purchase = lookup_purchase_by_payment_reference(
        engine, purchase.payment_reference
    )
    if existing_purchase is None:
        raise RuntimeError("Purchase conflict did not return an existing row")
    if existing_purchase != purchase:
        raise RuntimeError("Payment reference is bound to different purchase details")
    return existing_purchase


def lookup_purchase_by_payment_reference(
    engine: Engine,
    payment_reference: str,
) -> Optional[OneTimePurchase]:
    """Return the purchase stored for a payment reference."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    articles.c.slug.label("article_slug"),
                    one_time_purchases.c.wallet_address,
                    one_time_purchases.c.payment_reference,
                    one_time_purchases.c.amount,
                    one_time_purchases.c.currency,
                    one_time_purchases.c.network,
                    one_time_purchases.c.receipt,
                )
                .select_from(
                    one_time_purchases.join(
                        articles,
                        one_time_purchases.c.article_id == articles.c.id,
                    )
                )
                .where(one_time_purchases.c.payment_reference == payment_reference)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _one_time_purchase(row)


def _article_record(row: RowMapping) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        publisher_id=row["publisher_id"],
        title=row["title"],
        status=row["status"],
        author=row["author"],
        published_date=row["published_at"],
        price=row["price"],
        license=row["license"],
        summary=row["summary"],
        tags=list(row["tags"]) if row["tags"] is not None else None,
        key_claims=list(row["key_claims"]) if row["key_claims"] is not None else None,
        allowed_excerpts=(
            list(row["allowed_excerpts"])
            if row["allowed_excerpts"] is not None
            else None
        ),
        suggested_citation=row["suggested_citation"],
        slug=row["slug"],
        body=row["body"],
    )


def insert_article(
    engine: Engine,
    article_id: UUID,
    publisher_id: UUID,
    slug: str,
    title: str,
    body: str,
    author: Optional[str],
    price: Optional[Decimal],
    license: Optional[str],
    summary: Optional[str],
    tags: Optional[list[str]],
    key_claims: Optional[list[str]],
    allowed_excerpts: Optional[list[str]],
    suggested_citation: Optional[str],
) -> Optional[ArticleRecord]:
    """Insert a draft article. Return None on (publisher_id, slug) conflict.

    Args:
        engine: SQLAlchemy engine.
        article_id: UUID for the new article.
        publisher_id: Publisher that owns the article.
        slug: URL slug.
        title: Article title.
        body: Markdown body text.
        author: Optional author name.
        price: Optional price.
        license: Optional license string.
        summary: Optional summary.
        tags: Optional list of tags.
        key_claims: Optional list of key claims.
        allowed_excerpts: Optional list of allowed excerpts.
        suggested_citation: Optional citation string.

    Returns:
        ArticleRecord if inserted, None if slug conflict.
    """
    with engine.begin() as connection:
        row = (
            connection.execute(
                insert(articles)
                .values(
                    id=article_id,
                    publisher_id=publisher_id,
                    slug=slug,
                    title=title,
                    status="draft",
                    author=author,
                    price=price,
                    license=license,
                    summary=summary,
                    tags=tags,
                    key_claims=key_claims,
                    allowed_excerpts=allowed_excerpts,
                    suggested_citation=suggested_citation,
                    body=body,
                    created_at=text("now()"),
                    updated_at=text("now()"),
                )
                .on_conflict_do_nothing(
                    constraint="articles_publisher_slug_key",
                )
                .returning(articles)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def update_article(
    engine: Engine, slug: str, publisher_id: UUID, values: dict[str, object]
) -> None:
    """Update article fields by slug and publisher_id.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
        values: Column-value pairs to update.
    """
    values["updated_at"] = text("now()")
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(**values)
        )


def publish_article(engine: Engine, slug: str, publisher_id: UUID) -> None:
    """Set article status to published with current date.

    Args:
        engine: SQLAlchemy engine.
        slug: Article slug.
        publisher_id: Publisher UUID (ownership filter).
    """
    with engine.begin() as connection:
        connection.execute(
            update(articles)
            .where(articles.c.slug == slug)
            .where(articles.c.publisher_id == publisher_id)
            .values(
                status="published",
                published_at=date.today(),
                updated_at=text("now()"),
            )
        )


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


def _one_time_purchase(row: RowMapping) -> OneTimePurchase:
    return OneTimePurchase(
        article_slug=row["article_slug"],
        wallet_address=row["wallet_address"],
        payment_reference=row["payment_reference"],
        amount=row["amount"],
        currency=row["currency"],
        network=row["network"],
        receipt=dict(row["receipt"]),
    )
