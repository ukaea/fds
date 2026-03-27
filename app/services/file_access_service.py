import logging
from collections import defaultdict
from urllib.parse import urlparse

from sqlmodel import Session, col, select

from app.auth.access_control import get_effective_policy
from app.auth.permissions import check_shot_operator
from app.core.storage.providers import get_provider_for_protocol
from app.models.dataset import Dataset
from app.models.file_access import (
    CredentialManifest,
    CredentialPayload,
    CredentialRequest,
)
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
        Returns a manifest mapping each dataset URL to its credential.
        """
        allowed_urls = self._resolve_allowed_urls(user, request)

        if not allowed_urls:
            logger.info(
                "Access denied or no datasets found", extra={"user_id": user.id}
            )
            return CredentialManifest(resource_map={})

        grouped_urls = self._group_urls_by_protocol(allowed_urls)
        session_name = f"fds-sess-{user.id[-8:]}"
        resource_map: dict[str, CredentialPayload] = {}

        for protocol, urls in grouped_urls.items():
            if not urls:
                continue
            resource_map.update(
                self._mint_for_protocol(user, protocol, urls, session_name)
            )

        return CredentialManifest(resource_map=resource_map)

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
    ) -> dict[str, CredentialPayload]:
        result: dict[str, CredentialPayload] = {}
        try:
            provider = get_provider_for_protocol(protocol)
        except ValueError:
            logger.warning(
                f"No credential provider implemented for protocol: {protocol}. Skipping."
            )
            return {}

        chunks = [
            urls[i : i + self.MAX_DATASETS_PER_TOKEN]
            for i in range(0, len(urls), self.MAX_DATASETS_PER_TOKEN)
        ]

        for chunk_index, chunk in enumerate(chunks):
            logger.info(
                "Vending chunked credentials",
                extra={
                    "user_id": user.id,
                    "protocol": protocol,
                    "chunk_size": len(chunk),
                    "chunk_index": chunk_index,
                },
            )

            creds = provider.generate_credentials(
                chunk, f"{session_name}-{chunk_index}"
            )

            for url in chunk:
                bucket = urlparse(url).netloc
                if bucket in creds:
                    result[url] = creds[bucket]

        return result

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
            query = query.where(col(Dataset.data_url).in_(request.data_urls))

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
        Unified policy check for data access (credential vending).

        Uses the full effective policy resolved from the
        Dataset → Shot → Device hierarchy (same semantics as metadata reads).

        - PUBLIC:  always open (including anonymous).
        - EMBARGOED / RESTRICTED:
            1. Must be authenticated.
            2. If effective allowed_idps is set, user issuer must be in list.
            3. If effective required_scopes is explicitly set (including []):
               all listed scopes must be present; [] means auth-only gate.
            4. Otherwise fall back to context-based capability check
               (shot-operator role).
        """
        policy = get_effective_policy(dataset, self.session)

        # 1. PUBLIC is always open
        if policy.access_level == AccessLevel.PUBLIC:
            return True

        # 2. Must be authenticated for non-public data
        if user.is_anonymous:
            return False

        # 3. Enforce IdP restriction if specified
        if policy.allowed_idps is not None:
            if user.issuer not in policy.allowed_idps:
                return False

        # 4. Enforce required scopes if explicitly set at any hierarchy level
        #    None  → fall through to capability check
        #    []    → auth-only gate (already satisfied by step 2)
        #    [..] → all scopes must be present
        if policy.required_scopes is not None:
            if len(policy.required_scopes) == 0:
                return True
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    return False
            return True

        # 5. Capability fallback (no explicit required_scopes anywhere in hierarchy)
        try:
            if dataset.device_name:
                check_shot_operator(user, dataset.device_name)
                return True
        except ForbiddenError:
            return False

        # Default deny
        return False
