"""Add publisher profile columns and constraints.

Revision ID: 0002_age12_publisher_profile
Revises: 0001_age10_postgres_persistence
Create Date: 2026-05-01
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_age12_publisher_profile"
down_revision: str = "0001_age10_postgres_persistence"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Add owner_address, description, status, default prices to publishers."""
    op.add_column(
        "publishers",
        sa.Column(
            "owner_address",
            sa.Text(),
            sa.ForeignKey("wallet_principals.wallet_address"),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "default_article_price",
            sa.Numeric(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "default_subscription_price",
            sa.Numeric(),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_unique_constraint(
        "publishers_recipient_key", "publishers", ["recipient_address"]
    )
    op.create_check_constraint(
        "publishers_status_valid",
        "publishers",
        "status IN ('active', 'disabled')",
    )
    op.create_check_constraint(
        "publishers_article_price_positive",
        "publishers",
        "default_article_price > 0",
    )
    op.create_check_constraint(
        "publishers_subscription_price_positive",
        "publishers",
        "default_subscription_price > 0",
    )


def downgrade() -> None:
    """Remove publisher profile columns and constraints."""
    op.drop_constraint(
        "publishers_subscription_price_positive", "publishers", type_="check"
    )
    op.drop_constraint("publishers_article_price_positive", "publishers", type_="check")
    op.drop_constraint("publishers_status_valid", "publishers", type_="check")
    op.drop_constraint("publishers_recipient_key", "publishers", type_="unique")
    op.drop_column("publishers", "default_subscription_price")
    op.drop_column("publishers", "default_article_price")
    op.drop_column("publishers", "status")
    op.drop_column("publishers", "description")
    op.drop_column("publishers", "owner_address")
