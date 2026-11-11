"""store datetimes with their timezone

Revision ID: 722053fac80b
Revises: 2419cd702b7d
Create Date: 2026-10-02 12:04:22.645269

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "722053fac80b"
down_revision: str | Sequence[str] | None = "2419cd702b7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = {
    "activity": ("started_at", "ended_at"),
    "collection": ("created_at", "updated_at"),
    "dataset": ("created_at", "updated_at", "temporal_start", "temporal_end"),
    "device": ("created_at", "updated_at"),
    "shot": ("created_at", "updated_at", "shot_at", "shot_end", "t0_at"),
}


def upgrade() -> None:
    """Upgrade schema."""
    # Stored values are UTC without saying so. Name the zone in the cast: the
    # default reads them in the session's TimeZone, which need not be UTC.
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                existing_type=sa.DateTime(),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(),
                existing_type=sa.DateTime(timezone=True),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
