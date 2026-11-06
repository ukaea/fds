import pytest
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize("kind", ["datasets", "collections"])
def test_update_rejects_null_name(test_client, admin_user_token, kind):
    created = test_client.post(
        f"/v1/{kind}/", headers=admin_user_token, json={"name": "original"}
    )
    assert created.status_code == 201
    record_id = created.json()["id"]
    response = test_client.patch(
        f"/v1/{kind}/{record_id}",
        headers=admin_user_token,
        json={"name": None},
    )
    assert response.status_code == 422
    response = test_client.patch(
        f"/v1/{kind}/{record_id}", headers=admin_user_token, json={}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "original"


@pytest.mark.parametrize("kind", ["datasets", "collections"])
def test_update_missing_activity_preserves_integrity_error(
    test_client, admin_user_token, kind
):
    created = test_client.post(
        f"/v1/{kind}/", headers=admin_user_token, json={"name": "original"}
    )
    assert created.status_code == 201
    record_id = created.json()["id"]
    with pytest.raises(IntegrityError) as exc:
        test_client.patch(
            f"/v1/{kind}/{record_id}",
            headers=admin_user_token,
            json={"activity_id": 999999, "name": "changed"},
        )
    assert isinstance(exc.value.orig, ForeignKeyViolation)
    response = test_client.patch(
        f"/v1/{kind}/{record_id}", headers=admin_user_token, json={}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "original"
    assert response.json().get("activity_id") is None


@pytest.mark.parametrize(
    "operation", ["create_dataset", "update_dataset", "update_collection"]
)
@pytest.mark.parametrize(
    "error_type", [UniqueViolation, ForeignKeyViolation, NotNullViolation]
)
def test_persistence_maps_only_unique_violations(
    test_client, session, admin_user_token, mocker, operation, error_type
):
    kind = "collections" if operation == "update_collection" else "datasets"
    record_id = None
    if operation.startswith("update"):
        created = test_client.post(
            f"/v1/{kind}/", headers=admin_user_token, json={"name": "original"}
        )
        assert created.status_code == 201
        record_id = created.json()["id"]

    error = IntegrityError("INSERT or UPDATE", {}, error_type("constraint failed"))
    commit = mocker.patch.object(session, "commit", side_effect=error)
    rollback = mocker.spy(session, "rollback")

    def request():
        if record_id is None:
            return test_client.post(
                f"/v1/{kind}/", headers=admin_user_token, json={"name": "changed"}
            )
        return test_client.patch(
            f"/v1/{kind}/{record_id}",
            headers=admin_user_token,
            json={"name": "changed"},
        )

    if error_type is UniqueViolation:
        assert request().status_code == 409
    else:
        with pytest.raises(IntegrityError) as exc:
            request()
        assert exc.value is error
    commit.assert_called_once()
    rollback.assert_called_once()
