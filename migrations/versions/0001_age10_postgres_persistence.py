"""Create AGE-10 Postgres persistence tables.

Revision ID: 0001_age10_postgres_persistence
Revises:
Create Date: 2026-04-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_age10_postgres_persistence"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the AGE-10 foundation schema."""
    op.execute("""
        CREATE TABLE wallet_principals (
            wallet_address TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT wallet_principals_address_nonempty
                CHECK (wallet_address <> '')
        )
    """)
    op.execute("""
        CREATE TABLE publishers (
            id UUID PRIMARY KEY,
            handle TEXT NOT NULL,
            display_name TEXT NOT NULL,
            recipient_address TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT publishers_handle_nonempty CHECK (handle <> ''),
            CONSTRAINT publishers_handle_key UNIQUE (handle)
        )
    """)
    op.execute("""
        CREATE TABLE articles (
            id UUID PRIMARY KEY,
            publisher_id UUID NOT NULL REFERENCES publishers (id),
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            published_at DATE NOT NULL,
            price NUMERIC NOT NULL,
            license TEXT NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT[] NOT NULL,
            key_claims TEXT[] NOT NULL,
            allowed_excerpts TEXT[] NOT NULL,
            suggested_citation TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT articles_slug_nonempty CHECK (slug <> ''),
            CONSTRAINT articles_price_positive CHECK (price > 0),
            CONSTRAINT articles_publisher_slug_key UNIQUE (publisher_id, slug),
            CONSTRAINT articles_slug_key UNIQUE (slug)
        )
    """)
    op.execute("""
        CREATE TABLE one_time_purchases (
            id UUID PRIMARY KEY,
            wallet_address TEXT NOT NULL
                REFERENCES wallet_principals (wallet_address),
            article_id UUID NOT NULL REFERENCES articles (id),
            payment_reference TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            currency TEXT NOT NULL,
            network TEXT NOT NULL,
            receipt JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT one_time_purchases_reference_nonempty
                CHECK (payment_reference <> ''),
            CONSTRAINT one_time_purchases_amount_positive CHECK (amount > 0),
            CONSTRAINT one_time_purchases_payment_reference_key
                UNIQUE (payment_reference),
            CONSTRAINT one_time_purchases_wallet_article_key
                UNIQUE (wallet_address, article_id)
        )
    """)
    op.execute("""
        CREATE TABLE subscriptions (
            id UUID PRIMARY KEY,
            wallet_address TEXT NOT NULL
                REFERENCES wallet_principals (wallet_address),
            publisher_id UUID NOT NULL REFERENCES publishers (id),
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            payment_reference TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            currency TEXT NOT NULL,
            network TEXT NOT NULL,
            receipt JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT subscriptions_period_valid
                CHECK (period_end > period_start),
            CONSTRAINT subscriptions_amount_positive CHECK (amount > 0),
            CONSTRAINT subscriptions_payment_reference_key
                UNIQUE (payment_reference),
            CONSTRAINT subscriptions_wallet_publisher_period_key
                UNIQUE (wallet_address, publisher_id, period_start, period_end)
        )
    """)
    op.execute("""
        CREATE TABLE usage_events (
            id UUID PRIMARY KEY,
            wallet_address TEXT NOT NULL
                REFERENCES wallet_principals (wallet_address),
            article_id UUID NOT NULL REFERENCES articles (id),
            event_type TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT usage_events_type_nonempty CHECK (event_type <> '')
        )
    """)
    op.execute("""
        CREATE TABLE feedback (
            id UUID PRIMARY KEY,
            wallet_address TEXT NOT NULL
                REFERENCES wallet_principals (wallet_address),
            article_id UUID NOT NULL REFERENCES articles (id),
            is_current BOOLEAN NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX feedback_one_current_per_wallet_article
            ON feedback (wallet_address, article_id)
            WHERE is_current IS TRUE
    """)


def downgrade() -> None:
    """Drop the AGE-10 foundation schema."""
    op.execute("DROP INDEX feedback_one_current_per_wallet_article")
    op.execute("DROP TABLE feedback")
    op.execute("DROP TABLE usage_events")
    op.execute("DROP TABLE subscriptions")
    op.execute("DROP TABLE one_time_purchases")
    op.execute("DROP TABLE articles")
    op.execute("DROP TABLE publishers")
    op.execute("DROP TABLE wallet_principals")
