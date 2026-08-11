import logging
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_is_admin
from app.core.config import config
from app.core.naming import normalise_device_name
from app.models.activity import Activity
from app.models.collection import (
    Collection,
    CollectionCreate,
    CollectionDataset,
    CollectionMember,
    CollectionRead,
    CollectionUpdate,
)
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.source import Source
from app.services.base_service import BaseService
from app.services.dataset_service import DatasetService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.shot_service import ShotService

logger = logging.getLogger(__name__)


class CollectionService(BaseService[Collection, CollectionCreate, CollectionUpdate]):
    """Service for managing Collections (``dcat:Catalog``).

    Handles CRUD operations, dataset membership, child-collection nesting, and
    access control for Collections at all three scope levels (Global, Device,
    Shot). Access control mirrors ``DatasetService``: each Collection inherits
    its effective policy from the enclosing Shot → Device hierarchy when no
    explicit ``access_level`` is set.
    """

    def __init__(self, session: Session):
        """Initialise the service with a database session."""
        super().__init__(model=Collection, session=session)

    def check_read_access(
        self, collection: Collection, user: AuthenticatedUser
    ) -> None:
        """Enforce read access for Collection metadata.

        Resolves the full effective policy (inherited ``access_level``,
        ``required_scopes``, ``allowed_idps``) from the
        Collection → Shot → Device hierarchy.

        - PUBLIC / EMBARGOED: metadata is discoverable by everyone (EMBARGOED
          restricts data, not metadata — enforced at credential vending).
        - RESTRICTED: requires an authenticated user, then any IdP and scope
          gates set by the policy. With no explicit ``required_scopes`` it
          falls back to a capability check (device admin or global admin).

        Raises ``ForbiddenError`` when the user does not satisfy the policy.
        """
        policy = get_effective_policy(collection, self.session)

        # PUBLIC and EMBARGOED: metadata is discoverable by everyone
        if policy.access_level in (AccessLevel.PUBLIC, AccessLevel.EMBARGOED):
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
        # None → capability fallback; [] → auth-only gate (already passed above)
        if policy.required_scopes is not None:
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    raise ForbiddenError(f"Not authorized, requires scope: {scope}")
            return

        # Capability fallback (no explicit required_scopes at any level)
        if collection.device_name:
            check_device_admin(user, collection.device_name)
        else:
            check_is_admin(user)

    def create(self, obj_in: CollectionCreate, user: AuthenticatedUser) -> Collection:
        """Create a new Collection at Global, Device, or Shot scope.

        Validates policy invariants, verifies the referenced Shot/Device
        exists, checks for name collisions within the scope, and enforces
        tiered write authorization (device admin for Device/Shot scope,
        global admin for Global scope).
        """
        # 0. Validate policy invariants before any DB work
        validate_policy_fields(
            obj_in.access_level,
            obj_in.required_scopes,
            obj_in.allowed_idps,
        )
        obj_in.device_name = normalise_device_name(obj_in.device_name)

        # 1. Determine and validate context
        if obj_in.shot_id:
            if not obj_in.device_name:
                raise FDSValidationError(
                    "device_name is required when specifying a shot_id"
                )
            shot_service = ShotService(self.session)
            shot = shot_service.get((obj_in.device_name, obj_in.shot_id))
            if not shot:
                raise ResourceNotFoundError(
                    f"Shot {obj_in.shot_id} not found for device {obj_in.device_name}"
                )
            check_device_admin(user, obj_in.device_name)

        elif obj_in.device_name:
            stmt = select(Device).where(Device.name == obj_in.device_name)
            if not self.session.exec(stmt).first():
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")
            check_device_admin(user, obj_in.device_name)

        else:
            check_is_admin(user)

        # 2. Check for name collisions within scope
        existing = self.get_by_name_in_context(
            name=obj_in.name,
            device_name=obj_in.device_name,
            shot_id=obj_in.shot_id,
            user=user,
        )
        if existing:
            raise ConflictError(
                f"Collection '{obj_in.name}' already exists in this context"
            )

        # 3. Persist
        origin = obj_in.origin or config.catalog_uri
        db_obj = Collection.model_validate(obj_in, update={"origin": origin})
        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(
                f"Collection '{obj_in.name}' already exists in this context"
            ) from e
        self.session.refresh(db_obj)
        return db_obj

    def update(
        self, *, id: int, obj_in: CollectionUpdate, user: AuthenticatedUser
    ) -> Collection:
        """Partially update a Collection by internal ID.

        Enforces write authorization based on the Collection's existing scope.
        Rejects attempts to move the Collection between device or shot contexts.
        Re-validates policy fields using the merged (existing + incoming) state
        to catch invariant violations introduced by partial updates.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Collection {id} not found")

        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        if obj_in.device_name is not None:
            obj_in.device_name = normalise_device_name(obj_in.device_name)

        # Prevent context moves
        if obj_in.device_name and obj_in.device_name != db_obj.device_name:
            raise ForbiddenError("Cannot move a Collection between device contexts")
        if obj_in.shot_id and obj_in.shot_id != db_obj.shot_id:
            raise ForbiddenError("Cannot move a Collection between shots")

        # Validate the merged policy state
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
        """Delete a Collection by internal ID.

        Enforces write authorization. Deleting a Collection removes it from all
        parent Collections via cascade on the ``CollectionMember`` join rows.
        Member Datasets are not affected — membership records are removed but
        the Datasets themselves remain unchanged.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Collection {id} not found")

        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        return self.delete_unchecked(id)

    def get_multi(
        self,
        user: AuthenticatedUser = ANONYMOUS_USER,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Collection]:
        """Return the global list of Collections, filtered by access level."""
        statement = (
            select(Collection)
            .where(
                col(Collection.device_name).is_(None),
                col(Collection.shot_id).is_(None),
            )
            .order_by(col(Collection.id))
            .offset(offset)
            .limit(limit)
        )
        collections = self.session.exec(statement).all()
        return self._filter_accessible(collections, user)

    def get_by_name_in_context(
        self,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        device_name: str | None = None,
        shot_id: str | None = None,
    ) -> Collection | None:
        """Retrieve a Collection by name within its scope, enforcing read access.

        Returns ``None`` if no matching Collection exists or if the user does
        not have read access.
        """
        statement = select(Collection).where(
            Collection.name == name,
            Collection.device_name == normalise_device_name(device_name),
            Collection.shot_id == shot_id,
        )
        collection = self.session.exec(statement).first()
        if collection:
            self.check_read_access(collection, user)
        return collection

    def get_by_name_in_context_or_raise(
        self,
        *,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        device_name: str | None = None,
        shot_id: str | None = None,
    ) -> Collection:
        """Retrieve a Collection by name within its scope, raising a
        context-aware ``ResourceNotFoundError`` when absent.
        """
        collection = self.get_by_name_in_context(
            name=name,
            user=user,
            device_name=device_name,
            shot_id=shot_id,
        )
        if collection:
            return collection

        if device_name and shot_id:
            raise ResourceNotFoundError(
                f"Collection '{name}' not found in this context"
            )
        if device_name:
            raise ResourceNotFoundError(
                f"Collection '{name}' not found for device '{device_name}'"
            )
        raise ResourceNotFoundError(f"Global collection '{name}' not found")

    def get_collections_for_device(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Collection]:
        """Return device-level Collections (not tied to any shot), filtered by access."""
        statement = (
            select(Collection)
            .where(
                Collection.device_name == normalise_device_name(device_name),
                col(Collection.shot_id).is_(None),
            )
            .offset(offset)
            .limit(limit)
        )
        collections = self.session.exec(statement).all()
        return self._filter_accessible(collections, user)

    def get_collections_for_shot(
        self,
        shot_id: str,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Collection]:
        """Return all Collections scoped to a specific shot, filtered by access."""
        statement = (
            select(Collection)
            .where(
                Collection.shot_id == shot_id,
                Collection.device_name == normalise_device_name(device_name),
            )
            .offset(offset)
            .limit(limit)
        )
        collections = self.session.exec(statement).all()
        return self._filter_accessible(collections, user)

    def get_for_source(
        self,
        source_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Collection]:
        """Return all Collections whose linked Activity was produced by the given Source."""
        statement = (
            select(Collection)
            .join(Activity, Activity.id == Collection.activity_id)  # type: ignore[arg-type]
            .join(Source, Source.id == Activity.source_id)  # type: ignore[arg-type]
            .where(Source.name == source_name)
            .offset(offset)
            .limit(limit)
        )
        collections = self.session.exec(statement).all()
        return self._filter_accessible(collections, user)

    def add_dataset(
        self, collection_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> None:
        """Add a Dataset to a Collection as a member (``dcat:dataset``).

        Enforces write authorization on the Collection's scope. Raises
        ``ResourceNotFoundError`` if either the Collection or Dataset does not
        exist, and ``ConflictError`` if the Dataset is already a member.
        """
        collection = self.get(collection_id)
        if not collection:
            raise ResourceNotFoundError(f"Collection {collection_id} not found")

        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")

        self._check_write_auth(collection, user)

        existing = self.session.get(CollectionDataset, (collection_id, dataset_id))
        if existing:
            raise ConflictError(
                f"Dataset {dataset_id} is already a member of Collection {collection_id}"
            )

        self.session.add(
            CollectionDataset(collection_id=collection_id, dataset_id=dataset_id)
        )
        self.session.commit()

    def remove_dataset(
        self, collection_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> None:
        """Remove a Dataset from a Collection.

        Enforces write authorization. Raises ``ResourceNotFoundError`` if the
        Collection does not exist or the Dataset is not currently a member.
        """
        collection = self.get(collection_id)
        if not collection:
            raise ResourceNotFoundError(f"Collection {collection_id} not found")

        self._check_write_auth(collection, user)

        membership = self.session.get(CollectionDataset, (collection_id, dataset_id))
        if not membership:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} is not a member of Collection {collection_id}"
            )

        self.session.delete(membership)
        self.session.commit()

    def add_child_collection(
        self, parent_id: int, child_id: int, user: AuthenticatedUser
    ) -> None:
        """Nest a child Collection inside a parent Collection (``dcat:catalog``).

        Enforces write authorization on the parent Collection's scope. Raises
        ``ResourceNotFoundError`` if either Collection does not exist,
        ``ConflictError`` if the child is already nested, and
        ``FDSValidationError`` if adding the child would create a self-reference.
        """
        if parent_id == child_id:
            raise FDSValidationError("A Collection cannot contain itself")

        parent = self.get(parent_id)
        if not parent:
            raise ResourceNotFoundError(f"Collection {parent_id} not found")

        child = self.get(child_id)
        if not child:
            raise ResourceNotFoundError(f"Collection {child_id} not found")

        self._check_write_auth(parent, user)

        existing = self.session.get(CollectionMember, (parent_id, child_id))
        if existing:
            raise ConflictError(
                f"Collection {child_id} is already a child of Collection {parent_id}"
            )

        self.session.add(CollectionMember(parent_id=parent_id, child_id=child_id))
        self.session.commit()

    def remove_child_collection(
        self, parent_id: int, child_id: int, user: AuthenticatedUser
    ) -> None:
        """Remove a child Collection from a parent Collection.

        Enforces write authorization on the parent. Raises
        ``ResourceNotFoundError`` if the parent does not exist or the child is
        not currently nested within it.
        """
        parent = self.get(parent_id)
        if not parent:
            raise ResourceNotFoundError(f"Collection {parent_id} not found")

        self._check_write_auth(parent, user)

        membership = self.session.get(CollectionMember, (parent_id, child_id))
        if not membership:
            raise ResourceNotFoundError(
                f"Collection {child_id} is not a child of Collection {parent_id}"
            )

        self.session.delete(membership)
        self.session.commit()

    def to_read_model(
        self,
        collection: Collection,
        include_storage_options: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> CollectionRead:
        """Convert a Collection ORM object to a ``CollectionRead`` DTO.

        Member Datasets are inlined as ``DatasetRead`` objects. Pass
        ``include_storage_options=True`` to include short-lived credentials on
        each dataset. Child Collections are inlined one level deep — their own
        ``datasets`` and ``child_collections`` are omitted to prevent unbounded
        recursive serialisation.
        """
        member_datasets = self.get_member_datasets(collection.id)
        dataset_reads = (
            DatasetService(self.session).to_read_models(
                member_datasets,
                include_storage_options=include_storage_options,
                user=user,
            )
            or None
        )

        child_orm = self._get_child_collections(collection.id)
        child_reads = [
            CollectionRead.model_validate(
                c,
                update={
                    "effective_access_level": get_effective_access_level(
                        c, self.session
                    ),
                    "datasets": None,
                    "child_collections": None,
                },
            )
            for c in child_orm
        ] or None

        return CollectionRead.model_validate(
            collection,
            update={
                "effective_access_level": get_effective_access_level(
                    collection, self.session
                ),
                "datasets": dataset_reads,
                "child_collections": child_reads,
            },
        )

    def to_read_models(
        self,
        collections: Sequence[Collection],
        include_storage_options: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> list[CollectionRead]:
        """Batch convert Collection ORM objects to ``CollectionRead`` DTOs."""
        return [
            self.to_read_model(
                c, include_storage_options=include_storage_options, user=user
            )
            for c in collections
        ]

    def _check_write_auth(
        self, collection: Collection, user: AuthenticatedUser
    ) -> None:
        """Assert the user has write access to the given Collection's scope.

        Device-scoped Collections (and Shot-scoped ones, which inherit device
        context) require Device Admin. Global Collections require global Admin.
        """
        if collection.device_name:
            check_device_admin(user, collection.device_name)
        else:
            check_is_admin(user)

    def _filter_accessible(
        self, collections: Sequence[Collection], user: AuthenticatedUser
    ) -> list[Collection]:
        """Return only the Collections the user is permitted to read."""
        result = []
        for collection in collections:
            try:
                self.check_read_access(collection, user)
                result.append(collection)
            except ForbiddenError:
                continue
        return result

    def get_member_datasets(self, collection_id: int | None) -> list[Dataset]:
        """Return the Datasets that are members of a given Collection.

        Returns an empty list if ``collection_id`` is ``None`` (unpersisted Collection).
        """
        if collection_id is None:
            return []
        stmt = select(Dataset).where(
            col(Dataset.id).in_(
                select(col(CollectionDataset.dataset_id)).where(
                    col(CollectionDataset.collection_id) == collection_id
                )
            )
        )
        return list(self.session.exec(stmt).all())

    def _get_child_collections(self, parent_id: int | None) -> list[Collection]:
        """Return the Collections directly nested inside a given parent Collection.

        Returns an empty list if ``parent_id`` is ``None`` (unpersisted Collection).
        """
        if parent_id is None:
            return []
        stmt = select(Collection).where(
            col(Collection.id).in_(
                select(col(CollectionMember.child_id)).where(
                    col(CollectionMember.parent_id) == parent_id
                )
            )
        )
        return list(self.session.exec(stmt).all())
