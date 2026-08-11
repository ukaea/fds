import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate, CollectionUpdate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.shot_service import ShotService


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="dataset_service")
def dataset_service_fixture(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture(name="collection_service")
def collection_service_fixture(session: Session) -> CollectionService:
    return CollectionService(session)


def _make_device(device_service: DeviceService, admin: AuthenticatedUser, name="DEV"):
    return device_service.create(DeviceCreate(name=name, type="Tokamak"), user=admin)


def _make_shot(
    shot_service: ShotService, admin: AuthenticatedUser, shot_id="s1", device="DEV"
):
    return shot_service.create(ShotCreate(id=shot_id, device_name=device), user=admin)


def _make_dataset(
    dataset_service: DatasetService,
    admin: AuthenticatedUser,
    name: str = "ds",
    level: int = 1,
    url: str = "s3://bucket/ds",
    device_name: str | None = None,
    shot_id: str | None = None,
):
    return dataset_service.create(
        DatasetCreate(
            name=name, level=level, url=url, device_name=device_name, shot_id=shot_id
        ),
        user=admin,
    )


def test_create_global_collection(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """A global Collection is created with no device or shot context."""
    col = collection_service.create(
        CollectionCreate(name="jintrac-run-42", title="JINTRAC Run 42"),
        admin_user,
    )
    assert col.id is not None
    assert col.name == "jintrac-run-42"
    assert col.device_name is None
    assert col.shot_id is None


def test_create_device_collection(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """A device-scoped Collection is created with device_name set and shot_id absent."""
    _make_device(device_service, admin_user)
    col = collection_service.create(
        CollectionCreate(name="machine-diagnostics", device_name="DEV"),
        admin_user,
    )
    assert col.device_name == "dev"
    assert col.shot_id is None


def test_create_shot_collection(
    device_service: DeviceService,
    shot_service: ShotService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """A shot-scoped Collection is created with both device_name and shot_id set."""
    _make_device(device_service, admin_user)
    _make_shot(shot_service, admin_user)
    col = collection_service.create(
        CollectionCreate(name="jintrac-outputs", device_name="DEV", shot_id="s1"),
        admin_user,
    )
    assert col.device_name == "dev"
    assert col.shot_id == "s1"


def test_create_collection_missing_device_name_for_shot(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Providing shot_id without device_name raises a validation error."""
    with pytest.raises(FDSValidationError, match="device_name is required"):
        collection_service.create(
            CollectionCreate(name="orphan", shot_id="s1"),
            admin_user,
        )


def test_create_collection_nonexistent_shot(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """Creating a Collection for a shot that does not exist raises ResourceNotFoundError."""
    _make_device(device_service, admin_user)
    with pytest.raises(ResourceNotFoundError):
        collection_service.create(
            CollectionCreate(name="bad", device_name="DEV", shot_id="ghost"),
            admin_user,
        )


def test_create_collection_nonexistent_device(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Creating a device-scoped Collection for a non-existent device raises DeviceNotFoundError."""
    with pytest.raises(DeviceNotFoundError):
        collection_service.create(
            CollectionCreate(name="ghost-col", device_name="GHOST"),
            admin_user,
        )


def test_create_collection_name_collision(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Creating two Collections with the same name in the same scope raises ConflictError."""
    collection_service.create(CollectionCreate(name="dup"), admin_user)
    with pytest.raises(ConflictError):
        collection_service.create(CollectionCreate(name="dup"), admin_user)


def test_create_collection_same_name_different_scope(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """The same name can be reused in different scopes (global vs device-level)."""
    _make_device(device_service, admin_user)
    collection_service.create(CollectionCreate(name="results"), admin_user)
    col = collection_service.create(
        CollectionCreate(name="results", device_name="DEV"), admin_user
    )
    assert col.device_name == "dev"


def test_create_collection_unauthorized_global(
    collection_service: CollectionService,
):
    """Non-admin users cannot create global Collections."""
    non_admin = AuthenticatedUser(id="user", scopes=())
    with pytest.raises(ForbiddenError):
        collection_service.create(CollectionCreate(name="forbidden"), non_admin)


def test_create_collection_unauthorized_device(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """A user without device-admin scope cannot create a device-scoped Collection."""
    _make_device(device_service, admin_user)
    wrong_user = AuthenticatedUser(id="other", scopes=("other_admin",))
    with pytest.raises(ForbiddenError):
        collection_service.create(
            CollectionCreate(name="nope", device_name="DEV"), wrong_user
        )


def test_get_collection_by_id(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """get() retrieves a Collection by its primary key."""
    col = collection_service.create(CollectionCreate(name="lookup"), admin_user)
    retrieved = collection_service.get(col.id)
    assert retrieved is not None
    assert retrieved.id == col.id


def test_get_collection_not_found(collection_service: CollectionService):
    """get() returns None for a non-existent ID."""
    assert collection_service.get(9999) is None


def test_get_by_name_in_context_global(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """get_by_name_in_context_or_raise resolves a global Collection by name."""
    collection_service.create(CollectionCreate(name="global-run"), admin_user)
    col = collection_service.get_by_name_in_context_or_raise(
        name="global-run", user=admin_user
    )
    assert col.name == "global-run"


def test_get_by_name_in_context_not_found(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """get_by_name_in_context_or_raise raises ResourceNotFoundError for an absent name."""
    with pytest.raises(ResourceNotFoundError, match="Global collection"):
        collection_service.get_by_name_in_context_or_raise(
            name="missing", user=admin_user
        )


def test_get_multi_global(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """get_multi returns only global (unscoped) Collections."""
    collection_service.create(CollectionCreate(name="g1"), admin_user)
    collection_service.create(CollectionCreate(name="g2"), admin_user)
    results = collection_service.get_multi(user=admin_user)
    assert len(results) == 2


def test_get_collections_for_device(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """get_collections_for_device excludes shot-scoped and global Collections."""
    _make_device(device_service, admin_user, name="D1")
    _make_device(device_service, admin_user, name="D2")
    collection_service.create(
        CollectionCreate(name="d1-col", device_name="D1"), admin_user
    )
    collection_service.create(
        CollectionCreate(name="d2-col", device_name="D2"), admin_user
    )
    collection_service.create(CollectionCreate(name="global"), admin_user)

    results = collection_service.get_collections_for_device("D1", user=admin_user)
    assert len(results) == 1
    assert results[0].name == "d1-col"


def test_get_collections_for_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """get_collections_for_shot returns only Collections scoped to that shot."""
    _make_device(device_service, admin_user)
    _make_shot(shot_service, admin_user, shot_id="s1")
    _make_shot(shot_service, admin_user, shot_id="s2")
    collection_service.create(
        CollectionCreate(name="run-a", device_name="DEV", shot_id="s1"), admin_user
    )
    collection_service.create(
        CollectionCreate(name="run-b", device_name="DEV", shot_id="s2"), admin_user
    )

    results = collection_service.get_collections_for_shot("s1", "DEV", user=admin_user)
    assert len(results) == 1
    assert results[0].shot_id == "s1"


def test_update_collection(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """update() applies partial changes to a Collection."""
    col = collection_service.create(
        CollectionCreate(name="before", title="Old Title"), admin_user
    )
    assert col.id is not None
    updated = collection_service.update(
        id=col.id,
        obj_in=CollectionUpdate(title="New Title"),
        user=admin_user,
    )
    assert updated.title == "New Title"
    assert updated.name == "before"


def test_update_collection_not_found(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Updating a non-existent Collection raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        collection_service.update(
            id=9999, obj_in=CollectionUpdate(title="X"), user=admin_user
        )


def test_update_collection_cannot_change_device(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """Attempting to change device_name during update raises ForbiddenError."""
    _make_device(device_service, admin_user, name="D1")
    _make_device(device_service, admin_user, name="D2")
    col = collection_service.create(
        CollectionCreate(name="col", device_name="D1"), admin_user
    )
    assert col.id is not None
    with pytest.raises(ForbiddenError):
        collection_service.update(
            id=col.id, obj_in=CollectionUpdate(device_name="D2"), user=admin_user
        )


def test_delete_collection(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """delete() removes a Collection; subsequent get() returns None."""
    col = collection_service.create(CollectionCreate(name="bye"), admin_user)
    assert col.id is not None
    collection_service.delete(col.id, admin_user)
    assert collection_service.get(col.id) is None


def test_delete_collection_not_found(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Deleting a non-existent Collection raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        collection_service.delete(9999, admin_user)


def test_add_and_remove_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """A Dataset can be added to a Collection and removed again."""
    _make_device(device_service, admin_user)
    _make_shot(shot_service, admin_user)
    ds = _make_dataset(
        dataset_service, admin_user, name="profiles", device_name="DEV", shot_id="s1"
    )
    assert ds.id is not None
    col = collection_service.create(CollectionCreate(name="run"), admin_user)
    assert col.id is not None

    collection_service.add_dataset(col.id, ds.id, admin_user)
    read = collection_service.to_read_model(col)
    assert any(d.id == ds.id for d in (read.datasets or []))

    collection_service.remove_dataset(col.id, ds.id, admin_user)
    read_after = collection_service.to_read_model(col)
    assert not any(d.id == ds.id for d in (read_after.datasets or []))


def test_add_dataset_duplicate(
    dataset_service: DatasetService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """Adding the same Dataset twice raises ConflictError."""
    ds = _make_dataset(dataset_service, admin_user)
    assert ds.id is not None
    col = collection_service.create(CollectionCreate(name="run"), admin_user)
    assert col.id is not None
    collection_service.add_dataset(col.id, ds.id, admin_user)
    with pytest.raises(ConflictError):
        collection_service.add_dataset(col.id, ds.id, admin_user)


def test_add_dataset_collection_not_found(
    dataset_service: DatasetService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """Adding a Dataset to a non-existent Collection raises ResourceNotFoundError."""
    ds = _make_dataset(dataset_service, admin_user)
    assert ds.id is not None
    with pytest.raises(ResourceNotFoundError):
        collection_service.add_dataset(9999, ds.id, admin_user)


def test_remove_dataset_not_member(
    dataset_service: DatasetService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """Removing a Dataset that is not a member raises ResourceNotFoundError."""
    ds = _make_dataset(dataset_service, admin_user)
    assert ds.id is not None
    col = collection_service.create(CollectionCreate(name="run"), admin_user)
    assert col.id is not None
    with pytest.raises(ResourceNotFoundError):
        collection_service.remove_dataset(col.id, ds.id, admin_user)


def test_dataset_belongs_to_multiple_collections(
    dataset_service: DatasetService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """A single Dataset can be a member of multiple Collections simultaneously."""
    ds = _make_dataset(dataset_service, admin_user)
    assert ds.id is not None
    col_a = collection_service.create(CollectionCreate(name="col-a"), admin_user)
    assert col_a.id is not None
    col_b = collection_service.create(CollectionCreate(name="col-b"), admin_user)
    assert col_b.id is not None
    collection_service.add_dataset(col_a.id, ds.id, admin_user)
    collection_service.add_dataset(col_b.id, ds.id, admin_user)

    read_a = collection_service.to_read_model(col_a)
    read_b = collection_service.to_read_model(col_b)
    assert any(d.id == ds.id for d in (read_a.datasets or []))
    assert any(d.id == ds.id for d in (read_b.datasets or []))


def test_add_and_remove_child_collection(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """A Collection can be nested inside another; removal unlinks it."""
    parent = collection_service.create(CollectionCreate(name="parent"), admin_user)
    assert parent.id is not None
    child = collection_service.create(CollectionCreate(name="child"), admin_user)
    assert child.id is not None

    collection_service.add_child_collection(parent.id, child.id, admin_user)
    read = collection_service.to_read_model(parent)
    assert any(c.id == child.id for c in (read.child_collections or []))

    collection_service.remove_child_collection(parent.id, child.id, admin_user)
    read_after = collection_service.to_read_model(parent)
    assert not any(c.id == child.id for c in (read_after.child_collections or []))


def test_add_child_collection_self_reference(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """A Collection cannot contain itself."""
    col = collection_service.create(CollectionCreate(name="self"), admin_user)
    assert col.id is not None
    with pytest.raises(FDSValidationError, match="cannot contain itself"):
        collection_service.add_child_collection(col.id, col.id, admin_user)


def test_add_child_collection_duplicate(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Nesting the same child twice raises ConflictError."""
    parent = collection_service.create(CollectionCreate(name="p"), admin_user)
    assert parent.id is not None
    child = collection_service.create(CollectionCreate(name="c"), admin_user)
    assert child.id is not None
    collection_service.add_child_collection(parent.id, child.id, admin_user)
    with pytest.raises(ConflictError):
        collection_service.add_child_collection(parent.id, child.id, admin_user)


def test_remove_child_collection_not_nested(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Removing a child that is not nested raises ResourceNotFoundError."""
    parent = collection_service.create(CollectionCreate(name="p"), admin_user)
    assert parent.id is not None
    child = collection_service.create(CollectionCreate(name="c"), admin_user)
    assert child.id is not None
    with pytest.raises(ResourceNotFoundError):
        collection_service.remove_child_collection(parent.id, child.id, admin_user)


def test_child_collections_not_recursive_in_read_model(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """Child Collections inlined in to_read_model have their own child_collections omitted."""
    grandparent = collection_service.create(CollectionCreate(name="gp"), admin_user)
    assert grandparent.id is not None
    parent = collection_service.create(CollectionCreate(name="p"), admin_user)
    assert parent.id is not None
    child = collection_service.create(CollectionCreate(name="c"), admin_user)
    assert child.id is not None
    collection_service.add_child_collection(grandparent.id, parent.id, admin_user)
    collection_service.add_child_collection(parent.id, child.id, admin_user)

    read = collection_service.to_read_model(grandparent)
    assert read.child_collections is not None
    assert len(read.child_collections) == 1
    # The parent is inlined but its own children are not recursed into
    assert read.child_collections[0].child_collections is None


def test_to_read_model_effective_access_level(
    device_service: DeviceService,
    collection_service: CollectionService,
    admin_user: AuthenticatedUser,
):
    """effective_access_level is resolved from the device when not set on the Collection."""
    device_service.create(
        DeviceCreate(name="PUB", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    col = collection_service.create(
        CollectionCreate(name="col", device_name="PUB"),
        admin_user,
    )
    read = collection_service.to_read_model(col)
    assert read.effective_access_level == AccessLevel.PUBLIC


def test_to_read_model_empty_collection(
    collection_service: CollectionService, admin_user: AuthenticatedUser
):
    """A Collection with no members serialises with datasets=None and child_collections=None."""
    col = collection_service.create(CollectionCreate(name="empty"), admin_user)
    read = collection_service.to_read_model(col)
    assert read.datasets is None
    assert read.child_collections is None
