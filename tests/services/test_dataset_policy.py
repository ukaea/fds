import pytest
from sqlmodel import Session

from app.auth.access_control import get_effective_policy, validate_policy_fields
from app.core.config import config
from app.models.dataset import Dataset, DatasetCreate, DatasetUpdate
from app.models.device import DeviceCreate
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import FDSValidationError, ForbiddenError
from app.services.shot_service import ShotService

pytestmark = pytest.mark.usefixtures("two_idp_config")


@pytest.fixture
def dataset_service(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture
def device_service(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture
def shot_service(session: Session) -> ShotService:
    return ShotService(session)


IDP_A = "https://idp-a.example.com"
IDP_B = "https://idp-b.example.com"


def test_public_with_required_scopes_invalid():
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        validate_policy_fields(AccessLevel.PUBLIC, ["some:scope"], None)


def test_public_with_allowed_idps_invalid():
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        validate_policy_fields(AccessLevel.PUBLIC, None, [IDP_A])


def test_null_access_level_with_required_scopes_invalid():
    with pytest.raises(FDSValidationError, match="required_scopes requires"):
        validate_policy_fields(None, ["some:scope"], None)


def test_null_access_level_with_allowed_idps_invalid():
    with pytest.raises(FDSValidationError, match="allowed_idps requires"):
        validate_policy_fields(None, None, [IDP_A])


def test_allowed_idps_empty_list_invalid():
    with pytest.raises(FDSValidationError, match="must not be an empty list"):
        validate_policy_fields(AccessLevel.RESTRICTED, None, [])


def test_allowed_idps_unknown_issuer_invalid():
    with pytest.raises(FDSValidationError, match="unknown IdP issuer"):
        validate_policy_fields(
            AccessLevel.RESTRICTED, None, ["https://not-trusted.com"]
        )


def test_allowed_idps_fails_when_trusted_idps_missing(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_IDPS", [])
    with pytest.raises(FDSValidationError, match="TRUSTED_IDPS is missing or empty"):
        validate_policy_fields(AccessLevel.RESTRICTED, None, [IDP_A])


def test_restricted_with_empty_required_scopes_valid():
    # Empty list = auth-only gate; should not raise.
    validate_policy_fields(AccessLevel.RESTRICTED, [], None)


def test_restricted_with_scopes_and_idps_valid():
    validate_policy_fields(AccessLevel.RESTRICTED, ["group:scientists"], [IDP_A])


def test_null_access_null_policy_valid():
    # Inheritance scenario: no explicit level or scope fields set.
    validate_policy_fields(None, None, None)


def test_create_public_with_required_scopes_rejected(dataset_service, admin_user):
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        dataset_service.create(
            DatasetCreate(
                name="bad",
                level=1,
                data_url="s3://x",
                access_level=AccessLevel.PUBLIC,
                required_scopes=["some:scope"],
            ),
            user=admin_user,
        )


def test_create_null_access_with_allowed_idps_rejected(dataset_service, admin_user):
    with pytest.raises(FDSValidationError, match="allowed_idps requires"):
        dataset_service.create(
            DatasetCreate(
                name="bad",
                level=1,
                data_url="s3://x",
                allowed_idps=[IDP_A],
            ),
            user=admin_user,
        )


def test_create_restricted_empty_scopes_allowed(dataset_service, admin_user):
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-only",
            level=1,
            data_url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=[],
        ),
        user=admin_user,
    )
    assert ds.id is not None
    assert ds.required_scopes == []


def test_update_transition_to_public_with_scopes_rejected(dataset_service, admin_user):
    ds = dataset_service.create(
        DatasetCreate(
            name="upgrading",
            level=1,
            data_url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["some:scope"],
        ),
        user=admin_user,
    )
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        dataset_service.update(
            db_obj=ds,
            obj_in=DatasetUpdate(access_level=AccessLevel.PUBLIC),
            user=admin_user,
        )


def test_effective_policy_inherits_required_scopes_from_device(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(
            name="LAB-A",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["lab:read"],
        ),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(name="ds", level=1, data_url="s3://x", device_name="LAB-A"),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.required_scopes == ["lab:read"]
    assert policy.access_level == AccessLevel.RESTRICTED


def test_effective_policy_dataset_overrides_device_required_scopes(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(
            name="LAB-B",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["lab:read"],
        ),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(
            name="ds",
            level=1,
            data_url="s3://x",
            device_name="LAB-B",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["special:top-secret"],
        ),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.required_scopes == ["special:top-secret"]


def test_effective_policy_inherits_allowed_idps_from_shot(
    session, device_service, shot_service, dataset_service, admin_user
):
    device_service.create(DeviceCreate(name="DEV-C"), user=admin_user)
    shot_service.create(
        ShotCreate(
            id="S1",
            device_name="DEV-C",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
        ),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(
            name="ds", level=1, data_url="s3://x", device_name="DEV-C", shot_id="S1"
        ),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.allowed_idps == [IDP_A]


def test_effective_policy_no_idp_restriction_when_unset(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(name="OPEN-DEV", access_level=AccessLevel.EMBARGOED),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(name="ds", level=1, data_url="s3://x", device_name="OPEN-DEV"),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.allowed_idps is None


def test_read_access_allowed_idp_permitted(dataset_service, device_service, admin_user):
    device_service.create(
        DeviceCreate(name="DEV-D", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(
            name="ds",
            level=1,
            data_url="s3://x",
            device_name="DEV-D",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
            required_scopes=[],  # explicit auth-only gate so we don't fall to capability check
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u1", scopes=(), issuer=IDP_A)
    # Should not raise — correct IdP, auth-only gate satisfied
    dataset_service.check_read_access(ds, user)


def test_read_access_wrong_idp_denied(dataset_service, device_service, admin_user):
    device_service.create(
        DeviceCreate(name="DEV-E", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(
            name="ds",
            level=1,
            data_url="s3://x",
            device_name="DEV-E",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
            required_scopes=[],
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u2", scopes=(), issuer=IDP_B)
    with pytest.raises(ForbiddenError, match="identity provider"):
        dataset_service.check_read_access(ds, user)


def test_read_access_restricted_empty_scopes_auth_only_gate(
    dataset_service, admin_user
):
    """RESTRICTED + required_scopes=[] gates on authentication only.

    Issuer trust is enforced at the token validation boundary (security.py), not
    re-checked at the service layer. An authenticated AuthenticatedUser object
    passes regardless of its issuer value, provided no allowed_idps restriction
    is set on the dataset.
    """
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-gate",
            level=1,
            data_url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=[],
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u3", scopes=(), issuer="https://test-idp.com")
    # Should not raise — auth-only gate, user is authenticated
    dataset_service.check_read_access(ds, user)


def test_read_access_restricted_empty_scopes_anonymous_denied(
    dataset_service, admin_user
):
    """RESTRICTED + required_scopes=[] still blocks anonymous users."""
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-gate-anon",
            level=1,
            data_url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=[],
        ),
        user=admin_user,
    )
    with pytest.raises(ForbiddenError, match="Authentication required"):
        dataset_service.check_read_access(ds, ANONYMOUS_USER)


def test_download_allowed_idp_correct_scope(session, device_service, admin_user):
    from app.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    device_service.create(
        DeviceCreate(name="DEV-F", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    ds = Dataset(
        name="ds",
        level=1,
        data_url="s3://x",
        access_level=AccessLevel.RESTRICTED,
        device_name="DEV-F",
        required_scopes=["read:data"],
        allowed_idps=[IDP_A],
    )
    user = AuthenticatedUser(id="u", scopes=("read:data",), issuer=IDP_A)
    assert svc._check_download_permission(user, ds) is True


def test_download_correct_scope_wrong_idp_denied(session):
    from app.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        data_url="s3://x",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=["read:data"],
        allowed_idps=[IDP_A],
    )
    user = AuthenticatedUser(id="u", scopes=("read:data",), issuer=IDP_B)
    assert svc._check_download_permission(user, ds) is False


def test_download_restricted_empty_scopes_anonymous_denied(session):
    from app.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        data_url="s3://x",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=[],
    )
    assert svc._check_download_permission(ANONYMOUS_USER, ds) is False


def test_download_embargoed_no_scopes_anonymous_denied(session):
    """Embargoed data should be denied to anonymous users even without required_scopes."""
    from app.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        data_url="s3://x",
        access_level=AccessLevel.EMBARGOED,
    )
    assert svc._check_download_permission(ANONYMOUS_USER, ds) is False
