from enum import Enum


class DeviceScope(str, Enum):
    """Which of a device's records a device listing returns.

    - ALL: all of them, whether attached to the device as a whole or to a shot.
    - DEVICE: only those attached to the device as a whole, not to a shot.
    - SHOT: only those attached to one of the device's shots.
    """

    ALL = "all"
    DEVICE = "device"
    SHOT = "shot"


class CatalogueScope(str, Enum):
    """Which records a listing of the whole catalogue returns.

    - ALL: every record.
    - GLOBAL: only records attached to no device.
    - DEVICE: only records attached to a device as a whole, not to a shot.
    - SHOT: only records attached to a shot.
    """

    ALL = "all"
    GLOBAL = "global"
    DEVICE = "device"
    SHOT = "shot"
