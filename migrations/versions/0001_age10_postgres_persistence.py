"""Create AGE-10 Postgres persistence tables.

Revision ID: 0001_age10_postgres_persistence
Revises:
Create Date: 2026-04-30
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_age10_postgres_persistence"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

SQL_DIR = Path(__file__).parent.parent / "sql"


def upgrade() -> None:
    """Create the AGE-10 foundation schema."""
    op.execute(sa.text((SQL_DIR / "0001_upgrade.sql").read_text()))


def downgrade() -> None:
    """Drop the AGE-10 foundation schema."""
    op.execute(sa.text((SQL_DIR / "0001_downgrade.sql").read_text()))
