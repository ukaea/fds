from collections import defaultdict
from typing import NamedTuple

import structlog
from sqlmodel import Session, col, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
)
from app.auth.permissions import check_shot_operator
from app.core.audit import record_data_access
from app.core.naming import normalise_device_name
from app.core.storage.providers import get_provider_for_endpoint
from app.models.dataset import Dataset
from app.models.distribution import Distribution
from app.models.file_access import (
    CredentialManifest,
    CredentialPayload,
    CredentialRequest,
    S3Credentials,
)
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.storage_options import (
    StorageBackend,
    StorageOptionsType,
    parse_storage_url,
)
from app.services.exceptions import ForbiddenError

logger = structlog.get_logger(__name__)


class ResolvedDistribution(NamedTuple):
    """A distribution URL the caller may read, with what vending needs.

    ``storage_options_type`` and ``region`` come straight off the Distribution
    row, so rendering opener-ready options needs no second query and no second
    guess at the media type.
    """

    url: str
    endpoint_url: str | None
    storage_options_type: StorageOptionsType | None
    region: str | None


class FileAccessService:
    MAX_DATASETS_PER_TOKEN = 5  # Safe limit for IAM Policy size

    def __init__(self, session: Session):
        self.session = session

    def generate_session_credentials(
        self,
        user: AuthenticatedUser,
        request: CredentialRequest,
        include_storage_options: bool = False,
    ) -> CredentialManifest:
        """
        Generates temporary storage credentials.
        Returns a manifest mapping each dataset URL to its credential.

        With ``include_storage_options`` each entry also carries an
        opener-ready ``storage_options`` rendering, in the shape the URL's own
        Distribution declares, so a worker can splat it into
        ``xr.open_dataset`` or ``icechunk.s3_storage`` without hand-mapping.
        """
        resolved = self._resolve_allowed_urls(user, request)

        if not resolved:
            logger.info("credentials.none_permitted")
            return CredentialManifest(resource_map={})

        grouped = self._group_by_endpoint(resolved)
        session_name = f"fds-sess-{user.id[-8:]}"
        resource_map: dict[str, CredentialPayload] = {}

        for (backend, endpoint_url), urls in grouped.items():
            resource_map.update(
                self._mint_for_backend(backend, endpoint_url, urls, session_name)
            )

        if include_storage_options:
            by_url = {r.url: r for r in resolved}
            resource_map = {
                url: self._render_storage_options(credential, by_url[url])
                for url, credential in resource_map.items()
            }

        return CredentialManifest(resource_map=resource_map)

    @staticmethod
    def _render_storage_options(
        credential: CredentialPayload, resolved: ResolvedDistribution
    ) -> CredentialPayload:
        """Return a copy of ``credential`` carrying its opener-ready rendering.

        A copy, not a mutation: the S3 provider hands the same credential
        object back for every bucket in a chunk, and two URLs on that chunk can
        want different shapes or regions.
        """
        if isinstance(credential, S3Credentials):
            if resolved.storage_options_type is None:
                # The Distribution opted out of generated storage options
                # (plain HTTPS download, MDSplus reference, and so on).
                return credential
            options = credential.to_storage_options(
                resolved.storage_options_type, region=resolved.region
            )
        else:
            # Azure and GCS render one shape each, with no target type to pick.
            options = credential.to_storage_options()
        return credential.model_copy(update={"storage_options": options})

    def _group_by_endpoint(
        self, resolved: list[ResolvedDistribution]
    ) -> dict[tuple[StorageBackend, str | None], list[str]]:
        logger.debug("credentials.grouping_urls", url_count=len(resolved))
        grouped: dict[tuple[StorageBackend, str | None], list[str]] = defaultdict(list)
        for entry in resolved:
            location = parse_storage_url(entry.url)
            if location:
                grouped[(location.backend, entry.endpoint_url)].append(entry.url)
        return grouped

    def _mint_for_backend(
        self,
        backend: StorageBackend,
        endpoint_url: str | None,
        urls: list[str],
        session_name: str,
    ) -> dict[str, CredentialPayload]:
        result: dict[str, CredentialPayload] = {}
        provider = get_provider_for_endpoint(backend, endpoint_url)
        if provider is None:
            logger.warning(
                "credentials.no_provider", backend=backend, endpoint_url=endpoint_url
            )
            return {}

        chunks = [
            urls[i : i + self.MAX_DATASETS_PER_TOKEN]
            for i in range(0, len(urls), self.MAX_DATASETS_PER_TOKEN)
        ]

        for chunk_index, chunk in enumerate(chunks):
            logger.info(
                "credentials.vending",
                backend=backend,
                endpoint_url=endpoint_url,
                chunk_size=len(chunk),
                chunk_index=chunk_index,
            )

            creds = provider.generate_credentials(
                chunk, f"{session_name}-{chunk_index}"
            )

            for url in chunk:
                location = parse_storage_url(url)
                if location and location.bucket in creds:
                    result[url] = creds[location.bucket]

        return result

    def _resolve_allowed_urls(
        self, user: AuthenticatedUser, request: CredentialRequest
    ) -> list[ResolvedDistribution]:
        """
        Queries the database to find allowed distribution URLs based on request filter.
        Returns one :class:`ResolvedDistribution` per permitted distribution.
        """
        # Guard: If no filters are provided, return empty list to avoid selecting *all* datasets.
        if not request.shot_id and not request.device_name and not request.data_urls:
            return []

        # Join Dataset → Distribution to resolve URLs.
        # Note: We do NOT filter by AccessLevel here yet, we filter by 'Scope' first,
        # then apply Access restrictions.
        query = select(Dataset, Distribution).join(Distribution)

        # Apply Filters
        if request.shot_id:
            query = query.where(Dataset.shot_id == request.shot_id)

        if request.device_name:
            query = query.where(
                Dataset.device_name == normalise_device_name(request.device_name)
            )

        if request.data_urls:
            query = query.where(col(Distribution.url).in_(request.data_urls))

        rows = self.session.exec(query).all()

        logger.debug(
            "credentials.candidates_resolved",
            row_count=len(rows),
            shot_id=request.shot_id,
            device_name=request.device_name,
            data_urls=request.data_urls,
        )

        seen: dict[str, ResolvedDistribution] = {}
        for ds, dist in rows:
            if self._check_download_permission(user, ds):
                seen[dist.url] = ResolvedDistribution(
                    url=dist.url,
                    endpoint_url=dist.endpoint_url,
                    storage_options_type=dist.storage_options_type,
                    region=dist.region,
                )
                record_data_access(
                    ds.id,
                    dist.url,
                    dist.endpoint_url,
                    get_effective_access_level(ds, self.session),
                )

        return list(seen.values())

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
        if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
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
