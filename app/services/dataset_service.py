import logging
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_is_admin, check_shot_operator
from app.core.config import S3StorageProvider, config
from app.models.dataset import Dataset, DatasetCreate, DatasetRead, DatasetUpdate
from app.models.device import Device
from app.models.distribution import Distribution, DistributionRead
from app.models.file_access import (
    CredentialRequest,
    S3Credentials,
    anonymous_storage_options,
)
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.storage_options import derive_storage_options_type
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.file_access_service import FileAccessService
from app.services.shot_service import ShotService

logger = logging.getLogger(__name__)


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

    def get_multi(
        self,
        user: AuthenticatedUser = ANONYMOUS_USER,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Global list of datasets. Filters by access level.
        """
        statement = select(self.model).offset(offset).limit(limit)
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def check_read_access(self, dataset: Dataset, user: AuthenticatedUser) -> None:
        """
        Enforces read access for dataset metadata.
        Uses the full effective policy (inherited access_level, required_scopes,
        allowed_idps) from the Dataset → Shot → Device hierarchy.
        """
        policy = get_effective_policy(dataset, self.session)

        # PUBLIC and EMBARGOED: metadata is discoverable by everyone
        if (
            policy.access_level == AccessLevel.PUBLIC
            or policy.access_level == AccessLevel.EMBARGOED
        ):
            return

        # RESTRICTED: must be authenticated
        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

        # Enforce IdP restriction if specified
        if policy.allowed_idps is not None:
            if user.issuer not in policy.allowed_idps:
                raise ForbiddenError(
                    "Access denied: your identity provider is not permitted "
                    "for this resource"
                )

        # Enforce required scopes if explicitly set
        # None → use capability fallback; [] → auth-only gate (already passed above)
        if policy.required_scopes is not None:
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    raise ForbiddenError(f"Not authorized, requires scope: {scope}")
            return

        # Capability fallback (no explicit required_scopes at any level)
        if dataset.device_name:
            if dataset.shot_id:
                check_shot_operator(user, dataset.device_name)
            else:
                check_device_admin(user, dataset.device_name)
        else:
            check_is_admin(user)

    def create(self, obj_in: DatasetCreate, user: AuthenticatedUser) -> Dataset:
        """
        Create a new dataset. Handles global, device, or shot context.
        """
        # 0. Validate policy invariants before any DB work
        validate_policy_fields(
            obj_in.access_level,
            obj_in.required_scopes,
            obj_in.allowed_idps,
        )

        # 1. Determine and Validate Context
        if obj_in.shot_id:
            if not obj_in.device_name:
                raise FDSValidationError(
                    "Device name is required when specifying a shot_id"
                )

            # Verify the shot exists under this device
            shot_service = ShotService(self.session)
            shot = shot_service.get((obj_in.device_name, obj_in.shot_id))
            if not shot:
                raise ResourceNotFoundError(
                    f"Shot {obj_in.shot_id} not found for device {obj_in.device_name}"
                )

            # Auth: Device Admin
            check_device_admin(user, obj_in.device_name)

        elif obj_in.device_name:
            # Verify device exists
            stmt = select(Device).where(Device.name == obj_in.device_name)
            if not self.session.exec(stmt).first():
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")

            # Auth: Device Admin
            check_device_admin(user, obj_in.device_name)
        else:
            # Global dataset
            check_is_admin(user)

        # 2. Create DB Object — device_name flows through from obj_in directly
        origin = obj_in.origin or config.catalog_uri
        db_obj = Dataset.model_validate(
            obj_in, update={"distributions": [], "origin": origin}
        )

        distribution = Distribution(
            url=obj_in.url,
            endpoint_url=obj_in.endpoint_url,
            region=obj_in.region,
            media_type=obj_in.media_type,
            format=obj_in.format,
            storage_options_type=obj_in.storage_options_type
            or derive_storage_options_type(obj_in.media_type, obj_in.url),
            default_distribution=True,
        )
        db_obj.distributions.append(distribution)

        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(
                f"Dataset '{obj_in.name}' already exists in this context"
            ) from e
        self.session.refresh(db_obj)
        return db_obj

    def update(
        self, *, id: int, obj_in: DatasetUpdate, user: AuthenticatedUser
    ) -> Dataset:
        """
        Update a dataset. Resolves by ID internally.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Dataset {id} not found")

        # Auth check based on existing context
        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        # Prevent changing context during update
        if obj_in.device_name and obj_in.device_name != db_obj.device_name:
            raise ForbiddenError("Cannot move a dataset between device contexts")
        if obj_in.shot_id and obj_in.shot_id != db_obj.shot_id:
            raise ForbiddenError("Cannot move a dataset between shots")

        # Validate updated policy fields against the resulting effective state.
        # Use incoming value if provided, else fall back to the stored value.
        update_data = obj_in.model_dump(exclude_unset=True)
        effective_access_level = update_data.get("access_level", db_obj.access_level)
        effective_required_scopes = update_data.get(
            "required_scopes", db_obj.required_scopes
        )
        effective_allowed_idps = update_data.get("allowed_idps", db_obj.allowed_idps)
        validate_policy_fields(
            effective_access_level,
            effective_required_scopes,
            effective_allowed_idps,
        )

        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a dataset with authorization.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Dataset {id} not found")

        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        return self.delete_unchecked(id)

    def get_by_name_in_context(
        self,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        device_name: str | None = None,
        shot_id: str | None = None,
    ) -> list[Dataset]:
        """
        Return all datasets with the given name in the given context.
        Multiple datasets may share a name when produced by different Activities.
        """
        statement = select(Dataset).where(
            Dataset.name == name,
            Dataset.device_name == device_name,
            Dataset.shot_id == shot_id,
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def get_device_level_datasets(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Get datasets belonging to a device (but not to a specific shot), filtering by access.
        """
        statement = (
            select(Dataset)
            .where(Dataset.device_name == device_name, col(Dataset.shot_id).is_(None))
            .offset(offset)
            .limit(limit)
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def get_datasets_for_shot(
        self,
        shot_id: str,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Get all datasets for a specific shot (scoped by device name).
        """
        statement = (
            select(Dataset)
            .where(Dataset.shot_id == shot_id, Dataset.device_name == device_name)
            .offset(offset)
            .limit(limit)
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def to_read_model(
        self,
        dataset: Dataset,
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
    ) -> DatasetRead:
        """
        Converts a Dataset ORM object to a DatasetRead DTO, including the effective access level.
        The default distribution's fields are inlined; other distributions appear in `formats`.
        Optionally enriches it with temporary storage credentials if permitted.
        """
        default_dist = next(
            (d for d in dataset.distributions if d.default_distribution), None
        )

        read_model = DatasetRead.model_validate(
            dataset,
            update={
                "url": default_dist.url if default_dist else "",
                "media_type": default_dist.media_type if default_dist else None,
                "format": default_dist.format if default_dist else None,
                "distributions": [
                    DistributionRead.model_validate(d) for d in dataset.distributions
                ]
                or None,
            },
        )
        read_model.effective_access_level = get_effective_access_level(
            dataset, self.session
        )
        if include_storage_options and user:
            read_model = self.enrich_with_storage_options([read_model], user)[0]
        return read_model

    def to_read_models(
        self,
        datasets: Sequence[Dataset],
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
    ) -> list[DatasetRead]:
        """
        Batch converts ORM objects to DatasetRead DTOs, efficiently applying batch enrichment
        for temporary storage credentials to avoid N+1 IAM calls.
        """
        models = [self.to_read_model(d) for d in datasets]
        if include_storage_options and user:
            models = self.enrich_with_storage_options(models, user)
        return models

    def _filter_accessible_datasets(
        self, datasets: Sequence[Dataset], user: AuthenticatedUser
    ) -> list[Dataset]:
        """
        Helper to filter a list of datasets, returning only those the user can read.
        """
        accessible_datasets = []
        for dataset in datasets:
            try:
                self.check_read_access(dataset, user)
                accessible_datasets.append(dataset)
            except ForbiddenError:
                continue
        return accessible_datasets

    def enrich_with_storage_options(
        self, read_models: list[DatasetRead], user: AuthenticatedUser
    ) -> list[DatasetRead]:
        """
        Batch-injects ``storage_options`` into DatasetRead models in the shape
        declared by the default distribution's ``storage_options_type``
        (``fsspec_s3`` or ``icechunk_s3``). Public datasets receive anonymous
        options directly; non-public datasets go through credential vending via
        FileAccessService.
        """
        if not read_models:
            return read_models

        public = [
            m for m in read_models if m.effective_access_level == AccessLevel.PUBLIC
        ]
        non_public = [
            m for m in read_models if m.effective_access_level != AccessLevel.PUBLIC
        ]

        for model in public:
            if not model.url:
                continue
            default_dist = self._default_distribution(model)
            target_type = default_dist.storage_options_type if default_dist else None
            if target_type is None:
                # Distribution opted out of automated storage_options
                # (e.g. plain HTTPS download, MDSplus reference, etc.).
                continue
            endpoint_url = default_dist.endpoint_url if default_dist else None
            region = (
                default_dist.region if default_dist and default_dist.region else None
            ) or self._region_for_endpoint(endpoint_url)
            opts = anonymous_storage_options(
                model.url, endpoint_url, region, target_type
            )
            if opts is None:
                logger.warning(
                    "No anonymous storage options for scheme",
                    extra={"url": model.url},
                )
            elif isinstance(opts, dict):
                # Azure / GCS plain-dict shapes — not yet typed as StorageOptions.
                # Skip injection rather than violate the field's declared type.
                logger.warning(
                    "Anonymous options for non-S3 scheme are not typed yet",
                    extra={"url": model.url},
                )
            else:
                model.storage_options = opts

        credentialed_urls = [m.url for m in non_public if m.url]
        if credentialed_urls:
            manifest = FileAccessService(self.session).generate_session_credentials(
                user=user,
                request=CredentialRequest(data_urls=credentialed_urls),
            )
            for model in non_public:
                if model.url and (cred := manifest.resource_map.get(model.url)):
                    default_dist = self._default_distribution(model)
                    target_type = (
                        default_dist.storage_options_type if default_dist else None
                    )
                    if target_type is None:
                        continue
                    region_override = (
                        default_dist.region
                        if default_dist and default_dist.region
                        else None
                    )
                    if isinstance(cred, S3Credentials):
                        model.storage_options = cred.to_storage_options(
                            target_type, region=region_override
                        )

        return read_models

    @staticmethod
    def _default_distribution(model: DatasetRead) -> DistributionRead | None:
        return next(
            (d for d in (model.distributions or []) if d.default_distribution),
            None,
        )

    @staticmethod
    def _region_for_endpoint(endpoint_url: str | None) -> str | None:
        for pc in config.STORAGE_PROVIDERS:
            if isinstance(pc, S3StorageProvider) and pc.endpoint_url == endpoint_url:
                return pc.region
        return None
