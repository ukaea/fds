from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate
from app.models.dataset import DatasetCreate
from app.models.device import Device
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.models.source import SourceCreate
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.source_service import SourceService


def test_jsonld_provenance(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    # 1. Setup Resources
    device = Device(name="prov-device", description="Test Device", type="tokamak")
    session.add(device)
    session.commit()

    shot = Shot(id="100", device_name=device.name)
    session.add(shot)
    session.commit()

    # Create Source and Activity
    source_service = SourceService(session)
    source = source_service.create(
        SourceCreate(name="prov-source", description="Provenance Source"),
        user=admin_user,
    )

    assert source.id is not None
    activity_service = ActivityService(session)
    activity = activity_service.create(
        ActivityCreate(
            source_id=source.id,
            activity_type="SIMULATION",
            source_version="v1.0",
            parameters={"run_id": 99},
        ),
        user=admin_user,
    )

    # Create Dataset linked to the Activity
    dataset_service = DatasetService(session)
    dataset = dataset_service.create(
        DatasetCreate(
            name="prov-dataset",
            level=1,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/prov",
            access_level=AccessLevel("public"),
            activity_id=activity.id,
        ),
        user=admin_user,
    )

    # 2. Request JSON-LD
    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"

    url = f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/{dataset.name}"
    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/ld+json"

    data = resp.json()

    # 3. Verify PROV-O structure
    assert "@context" in data
    assert "prov" in data["@context"]
    assert "prov:wasGeneratedBy" in data

    prov = data["prov:wasGeneratedBy"]
    assert prov["@type"] == "prov:Activity"
    assert prov["prov:type"] == "SIMULATION"

    # Verify Agent (Source) association
    agent = prov["prov:wasAssociatedWith"]
    assert agent["@type"] == "prov:SoftwareAgent"
    assert agent["dct:title"] == "prov-source"
    assert agent["dcat:version"] == "v1.0"

    # Verify parameters
    assert prov["prov:value"] == {"run_id": 99}


def test_jsonld_no_provenance(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    """Dataset without an activity should not include prov:wasGeneratedBy."""
    device = Device(name="no-prov-device", type="tokamak")
    session.add(device)
    shot = Shot(id="200", device_name=device.name)
    session.add(shot)
    session.commit()

    dataset_service = DatasetService(session)
    dataset = dataset_service.create(
        DatasetCreate(
            name="no-prov-dataset",
            level=1,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/noprov",
            access_level=AccessLevel("public"),
        ),
        user=admin_user,
    )

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    url = f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/{dataset.name}"
    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200
    assert "prov:wasGeneratedBy" not in resp.json()


def test_jsonld_provenance_with_timestamps(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    """prov:startedAtTime and prov:endedAtTime appear when set on the Activity."""
    from datetime import datetime, timezone

    device = Device(name="ts-device", type="tokamak")
    session.add(device)
    shot = Shot(id="300", device_name=device.name)
    session.add(shot)
    session.commit()

    source = SourceService(session).create(
        SourceCreate(name="ts-source"), user=admin_user
    )
    assert source.id is not None
    activity = ActivityService(session).create(
        ActivityCreate(
            source_id=source.id,
            started_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            ended_at=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        ),
        user=admin_user,
    )
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="ts-dataset",
            level=0,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/ts",
            access_level=AccessLevel("public"),
            activity_id=activity.id,
        ),
        user=admin_user,
    )

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    url = f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/{dataset.name}"
    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200
    prov = resp.json()["prov:wasGeneratedBy"]
    assert "prov:startedAtTime" in prov
    assert "prov:endedAtTime" in prov


def test_jsonld_provenance_with_inputs(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    """prov:used lists input datasets when ActivityInputs are registered."""
    from app.models.activity import ActivityCreate
    from app.services.activity_service import ActivityService

    device = Device(name="inp-prov-device", type="tokamak")
    session.add(device)
    shot = Shot(id="400", device_name=device.name)
    session.add(shot)
    session.commit()

    source = SourceService(session).create(
        SourceCreate(name="inp-source"), user=admin_user
    )
    assert source.id is not None

    activity = ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type="SIMULATION"),
        user=admin_user,
    )

    raw = DatasetService(session).create(
        DatasetCreate(
            name="raw-input",
            level=0,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/raw",
            access_level=AccessLevel("public"),
        ),
        user=admin_user,
    )
    derived = DatasetService(session).create(
        DatasetCreate(
            name="derived",
            level=1,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/derived",
            access_level=AccessLevel("public"),
            activity_id=activity.id,
        ),
        user=admin_user,
    )

    assert raw.id is not None
    assert activity.id is not None
    ActivityService(session).add_input(
        activity_id=activity.id, dataset_id=raw.id, user=admin_user
    )

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    url = f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/{derived.name}"
    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200

    prov = resp.json()["prov:wasGeneratedBy"]
    assert "prov:used" in prov
    used = prov["prov:used"]
    assert len(used) == 1
    assert used[0]["@type"] == "prov:Entity"
    assert str(raw.id) in used[0]["@id"]
