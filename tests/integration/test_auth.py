import pytest

from tests.integration.conftest import FDS_URL

pytestmark = pytest.mark.integration


def test_admin_token_accepted(http_client, admin_headers):
    resp = http_client.get(f"{FDS_URL}/devices/", headers=admin_headers)
    assert resp.status_code == 200


def test_user_token_accepted(http_client, user_headers):
    resp = http_client.get(f"{FDS_URL}/devices/", headers=user_headers)
    assert resp.status_code == 200


def test_no_token_read_is_allowed(http_client):
    resp = http_client.get(f"{FDS_URL}/devices/")
    assert resp.status_code == 200


def test_no_token_write_is_rejected(http_client):
    resp = http_client.post(
        f"{FDS_URL}/devices/",
        json={"name": "test-device", "description": "test", "access_level": "public"},
    )
    assert resp.status_code in (401, 403)


def test_user_cannot_create_device(http_client, user_headers):
    resp = http_client.post(
        f"{FDS_URL}/devices/",
        json={"name": "test-device", "description": "test", "access_level": "public"},
        headers=user_headers,
    )
    assert resp.status_code == 403


def test_mast_admin_cannot_create_global_device(http_client, mast_admin_headers):
    resp = http_client.post(
        f"{FDS_URL}/devices/",
        json={
            "name": "test-device-2",
            "description": "test",
            "access_level": "public",
        },
        headers=mast_admin_headers,
    )
    assert resp.status_code == 403
