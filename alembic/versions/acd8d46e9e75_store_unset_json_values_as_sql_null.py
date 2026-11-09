"""store unset json values as sql null

Revision ID: acd8d46e9e75
Revises: 4dbb5a896dc9
Create Date: 2026-11-09 13:42:10.808472

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'acd8d46e9e75'
down_revision: Union[str, Sequence[str], None] = '4dbb5a896dc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_COLUMNS = {
    "activity": ("parameters",),
    "collection": ("scientific_metadata", "required_scopes", "allowed_idps"),
    "dataset": (
        "scientific_metadata",
        "required_scopes",
        "allowed_idps",
        "geometry_references",
        "geometry_roles",
        "calibration_references",
        "calibration_roles",
        "applies_to",
    ),
    "device": ("required_scopes", "allowed_idps"),
    "shot": ("scientific_metadata", "required_scopes", "allowed_idps"),
}


def upgrade() -> None:
    """Upgrade schema."""
    for table, columns in JSON_COLUMNS.items():
        assignments = ", ".join(
            f"{column} = NULLIF({column}, 'null'::jsonb)" for column in columns
        )
        op.execute(f"UPDATE {table} SET {assignments}")


def downgrade() -> None:
    """Downgrade schema."""
    # The code before this revision reads SQL NULL and a JSON null alike.
    pass
