"""Database query and engine functions."""

from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, RowMapping

from app.db.records import ArticleRecord, OneTimePurchase
from app.db.schema import articles, metadata, one_time_purchases, wallet_principals
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
    """Return public metadata for all articles ordered by slug."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(
                articles.c.title,
                articles.c.author,
                articles.c.published_at,
                articles.c.price,
                articles.c.slug,
            ).order_by(articles.c.slug)
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


def get_article_by_slug(engine: Engine, slug: str) -> ArticleRecord | None:
    """Return one article by its slug."""
    with engine.connect() as connection:
        row = (
            connection.execute(select(articles).where(articles.c.slug == slug))
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    return _article_record(row)


def insert_one_time_purchase(
    engine: Engine,
    purchase: OneTimePurchase,
    article_id: UUID,
) -> OneTimePurchase:
    """Persist a wallet principal and one-time purchase."""
    with engine.begin() as connection:
        connection.execute(
            insert(wallet_principals)
            .values(wallet_address=purchase.wallet_address, created_at=text("now()"))
            .on_conflict_do_nothing(index_elements=[wallet_principals.c.wallet_address])
        )
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
) -> OneTimePurchase | None:
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
        title=row["title"],
        author=row["author"],
        published_date=row["published_at"],
        price=row["price"],
        license=row["license"],
        summary=row["summary"],
        tags=list(row["tags"]),
        key_claims=list(row["key_claims"]),
        allowed_excerpts=list(row["allowed_excerpts"]),
        suggested_citation=row["suggested_citation"],
        slug=row["slug"],
        body=row["body"],
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
