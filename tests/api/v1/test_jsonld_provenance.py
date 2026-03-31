from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import Device
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.models.source import SourceCreate
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

    # Create Source
    source_service = SourceService(session)
    source = source_service.create(
        SourceCreate(name="prov-source", description="Provenance Source"),
        user=admin_user,
    )

    # Create Dataset
    dataset_service = DatasetService(session)
    dataset = dataset_service.create(
        DatasetCreate(
            name="prov-dataset",
            level=1,
            device_name=device.name,
            shot_id=shot.id,
            url="s3://test/prov",
            access_level=AccessLevel("public"),
        ),
        user=admin_user,
    )

    # 2. Link Source to Dataset
    link_data = {
        "source_id": source.id,
        "activity_type": "SIMULATION",
        "source_version": "v1.0",
        "parameters": {"run_id": 99},
    }

    resp = test_client.post(
        f"/api/v1/datasets/{dataset.id}/sources",
        json=link_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 201

    # 3. Request JSON-LD
    headers = admin_user_token.copy()
    headers["Accept"] = "application/ld+json"

    # Use the context-aware endpoint
    url = f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/{dataset.name}"

    resp = test_client.get(url, headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/ld+json"

    data = resp.json()

    # 4. Verify PROV-O
    assert "@context" in data
    assert "prov" in data["@context"]
    assert "prov:wasGeneratedBy" in data

    activity = data["prov:wasGeneratedBy"]
    assert activity["@type"] == "prov:Activity"
    assert activity["prov:type"] == "SIMULATION"

    # Verify Entity (Source) usage
    usage = activity["prov:used"]
    assert usage["@type"] == "prov:Entity"
    assert usage["dct:title"] == "prov-source"
    assert usage["dcat:version"] == "v1.0"

    # Verify value/parameters
    assert activity["prov:value"] == {"run_id": 99}
