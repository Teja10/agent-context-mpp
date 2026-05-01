from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    Table,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT, UUID as PG_UUID, insert

metadata = MetaData()

wallet_principals = Table(
    "wallet_principals",
    metadata,
    Column("wallet_address", TEXT, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("wallet_address <> ''", name="wallet_principals_address_nonempty"),
)
publishers = Table(
    "publishers",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("handle", TEXT, nullable=False),
    Column("display_name", TEXT, nullable=False),
    Column("recipient_address", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("handle", name="publishers_handle_key"),
    CheckConstraint("handle <> ''", name="publishers_handle_nonempty"),
)
articles = Table(
    "articles",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "publisher_id",
        PG_UUID(as_uuid=True),
        ForeignKey("publishers.id"),
        nullable=False,
    ),
    Column("slug", TEXT, nullable=False),
    Column("title", TEXT, nullable=False),
    Column("author", TEXT, nullable=False),
    Column("published_at", Date, nullable=False),
    Column("price", Numeric(), nullable=False),
    Column("license", TEXT, nullable=False),
    Column("summary", TEXT, nullable=False),
    Column("tags", ARRAY(TEXT), nullable=False),
    Column("key_claims", ARRAY(TEXT), nullable=False),
    Column("allowed_excerpts", ARRAY(TEXT), nullable=False),
    Column("suggested_citation", TEXT, nullable=False),
    Column("body", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("publisher_id", "slug", name="articles_publisher_slug_key"),
    UniqueConstraint("slug", name="articles_slug_key"),
    CheckConstraint("slug <> ''", name="articles_slug_nonempty"),
    CheckConstraint("price > 0", name="articles_price_positive"),
)
one_time_purchases = Table(
    "one_time_purchases",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "wallet_address",
        TEXT,
        ForeignKey("wallet_principals.wallet_address"),
        nullable=False,
    ),
    Column(
        "article_id", PG_UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    ),
    Column("payment_reference", TEXT, nullable=False),
    Column("amount", Numeric(), nullable=False),
    Column("currency", TEXT, nullable=False),
    Column("network", TEXT, nullable=False),
    Column("receipt", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "payment_reference", name="one_time_purchases_payment_reference_key"
    ),
    UniqueConstraint(
        "wallet_address",
        "article_id",
        name="one_time_purchases_wallet_article_key",
    ),
    CheckConstraint(
        "payment_reference <> ''", name="one_time_purchases_reference_nonempty"
    ),
    CheckConstraint("amount > 0", name="one_time_purchases_amount_positive"),
)
subscriptions = Table(
    "subscriptions",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "wallet_address",
        TEXT,
        ForeignKey("wallet_principals.wallet_address"),
        nullable=False,
    ),
    Column(
        "publisher_id",
        PG_UUID(as_uuid=True),
        ForeignKey("publishers.id"),
        nullable=False,
    ),
    Column("period_start", Date, nullable=False),
    Column("period_end", Date, nullable=False),
    Column("payment_reference", TEXT, nullable=False),
    Column("amount", Numeric(), nullable=False),
    Column("currency", TEXT, nullable=False),
    Column("network", TEXT, nullable=False),
    Column("receipt", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("payment_reference", name="subscriptions_payment_reference_key"),
    UniqueConstraint(
        "wallet_address",
        "publisher_id",
        "period_start",
        "period_end",
        name="subscriptions_wallet_publisher_period_key",
    ),
    CheckConstraint("period_end > period_start", name="subscriptions_period_valid"),
    CheckConstraint("amount > 0", name="subscriptions_amount_positive"),
)
usage_events = Table(
    "usage_events",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "wallet_address",
        TEXT,
        ForeignKey("wallet_principals.wallet_address"),
        nullable=False,
    ),
    Column(
        "article_id", PG_UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    ),
    Column("event_type", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("event_type <> ''", name="usage_events_type_nonempty"),
)
feedback = Table(
    "feedback",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "wallet_address",
        TEXT,
        ForeignKey("wallet_principals.wallet_address"),
        nullable=False,
    ),
    Column(
        "article_id", PG_UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    ),
    Column("is_current", Boolean, nullable=False),
    Column("body", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index(
    "feedback_one_current_per_wallet_article",
    feedback.c.wallet_address,
    feedback.c.article_id,
    unique=True,
    postgresql_where=feedback.c.is_current.is_(True),
)


@dataclass(frozen=True)
class ArticleRecord:
    """Article content loaded from Postgres."""

    id: UUID
    title: str
    author: str
    published_date: date
    price: Decimal
    license: str
    summary: str
    tags: list[str]
    key_claims: list[str]
    allowed_excerpts: list[str]
    suggested_citation: str
    slug: str
    body: str


@dataclass(frozen=True)
class OneTimePurchase:
    """One-time article purchase stored by payment reference."""

    article_slug: str
    wallet_address: str
    payment_reference: str
    amount: Decimal
    currency: str
    network: str
    receipt: dict[str, str]


def create_database_engine(database_url: str) -> Engine:
    """Create a Postgres SQLAlchemy engine from an explicit URL."""
    return create_engine(database_url)


def verify_database(engine: Engine) -> None:
    """Verify connectivity and that migrations have created AGE-10 tables."""
    expected_tables = {
        "wallet_principals",
        "publishers",
        "articles",
        "one_time_purchases",
        "subscriptions",
        "usage_events",
        "feedback",
    }
    with engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version"))
        if version.scalar_one() != "0001_age10_postgres_persistence":
            raise RuntimeError("Database migrations are not at AGE-10 head")
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
        raise RuntimeError(f"Database is missing AGE-10 tables: {missing_tables}")


def list_articles(engine: Engine) -> list[ArticleRecord]:
    """Return all public articles ordered by slug."""
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
) -> OneTimePurchase:
    """Persist a wallet principal and one-time purchase."""
    article = get_article_by_slug(engine, purchase.article_slug)
    if article is None:
        raise ValueError("Article not found")
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
                article_id=article.id,
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
