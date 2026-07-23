import pytest

from tests.integration.conftest import FDS_URL

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded_data")]


def test_geometry_versions_registered(http_client):
    resp = http_client.get(f"{FDS_URL}/devices/mast/datasets")
    assert resp.status_code == 200
    names = {ds["name"] for ds in resp.json()}
    assert {"thomson_positions_v1", "thomson_positions_v2"} <= names


def test_geometry_off_by_default(http_client):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/datasets/thomson_scattering"
    )
    assert resp.status_code == 200
    assert "geometry" not in resp.json()[0]


@pytest.mark.parametrize(
    ("shot_id", "expected_version"),
    [("30420", "thomson_positions_v1"), ("30421", "thomson_positions_v2")],
)
def test_geometry_resolves_per_shot(http_client, shot_id, expected_version):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/{shot_id}/datasets/thomson_scattering",
        params={"include_geometry": "true"},
    )
    assert resp.status_code == 200
    geometry = resp.json()[0]["geometry"]
    assert len(geometry) == 1
    assert geometry[0]["name"] == expected_version
    # storage_options are withheld unless include_storage_options is also set.
    assert "storage_options" not in geometry[0]


def test_geometry_storage_options_vended(http_client):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/datasets/thomson_scattering",
        params={"include_geometry": "true", "include_storage_options": "true"},
    )
    assert resp.status_code == 200
    geometry = resp.json()[0]["geometry"]
    assert geometry[0]["storage_options"] is not None
