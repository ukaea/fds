from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.auth.access_control import (
    EffectivePolicy,
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_is_admin, check_shot_operator
from app.core.audit import record_restricted_read
from app.core.config import S3StorageProvider, config
from app.core.context import ReadTier, record_returned
from app.core.naming import normalise_device_name
from app.models.dataset import (
    Dataset,
    DatasetCreate,
    DatasetDerivation,
    DatasetDerivationCreate,
    DatasetLineageNode,
    DatasetRead,
    DatasetScope,
    DatasetUpdate,
)
from app.models.device import Device
from app.models.distribution import Distribution, DistributionRead
from app.models.file_access import (
    CredentialRequest,
    S3Credentials,
    anonymous_storage_options,
)
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.models.storage_options import derive_storage_options_type
from app.services.annotation_service import AnnotationService
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.file_access_service import FileAccessService
from app.services.filters import annotation_clauses
from app.services.jsonld import map_dataset_to_dcat
from app.services.reference_service import (
    CALIBRATION,
    GEOMETRY,
    REFERENCE_KINDS,
    ReferenceKind,
    ReferenceService,
)

logger = structlog.get_logger(__name__)


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

    def get_multi(
        self,
        user: AuthenticatedUser = ANONYMOUS_USER,
        *,
        offset: int = 0,
        limit: int = 100,
        name: str | None = None,
        annotations: list[str] | None = None,
        shot_annotations: list[str] | None = None,
    ) -> Sequence[Dataset]:
        """
        Global list of datasets. Filters by access level.

        ``annotations`` filters on the dataset's own feature annotations;
        ``shot_annotations`` on those of its parent shot. A dataset with no shot
        never matches ``shot_annotations``. To scope to one device, use
        ``get_datasets_for_device`` rather than filtering here.
        """
        statement = select(self.model)
        if name is not None:
            statement = statement.where(self.model.name == name)
        statement = statement.where(
            *annotation_clauses(self.model.scientific_metadata, annotations)
        )
        statement = self._apply_shot_annotations(statement, shot_annotations)
        statement = statement.order_by(col(Dataset.id)).offset(offset).limit(limit)
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def _apply_shot_annotations(self, statement, shot_annotations: list[str] | None):
        """Join Dataset to its parent Shot and filter on the shot's annotations.

        Shared by the global and per-device listings so the two-level query behaves
        identically wherever it is offered.
        """
        if not shot_annotations:
            return statement
        return statement.join(
            Shot,
            (col(Dataset.shot_id) == col(Shot.id))
            & (col(Dataset.device_name) == col(Shot.device_name)),
        ).where(*annotation_clauses(Shot.scientific_metadata, shot_annotations))

    def check_read_access(
        self,
        dataset: Dataset,
        user: AuthenticatedUser,
        tier: ReadTier = ReadTier.READ,
    ) -> None:
        """Enforce read access, and record it when the resource is not public."""
        policy = get_effective_policy(dataset, self.session)
        self._enforce_read_policy(dataset, policy, user)
        record_restricted_read(dataset, policy.access_level, tier)

    def _enforce_read_policy(
        self, dataset: Dataset, policy: EffectivePolicy, user: AuthenticatedUser
    ) -> None:
        """Enforce read access for Dataset metadata.

        Resolves the full effective policy (inherited ``access_level``,
        ``required_scopes``, ``allowed_idps``) from the
        Dataset → Shot → Device hierarchy.

        - PUBLIC / EMBARGOED: metadata is discoverable by everyone (EMBARGOED
          restricts data, not metadata — enforced at credential vending).
        - RESTRICTED: requires an authenticated user, then any IdP and scope
          gates set by the policy. With no explicit ``required_scopes`` it
          falls back to a capability check (shot operator or device admin).

        Raises ``ForbiddenError`` when the user does not satisfy the policy.
        """
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
        if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
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
        """Create a new dataset. Handles global, device, or shot context."""
        validate_policy_fields(
            obj_in.access_level, obj_in.required_scopes, obj_in.allowed_idps
        )
        obj_in.device_name = normalise_device_name(obj_in.device_name)
        self._resolve_and_authorize_context(obj_in, user)

        origin = obj_in.origin
        self._reject_duplicate(obj_in, origin)
        self._validate_references(obj_in)

        for derivation in obj_in.derived_from:
            self._validate_derivation(derivation)

        db_obj = Dataset.model_validate(
            obj_in, update={"distributions": [], "origin": origin}
        )
        if obj_in.url:
            db_obj.distributions.append(self._build_distribution(obj_in, obj_in.url))
        dataset = self._persist(db_obj, obj_in.name)

        if obj_in.derived_from:
            assert dataset.id is not None
            for derivation in obj_in.derived_from:
                self.session.add(
                    DatasetDerivation.model_validate(
                        derivation, update={"dataset_id": dataset.id}
                    )
                )
            self.session.commit()
            self.session.refresh(dataset)
        return dataset

    def _resolve_and_authorize_context(
        self, obj_in: DatasetCreate, user: AuthenticatedUser
    ) -> None:
        """Validate the dataset's context (global / device / shot) and authorize the
        caller for it. Raises if the shot or device is missing, or the user lacks the
        required admin capability."""
        if obj_in.shot_id:
            if not obj_in.device_name:
                raise FDSValidationError(
                    "Device name is required when specifying a shot_id"
                )
            shot = self.session.exec(
                select(Shot).where(
                    Shot.device_name == obj_in.device_name,
                    Shot.id == obj_in.shot_id,
                )
            ).first()
            if not shot:
                raise ResourceNotFoundError(
                    f"Shot {obj_in.shot_id} not found for device {obj_in.device_name}"
                )
        elif obj_in.device_name:
            stmt = select(Device).where(Device.name == obj_in.device_name)
            if not self.session.exec(stmt).first():
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")
        self._authorize_write(obj_in.device_name, user)

    def _reject_duplicate(self, obj_in: DatasetCreate, origin: str | None) -> None:
        """Reject an exact duplicate up front so a re-POST of an identical dataset
        reads as 409 (already exists) rather than the reference-overlap 422 that
        validation would raise first — a version trivially overlaps itself, which
        would otherwise mask the duplicate behind a misleading error."""
        duplicate = select(Dataset).where(
            Dataset.name == obj_in.name,
            Dataset.device_name == obj_in.device_name,
            Dataset.shot_id == obj_in.shot_id,
        )
        if obj_in.activity_id is not None:
            duplicate = duplicate.where(Dataset.activity_id == obj_in.activity_id)
        else:
            duplicate = duplicate.where(
                col(Dataset.activity_id).is_(None), Dataset.origin == origin
            )
        if self.session.exec(duplicate).first() is not None:
            raise ConflictError(
                f"Dataset '{obj_in.name}' already exists in this context"
            )

    def _validate_references(self, obj_in: DatasetCreate) -> None:
        """Enforce reference (geometry / calibration) write rules before any DB work."""
        for kind in REFERENCE_KINDS:
            ReferenceService(self.session, kind).validate_new_version(
                obj_in.device_name,
                getattr(obj_in, kind.roles_attr),
                obj_in.applies_to,
                order=getattr(obj_in, kind.order_attr) if kind.order_attr else None,
                references=getattr(obj_in, kind.references_attr),
                shot_id=obj_in.shot_id,
            )

    def _build_distribution(self, obj_in: DatasetCreate, url: str) -> Distribution:
        """Build the default distribution for a dataset's ``url``."""
        return Distribution(
            url=url,
            endpoint_url=obj_in.endpoint_url,
            region=obj_in.region,
            media_type=obj_in.media_type,
            format=obj_in.format,
            storage_options_type=obj_in.storage_options_type
            or derive_storage_options_type(obj_in.media_type, url),
            default_distribution=True,
        )

    def _validate_derivation(
        self, derivation: DatasetDerivationCreate, dataset_id: int | None = None
    ) -> None:
        """Validate an asserted upstream against the database."""
        if derivation.source_dataset_id is None:
            return
        if derivation.source_dataset_id == dataset_id:
            raise FDSValidationError("A dataset cannot be derived from itself")
        if not self.session.get(Dataset, derivation.source_dataset_id):
            raise ResourceNotFoundError(
                f"Dataset {derivation.source_dataset_id} not found"
            )
        # dataset_id is None while registering a dataset: it does not exist yet, so
        # nothing can derive from it and no cycle is reachable.
        if dataset_id is not None and self._derives_from(
            derivation.source_dataset_id, dataset_id
        ):
            raise FDSValidationError(
                f"Dataset {derivation.source_dataset_id} already derives from "
                f"dataset {dataset_id}, so neither can have been built from the "
                "other"
            )

    def _derives_from(self, dataset_id: int, ancestor_id: int) -> bool:
        """Whether ``ancestor_id`` is upstream of ``dataset_id``, at any depth.

        Walks the asserted derivations, ignoring upstreams that are not registered
        datasets since those are leaves. The visited set keeps the walk finite over
        data that already contains a cycle: the check stops new ones being
        asserted, it does not repair rows written before it existed.
        """
        seen: set[int] = set()
        frontier = [dataset_id]
        while frontier:
            current = frontier.pop()
            if current == ancestor_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            upstreams = self.session.exec(
                select(DatasetDerivation).where(
                    DatasetDerivation.dataset_id == current,
                    col(DatasetDerivation.source_dataset_id).is_not(None),
                )
            ).all()
            frontier.extend(
                link.source_dataset_id
                for link in upstreams
                if link.source_dataset_id is not None
            )
        return False

    def add_derivation(
        self,
        *,
        dataset_id: int,
        obj_in: DatasetDerivationCreate,
        user: AuthenticatedUser,
    ) -> DatasetDerivation:
        """Assert an upstream this dataset was derived from. Requires write access."""
        dataset = self._require_dataset(dataset_id)
        self._authorize_write(dataset.device_name, user)
        self._validate_derivation(obj_in, dataset_id=dataset_id)

        link = DatasetDerivation.model_validate(
            obj_in, update={"dataset_id": dataset_id}
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def remove_derivation(
        self, *, dataset_id: int, derivation_id: int, user: AuthenticatedUser
    ) -> bool:
        """Retract an asserted upstream. Requires write access."""
        dataset = self._require_dataset(dataset_id)
        self._authorize_write(dataset.device_name, user)

        link = self.session.get(DatasetDerivation, derivation_id)
        if not link or link.dataset_id != dataset_id:
            raise ResourceNotFoundError(
                f"Derivation {derivation_id} not found for Dataset {dataset_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_derivations(
        self,
        dataset_id: int,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[DatasetDerivation]:
        """List the upstreams asserted for a dataset.

        Enforces read access to the *derived* dataset here rather than in the
        router, so a caller cannot reach a restricted dataset's provenance by
        going straight to the sub-resource.
        """
        dataset = self._require_dataset(dataset_id)
        self.check_read_access(dataset, user)
        statement = (
            select(DatasetDerivation)
            .where(DatasetDerivation.dataset_id == dataset_id)
            .order_by(col(DatasetDerivation.id))
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_lineage(
        self, dataset_id: int, user: AuthenticatedUser
    ) -> DatasetLineageNode:
        """Walk a dataset's asserted upstreams transitively.

        Only asserted derivations are followed. A run's inputs are not lineage on
        their own: PROV-DM makes a usage-and-generation chain necessary but not
        sufficient for derivation, so composing them would claim edges nobody
        asserted.

        Each dataset is expanded once. A repeat is emitted as a ``seen`` stub, so
        the walk terminates on a cycle and a shared ancestor is not duplicated
        down every path that reaches it. The response is therefore bounded by the
        number of distinct datasets reachable, with no depth limit needed.
        """
        dataset = self._require_dataset(dataset_id)
        self.check_read_access(dataset, user)
        return self._expand_lineage(dataset, user, expanded=set())

    def _expand_lineage(
        self, dataset: Dataset, user: AuthenticatedUser, expanded: set[int]
    ) -> DatasetLineageNode:
        """Build a node for ``dataset`` and recurse into each asserted upstream."""
        assert dataset.id is not None
        expanded.add(dataset.id)

        derivations = self.session.exec(
            select(DatasetDerivation)
            .where(DatasetDerivation.dataset_id == dataset.id)
            .order_by(col(DatasetDerivation.id))
        ).all()

        return DatasetLineageNode(
            dataset_id=dataset.id,
            name=dataset.name,
            derived_from=[
                self._lineage_upstream(derivation, user, expanded)
                for derivation in derivations
            ],
        )

    def _lineage_upstream(
        self,
        derivation: DatasetDerivation,
        user: AuthenticatedUser,
        expanded: set[int],
    ) -> DatasetLineageNode:
        """Turn one asserted derivation into a node, expanding it where possible."""
        if derivation.source_dataset_id is None:
            # An external or described-only upstream. FDS holds nothing further
            # about it, so it is always a leaf.
            return DatasetLineageNode(
                identifier=derivation.source_identifier,
                label=derivation.source_label,
                description=derivation.source_description,
            )

        source_id = derivation.source_dataset_id
        if source_id in expanded:
            return DatasetLineageNode(dataset_id=source_id, seen=True)

        upstream = self.session.get(Dataset, source_id)
        if upstream is None:
            return DatasetLineageNode(dataset_id=source_id, missing=True)

        try:
            self.check_read_access(upstream, user)
        except ForbiddenError:
            # Withhold the name and the branch below it. The id is already
            # visible through the derivations listing, so this reveals nothing
            # new while keeping the truncation explicit.
            return DatasetLineageNode(dataset_id=source_id, restricted=True)

        return self._expand_lineage(upstream, user, expanded)

    def _require_dataset(self, dataset_id: int) -> Dataset:
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        return dataset

    def _persist(self, db_obj: Dataset, name: str) -> Dataset:
        """Add, commit (mapping a uniqueness violation to 409), refresh, and return."""
        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(
                f"Dataset '{name}' already exists in this context"
            ) from e
        self.session.refresh(db_obj)
        return db_obj

    def _authorize_write(
        self, device_name: str | None, user: AuthenticatedUser
    ) -> None:
        """Authorize a write: device admin if device-scoped, else global admin."""
        if device_name:
            check_device_admin(user, device_name)
        else:
            check_is_admin(user)

    def _get_or_raise(self, id: int) -> Dataset:
        """Fetch a dataset by id or raise ``ResourceNotFoundError``."""
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Dataset {id} not found")
        return db_obj

    def update(
        self, *, id: int, obj_in: DatasetUpdate, user: AuthenticatedUser
    ) -> Dataset:
        """
        Update a dataset. Resolves by ID internally.
        """
        db_obj = self._get_or_raise(id)
        self._authorize_write(db_obj.device_name, user)

        if obj_in.device_name is not None:
            obj_in.device_name = normalise_device_name(obj_in.device_name)

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

        # Re-validate reference resources against the merged state.
        effective_applies_to = update_data.get("applies_to", db_obj.applies_to)
        for kind in REFERENCE_KINDS:
            effective_roles = update_data.get(
                kind.roles_attr, getattr(db_obj, kind.roles_attr)
            )
            effective_references = update_data.get(
                kind.references_attr, getattr(db_obj, kind.references_attr)
            )
            effective_order = (
                update_data.get(kind.order_attr, getattr(db_obj, kind.order_attr))
                if kind.order_attr
                else None
            )
            ReferenceService(self.session, kind).validate_new_version(
                db_obj.device_name,
                effective_roles,
                effective_applies_to,
                order=effective_order,
                references=effective_references,
                shot_id=db_obj.shot_id,
                exclude_id=db_obj.id,
            )

        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a dataset with authorization.
        """
        db_obj = self._get_or_raise(id)
        self._authorize_write(db_obj.device_name, user)
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
            Dataset.device_name == normalise_device_name(device_name),
            Dataset.shot_id == shot_id,
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def get_datasets_for_device(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        scope: DatasetScope = DatasetScope.ALL,
        offset: int = 0,
        limit: int = 100,
        name: str | None = None,
        annotations: list[str] | None = None,
        shot_annotations: list[str] | None = None,
    ) -> Sequence[Dataset]:
        """
        Get datasets hosted by a device, filtering by access.

        ``scope`` narrows the listing: ``ALL`` returns device-level and
        shot-level datasets together, ``DEVICE`` only those belonging to the
        device as a whole rather than to any one shot, ``SHOT`` only those
        attached to one of the device's shots.

        ``annotations`` filters on each dataset's own feature annotations;
        ``shot_annotations`` on those of its parent shot, which answers questions
        spanning both levels (e.g. equilibrium datasets from shots that had ELMs).
        Since device-level datasets have no shot, combining ``shot_annotations``
        with ``scope=DEVICE`` matches nothing.
        """
        statement = select(Dataset).where(
            Dataset.device_name == normalise_device_name(device_name)
        )
        if scope is DatasetScope.DEVICE:
            statement = statement.where(col(Dataset.shot_id).is_(None))
        elif scope is DatasetScope.SHOT:
            statement = statement.where(col(Dataset.shot_id).is_not(None))
        if name is not None:
            statement = statement.where(Dataset.name == name)
        statement = statement.where(
            *annotation_clauses(Dataset.scientific_metadata, annotations)
        )
        statement = self._apply_shot_annotations(statement, shot_annotations)
        statement = statement.order_by(col(Dataset.id)).offset(offset).limit(limit)
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def get_datasets_for_shot(
        self,
        shot_id: str,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
        annotations: list[str] | None = None,
    ) -> Sequence[Dataset]:
        """
        Get all datasets for a specific shot (scoped by device name).
        """
        statement = (
            select(Dataset)
            .where(
                Dataset.shot_id == shot_id,
                Dataset.device_name == normalise_device_name(device_name),
            )
            .where(*annotation_clauses(Dataset.scientific_metadata, annotations))
            .order_by(col(Dataset.id))
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
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
    ) -> DatasetRead:
        """
        Converts a Dataset ORM object to a DatasetRead DTO, including the effective access level.
        The default distribution's fields are inlined; other distributions appear in `formats`.
        Optionally enriches it with temporary storage credentials if permitted.
        When ``include_geometry`` / ``include_calibration`` is set, resolves the
        signal's ``geometry_references`` / ``calibration_references`` to their
        applicable versions.
        """
        default_dist = next(
            (d for d in dataset.distributions if d.default_distribution), None
        )

        read_model = DatasetRead.model_validate(
            dataset,
            update={
                "url": default_dist.url if default_dist else None,
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
        if include_geometry:
            read_model.geometry = self._resolve_reference_read_models(
                dataset,
                GEOMETRY,
                include_storage_options=include_storage_options,
                user=user,
            )
        if include_calibration:
            read_model.calibration = self._resolve_reference_read_models(
                dataset,
                CALIBRATION,
                include_storage_options=include_storage_options,
                user=user,
            )
        if include_annotations:
            read_model.annotations = self._resolve_annotation_read_models(
                dataset, include_storage_options=include_storage_options, user=user
            )
        return read_model

    def to_dcat(
        self,
        dataset: Dataset,
        base_url: str,
        *,
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
    ) -> dict[str, Any]:
        """Build the dataset's DCAT/JSON-LD document, resolving the requested
        related datasets (geometry, calibration, annotations) into qualified
        relations."""
        enriched = self.to_read_model(
            dataset,
            include_geometry=include_geometry,
            include_calibration=include_calibration,
            include_annotations=include_annotations,
        )
        return map_dataset_to_dcat(
            dataset,
            base_url,
            geometry=enriched.geometry if include_geometry else None,
            calibration=enriched.calibration if include_calibration else None,
            annotations=enriched.annotations if include_annotations else None,
        )

    def _resolve_annotation_read_models(
        self,
        dataset: Dataset,
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
    ) -> list[DatasetRead] | None:
        """
        Dataset annotations as read models, or ``None``.
        """
        annotations = AnnotationService(self.session).for_dataset(dataset)
        models = [
            self.to_read_model(
                annotation,
                include_storage_options=include_storage_options,
                user=user,
            )
            for annotation in annotations
        ]
        return models or None

    def _resolve_reference_read_models(
        self,
        dataset: Dataset,
        kind: ReferenceKind,
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
        shot: Shot | None = None,
        visited: set[int] | None = None,
    ) -> list[DatasetRead] | None:
        """Resolve ``dataset``'s references of ``kind`` to deduped read models, or
        ``None`` if it declares none or has no resolvable shot.

        Resolution is anchored to ``shot``. At the top level ``shot`` is ``None``
        and taken from ``dataset``'s own shot; a nested reference *version* (a
        device-level dataset with no shot of its own) is resolved at the *same*
        anchoring shot, so calibrated geometry — a geometry version that itself
        carries ``calibration_references`` — resolves at the original signal's
        shot. ``visited`` carries the ancestor version ids to break cycles.
        """
        references = getattr(dataset, kind.references_attr)
        if not references:
            return None
        if shot is None:
            if not dataset.shot_id:
                return None
            shot = self.session.exec(
                select(Shot).where(
                    Shot.device_name == dataset.device_name,
                    Shot.id == dataset.shot_id,
                )
            ).first()
            if shot is None:
                return None
        service = ReferenceService(self.session, kind)
        if kind.order_attr is not None:
            # Ordered kind: each role resolves to a stage-ordered chain.
            chains = service.resolve_chain(shot, references)
            ordered = [version for role in references for version in chains[role]]
        else:
            resolved = service.resolve(shot, references)
            ordered = [resolved[role] for role in references]
        seen: set[int] = set()
        models: list[DatasetRead] = []
        for version in ordered:
            if version is None or version.id is None or version.id in seen:
                continue
            seen.add(version.id)
            models.append(
                self._reference_version_read_model(
                    version, shot, include_storage_options, user, visited or set()
                )
            )
        return models or None

    def _reference_version_read_model(
        self,
        version: Dataset,
        shot: Shot,
        include_storage_options: bool,
        user: AuthenticatedUser | None,
        visited: set[int],
    ) -> DatasetRead:
        """Read model for a resolved reference ``version``, recursively resolving
        its own reference kinds at the same anchoring ``shot`` (calibrated
        geometry). ``visited`` (the ancestor version ids) breaks reference cycles:
        a version already on the path is emitted but not descended into."""
        model = self.to_read_model(
            version, include_storage_options=include_storage_options, user=user
        )
        if version.id is None or version.id in visited:
            return model
        next_visited = visited | {version.id}
        for nested_kind in REFERENCE_KINDS:
            nested = self._resolve_reference_read_models(
                version,
                nested_kind,
                include_storage_options=include_storage_options,
                user=user,
                shot=shot,
                visited=next_visited,
            )
            if nested is not None:
                setattr(model, nested_kind.name, nested)
        return model

    def to_read_models(
        self,
        datasets: Sequence[Dataset],
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
    ) -> list[DatasetRead]:
        """
        Batch converts ORM objects to DatasetRead DTOs, efficiently applying batch enrichment
        for temporary storage credentials to avoid N+1 IAM calls.
        """
        models = [self.to_read_model(d) for d in datasets]
        if include_storage_options and user:
            models = self.enrich_with_storage_options(models, user)
        if include_geometry:
            for source, model in zip(datasets, models):
                model.geometry = self._resolve_reference_read_models(
                    source,
                    GEOMETRY,
                    include_storage_options=include_storage_options,
                    user=user,
                )
        if include_calibration:
            for source, model in zip(datasets, models):
                model.calibration = self._resolve_reference_read_models(
                    source,
                    CALIBRATION,
                    include_storage_options=include_storage_options,
                    user=user,
                )
        if include_annotations:
            for source, model in zip(datasets, models):
                model.annotations = self._resolve_annotation_read_models(
                    source, include_storage_options=include_storage_options, user=user
                )
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
                self.check_read_access(dataset, user, ReadTier.LISTED)
                accessible_datasets.append(dataset)
            except ForbiddenError:
                continue
        record_returned(len(accessible_datasets))
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
                logger.warning("storage_options.unavailable", url=model.url)
            elif isinstance(opts, dict):
                # Azure / GCS plain-dict shapes — not yet typed as StorageOptions.
                # Skip injection rather than violate the field's declared type.
                logger.warning("storage_options.untyped_scheme", url=model.url)
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
