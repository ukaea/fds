from unittest.mock import MagicMock, patch

from app.models.dataset import Dataset
from app.models.file_access import CredentialRequest
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.services.file_access_service import FileAccessService

# We use the 'session' fixture from conftest.py which gives us an in-memory SQLite DB


def test_generate_session_credentials_integration(session, admin_user):
    """
    Integration test using in-memory DB to verify:
    1. Query filtering works (shot_id matching).
    2. Manifest generation works.
    """
    # 1. Setup Data
    # Identify Shot ID
    shot_id = "12345"
    # Create Shot (AccessLevel.PUBLIC for simplicity)
    shot = Shot(id=shot_id, access_level=AccessLevel.PUBLIC)
    session.add(shot)
    session.commit()

    # Create 5 Datasets for this shot
    for i in range(5):
        ds = Dataset(
            name=f"signal_{i:02d}",
            level=1,
            shot_id=shot_id,
            data_url=f"s3://fds-data/shots/{shot_id}/signals/signal_{i:02d}",
            access_level=AccessLevel.PUBLIC,
            media_type="application/x-zarr",
        )
        session.add(ds)

    # Create 1 Dataset for a DIFFERENT shot (noise)
    other_shot_id = "999"
    other_shot = Shot(id=other_shot_id, access_level=AccessLevel.PUBLIC)
    session.add(other_shot)
    ds_noise = Dataset(
        name="noise",
        level=1,
        shot_id=other_shot_id,
        data_url="s3://fds-data/shots/999/noise",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(ds_noise)

    session.commit()

    # Verify data is in DB
    assert len(session.query(Dataset).all()) == 6

    # 2. Setup Service
    service = FileAccessService(session=session)
    request = CredentialRequest(shot_id=shot_id)

    # 3. Mock Provider to avoid calling AWS STS
    # We patch at the module level where FileAccessService imports it
    mock_provider = MagicMock()
    mock_provider.generate_credentials.side_effect = lambda urls, name: {
        "access_key_id": "fake",
        "secret_access_key": "fake",
        "session_token": "fake",
    }

    with patch(
        "app.services.file_access_service.get_provider_for_protocol",
        return_value=mock_provider,
    ) as mock_get_provider:
        # 4. Execute
        manifest = service.generate_session_credentials(admin_user, request)

        # 5. Assertions
        # Should have found 5 datasets
        assert len(manifest.resource_map) == 5, (
            "Should return 5 datasets matching shot_id 12345"
        )

        # Should NOT include the noise dataset
        assert "s3://fds-data/shots/999/noise" not in manifest.resource_map

        # Should have generated at least one token
        assert len(manifest.tokens) >= 1

        # Check provider was called with correct URLs
        # (The exact assertion depends on chunking, but we know all 5 are s3)
        mock_get_provider.assert_called_with("s3")

        # Verify call args of generate_credentials
        # expected_urls = [d.data_url for d in ... if d in shot]
        # mock_provider.generate_credentials.assert_called()
