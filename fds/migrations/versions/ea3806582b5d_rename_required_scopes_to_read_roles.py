"""Rename required_scopes to read_roles

Revision ID: ea3806582b5d
Revises: 06544852b326
Create Date: 2026-11-27 08:36:24.269548

Written by hand. Autogenerate cannot detect a rename: it drops the column and
adds a new one, which loses the column's data. The column has no index or
constraint named after it, so renaming the column is all there is.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ea3806582b5d'
down_revision: Union[str, Sequence[str], None] = '06544852b326'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('device', 'shot', 'collection', 'dataset')


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.alter_column(table, 'required_scopes', new_column_name='read_roles')


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        op.alter_column(table, 'read_roles', new_column_name='required_scopes')
