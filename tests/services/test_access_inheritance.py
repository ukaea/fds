import pytest
from sqlmodel import Session, select

from app.auth.access_control import (
    get_effective_policies,
    get_effective_policy,
    resolve_policy,
)
from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import Device, DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


@pytest.fixture
def device_service(session: Session):
    return DeviceService(session)


@pytest.fixture
def shot_service(session: Session):
    return ShotService(session)


@pytest.fixture
def dataset_service(session: Session):
    return DatasetService(session)


def test_access_inheritance_dataset_from_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (RESTRICTED default) -> Shot (PUBLIC override) -> Dataset (Inherit)
    device_service.create(DeviceCreate(name="TOKAMAK"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="SHOT-1", device_name="TOKAMAK", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    dataset = dataset_service.create(
        DatasetCreate(
            name="data", level=1, url="url", shot_id=shot.id, device_name="TOKAMAK"
        ),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.access_level is None
    assert read_model.effective_access_level == AccessLevel.PUBLIC


def test_access_inheritance_dataset_from_device(
    device_service: DeviceService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (EMBARGOED override) -> Dataset (Inherit, device context)
    device_service.create(
        DeviceCreate(name="SECRET-LAB", access_level=AccessLevel.EMBARGOED),
        user=admin_user,
    )
    dataset = dataset_service.create(
        DatasetCreate(name="top-secret", level=1, url="url", device_name="SECRET-LAB"),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.effective_access_level == AccessLevel.EMBARGOED


def test_access_inheritance_global_default(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    # Setup: Global Dataset -> Inherit (RESTRICTED default)
    dataset = dataset_service.create(
        DatasetCreate(name="global-data", level=1, url="url"), user=admin_user
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.effective_access_level == AccessLevel.RESTRICTED


def test_access_override_at_dataset_level(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (RESTRICTED) -> Shot (RESTRICTED) -> Dataset (EMBARGOED override)
    device_service.create(DeviceCreate(name="DEV"), user=admin_user)
    shot = shot_service.create(ShotCreate(id="S1", device_name="DEV"), user=admin_user)
    dataset = dataset_service.create(
        DatasetCreate(
            name="override",
            level=1,
            url="url",
            shot_id=shot.id,
            device_name="DEV",
            access_level=AccessLevel.EMBARGOED,
        ),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.access_level == AccessLevel.EMBARGOED
    assert read_model.effective_access_level == AccessLevel.EMBARGOED


def test_shot_inherits_from_device(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (PUBLIC) -> Shot (Inherit)
    device_service.create(
        DeviceCreate(name="OPEN-DEV", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    shot = shot_service.create(
        ShotCreate(id="S2", device_name="OPEN-DEV"), user=admin_user
    )

    read_model = shot_service.to_read_model(shot)
    assert read_model.effective_access_level == AccessLevel.PUBLIC


@pytest.mark.parametrize(
    "shot_policy",
    [
        {},
        {"access_level": AccessLevel.PUBLIC},
        {"access_level": AccessLevel.RESTRICTED},
        {"access_level": AccessLevel.RESTRICTED, "required_scopes": ["mast_admin"]},
        {"access_level": AccessLevel.RESTRICTED, "required_scopes": []},
        {
            "access_level": AccessLevel.RESTRICTED,
            "allowed_idps": ["https://idp-a.example.com"],
        },
    ],
)
@pytest.mark.usefixtures("two_idp_config")
def test_resolve_policy_agrees_with_get_effective_policy(
    session: Session, admin_user: AuthenticatedUser, shot_policy: dict
) -> None:
    """The tuple form must decide exactly what the instance form decides.

    ``resolve_policy`` restates the inheritance rule over a tuple so an
    aggregate can resolve a policy without loading the row. Restating a rule is
    how two rules appear, so this pins them together: each field must still fall
    back independently.
    """
    DeviceService(session).create(
        DeviceCreate(
            name="EQUIV",
            type="Tokamak",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["device_scope"],
            allowed_idps=["https://idp-b.example.com"],
        ),
        admin_user,
    )
    device = session.exec(select(Device).where(Device.name == "equiv")).one()
    shot = ShotService(session).create(
        ShotCreate(id="1", device_name="EQUIV", **shot_policy), admin_user
    )

    assert resolve_policy(
        shot.access_level,
        shot.required_scopes,
        shot.allowed_idps,
        get_effective_policy(device, session),
    ) == get_effective_policy(shot, session)


def test_get_effective_policies_resolves_each_record_from_its_own_parents(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """A batch must give each record the policy it would get on its own.

    Both devices have a shot "1", so a shot found by id alone would hand one
    device's datasets the other's policy. The first dataset takes its
    access_level from its shot and its required_scopes from its device.
    """
    for name, embargoed_shot in (("A", True), ("B", False)):
        DeviceService(session).create(
            DeviceCreate(
                name=name,
                type="Tokamak",
                access_level=AccessLevel.RESTRICTED,
                required_scopes=[f"{name}:read"],
            ),
            admin_user,
        )
        ShotService(session).create(
            ShotCreate(
                id="1",
                device_name=name,
                access_level=AccessLevel.EMBARGOED if embargoed_shot else None,
            ),
            admin_user,
        )
    datasets = [
        DatasetService(session).create(
            DatasetCreate(name="d", level=1, device_name=device, shot_id=shot),
            admin_user,
        )
        for device, shot in (("A", "1"), ("B", "1"), ("A", None))
    ]

    policies = get_effective_policies(datasets, session)

    assert [(p.access_level, p.required_scopes) for p in policies] == [
        (AccessLevel.EMBARGOED, ["A:read"]),
        (AccessLevel.RESTRICTED, ["B:read"]),
        (AccessLevel.RESTRICTED, ["A:read"]),
    ]
