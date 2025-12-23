from typing import Union
from sqlmodel import Session, select
from app.models.common import AccessLevel
from app.models.device import Device
from app.models.shot import Shot
from app.models.dataset import Dataset

DEFAULT_ACCESS_LEVEL = AccessLevel.RESTRICTED


def get_effective_access_level(
    obj: Union[Dataset, Shot, Device], session: Session
) -> AccessLevel:
    """
    Calculates the effective access level for an object based on inheritance:
    Specific Overrides General.
    Hierarchy: Dataset -> Shot -> Device -> Global Default
    """
    # 1. Direct override
    if obj.access_level:
        return obj.access_level

    # 2. Inherit from Shot (if applicable)
    if isinstance(obj, Dataset) and obj.shot_id:
        shot = session.get(Shot, obj.shot_id)
        if shot:
            return get_effective_access_level(shot, session)

    # 3. Inherit from Device
    device = None
    if isinstance(obj, Dataset) and obj.device_name:
        statement = select(Device).where(Device.name == obj.device_name)
        device = session.exec(statement).first()
    elif isinstance(obj, Shot) and obj.device_id:
        device = session.get(Device, obj.device_id)

    if device:
        return get_effective_access_level(device, session)

    # 4. Fallback to Global Default
    return DEFAULT_ACCESS_LEVEL
