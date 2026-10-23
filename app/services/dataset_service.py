from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import QueryableAttribute, selectinload
from sqlmodel import Session, col, select, tuple_

from app.auth.access_control import (
    check_read,
    get_effective_policies,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_is_admin
from app.core.config import AzureStorageProvider, S3StorageProvider, config
from app.core.context import ReadTier
from app.core.naming import normalise_device_name
from app.models.activity import (
    Activity,
    ActivityAgent,
    ActivitySummary,
    ActivityType,
)
from app.models.dataset import (
    Dataset,
    DatasetCreate,
    DatasetDerivation,
    DatasetDerivationCreate,
    DatasetLineageNode,
    DatasetRead,
    DatasetUpdate,
)
from app.models.device import Device
from app.models.distribution import Distribution, DistributionRead
from app.models.file_access import CredentialRequest, anonymous_storage_options
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.scope import CatalogueScope, DeviceScope
from app.models.shot import Shot
from app.models.storage_options import derive_storage_options_type
from app.services.activity_service import ActivityService
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
from app.services.filters import (
    activity_clauses,
    property_clauses,
    scope_clauses,
    shot_id_prefix_clauses,
)
from app.services.jsonld import dataset_node, generate_context, map_dataset_to_dcat
from app.services.reference_service import (
    CALIBRATION,
    GEOMETRY,
    REFERENCE_KINDS,
    ReferenceKind,
    ReferenceService,
)
from app.services.visibility import read_page, readable_clause, readable_only

logger = structlog.get_logger(__name__)


def _attribute(relationship: object) -> QueryableAttribute[Any]:
    """A relationship on a model class, typed as SQLAlchemy's loader options take it.

    SQLModel types a relationship as the objects it holds, but read from the
    class it is SQLAlchemy's attribute.
    """
    if not isinstance(relationship, QueryableAttribute):
        raise TypeError(f"Not a SQLAlchemy relationship: {relationship!r}")
    return relationship


@dataclass
class _Reference:
    """A resolved reference version, and the references it resolves in turn by
    kind name."""

    version: Dataset
    nested: dict[str, list["_Reference"]] = field(default_factory=dict)


@dataclass
class _Pending:
    """Versions that references of a kind resolve to at ``shot``, awaiting an
    access check before joining ``into``. ``ancestors`` are the versions above
    them, whose references are not followed again."""

    into: dict[str, list[_Reference]]
    kind_name: str
    versions: list[Dataset]
    shot: Shot
    ancestors: frozenset[int | None]


def _assemble(
    references: list[_Reference], models: dict[int | None, DatasetRead]
) -> list[DatasetRead]:
    """``references`` as read models, each a copy since a version can sit at
    several places in the tree with different nested references."""
    assembled = []
    for reference in references:
        model = models[reference.version.id].model_copy()
        for kind_name, nested in reference.nested.items():
            setattr(model, kind_name, _assemble(nested, models))
        assembled.append(model)
    return assembled


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

    def get_multi(
        self,
        user: AuthenticatedUser = ANONYMOUS_USER,
        *,
        scope: CatalogueScope = CatalogueScope.ALL,
        offset: int = 0,
        limit: int = 100,
        name: str | None = None,
        properties: list[str] | None = None,
        shot_properties: list[str] | None = None,
        activity_type: ActivityType | None = None,
        source: str | None = None,
        activity_id: int | None = None,
        shot_id_prefix: str | None = None,
    ) -> Sequence[Dataset]:
        """
        Every dataset, whatever its scope. Filters by access level.

        ``scope`` narrows it: ``GLOBAL`` to the datasets attached to no device,
        ``DEVICE`` to those belonging to a device as a whole, ``SHOT`` to those
        on a shot.

        ``properties`` filters on the dataset's own properties;
        ``shot_properties`` on those of its parent shot. A dataset with no shot
        never matches ``shot_properties``. To scope to one device, use
        ``get_datasets_for_device`` rather than filtering here.
        """
        statement = select(self.model).where(
            *scope_clauses(col(Dataset.device_name), col(Dataset.shot_id), scope)
        )
        if name is not None:
            statement = statement.where(self.model.name == name)
        statement = statement.where(
            *property_clauses(self.model.scientific_metadata, properties),
            *activity_clauses(
                col(Dataset.activity_id), activity_type, source, activity_id
            ),
            *shot_id_prefix_clauses(col(Dataset.shot_id), shot_id_prefix),
        )
        statement = self._apply_shot_properties(statement, shot_properties, user)
        return read_page(
            self.session,
            Dataset,
            statement.order_by(col(Dataset.id)),
            user,
            offset=offset,
            limit=limit,
        )

    def _apply_shot_properties(
        self,
        statement,
        shot_properties: list[str] | None,
        user: AuthenticatedUser,
    ):
        """Join Dataset to its parent Shot and filter on the shot's properties.

        Shared by the global and per-device listings so the two-level query behaves
        identically wherever it is offered.

        Only shots ``user`` may read can match. A public dataset can belong to a
        restricted shot, and without this the filter would answer questions about
        that shot's properties.
        """
        if not shot_properties:
            return statement
        matching = property_clauses(Shot.scientific_metadata, shot_properties)
        return statement.join(
            Shot,
            (col(Dataset.shot_id) == col(Shot.id))
            & (col(Dataset.device_name) == col(Shot.device_name)),
        ).where(
            *matching,
            readable_clause(self.session, Shot, user, select(Shot).where(*matching)),
        )

    def check_read_access(
        self,
        dataset: Dataset,
        user: AuthenticatedUser,
        tier: ReadTier = ReadTier.READ,
    ) -> None:
        """Enforce read access, and record it when the resource is not public."""
        check_read(dataset, self.session, user, tier)

    def get_activity(self, dataset_id: int, user: AuthenticatedUser) -> Activity:
        """The Activity that produced the dataset, for a caller who may read it.

        The dataset's read check runs here rather than in the router, so a caller
        cannot reach a restricted dataset's run parameters through this
        sub-resource. It runs before the "no associated activity" 404, so the
        response does not reveal whether a dataset the caller cannot read has
        provenance recorded.
        """
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        self.check_read_access(dataset, user)
        if not dataset.activity_id:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} has no associated activity"
            )
        activity = self.session.get(Activity, dataset.activity_id)
        if not activity:
            raise ResourceNotFoundError(f"Activity {dataset.activity_id} not found")
        return activity

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
            group=obj_in.group,
            conforms_to=obj_in.conforms_to,
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
        self._reject_if_upstream(id)
        return self.delete_unchecked(id)

    def _reject_if_upstream(self, id: int) -> None:
        dependants = self.session.exec(
            select(DatasetDerivation.dataset_id).where(
                DatasetDerivation.source_dataset_id == id
            )
        ).all()
        if dependants:
            unique = sorted(set(dependants))
            listed = ", ".join(str(d) for d in unique)
            one = len(unique) == 1
            noun = "dataset" if one else "datasets"
            derivation = "That derivation" if one else "Those derivations"
            raise ConflictError(
                f"Dataset {id} is an asserted source for {noun} {listed}. "
                f"{derivation} would be deleted with it."
            )

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
        return read_page(
            self.session, Dataset, statement.order_by(col(Dataset.id)), user
        )

    def get_datasets_for_device(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        scope: DeviceScope = DeviceScope.ALL,
        offset: int = 0,
        limit: int = 100,
        name: str | None = None,
        properties: list[str] | None = None,
        shot_properties: list[str] | None = None,
        activity_type: ActivityType | None = None,
        source: str | None = None,
        activity_id: int | None = None,
        shot_id_prefix: str | None = None,
    ) -> Sequence[Dataset]:
        """
        Get datasets hosted by a device, filtering by access.

        ``scope`` narrows the listing: ``ALL`` returns device-level and
        shot-level datasets together, ``DEVICE`` only those belonging to the
        device as a whole rather than to any one shot, ``SHOT`` only those
        attached to one of the device's shots.

        ``properties`` filters on each dataset's own properties;
        ``shot_properties`` on those of its parent shot, which answers questions
        spanning both levels (e.g. equilibrium datasets from shots that had ELMs).
        Since device-level datasets have no shot, combining ``shot_properties``
        with ``scope=DEVICE`` matches nothing.
        """
        statement = select(Dataset).where(
            Dataset.device_name == normalise_device_name(device_name),
            *scope_clauses(col(Dataset.device_name), col(Dataset.shot_id), scope),
        )
        if name is not None:
            statement = statement.where(Dataset.name == name)
        statement = statement.where(
            *property_clauses(Dataset.scientific_metadata, properties),
            *activity_clauses(
                col(Dataset.activity_id), activity_type, source, activity_id
            ),
            *shot_id_prefix_clauses(col(Dataset.shot_id), shot_id_prefix),
        )
        statement = self._apply_shot_properties(statement, shot_properties, user)
        return read_page(
            self.session,
            Dataset,
            statement.order_by(col(Dataset.id)),
            user,
            offset=offset,
            limit=limit,
        )

    def get_datasets_for_shot(
        self,
        shot_id: str,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
        properties: list[str] | None = None,
        activity_type: ActivityType | None = None,
        source: str | None = None,
        activity_id: int | None = None,
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
            .where(
                *property_clauses(Dataset.scientific_metadata, properties),
                *activity_clauses(
                    col(Dataset.activity_id), activity_type, source, activity_id
                ),
            )
            .order_by(col(Dataset.id))
        )
        return read_page(
            self.session, Dataset, statement, user, offset=offset, limit=limit
        )

    def to_read_model(
        self,
        dataset: Dataset,
        include_storage_options: bool = False,
        user: AuthenticatedUser | None = None,
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
    ) -> DatasetRead:
        """``to_read_models`` for a single dataset."""
        return self.to_read_models(
            [dataset],
            include_storage_options=include_storage_options,
            user=user,
            include_geometry=include_geometry,
            include_calibration=include_calibration,
            include_annotations=include_annotations,
        )[0]

    def _read_model(
        self,
        dataset: Dataset,
        distributions: list[Distribution],
        access_level: AccessLevel,
        run: ActivitySummary | None,
    ) -> DatasetRead:
        """``dataset`` as a DatasetRead, its default distribution's fields inlined.

        ``run`` is passed in rather than read from ``dataset``, whose ``activity``
        is the ORM relationship: reading it would load each row's run separately.
        """
        default_dist = next((d for d in distributions if d.default_distribution), None)
        return DatasetRead.model_validate(
            dataset,
            update={
                "url": default_dist.url if default_dist else None,
                "group": default_dist.group if default_dist else None,
                "conforms_to": default_dist.conforms_to if default_dist else None,
                "media_type": default_dist.media_type if default_dist else None,
                "format": default_dist.format if default_dist else None,
                "distributions": [
                    DistributionRead.model_validate(d) for d in distributions
                ]
                or None,
                "effective_access_level": access_level,
                "activity": run,
            },
        )

    def to_dcat(
        self,
        dataset: Dataset,
        base_url: str,
        *,
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> dict[str, Any]:
        """Build the dataset's DCAT/JSON-LD document, resolving the requested
        related datasets (geometry, calibration, properties) into qualified
        relations."""
        enriched = self.to_read_model(
            dataset,
            user=user,
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
            run_inputs=(
                readable_only(self.session, dataset.activity.input_datasets, user)
                if dataset.activity
                else []
            ),
        )

    def to_dcat_listing(
        self,
        datasets: Sequence[Dataset],
        base_url: str,
        *,
        include_geometry: bool = False,
        include_calibration: bool = False,
        include_annotations: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> dict[str, Any]:
        """A page of a dataset listing as one JSON-LD document.

        Its ``@graph`` holds each dataset's ``dcat:Dataset`` node, in order,
        without FDS's record of it. The runs, distributions and derivations the
        nodes describe, and the related datasets asked for, are loaded for all
        the datasets at once, and each run lists only the inputs ``user`` may
        read.
        """
        self._load_jsonld_relations(datasets)
        enriched = self.to_read_models(
            datasets,
            user=user,
            include_geometry=include_geometry,
            include_calibration=include_calibration,
            include_annotations=include_annotations,
        )
        inputs = self._readable_run_inputs(datasets, user)
        return {
            "@context": generate_context(),
            "@graph": [
                dataset_node(
                    dataset,
                    base_url,
                    geometry=model.geometry if include_geometry else None,
                    calibration=model.calibration if include_calibration else None,
                    annotations=model.annotations if include_annotations else None,
                    run_inputs=run_inputs,
                )
                for dataset, model, run_inputs in zip(
                    datasets, enriched, inputs, strict=True
                )
            ],
        }

    def _load_jsonld_relations(self, datasets: Sequence[Dataset]) -> None:
        """Load what the JSON-LD of ``datasets`` reads, for all of them at once.

        Mapping a dataset follows its run, distributions and derivations, and the
        run's agents, instruments and inputs. Left to load as the mapping reaches
        them, each would cost a statement per dataset.
        """
        ids = [dataset.id for dataset in datasets]
        if not ids:
            return
        run = selectinload(_attribute(Dataset.activity))
        self.session.exec(
            select(Dataset)
            .where(col(Dataset.id).in_(ids))
            .options(
                selectinload(_attribute(Dataset.distributions)),
                selectinload(_attribute(Dataset.derivations)),
                run.selectinload(_attribute(Activity.source)),
                run.selectinload(_attribute(Activity.instruments)),
                run.selectinload(_attribute(Activity.input_datasets)),
                run.selectinload(_attribute(Activity.delegation_links)),
                run.selectinload(_attribute(Activity.agent_links)).selectinload(
                    _attribute(ActivityAgent.source)
                ),
            )
        ).all()

    def _readable_run_inputs(
        self, datasets: Sequence[Dataset], user: AuthenticatedUser
    ) -> list[list[Dataset]]:
        """For each of ``datasets``, the inputs ``user`` may read of the run that
        generated it. The inputs of every run are checked together."""
        every_input = {
            input_dataset.id: input_dataset
            for dataset in datasets
            if dataset.activity
            for input_dataset in dataset.activity.input_datasets
        }
        readable = {
            input_dataset.id
            for input_dataset in readable_only(
                self.session, list(every_input.values()), user
            )
        }
        return [
            [d for d in dataset.activity.input_datasets if d.id in readable]
            if dataset.activity
            else []
            for dataset in datasets
        ]

    def readable_read_models(
        self,
        groups: Sequence[Sequence[Dataset]],
        user: AuthenticatedUser | None,
        include_storage_options: bool = False,
    ) -> list[list[DatasetRead]]:
        """Each group's datasets that ``user`` may read, as read models, in order.
        A dataset in several groups is checked and built once."""
        distinct = {dataset.id: dataset for group in groups for dataset in group}
        readable = readable_only(
            self.session, list(distinct.values()), user or ANONYMOUS_USER
        )
        built = self.to_read_models(
            readable, include_storage_options=include_storage_options, user=user
        )
        models = {d.id: model for d, model in zip(readable, built, strict=True)}
        return [[models[d.id] for d in group if d.id in models] for group in groups]

    def _reference_read_models(
        self,
        datasets: Sequence[Dataset],
        kinds: Sequence[ReferenceKind],
        include_storage_options: bool,
        user: AuthenticatedUser | None,
    ) -> list[dict[str, list[DatasetRead] | None]]:
        """Each dataset's references of ``kinds`` as deduped read models by kind
        name; ``None`` where it declares none or has no resolvable shot.

        Resolution is anchored to the dataset's own shot. A resolved version's
        own references (calibrated geometry: a geometry version carrying
        ``calibration_references``) resolve at that same shot, unless the version
        is one of its own ancestors, which breaks cycles. The whole page resolves
        together, and every version is built in one ``to_read_models`` call.
        """
        shots = self._shots_with_references(datasets, kinds)
        services = {
            kind.name: ReferenceService(self.session, kind) for kind in REFERENCE_KINDS
        }
        for service in services.values():
            service.load({shot.device_name for shot in shots.values()})

        roots: list[dict[str, list[_Reference]]] = [{} for _ in datasets]
        pending = [
            _Pending(root, kind.name, versions, shot, frozenset())
            for dataset, root in zip(datasets, roots, strict=True)
            if (shot := shots.get((dataset.device_name, dataset.shot_id))) is not None
            for kind in kinds
            if (versions := services[kind.name].resolve_references(dataset, shot))
        ]
        served = self._follow_references(pending, services, user)
        built = self.to_read_models(
            list(served.values()),
            include_storage_options=include_storage_options,
            user=user,
        )
        models = dict(zip(served, built, strict=True))
        return [
            {
                kind.name: _assemble(root[kind.name], models)
                if kind.name in root
                else None
                for kind in kinds
            }
            for root in roots
        ]

    def _shots_with_references(
        self, datasets: Sequence[Dataset], kinds: Sequence[ReferenceKind]
    ) -> dict[tuple[str | None, str | None], Shot]:
        """The shots of the ``datasets`` that declare references of ``kinds``, by
        device and id, in one query."""
        keys = {
            (dataset.device_name, dataset.shot_id)
            for dataset in datasets
            if dataset.shot_id
            and any(getattr(dataset, kind.references_attr) for kind in kinds)
        }
        if not keys:
            return {}
        statement = select(Shot).where(tuple_(Shot.device_name, Shot.id).in_(keys))
        return {
            (shot.device_name, shot.id): shot for shot in self.session.exec(statement)
        }

    def _follow_references(
        self,
        pending: list[_Pending],
        services: dict[str, ReferenceService],
        user: AuthenticatedUser | None,
    ) -> dict[int | None, Dataset]:
        """Place each pending version ``user`` may read, then follow its own
        references, until none are left; the versions placed, by id.

        Each level of nesting is checked for access in one batch, so only
        versions reached through readable ones are checked.
        """
        checked: set[int | None] = set()
        readable: set[int | None] = set()
        served: dict[int | None, Dataset] = {}
        while pending:
            unchecked = {
                version.id: version
                for each in pending
                for version in each.versions
                if version.id not in checked
            }
            checked |= unchecked.keys()
            readable |= {
                version.id
                for version in readable_only(
                    self.session, list(unchecked.values()), user or ANONYMOUS_USER
                )
            }
            following: list[_Pending] = []
            for each in pending:
                kept = {v.id: v for v in each.versions if v.id in readable}
                if not kept:
                    continue
                served |= kept
                references = [_Reference(version) for version in kept.values()]
                each.into[each.kind_name] = references
                for reference in references:
                    if reference.version.id in each.ancestors:
                        continue
                    ancestors = each.ancestors | {reference.version.id}
                    for kind in REFERENCE_KINDS:
                        service = services[kind.name]
                        versions = service.resolve_references(
                            reference.version, each.shot
                        )
                        if versions:
                            following.append(
                                _Pending(
                                    reference.nested,
                                    kind.name,
                                    versions,
                                    each.shot,
                                    ancestors,
                                )
                            )
            pending = following
        return served

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
        Converts Dataset ORM objects to DatasetRead DTOs, including the effective
        access level. The default distribution's fields are inlined, every
        distribution is listed, and each read includes a summary of the run that
        generated its dataset. Distributions, policies, runs and storage
        credentials, and references and annotations when included, are each
        resolved for all the datasets at once. ``include_geometry`` /
        ``include_calibration`` resolve each dataset's ``geometry_references`` /
        ``calibration_references`` to their applicable versions.
        """
        distributions = self._distributions_of(datasets)
        policies = get_effective_policies(datasets, self.session)
        runs = ActivityService(self.session).get_summaries(
            d.activity_id for d in datasets
        )
        models = [
            self._read_model(
                dataset,
                distributions[dataset.id],
                policy.access_level,
                runs.get(dataset.activity_id) if dataset.activity_id else None,
            )
            for dataset, policy in zip(datasets, policies, strict=True)
        ]
        if include_storage_options and user:
            models = self.enrich_with_storage_options(models, user)
        kinds = [
            kind
            for kind, included in (
                (GEOMETRY, include_geometry),
                (CALIBRATION, include_calibration),
            )
            if included
        ]
        if kinds:
            references = self._reference_read_models(
                datasets, kinds, include_storage_options, user
            )
            for model, resolved in zip(models, references, strict=True):
                for kind in kinds:
                    setattr(model, kind.name, resolved[kind.name])
        if include_annotations:
            annotations = self.readable_read_models(
                AnnotationService(self.session).for_datasets(datasets),
                user,
                include_storage_options=include_storage_options,
            )
            for model, resolved in zip(models, annotations, strict=True):
                model.annotations = resolved or None
        return models

    def _distributions_of(
        self, datasets: Sequence[Dataset]
    ) -> defaultdict[int | None, list[Distribution]]:
        """The distributions of ``datasets`` by dataset id, in one query."""
        by_dataset: defaultdict[int | None, list[Distribution]] = defaultdict(list)
        ids = [d.id for d in datasets]
        if ids:
            for distribution in self.session.exec(
                select(Distribution)
                .where(col(Distribution.dataset_id).in_(ids))
                .order_by(col(Distribution.id))
            ):
                by_dataset[distribution.dataset_id].append(distribution)
        return by_dataset

    def enrich_with_storage_options(
        self, read_models: list[DatasetRead], user: AuthenticatedUser
    ) -> list[DatasetRead]:
        """
        Batch-injects opener-ready ``storage_options`` into DatasetRead models.

        Public datasets receive anonymous options directly. Non-public datasets
        go through credential vending via FileAccessService, rendered exactly
        as the bulk credentials endpoint renders them.
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
            default_dist = self._default_distribution(model)
            if not model.url or default_dist is None:
                continue
            target_type = default_dist.storage_options_type
            endpoint_url = default_dist.endpoint_url
            model.storage_options = anonymous_storage_options(
                model.url,
                target_type,
                endpoint_url=endpoint_url,
                region=default_dist.region or self._region_for_endpoint(endpoint_url),
                account_name=self._account_for_endpoint(endpoint_url),
            )
            if model.storage_options is None and target_type is not None:
                logger.warning("storage_options.unavailable", url=model.url)

        credentialed_urls = [m.url for m in non_public if m.url]
        if credentialed_urls:
            manifest = FileAccessService(self.session).generate_session_credentials(
                user=user,
                request=CredentialRequest(data_urls=credentialed_urls),
                include_storage_options=True,
            )
            for model in non_public:
                if model.url and (cred := manifest.resource_map.get(model.url)):
                    model.storage_options = cred.storage_options

        return read_models

    @staticmethod
    def _default_distribution(model: DatasetRead) -> DistributionRead | None:
        return next(
            (d for d in (model.distributions or []) if d.default_distribution),
            None,
        )

    @staticmethod
    def _region_for_endpoint(endpoint_url: str | None) -> str | None:
        pc = config.storage_provider("s3", endpoint_url)
        return pc.region if isinstance(pc, S3StorageProvider) else None

    @staticmethod
    def _account_for_endpoint(endpoint_url: str | None) -> str | None:
        pc = config.storage_provider("azure", endpoint_url)
        return pc.storage_account if isinstance(pc, AzureStorageProvider) else None
