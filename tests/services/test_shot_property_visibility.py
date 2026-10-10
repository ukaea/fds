import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.identity import ANONYMOUS_USER
from app.models.policy import AccessLevel
from app.models.scientific_metadata import ScientificProperty
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

DEVICE = "MAST-U"
L_MODE = "confinement_mode:L-mode"


@pytest.fixture(name="restricted_shot_with_public_dataset")
def restricted_shot_with_public_dataset_fixture(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    DeviceService(session).create(
        DeviceCreate(name=DEVICE, type="Tokamak", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(
        ShotCreate(
            id="50001",
            device_name=DEVICE,
            access_level=AccessLevel.RESTRICTED,
            scientific_metadata=[
                ScientificProperty(name="confinement_mode", value="L-mode")
            ],
        ),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="equilibrium",
            level=2,
            device_name=DEVICE,
            shot_id="50001",
            access_level=AccessLevel.PUBLIC,
            url="s3://data/50001/equilibrium.nc",
        ),
        admin_user,
    )
    session.commit()


@pytest.mark.usefixtures("restricted_shot_with_public_dataset")
def test_shot_property_filter_does_not_match_on_an_unreadable_shot(session: Session):
    """A caller who cannot read a shot cannot learn its properties by filtering."""
    datasets = DatasetService(session)

    assert (
        datasets.get_datasets_for_device(
            DEVICE, ANONYMOUS_USER, shot_properties=[L_MODE]
        )
        == []
    )
    assert datasets.get_multi(ANONYMOUS_USER, shot_properties=[L_MODE]) == []


@pytest.mark.usefixtures("restricted_shot_with_public_dataset")
def test_shot_property_filter_matches_on_a_readable_shot(
    session: Session, admin_user: AuthenticatedUser
):
    datasets = DatasetService(session)

    assert [
        d.shot_id
        for d in datasets.get_datasets_for_device(
            DEVICE, admin_user, shot_properties=[L_MODE]
        )
    ] == ["50001"]
    assert [
        d.shot_id for d in datasets.get_multi(admin_user, shot_properties=[L_MODE])
    ] == ["50001"]


@pytest.mark.usefixtures("restricted_shot_with_public_dataset")
def test_the_dataset_itself_stays_listed_without_a_shot_filter(session: Session):
    """The dataset's own public level still applies; only the shot filter changes."""
    datasets = DatasetService(session)

    assert [
        d.shot_id for d in datasets.get_datasets_for_device(DEVICE, ANONYMOUS_USER)
    ] == ["50001"]
