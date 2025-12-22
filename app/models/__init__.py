from .device import Device, DeviceRead, DeviceCreate, DeviceUpdate
from .shot import Shot, ShotRead, ShotCreate, ShotUpdate

# Resolve forward references for models with circular dependencies
ShotRead.model_rebuild()

__all__ = [
    "Device",
    "DeviceRead",
    "DeviceCreate",
    "DeviceUpdate",
    "Shot",
    "ShotRead",
    "ShotCreate",
    "ShotUpdate",
]
