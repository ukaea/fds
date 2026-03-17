from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_is_admin, check_shot_operator
from app.models.dataset import Dataset, DatasetCreate, DatasetRead, DatasetUpdate
from app.models.device import Device
from app.models.file_access import CredentialRequest
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
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

        # 2. Check for Name Collisions
        existing = self.get_by_name_in_context(
            name=obj_in.name,
            device_name=obj_in.device_name,
            shot_id=obj_in.shot_id,
            user=user,
        )
        if existing:
            raise ConflictError(f"Dataset {obj_in.name} already exists in this context")

        # 3. Create DB Object — device_name flows through from obj_in directly
        db_obj = Dataset.model_validate(obj_in)

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
        self, *, db_obj: Dataset, obj_in: DatasetUpdate, user: AuthenticatedUser
    ) -> Dataset:
        """
        Update a dataset.
        """
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
    ) -> Dataset | None:
        """
        Retrieve a dataset by name within its context, enforcing read access.
        """
        statement = select(Dataset).where(
            Dataset.name == name,
            Dataset.device_name == device_name,
            Dataset.shot_id == shot_id,
        )
        dataset = self.session.exec(statement).first()
        if dataset:
            self.check_read_access(dataset, user)
        return dataset

    def get_datasets_for_device(
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
        Optionally enriches it with temporary storage credentials if permitted.
        """
        read_model = DatasetRead.model_validate(dataset)
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
        Takes a list of DatasetRead models and batch-injects standard FSSpec `storage_options` dictionaries
        containing temporary S3/MinIO STS credentials for authorized resources.
        Filters natively handle access control logic inside FileAccessService.
        """
        if not read_models:
            return read_models

        # Extract all valid protocol URLs
        urls = [m.data_url for m in read_models if m.data_url]
        if not urls:
            return read_models

        # Request tokens for the batch in a single call to prevent N+1 IAM assumptions
        file_access_service = FileAccessService(self.session)
        request = CredentialRequest(data_urls=urls)

        # This service internally runs the _check_download_permission policy engine.
        # Unknown/Unauthorised URLs will simply not appear in the resulting manifest map.
        manifest = file_access_service.generate_session_credentials(
            user=user, request=request
        )

        for model in read_models:
            if model.data_url not in manifest.resource_map:
                continue

            token_idx = manifest.resource_map[model.data_url]
            token_payload = manifest.tokens[token_idx]

            # The payload contains {"provider": str, "credentials": {"resource": CredentialModel}}
            raw_creds = list(token_payload["credentials"].values())[0]

            # Cloud Agnostic Dispatch: Let the Credential model define its own FSSpec arg mapping
            if hasattr(raw_creds, "to_storage_options"):
                storage_options = raw_creds.to_storage_options()
            elif hasattr(raw_creds, "model_dump"):
                storage_options = raw_creds.model_dump()
            elif hasattr(raw_creds, "dict"):
                storage_options = raw_creds.dict()
            else:
                storage_options = dict(raw_creds)

            model.storage_options = storage_options

        return read_models
