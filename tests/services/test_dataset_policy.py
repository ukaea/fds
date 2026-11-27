import pytest
from sqlmodel import Session

from fds.auth.access_control import get_effective_policy, validate_allowed_idps
from fds.core.config import config
from fds.models.dataset import Dataset, DatasetCreate
from fds.models.device import DeviceCreate
from fds.models.identity import ANONYMOUS_USER, AuthenticatedUser
from fds.models.policy import AccessLevel
from fds.models.shot import ShotCreate
from fds.services.dataset_service import DatasetService
from fds.services.device_service import DeviceService
from fds.services.exceptions import FDSValidationError, ForbiddenError
from fds.services.shot_service import ShotService

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


def test_allowed_idps_empty_list_invalid():
    with pytest.raises(FDSValidationError, match="must not be an empty list"):
        validate_allowed_idps([])


def test_allowed_idps_unknown_issuer_invalid():
    with pytest.raises(FDSValidationError, match="unknown IdP issuer"):
        validate_allowed_idps(["https://not-trusted.com"])


def test_allowed_idps_fails_when_trusted_idps_missing(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_IDPS", [])
    with pytest.raises(FDSValidationError, match="TRUSTED_IDPS is missing or empty"):
        validate_allowed_idps([IDP_A])


def test_trusted_allowed_idps_valid():
    validate_allowed_idps([IDP_A])


def test_null_allowed_idps_valid():
    validate_allowed_idps(None)


def test_public_device_names_issuers_its_restricted_datasets_inherit(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(
            name="OPEN", access_level=AccessLevel.PUBLIC, allowed_idps=[IDP_A]
        ),
        admin_user,
    )
    dataset = dataset_service.create(
        DatasetCreate(
            name="d", device_name="OPEN", access_level=AccessLevel.RESTRICTED
        ),
        admin_user,
    )
    assert get_effective_policy(dataset, session).allowed_idps == [IDP_A]


def test_create_public_with_read_roles_allowed(device_service, admin_user):
    """A public record may name read roles for the restricted records that
    inherit them."""
    device = device_service.create(
        DeviceCreate(
            name="OPEN", access_level=AccessLevel.PUBLIC, read_roles=["open-read"]
        ),
        user=admin_user,
    )
    assert device.read_roles == ["open-read"]


def test_create_inheriting_level_with_read_roles_allowed(dataset_service, admin_user):
    ds = dataset_service.create(
        DatasetCreate(name="own-roles", level=1, url="s3://x", read_roles=["a"]),
        user=admin_user,
    )
    assert ds.read_roles == ["a"]


def test_create_inheriting_level_with_allowed_idps_allowed(dataset_service, admin_user):
    ds = dataset_service.create(
        DatasetCreate(name="own-issuers", level=1, url="s3://x", allowed_idps=[IDP_A]),
        user=admin_user,
    )
    assert ds.allowed_idps == [IDP_A]


def test_create_restricted_empty_roles_allowed(dataset_service, admin_user):
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-only",
            level=1,
            url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            read_roles=[],
        ),
        user=admin_user,
    )
    assert ds.id is not None
    assert ds.read_roles == []


def test_effective_policy_inherits_read_roles_from_device(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(
            name="LAB-A",
            access_level=AccessLevel.RESTRICTED,
            read_roles=["lab:read"],
        ),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(name="ds", level=1, url="s3://x", device_name="LAB-A"),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.read_roles == ["lab:read"]
    assert policy.access_level == AccessLevel.RESTRICTED


def test_effective_policy_dataset_overrides_device_read_roles(
    session, device_service, dataset_service, admin_user
):
    device_service.create(
        DeviceCreate(
            name="LAB-B",
            access_level=AccessLevel.RESTRICTED,
            read_roles=["lab:read"],
        ),
        user=admin_user,
    )
    ds = dataset_service.create(
        DatasetCreate(
            name="ds",
            level=1,
            url="s3://x",
            device_name="LAB-B",
            access_level=AccessLevel.RESTRICTED,
            read_roles=["special:top-secret"],
        ),
        user=admin_user,
    )
    policy = get_effective_policy(ds, session)
    assert policy.read_roles == ["special:top-secret"]


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
            name="ds", level=1, url="s3://x", device_name="DEV-C", shot_id="S1"
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
        DatasetCreate(name="ds", level=1, url="s3://x", device_name="OPEN-DEV"),
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
            url="s3://x",
            device_name="DEV-D",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
            read_roles=[],  # explicit auth-only gate so we don't fall to capability check
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u1", roles=(), issuer=IDP_A)
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
            url="s3://x",
            device_name="DEV-E",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
            read_roles=[],
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u2", roles=(), issuer=IDP_B)
    with pytest.raises(ForbiddenError, match="identity provider"):
        dataset_service.check_read_access(ds, user)


def test_read_access_restricted_empty_roles_auth_only_gate(dataset_service, admin_user):
    """RESTRICTED + read_roles=[] gates on authentication only.

    Issuer trust is enforced at the token validation boundary (security.py), not
    re-checked at the service layer. An authenticated AuthenticatedUser object
    passes regardless of its issuer value, provided no allowed_idps restriction
    is set on the dataset.
    """
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-gate",
            level=1,
            url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            read_roles=[],
        ),
        user=admin_user,
    )
    user = AuthenticatedUser(id="u3", roles=(), issuer="https://test-idp.com")
    # Should not raise — auth-only gate, user is authenticated
    dataset_service.check_read_access(ds, user)


def test_read_access_restricted_empty_roles_anonymous_denied(
    dataset_service, admin_user
):
    """RESTRICTED + read_roles=[] still blocks anonymous users."""
    ds = dataset_service.create(
        DatasetCreate(
            name="auth-gate-anon",
            level=1,
            url="s3://x",
            access_level=AccessLevel.RESTRICTED,
            read_roles=[],
        ),
        user=admin_user,
    )
    with pytest.raises(ForbiddenError, match="Authentication required"):
        dataset_service.check_read_access(ds, ANONYMOUS_USER)


def test_download_allowed_idp_correct_role(session, device_service, admin_user):
    from fds.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    device_service.create(
        DeviceCreate(name="DEV-F", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    ds = Dataset(
        name="ds",
        level=1,
        access_level=AccessLevel.RESTRICTED,
        device_name="DEV-F",
        read_roles=["read:data"],
        allowed_idps=[IDP_A],
    )
    user = AuthenticatedUser(id="u", roles=("read:data",), issuer=IDP_A)
    assert svc._check_download_permission(user, ds) is True


def test_download_correct_role_wrong_idp_denied(session):
    from fds.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        access_level=AccessLevel.RESTRICTED,
        read_roles=["read:data"],
        allowed_idps=[IDP_A],
    )
    user = AuthenticatedUser(id="u", roles=("read:data",), issuer=IDP_B)
    assert svc._check_download_permission(user, ds) is False


def test_download_restricted_empty_roles_anonymous_denied(session):
    from fds.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        access_level=AccessLevel.RESTRICTED,
        read_roles=[],
    )
    assert svc._check_download_permission(ANONYMOUS_USER, ds) is False


def test_download_embargoed_no_roles_anonymous_denied(session):
    """Embargoed data should be denied to anonymous users even without read_roles."""
    from fds.services.file_access_service import FileAccessService

    svc = FileAccessService(session)
    ds = Dataset(
        name="ds",
        level=1,
        access_level=AccessLevel.EMBARGOED,
    )
    assert svc._check_download_permission(ANONYMOUS_USER, ds) is False
