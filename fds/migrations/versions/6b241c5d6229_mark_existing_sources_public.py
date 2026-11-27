"""Mark existing sources public

Revision ID: 6b241c5d6229
Revises: de0d096e4618
Create Date: 2026-11-27 14:43:38.707461

Written by hand: it changes data, not the schema. Sources had no access level,
and anyone could read them. A source with no level now inherits its device's,
or is restricted, so without this step every source would disappear from view
on upgrade. Downgrading drops the column, so there is nothing to undo.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6b241c5d6229'
down_revision: Union[str, Sequence[str], None] = 'de0d096e4618'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE source SET access_level = 'PUBLIC' WHERE access_level IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    pass
