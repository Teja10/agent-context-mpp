"""Initial Thoth schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-05
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Optional[str] = None
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

SQL_DIR = Path(__file__).parent.parent / "sql"


def upgrade() -> None:
    """Create the initial Thoth schema."""
    op.execute(sa.text((SQL_DIR / "0001_upgrade.sql").read_text()))


def downgrade() -> None:
    """Drop the initial Thoth schema."""
    op.execute(sa.text((SQL_DIR / "0001_downgrade.sql").read_text()))
