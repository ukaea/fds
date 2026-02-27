import google.auth
import google.auth.downscoped
from google.auth import exceptions
from google.auth.transport.requests import Request

from app.models.file_access import GCSCredentials
from app.services.exceptions import ConfigurationError

# Note: We import Request from google.auth.transport.requests
# This ensures google-auth uses the 'requests' library for token refresh/exchange.


class GCSCredentialProvider:
    """
    Vendor Google Cloud Storage credentials using Downscoped Credentials (CAB).
    """

    def generate_credentials(
        self, allowed_prefixes: list[str], _session_name: str
    ) -> dict[str, GCSCredentials]:
        # 1. Initialize Base Credentials
        try:
            # We explicitly create a Request object.
            # google.auth.default() uses environment variables to find credentials.
            base_creds, project_id = google.auth.default()
        except exceptions.DefaultCredentialsError:
            raise ConfigurationError(
                "Could not determine Google Cloud credentials. "
                "Ensure GOOGLE_APPLICATION_CREDENTIALS is set."
            )

        # 2. Define Access Boundary
        rules = []
        buckets = set()

        for prefix in allowed_prefixes:
            # Expected format: gs://bucket/path
            parts = prefix.replace("gs://", "").split("/", 1)
            bucket_name = parts[0]
            buckets.add(bucket_name)

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
            base_creds, access_boundary=cab
        )

        # 4. Refresh to mint the token immediately
        try:
            downscoped_creds.refresh(request)
        except Exception as e:
            raise ConfigurationError(f"Failed to vend GCS credentials: {e}")

        # 5. Structure Response
        result = {}

        for bucket_name in buckets:
            result[bucket_name] = GCSCredentials(
                token=downscoped_creds.token,
                expiry=downscoped_creds.expiry.isoformat()
                if downscoped_creds.expiry
                else None,
            )

        return result
