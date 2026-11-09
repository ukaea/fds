import pytest
from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, SQLModel, col, select

import app.models  # noqa: F401  (registers every table)
from app.auth.security import AuthenticatedUser
from app.models.device import Device, DeviceCreate
from app.services.device_service import DeviceService

JSON_COLUMNS = [
    column
    for table in SQLModel.metadata.tables.values()
    for column in table.columns
    if isinstance(column.type, JSON)
]


@pytest.mark.parametrize("column", JSON_COLUMNS, ids=str)
def test_every_json_column_is_jsonb_storing_none_as_sql_null(column: Column):
    assert isinstance(column.type, JSONB)
    assert column.type.none_as_null


def test_an_unset_value_is_stored_as_sql_null(
    session: Session, admin_user: AuthenticatedUser
):
    device = DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), admin_user
    )

    unset = session.exec(
        select(col(Device.required_scopes).is_(None)).where(Device.name == device.name)
    ).one()

    assert unset
