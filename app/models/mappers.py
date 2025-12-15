from app.models.device import DeviceRead
from app.models.shot import ShotRead


class DeviceReadWithShots(DeviceRead):
    """
    A DeviceRead model that includes a list of associated shots.
    """

    shots: list[ShotRead] = []


class ShotReadWithDevice(ShotRead):
    """
    A ShotRead model that includes the associated device.
    """

    device: DeviceRead
