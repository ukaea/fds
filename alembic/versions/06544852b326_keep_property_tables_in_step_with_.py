"""keep property tables in step with scientific metadata

Revision ID: 06544852b326
Revises: e1cfa1336104
Create Date: 2026-11-09 14:54:20.182604

Written by hand: Alembic cannot generate functions or triggers. The function
scientific_properties flattens a record's scientific_metadata into one row per
property at every depth. A trigger on each table that holds metadata replaces a
record's rows whenever its metadata is written, and the tables are filled from
the metadata already stored. Changing how the tree is flattened takes a new
migration like this one, which replaces the function and refills the tables.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '06544852b326'
down_revision: Union[str, Sequence[str], None] = 'e1cfa1336104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table holding metadata, its property table, the property table's columns
# naming the record, the record's key columns they hold)
TABLES = [
    ('shot', 'shotproperty', ('device_name', 'shot'), ('device_name', 'id')),
    ('dataset', 'datasetproperty', ('dataset',), ('id',)),
    ('collection', 'collectionproperty', ('collection',), ('id',)),
]

COLUMNS = '"position", path, is_group, value, number, unit, description, kind, dimension'

# The pattern is NUMERIC_TEXT in app/services/filters.py, as it stood when this
# was written. pg_input_is_valid leaves out a number too large for numeric,
# such as the string "1e200000", which would otherwise fail the write.
WALK = r"""
CREATE FUNCTION scientific_properties(metadata jsonb)
RETURNS TABLE (
    "position" integer[], path text, is_group boolean, value jsonb,
    number numeric, unit text, description text, kind text, dimension text
)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE walk ("position", path, entry, extent) AS (
        SELECT ARRAY[top.i::integer - 1], top.entry ->> 'name', top.entry,
               top.entry -> 'extent'
        FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(metadata) = 'array' THEN metadata ELSE '[]' END
        ) WITH ORDINALITY AS top (entry, i)
        UNION ALL
        SELECT walk."position" || (child.i::integer - 1),
               concat(walk.path, '.', child.entry ->> 'name'),
               child.entry,
               walk.extent
        FROM walk, jsonb_array_elements(
            CASE WHEN jsonb_typeof(walk.entry -> 'properties') = 'array'
                 THEN walk.entry -> 'properties' ELSE '[]' END
        ) WITH ORDINALITY AS child (entry, i)
    )
    SELECT "position",
           path,
           jsonb_typeof(entry -> 'properties') IS NOT DISTINCT FROM 'array',
           NULLIF(entry -> 'value', 'null'),
           CASE WHEN entry ->> 'value' ~ '^-?\d+(\.\d+)?([eE][-+]?\d+)?$'
                     AND pg_input_is_valid(entry ->> 'value', 'numeric')
                THEN (entry ->> 'value')::numeric END,
           entry ->> 'unit',
           entry ->> 'description',
           entry ->> 'kind',
           extent ->> 'dimension'
    FROM walk
$$
"""


def _list(columns: tuple[str, ...], of: str = '') -> str:
    return ', '.join(f'{of}{column}' for column in columns)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(WALK)
    for table, rows, keys, record_keys in TABLES:
        op.execute(f"""
            CREATE FUNCTION refresh_{rows}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                DELETE FROM {rows}
                WHERE ({_list(keys)}) = ({_list(record_keys, 'NEW.')});
                INSERT INTO {rows} ({_list(keys)}, {COLUMNS})
                SELECT {_list(record_keys, 'NEW.')}, p.*
                FROM scientific_properties(NEW.scientific_metadata) AS p;
                RETURN NULL;
            END
            $$
        """)
        op.execute(f"""
            CREATE TRIGGER refresh_{rows}
            AFTER INSERT OR UPDATE OF scientific_metadata ON {table}
            FOR EACH ROW EXECUTE FUNCTION refresh_{rows}()
        """)
        op.execute(f"""
            INSERT INTO {rows} ({_list(keys)}, {COLUMNS})
            SELECT {_list(record_keys, 'record.')}, p.*
            FROM {table} AS record,
                 scientific_properties(record.scientific_metadata) AS p
        """)


def downgrade() -> None:
    """Downgrade schema."""
    for table, rows, _, _ in TABLES:
        op.execute(f'DROP TRIGGER refresh_{rows} ON {table}')
        op.execute(f'DROP FUNCTION refresh_{rows}()')
        op.execute(f'DELETE FROM {rows}')
    op.execute('DROP FUNCTION scientific_properties(jsonb)')
