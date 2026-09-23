import pytest
from sqlmodel import Session

from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def request_line(lines: list[dict]) -> dict:
    (line,) = [
        entry
        for entry in lines
        if entry.get("logger") == "fds.audit" and entry["event"] == "request"
    ]
    return line


@pytest.fixture
def catalogue(session: Session, admin_user: AuthenticatedUser):
    """One dataset at each access level, on the same shot."""
    DeviceService(session).create(
        DeviceCreate(name="mast", access_level=AccessLevel.PUBLIC), admin_user
    )
    ShotService(session).create(
        ShotCreate(id="30420", device_name="mast", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    service = DatasetService(session)
    public = service.create(
        DatasetCreate(
            name="ip",
            shot_id="30420",
            device_name="mast",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    restricted = service.create(
        DatasetCreate(
            name="thomson",
            shot_id="30420",
            device_name="mast",
            access_level=AccessLevel.RESTRICTED,
        ),
        admin_user,
    )
    embargoed = service.create(
        DatasetCreate(
            name="mag",
            shot_id="30420",
            device_name="mast",
            access_level=AccessLevel.EMBARGOED,
        ),
        admin_user,
    )
    return public, restricted, embargoed


class TestListedTier:
    def test_restricted_dataset_is_recorded_from_a_list(
        self, test_client, admin_user_token, catalogue, log_lines
    ):
        _, restricted, _ = catalogue

        response = test_client.get("/v1/datasets?limit=100", headers=admin_user_token)
        assert response.status_code == 200

        line = request_line(log_lines())
        assert line["restricted_listed"] == {"dataset": [restricted.id]}

    def test_public_and_embargoed_are_not_recorded(
        self, test_client, admin_user_token, catalogue, log_lines
    ):
        """Embargoed metadata is discoverable by everyone, so reading it needs
        no permission. Only RESTRICTED hides metadata."""
        public, _, embargoed = catalogue

        test_client.get("/v1/datasets?limit=100", headers=admin_user_token)

        recorded = request_line(log_lines())["restricted_listed"]["dataset"]
        assert public.id not in recorded
        assert embargoed.id not in recorded

    def test_returned_counts_what_was_served(
        self, test_client, admin_user_token, catalogue, log_lines
    ):
        """The only signal that would show an unbounded `limit` being abused."""
        test_client.get("/v1/datasets?limit=100", headers=admin_user_token)

        assert request_line(log_lines())["returned"] == 3


class TestReadTier:
    def test_single_read_lands_in_the_read_tier(
        self, test_client, admin_user_token, catalogue, log_lines
    ):
        _, restricted, _ = catalogue

        response = test_client.get(
            f"/v1/datasets/id/{restricted.id}", headers=admin_user_token
        )
        assert response.status_code == 200

        line = request_line(log_lines())
        assert line["restricted_read"] == {"dataset": [restricted.id]}
        assert "restricted_listed" not in line


class TestNothingToRecord:
    def test_public_only_request_carries_no_arrays(
        self, test_client, catalogue, log_lines
    ):
        public, _, _ = catalogue

        test_client.get(f"/v1/datasets/id/{public.id}")

        line = request_line(log_lines())
        assert "restricted_read" not in line
        assert "restricted_listed" not in line
