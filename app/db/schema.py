"""SQLAlchemy Core table definitions for the Thoth database."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, TEXT, UUID as PG_UUID

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
    Column(
        "owner_address",
        TEXT,
        ForeignKey("wallet_principals.wallet_address"),
        nullable=False,
    ),
    Column("description", TEXT, nullable=False),
    Column("status", TEXT, nullable=False),
    Column("recipient_address", TEXT, nullable=False),
    Column("default_article_price", Numeric(), nullable=False),
    Column("default_subscription_price", Numeric(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("handle", name="publishers_handle_key"),
    UniqueConstraint("recipient_address", name="publishers_recipient_key"),
    CheckConstraint("handle <> ''", name="publishers_handle_nonempty"),
    CheckConstraint("status IN ('active', 'disabled')", name="publishers_status_valid"),
    CheckConstraint(
        "default_article_price > 0", name="publishers_article_price_positive"
    ),
    CheckConstraint(
        "default_subscription_price > 0",
        name="publishers_subscription_price_positive",
    ),
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
    Column("status", TEXT, nullable=False),
    Column("author", TEXT, nullable=True),
    Column("published_at", Date, nullable=True),
    Column("price", Numeric(), nullable=True),
    Column("license", TEXT, nullable=True),
    Column("summary", TEXT, nullable=True),
    Column("tags", ARRAY(TEXT), nullable=True),
    Column("key_claims", ARRAY(TEXT), nullable=True),
    Column("allowed_excerpts", ARRAY(TEXT), nullable=True),
    Column("suggested_citation", TEXT, nullable=True),
    Column("body", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("publisher_id", "slug", name="articles_publisher_slug_key"),
    UniqueConstraint("slug", name="articles_slug_key"),
    CheckConstraint("slug <> ''", name="articles_slug_nonempty"),
    CheckConstraint("price IS NULL OR price > 0", name="articles_price_positive"),
    CheckConstraint("status IN ('draft', 'published')", name="articles_status_valid"),
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
    Column("recipient_wallet", TEXT, nullable=False),
    Column("receipt", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "recipient_wallet <> ''", name="one_time_purchases_recipient_nonempty"
    ),
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
    Column("period_start", DateTime(timezone=True), nullable=False),
    Column("period_end", DateTime(timezone=True), nullable=False),
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
subscription_authorizations = Table(
    "subscription_authorizations",
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
    Column("key_id", TEXT, nullable=False),
    Column("expiry", DateTime(timezone=True), nullable=False),
    Column("status", TEXT, nullable=False),
    Column("authorize_tx_hash", TEXT, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('active', 'cancelled', 'revoked', 'expired', 'renewal_failed')",
        name="subscription_authorizations_status_valid",
    ),
    CheckConstraint("key_id <> ''", name="subscription_authorizations_key_id_nonempty"),
    UniqueConstraint(
        "authorize_tx_hash",
        name="subscription_authorizations_authorize_tx_hash_key",
    ),
)
Index(
    "subscription_authorizations_one_active",
    subscription_authorizations.c.wallet_address,
    subscription_authorizations.c.publisher_id,
    unique=True,
    postgresql_where=subscription_authorizations.c.status == "active",
)
subscription_authorization_keys = Table(
    "subscription_authorization_keys",
    metadata,
    Column(
        "authorization_id",
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_authorizations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("ciphertext", BYTEA, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
subscription_renewal_attempts = Table(
    "subscription_renewal_attempts",
    metadata,
    Column(
        "authorization_id",
        PG_UUID(as_uuid=True),
        ForeignKey("subscription_authorizations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("period_start", DateTime(timezone=True), primary_key=True),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_attempt_at", DateTime(timezone=True), nullable=False),
    Column("last_error", TEXT, nullable=True),
)
