"""Add article draft/published status and make metadata columns nullable.

Revision ID: 0003_age13_article_draft_status
Revises: 0002_age12_publisher_profile
Create Date: 2026-05-01
"""

from collections.abc import Sequence
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_age13_article_draft_status"
down_revision: str = "0002_age12_publisher_profile"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_NULLABLE_COLUMNS = [
    "author",
    "published_at",
    "price",
    "license",
    "summary",
    "tags",
    "key_claims",
    "allowed_excerpts",
    "suggested_citation",
]


def upgrade() -> None:
    """Add status column, make metadata nullable, update constraints."""
    op.add_column(
        "articles",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="published",
        ),
    )
    for col in _NULLABLE_COLUMNS:
        op.alter_column("articles", col, existing_nullable=False, nullable=True)
    op.drop_constraint("articles_price_positive", "articles", type_="check")
    op.create_check_constraint(
        "articles_price_positive",
        "articles",
        "price IS NULL OR price > 0",
    )
    op.create_check_constraint(
        "articles_status_valid",
        "articles",
        "status IN ('draft', 'published')",
    )


def downgrade() -> None:
    """Remove status column, restore NOT NULL and original price check."""
    op.drop_constraint("articles_status_valid", "articles", type_="check")
    op.drop_constraint("articles_price_positive", "articles", type_="check")
    op.create_check_constraint(
        "articles_price_positive",
        "articles",
        "price > 0",
    )
    for col in reversed(_NULLABLE_COLUMNS):
        op.alter_column("articles", col, existing_nullable=True, nullable=False)
    op.drop_column("articles", "status")
