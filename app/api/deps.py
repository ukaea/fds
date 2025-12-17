from typing import Annotated

from fastapi import Depends

from app.core.db import SessionDep
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


def get_device_service(session: SessionDep) -> DeviceService:
    return DeviceService(session)


def get_shot_service(session: SessionDep) -> ShotService:
    return ShotService(session)


def get_source_service(session: SessionDep) -> SourceService:
    return SourceService(session)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
ShotServiceDep = Annotated[ShotService, Depends(get_shot_service)]
SourceServiceDep = Annotated[SourceService, Depends(get_source_service)]
