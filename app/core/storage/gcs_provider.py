import google.auth
import google.auth.downscoped
from google.auth import exceptions
from google.auth.transport.requests import Request

from app.models.file_access import GCSCredentials
from app.models.storage_options import parse_storage_url
from app.services.exceptions import ConfigurationError

# Note: We import Request from google.auth.transport.requests
# This ensures google-auth uses the 'requests' library for token refresh/exchange.


class GCSCredentialProvider:
    """
    Vendor Google Cloud Storage credentials using Downscoped Credentials (CAB).
    """

    def __init__(self, provider_config):
        self._provider_config = provider_config

    def generate_credentials(
        self, allowed_prefixes: list[str], _session_name: str
    ) -> dict[str, GCSCredentials]:
        """Downscope a token to the buckets named. URLs that are not GCS are skipped."""
        buckets = {
            location.bucket
            for location in map(parse_storage_url, allowed_prefixes)
            if location and location.backend == "gcs"
        }
        if not buckets:
            return {}

        # 1. Initialize Base Credentials
        try:
            # We explicitly create a Request object.
            # google.auth.default() uses environment variables to find credentials.
            base_creds, _project_id = google.auth.default()
        except exceptions.DefaultCredentialsError:
            raise ConfigurationError(
                "Could not determine Google Cloud credentials. "
                "Ensure GOOGLE_APPLICATION_CREDENTIALS is set."
            )

        # 2. Define Access Boundary
        rules = []
        for bucket_name in buckets:
            # Resource Format for Bucket: //storage.googleapis.com/projects/_/buckets/{bucket_name}
            resource = f"//storage.googleapis.com/projects/_/buckets/{bucket_name}"

            rules.append(
                {
                    "availableResource": resource,
                    "availablePermissions": ["inRole:roles/storage.objectViewer"],
                }
            )

        # 3. Create Downscoped Credential
        cab = google.auth.downscoped.CredentialAccessBoundary(rules=rules)

        # Use standard google.auth Request object (wraps 'requests')
        request = Request()

        downscoped_creds = google.auth.downscoped.Credentials(
            base_creds, credential_access_boundary=cab
        )

        # 4. Refresh to mint the token immediately
        try:
            downscoped_creds.refresh(request)
        except Exception as e:  # noqa: BLE001 - SDK raises many types; all mean misconfiguration
            raise ConfigurationError(f"Failed to vend GCS credentials: {e}")

        # 5. Structure Response
        result = {}

        token = downscoped_creds.token
        if not isinstance(token, str):
            raise ConfigurationError("Failed to vend GCS credentials: missing token")

        for bucket_name in buckets:
            result[bucket_name] = GCSCredentials(
                token=token,
                expiry=downscoped_creds.expiry.isoformat()
                if downscoped_creds.expiry
                else None,
            )

        return result
