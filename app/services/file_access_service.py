import logging
from collections import defaultdict
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.auth.permissions import check_shot_operator
from app.core.storage.providers import get_provider_for_protocol
from app.models.dataset import Dataset
from app.models.file_access import CredentialManifest, CredentialRequest
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.exceptions import ForbiddenError

logger = logging.getLogger(__name__)


class FileAccessService:
    MAX_DATASETS_PER_TOKEN = 5  # Safe limit for IAM Policy size

    def __init__(self, session: Session):
        self.session = session

    def generate_session_credentials(
        self, user: AuthenticatedUser, request: CredentialRequest
    ) -> CredentialManifest:
        """
        Generates temporary storage credentials.
        Returns a Manifest containing multiple tokens if necessary.
        """
        allowed_urls = self._resolve_allowed_urls(user, request)

        if not allowed_urls:
            logger.info(
                "Access denied or no datasets found", extra={"user_id": user.id}
            )
            return CredentialManifest(tokens=[], resource_map={})

        grouped_urls = self._group_urls_by_protocol(allowed_urls)

        manifest = CredentialManifest(tokens=[], resource_map={})
        token_index_counter = 0
        session_name = f"fds-sess-{user.id[-8:]}"

        for protocol, urls in grouped_urls.items():
            if not urls:
                continue

            new_tokens, new_map = self._mint_for_protocol(
                user, protocol, urls, session_name, token_index_counter
            )

            manifest.tokens.extend(new_tokens)
            manifest.resource_map.update(new_map)
            token_index_counter += len(new_tokens)

        return manifest

    def _group_urls_by_protocol(self, urls: list[str]) -> dict[str, list[str]]:
        logger.info(f"Grouping {len(urls)} URLs by protocol")
        grouped = defaultdict(list)
        for url in urls:
            parsed = urlparse(url)
            protocol = parsed.scheme
            if protocol:
                grouped[protocol].append(url)
        return grouped

    def _mint_for_protocol(
        self,
        user: AuthenticatedUser,
        protocol: str,
        urls: list[str],
        session_name: str,
        start_index: int,
    ) -> tuple[list[dict], dict[str, int]]:
        tokens = []
        resource_map = {}
        provider = get_provider_for_protocol(protocol)
        provider_key = self._get_provider_key(protocol)

        # Split urls into chunks
        chunks = [
            urls[i : i + self.MAX_DATASETS_PER_TOKEN]
            for i in range(0, len(urls), self.MAX_DATASETS_PER_TOKEN)
        ]

        for chunk in chunks:
            current_index = start_index + len(tokens)

            logger.info(
                "Vending chunked credentials",
                extra={
                    "user_id": user.id,
                    "protocol": protocol,
                    "chunk_size": len(chunk),
                    "token_index": current_index,
                },
            )

            # Generic provider returns dict (e.g. S3Credentials or similar)
            creds = provider.generate_credentials(
                chunk, f"{session_name}-{current_index}"
            )

            # We wrap it in a structure that identifies it as part of the list
            token_payload = {"provider": provider_key, "credentials": creds}
            tokens.append(token_payload)

            # Map these resources to this token index
            for url in chunk:
                resource_map[url] = current_index

        return tokens, resource_map

    def _resolve_allowed_urls(
        self, user: AuthenticatedUser, request: CredentialRequest
    ) -> list[str]:
        """
        Queries the database to find specific allowed S3 prefixes based on request filter.
        """
        # Guard: If no filters are provided, return empty list to avoid selecting *all* datasets.
        if not request.shot_id and not request.device_name and not request.data_urls:
            return []

        # Base query: Active Datasets
        # Note: We do NOT filter by AccessLevel here yet, we filter by 'Scope' first,
        # then apply Access restrictions.
        query = select(Dataset)

        # Apply Filters
        if request.shot_id:
            query = query.where(Dataset.shot_id == request.shot_id)

        if request.device_name:
            query = query.where(Dataset.device_name == request.device_name)

        if request.data_urls:
            query = query.where(Dataset.data_url.in_(request.data_urls))

        datasets = self.session.exec(query).all()

        logger.info(
            f"Query returned {len(datasets)} datasets for request: {request.model_dump_json(exclude_none=True)}"
        )

        final_urls = []
        for ds in datasets:
            if self._check_download_permission(user, ds):
                if ds.data_url:
                    final_urls.append(ds.data_url)

        return list(set(final_urls))  # Dedup

    def _check_download_permission(
        self, user: AuthenticatedUser, dataset: Dataset
    ) -> bool:
        """
        Unified policy check for data access.
        - Public: Always allowed.
        - Specific Override: If required_scope is set, user must have it.
        - General Fallback: If no required_scope, fall back to context (Shot/Device).
        """
        # 1. Public is always open
        if dataset.access_level == AccessLevel.PUBLIC:
            return True

        # 2. Specific Override (Data-Driven)
        if dataset.required_scope:
            if dataset.required_scope in user.scopes:
                return True
            # If a specific scope IS required but user lacks it, we deny access
            # We do NOT fallback to general checks if a specific lock is present.
            return False

        # 3. General Fallback (Implicit Scopes based on Context)
        # Used for Restricted/Embargoed datasets without a specific required_scope
        try:
            # Shot Context -> Shot Operator
            if dataset.shot_id and dataset.device_name:
                check_shot_operator(user, dataset.device_name)
                return True

            # Device Context (No Shot) -> Device Admin?
            # (Assuming device-admin is implied if not a shot, or maybe we just check shot-operator for simplicity)
            # For now, let's stick to the Shot Operator role for data access as discussed
            if dataset.device_name:
                # Re-using check_shot_operator as generic "Data Access" role for device
                check_shot_operator(user, dataset.device_name)
                return True

        except ForbiddenError:
            return False

        # Default Deny
        return False

    def _get_provider_key(self, protocol: str) -> str:
        if protocol == "s3":
            return "s3"
        if protocol in ("az", "abfs"):
            return "azure"
        if protocol == "gs":
            return "gcp"
        return protocol
