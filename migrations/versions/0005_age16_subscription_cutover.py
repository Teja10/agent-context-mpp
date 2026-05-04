"""Cut over subscriptions to TIMESTAMPTZ and add access-key authorization tables.

Revision ID: 0005_age16_subscription_cutover
Revises: 0004_age13_article_draft_status
Create Date: 2026-05-03
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_age16_subscription_cutover"
down_revision: str = "0004_age13_article_draft_status"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

SQL_DIR = Path(__file__).parent.parent / "sql"


def upgrade() -> None:
    """Cut over subscription period columns and add authorization tables."""
    op.execute(sa.text((SQL_DIR / "0005_upgrade.sql").read_text()))


def downgrade() -> None:
    """Drop authorization tables and revert period columns to DATE."""
    op.execute(sa.text((SQL_DIR / "0005_downgrade.sql").read_text()))
