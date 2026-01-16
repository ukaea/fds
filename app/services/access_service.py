from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.core.storage.providers import get_provider_for_protocol
from app.models.common import AccessLevel
from app.models.dataset import Dataset
from app.models.user import AuthenticatedUser


class AccessService:
    SUPPORTED_PROTOCOLS = ["s3"]

    def __init__(self, session: Session):
        self.session = session

    def generate_session_credentials(self, user: AuthenticatedUser) -> dict[str, Any]:
        """
        Generates temporary storage credentials for all datasets the user can access.
        Supports multiple storage backends (AWS, Azure, etc.) simultaneously.

        Returns:
            Dict[str, Any]: A map of provider_key -> credentials object.
            Example:
            {
                "aws": AWSCredentials(...),
                "azure": AzureCredentials(...)
            }
        """

        # 1. Scope Resolution
        allowed_urls = self._resolve_allowed_urls(user)

        if not allowed_urls:
            # Return empty dict if no access
            return {}

        if "*" in allowed_urls:
            # Global Admin gets credentials for all protocols
            grouped_urls = {p: ["*"] for p in self.SUPPORTED_PROTOCOLS}
        else:
            # 2. Group by Protocol
            grouped_urls = defaultdict(list)
            for url in allowed_urls:
                try:
                    parsed = urlparse(url)
                    protocol = parsed.scheme
                    if protocol:
                        grouped_urls[protocol].append(url)
                except Exception:
                    continue  # Skip invalid URLs

        # 3. Generate Credentials for each group
        credentials_map = {}
        session_name = f"fds-session-{user.id[-10:]}"

        for protocol, urls in grouped_urls.items():
            if not urls:
                continue

            try:
                provider = get_provider_for_protocol(protocol)
                # The provider returns a credential object (e.g. S3Credentials)
                # We key the response by the protocol primarily, or we can use the provider class name.
                # Let's use the protocol for now as the key, e.g. "s3".

                # Setup Refinement:
                # s3 -> s3
                # az -> azure
                # gs -> gcp
                provider_key = self._get_provider_key(protocol)

                creds = provider.generate_credentials(urls, session_name)
                credentials_map[provider_key] = creds
            except Exception as e:
                # Log error but don't fail entire request?
                # For now, strict fail is safer to detect configs.
                raise e

        return credentials_map

    def _resolve_allowed_urls(self, user: AuthenticatedUser) -> list[str]:
        """
        Queries the database to find all S3 prefixes (data_urls) the user can access.
        """
        if user.is_admin():
            return ["*"]  # Special flag for providers to give full access

        query = select(Dataset.data_url).where(
            Dataset.access_level == AccessLevel.PUBLIC
        )
        query_restricted = select(Dataset.data_url).where(
            Dataset.access_level == AccessLevel.RESTRICTED
        )

        urls = []
        urls.extend(self.session.exec(query).all())
        urls.extend(self.session.exec(query_restricted).all())

        return [u for u in urls if u]

    def _get_provider_key(self, protocol: str) -> str:
        """Map URL scheme to a stable JSON key for the response."""
        if protocol == "s3":
            return "s3"
        if protocol in ("az", "abfs"):
            return "azure"
        if protocol == "gs":
            return "gcp"
        return protocol
