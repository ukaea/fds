from datetime import UTC

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import (
    ActivityAgentInput,
    ActivityCreate,
    ActivityType,
    AgentRole,
)
from app.models.dataset import DatasetCreate
from app.models.device import Device
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.jsonld import (
    FUEL_EXECUTOR_ROLE,
    FUEL_INPUT_ROLE,
    FUEL_INSTRUMENT_ROLE,
    FUEL_ORCHESTRATOR_ROLE,
)
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
        SourceCreate(
            name="prov-source",
            description="Provenance Source",
            kind=SourceKind.SOFTWARE,
        ),
        user=admin_user,
    )

    assert source.id is not None
    activity_service = ActivityService(session)
    activity = activity_service.create(
        ActivityCreate(
            source_id=source.id,
            activity_type=ActivityType.SIMULATION,
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

    url = f"/api/v1/datasets/id/{dataset.id}"
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
    assert prov["prov:type"] == "simulation"

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
    url = f"/api/v1/datasets/id/{dataset.id}"
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
    from datetime import datetime

    device = Device(name="ts-device", type="tokamak")
    session.add(device)
    shot = Shot(id="300", device_name=device.name)
    session.add(shot)
    session.commit()

    source = SourceService(session).create(
        SourceCreate(name="ts-source", kind=SourceKind.SOFTWARE), user=admin_user
    )
    assert source.id is not None
    activity = ActivityService(session).create(
        ActivityCreate(
            source_id=source.id,
            started_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            ended_at=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
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
    url = f"/api/v1/datasets/id/{dataset.id}"
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
    """prov:used lists the input datasets declared on the producing Activity."""
    device = Device(name="inp-prov-device", type="tokamak")
    session.add(device)
    shot = Shot(id="400", device_name=device.name)
    session.add(shot)
    session.commit()

    source = SourceService(session).create(
        SourceCreate(name="inp-source", kind=SourceKind.SOFTWARE), user=admin_user
    )
    assert source.id is not None

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
    assert raw.id is not None

    activity = ActivityService(session).create(
        ActivityCreate(
            source_id=source.id, activity_type=ActivityType.SIMULATION, inputs=[raw.id]
        ),
        user=admin_user,
    )
    assert activity.id is not None

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

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    url = f"/api/v1/datasets/id/{derived.id}"
    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200

    prov = resp.json()["prov:wasGeneratedBy"]
    assert "prov:used" in prov
    used = prov["prov:used"]
    assert len(used) == 1
    assert used[0]["@type"] == "prov:Entity"
    assert str(raw.id) in used[0]["@id"]
    usage = prov["prov:qualifiedUsage"]
    assert len(usage) == 1
    assert usage[0]["prov:hadRole"] == {"@id": FUEL_INPUT_ROLE}
    assert str(raw.id) in usage[0]["prov:entity"]["@id"]


def test_jsonld_provenance_with_instrument(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    """An instrument (Source kind=instrument) serialises as a roled prov:used Entity."""
    device = Device(name="instr-device", type="tokamak")
    session.add(device)
    shot = Shot(id="500", device_name=device.name)
    session.add(shot)
    session.commit()

    diagnostic = SourceService(session).create(
        SourceCreate(name="thomson-scattering", kind=SourceKind.INSTRUMENT),
        user=admin_user,
    )
    assert diagnostic.id is not None

    # The acquisition has no agent — the instrument is a used entity, not an agent.
    acquisition = ActivityService(session).create(
        ActivityCreate(
            activity_type=ActivityType.MEASUREMENT, instruments=[diagnostic.id]
        ),
        user=admin_user,
    )
    assert acquisition.id is not None

    raw = DatasetService(session).create(
        DatasetCreate(
            name="raw-thomson",
            level=0,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/raw-thomson",
            access_level=AccessLevel("public"),
            activity_id=acquisition.id,
        ),
        user=admin_user,
    )

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    resp = test_client.get(f"/api/v1/datasets/id/{raw.id}", headers=headers)
    assert resp.status_code == 200

    prov = resp.json()["prov:wasGeneratedBy"]
    usage = prov["prov:qualifiedUsage"]
    instrument_usages = [
        u for u in usage if u["prov:hadRole"] == {"@id": FUEL_INSTRUMENT_ROLE}
    ]
    assert len(instrument_usages) == 1
    assert str(diagnostic.id) in instrument_usages[0]["prov:entity"]["@id"]
    # No agent: the acquisition is agent-less, so no executor association.
    assert "prov:wasAssociatedWith" not in prov


def test_jsonld_multi_agent_associations(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict[str, str],
):
    """Executor + orchestrator appear as roled prov:qualifiedAssociation."""
    device = Device(name="multi-agent-device", type="tokamak")
    session.add(device)
    shot = Shot(id="600", device_name=device.name)
    session.add(shot)
    session.commit()

    code = SourceService(session).create(
        SourceCreate(name="thomson-analysis", kind=SourceKind.SOFTWARE),
        user=admin_user,
    )
    scheduler = SourceService(session).create(
        SourceCreate(name="intershot-scheduler", kind=SourceKind.SOFTWARE),
        user=admin_user,
    )
    assert code.id is not None
    assert scheduler.id is not None

    analysis = ActivityService(session).create(
        ActivityCreate(
            source_id=code.id,
            activity_type=ActivityType.ANALYSIS,
            agents=[
                ActivityAgentInput(source_id=scheduler.id, role=AgentRole.ORCHESTRATOR)
            ],
        ),
        user=admin_user,
    )
    assert analysis.id is not None

    profile = DatasetService(session).create(
        DatasetCreate(
            name="t_e_profile",
            level=2,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/te",
            access_level=AccessLevel("public"),
            activity_id=analysis.id,
        ),
        user=admin_user,
    )

    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"
    resp = test_client.get(f"/api/v1/datasets/id/{profile.id}", headers=headers)
    assert resp.status_code == 200

    prov = resp.json()["prov:wasGeneratedBy"]
    # Executor still serialises as the primary wasAssociatedWith (a SoftwareAgent).
    assert prov["prov:wasAssociatedWith"]["@type"] == "prov:SoftwareAgent"
    assert str(code.id) in prov["prov:wasAssociatedWith"]["@id"]
    # Both agents appear with roles in the qualified association list.
    assoc = prov["prov:qualifiedAssociation"]
    roles = {a["prov:hadRole"]["@id"] for a in assoc}
    assert roles == {FUEL_EXECUTOR_ROLE, FUEL_ORCHESTRATOR_ROLE}
