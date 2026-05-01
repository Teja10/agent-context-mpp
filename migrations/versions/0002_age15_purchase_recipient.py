"""Add recipient_wallet to one_time_purchases.

Revision ID: 0002_age15_purchase_recipient
Revises: 0001_age10_postgres_persistence
Create Date: 2026-05-01
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_age15_purchase_recipient"
down_revision: Optional[str] = "0001_age10_postgres_persistence"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

SQL_DIR = Path(__file__).parent.parent / "sql"


def upgrade() -> None:
    """Add recipient_wallet column to one_time_purchases."""
    op.execute(sa.text((SQL_DIR / "0002_upgrade.sql").read_text()))


def downgrade() -> None:
    """Drop recipient_wallet column from one_time_purchases."""
    op.execute(sa.text((SQL_DIR / "0002_downgrade.sql").read_text()))
