from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import Device
from app.models.shot import Shot


def test_hybrid_storage_fields(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    # 1. Create Context (Device & Shot)
    device = Device(name="test-device-hybrid", description="Hybrid Storage Test Device")
    session.add(device)
    session.commit()

    shot = Shot(id="1001", device_name=device.name)
    session.add(shot)
    session.commit()

    # 2. Create Dataset with Hybrid Storage fields
    dataset_data = {
        "name": "hybrid_dataset",
        "level": 1,
        "url": "s3://bucket/hybrid",
        "device_name": device.name,
        "shot_id": shot.id,
        "media_type": "application/vnd.icechunk+zarr",
        "format": "icechunk",
        "title": "Hybrid Storage Dataset",
    }

    # We use the API to create it to ensure the Pydantic model accepts the fields
    # Note: We must use the admin_user_token to be authorized
    response = test_client.post(
        f"/api/v1/devices/{device.name}/shots/{shot.id}/datasets/",
        json=dataset_data,
        headers=admin_user_token,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["media_type"] == "application/vnd.icechunk+zarr"
    assert data["format"] == "icechunk"
    dataset_id = data["id"]

    # 3. Retrieve content negotiation (JSON-LD) — by ID
    response = test_client.get(
        f"/api/v1/datasets/id/{dataset_id}",
        headers={"Accept": "application/ld+json"},
    )
    assert response.status_code == 200
    ld_data = response.json()

    # 4. Verify JSON-LD mapping — media_type and format now live in dcat:distribution
    assert "dcat:distribution" in ld_data
    assert len(ld_data["dcat:distribution"]) == 1
    dist = ld_data["dcat:distribution"][0]
    assert dist["dcat:mediaType"] == "application/vnd.icechunk+zarr"
    assert dist["dct:format"] == "icechunk"
    # S3 URIs use accessURL only; downloadURL is reserved for HTTP/S direct downloads
    assert dist["dcat:accessURL"] == "s3://bucket/hybrid"
    assert "dcat:downloadURL" not in ld_data
