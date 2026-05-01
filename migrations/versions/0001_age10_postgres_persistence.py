"""Create AGE-10 Postgres persistence tables.

Revision ID: 0001_age10_postgres_persistence
Revises:
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_age10_postgres_persistence"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the AGE-10 foundation schema."""
    op.create_table(
        "wallet_principals",
        sa.Column("wallet_address", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "wallet_address <> ''",
            name="wallet_principals_address_nonempty",
        ),
    )
    op.create_table(
        "publishers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("handle", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("recipient_address", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("handle <> ''", name="publishers_handle_nonempty"),
        sa.UniqueConstraint("handle", name="publishers_handle_key"),
    )
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("key_claims", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("allowed_excerpts", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("suggested_citation", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("slug <> ''", name="articles_slug_nonempty"),
        sa.CheckConstraint("price > 0", name="articles_price_positive"),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"]),
        sa.UniqueConstraint("publisher_id", "slug", name="articles_publisher_slug_key"),
        sa.UniqueConstraint("slug", name="articles_slug_key"),
    )
    op.create_table(
        "one_time_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_reference", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("network", sa.Text(), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "payment_reference <> ''",
            name="one_time_purchases_reference_nonempty",
        ),
        sa.CheckConstraint("amount > 0", name="one_time_purchases_amount_positive"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.ForeignKeyConstraint(
            ["wallet_address"], ["wallet_principals.wallet_address"]
        ),
        sa.UniqueConstraint(
            "payment_reference",
            name="one_time_purchases_payment_reference_key",
        ),
        sa.UniqueConstraint(
            "wallet_address",
            "article_id",
            name="one_time_purchases_wallet_article_key",
        ),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payment_reference", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("network", sa.Text(), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "period_end > period_start",
            name="subscriptions_period_valid",
        ),
        sa.CheckConstraint("amount > 0", name="subscriptions_amount_positive"),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"]),
        sa.ForeignKeyConstraint(
            ["wallet_address"], ["wallet_principals.wallet_address"]
        ),
        sa.UniqueConstraint(
            "payment_reference",
            name="subscriptions_payment_reference_key",
        ),
        sa.UniqueConstraint(
            "wallet_address",
            "publisher_id",
            "period_start",
            "period_end",
            name="subscriptions_wallet_publisher_period_key",
        ),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type <> ''", name="usage_events_type_nonempty"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.ForeignKeyConstraint(
            ["wallet_address"], ["wallet_principals.wallet_address"]
        ),
    )
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wallet_address", sa.Text(), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.ForeignKeyConstraint(
            ["wallet_address"], ["wallet_principals.wallet_address"]
        ),
    )
    op.create_index(
        "feedback_one_current_per_wallet_article",
        "feedback",
        ["wallet_address", "article_id"],
        unique=True,
        postgresql_where=sa.text("is_current is true"),
    )


def downgrade() -> None:
    """Drop the AGE-10 foundation schema."""
    op.drop_index("feedback_one_current_per_wallet_article", table_name="feedback")
    op.drop_table("feedback")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("one_time_purchases")
    op.drop_table("articles")
    op.drop_table("publishers")
    op.drop_table("wallet_principals")
