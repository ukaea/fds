"""Full-stack reference-calibration resolution (ADR-0037).

Exercises the seeded Thomson calibration chain: two device-level stages on
`mast`, resolved as an ordered chain via `?include_calibration=true`.
"""

import pytest

from tests.integration.conftest import FDS_URL

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded_data")]


def test_calibration_versions_registered(http_client):
    resp = http_client.get(f"{FDS_URL}/devices/mast/datasets")
    assert resp.status_code == 200
    names = {ds["name"] for ds in resp.json()}
    assert {"thomson_gain", "thomson_absolute"} <= names


def test_calibration_off_by_default(http_client):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/datasets/thomson_scattering"
    )
    assert resp.status_code == 200
    assert "calibration" not in resp.json()[0]


@pytest.mark.parametrize("shot_id", ["30420", "30421"])
def test_calibration_resolves_as_ordered_chain(http_client, shot_id):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/{shot_id}/datasets/thomson_scattering",
        params={"include_calibration": "true"},
    )
    assert resp.status_code == 200
    chain = resp.json()[0]["calibration"]
    # Stage-ordered chain: gain (stage 1) then absolute (stage 2).
    assert [c["name"] for c in chain] == ["thomson_gain", "thomson_absolute"]
    # storage_options are withheld unless include_storage_options is also set.
    assert "storage_options" not in chain[0]


def test_calibration_storage_options_vended(http_client):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/datasets/thomson_scattering",
        params={"include_calibration": "true", "include_storage_options": "true"},
    )
    assert resp.status_code == 200
    chain = resp.json()[0]["calibration"]
    assert all(c["storage_options"] is not None for c in chain)
