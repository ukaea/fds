"""Drop the id suffix from column names

Revision ID: 849e20655c77
Revises: c98c5fc82cf0
Create Date: 2026-11-05 17:16:31.935227

Written by hand. Autogenerate cannot detect a rename: it drops the column and
adds a new one, which loses the column's data, and for a link table also its
primary key, since autogenerate does not compare primary keys. Each rename here
keeps the column's data, primary key and foreign key, and renames the foreign
key and index named after the old column to the names the new column would have
been given.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '849e20655c77'
down_revision: Union[str, Sequence[str], None] = 'c98c5fc82cf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, old column, new column, whether the column has its own index)
RENAMES = [
    ('activityagent', 'activity_id', 'activity', False),
    ('activitydelegation', 'activity_id', 'activity', False),
    ('activitydelegation', 'subordinate_source_id', 'subordinate_source', False),
    ('activitydelegation', 'responsible_source_id', 'responsible_source', False),
    ('activityinput', 'activity_id', 'activity', False),
    ('activityinput', 'dataset_id', 'dataset', False),
    ('activityinstrument', 'activity_id', 'activity', False),
    ('activityinstrument', 'source_id', 'source', False),
    ('collectiondataset', 'collection_id', 'collection', False),
    ('collectiondataset', 'dataset_id', 'dataset', False),
    ('collectionmember', 'parent_id', 'parent', False),
    ('collectionmember', 'child_id', 'child', False),
    ('dataset', 'subject_dataset_id', 'subject_dataset', True),
    ('datasetderivation', 'dataset_id', 'dataset', True),
]


def _rename(table: str, old: str, new: str, indexed: bool) -> None:
    op.alter_column(table, old, new_column_name=new)
    op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT {table}_{old}_fkey TO {table}_{new}_fkey')
    if indexed:
        op.execute(f'ALTER INDEX ix_{table}_{old} RENAME TO ix_{table}_{new}')


def upgrade() -> None:
    """Upgrade schema."""
    for table, old, new, indexed in RENAMES:
        _rename(table, old, new, indexed)


def downgrade() -> None:
    """Downgrade schema."""
    for table, old, new, indexed in reversed(RENAMES):
        _rename(table, new, old, indexed)
