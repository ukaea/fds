from typing import Annotated

from fastapi import Depends

from app.auth.security import get_current_user
from app.core.db import SessionDep
from app.models.identity import AuthenticatedUser
from app.services.activity_service import ActivityService
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.distribution_service import DistributionService
from app.services.file_access_service import FileAccessService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


def get_file_access_service(session: SessionDep) -> FileAccessService:
    return FileAccessService(session)


def get_device_service(session: SessionDep) -> DeviceService:
    return DeviceService(session)


def get_shot_service(session: SessionDep) -> ShotService:
    return ShotService(session)


def get_source_service(session: SessionDep) -> SourceService:
    return SourceService(session)


def get_collection_service(session: SessionDep) -> CollectionService:
    """Provide a ``CollectionService`` bound to the current request's session."""
    return CollectionService(session)


def get_dataset_service(session: SessionDep) -> DatasetService:
    return DatasetService(session)


def get_activity_service(session: SessionDep) -> ActivityService:
    return ActivityService(session)


def get_distribution_service(session: SessionDep) -> DistributionService:
    return DistributionService(session)


FileAccessServiceDep = Annotated[FileAccessService, Depends(get_file_access_service)]
DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
ShotServiceDep = Annotated[ShotService, Depends(get_shot_service)]
SourceServiceDep = Annotated[SourceService, Depends(get_source_service)]
CollectionServiceDep = Annotated[CollectionService, Depends(get_collection_service)]
DatasetServiceDep = Annotated[DatasetService, Depends(get_dataset_service)]
ActivityServiceDep = Annotated[ActivityService, Depends(get_activity_service)]
DistributionServiceDep = Annotated[
    DistributionService, Depends(get_distribution_service)
]

CurrentUserDep = Annotated[AuthenticatedUser, Depends(get_current_user)]
