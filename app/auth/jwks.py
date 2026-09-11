from typing import Annotated

import httpx
import jwt
import structlog
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status

from app.core.config import config

logger = structlog.get_logger(__name__)


class JwksClient:
    """
    A client for fetching and caching JSON Web Key Sets (JWKS) from
    trusted OIDC providers.
    """

    def __init__(self):
        # Cache key: issuer, value: jwks_data (dict)
        # Increased maxsize to support multiple IdPs
        self.cache = TTLCache[str, dict, float](maxsize=10, ttl=600)
        self.issuer_jwks_uris: dict[str, str] = {}
        # Reuse a single client for connection pooling
        self.client = httpx.AsyncClient()

    async def close(self):
        await self.client.aclose()

    def _is_trusted_issuer(self, issuer: str) -> bool:
        """
        Checks if the issuer is in TRUSTED_IDPS.
        """
        for trusted in config.TRUSTED_IDPS:
            if trusted.issuer == issuer:
                return True

        return False

    async def _discover_jwks_uri(self, issuer: str) -> str:
        """
        Discovers the JWKS URI for a given issuer.
        """
        if not self._is_trusted_issuer(issuer):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Untrusted Issuer: {issuer}",
            )

        discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"

        try:
            response = await self.client.get(discovery_url, timeout=5)
            response.raise_for_status()
            config_data = response.json()
            jwks_uri = config_data.get("jwks_uri")
            if not jwks_uri:
                raise Exception("jwks_uri not found in discovery doc")

            logger.info("jwks.uri_discovered", jwks_uri=jwks_uri, issuer=issuer)
            return jwks_uri
        except httpx.HTTPStatusError as e:
            logger.error(
                "jwks.discovery_rejected",
                issuer=issuer,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Identity Provider returned an error during discovery.",
            )
        except httpx.RequestError as e:
            logger.error("jwks.discovery_unreachable", issuer=issuer, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to connect to Identity Provider during discovery.",
            )
        except Exception as e:
            logger.error("jwks.discovery_failed", issuer=issuer, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to discover JWKS URI for {issuer}",
            )

    async def get_jwks(self, issuer: str) -> dict:
        """
        Fetches and caches the JWKS for a specific issuer.
        """
        cached = self.cache.get(issuer)
        if cached is not None:
            return cached

        # Resolve JWKS URI if not known
        if issuer not in self.issuer_jwks_uris:
            self.issuer_jwks_uris[issuer] = await self._discover_jwks_uri(issuer)

        jwks_uri = self.issuer_jwks_uris[issuer]

        try:
            response = await self.client.get(jwks_uri, timeout=5)
            response.raise_for_status()
            jwks_data = response.json()
            self.cache[issuer] = jwks_data
            return jwks_data
        except httpx.HTTPStatusError as e:
            logger.error(
                "jwks.fetch_rejected",
                issuer=issuer,
                jwks_uri=jwks_uri,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            # Retrieve specific details if available, but sanitize for client
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Identity Provider returned an error.",
            )
        except httpx.RequestError as e:
            logger.error(
                "jwks.fetch_unreachable",
                issuer=issuer,
                jwks_uri=jwks_uri,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to connect to Identity Provider.",
            )
        except Exception as e:
            logger.error("jwks.fetch_failed", jwks_uri=jwks_uri, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error processing JWKS.",
            )

    async def get_signing_key(self, token: str) -> str:
        """
        Finds the appropriate signing key for a given JWT.
        """
        try:
            unverified_header = jwt.get_unverified_header(token)
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token format: {e}",
            )

        kid = unverified_header.get("kid")
        issuer = unverified_payload.get("iss")

        if not kid or not issuer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing 'kid' or 'iss'",
            )

        jwks = await self.get_jwks(issuer)
        key = next((key for key in jwks["keys"] if key.get("kid") == kid), None)

        if not key:
            logger.warning("jwks.key_id_miss", kid=kid, issuer=issuer)
            self.cache.pop(issuer, None)
            jwks = await self.get_jwks(issuer)
            key = next((key for key in jwks["keys"] if key.get("kid") == kid), None)

        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Signing key not found for kid '{kid}' from issuer '{issuer}'",
            )

        return jwt.PyJWK(key).key


_jwks_client_instance: JwksClient | None = None


def get_jwks_client() -> JwksClient:
    """
    Dependency provider for the JwksClient.
    """
    global _jwks_client_instance
    if _jwks_client_instance is None:
        _jwks_client_instance = JwksClient()
    return _jwks_client_instance


JWKSClientDep = Annotated[JwksClient, Depends(get_jwks_client)]
