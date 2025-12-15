import httpx
import jwt
from cachetools import TTLCache
from fastapi import HTTPException, status

from app.core.config import config


class JwksClient:
    """
    A client for fetching and caching JSON Web Key Sets (JWKS) from an
    OIDC provider.
    """

    def __init__(self, domain: str):
        self.domain = domain
        self.jwks_uri = ""  # To be discovered from OIDC config
        # Cache the JWKS for 10 minutes
        self.cache = TTLCache(maxsize=1, ttl=600)
        self._jwks_uri_discovered = False  # New flag to track discovery

    async def _discover_jwks_uri(self):
        """
        Discovers the JWKS URI from the OIDC provider's well-known
        configuration endpoint.
        """
        if not self.domain:
            raise ValueError("OIDC_DOMAIN is not configured.")

        discovery_url = f"https://{self.domain}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(discovery_url, timeout=5)
                response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
                config_data = response.json()
                self.jwks_uri = config_data.get("jwks_uri")

                if not self.jwks_uri:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="JWKS URI not found in OIDC discovery configuration.",
                    )
                self._jwks_uri_discovered = True  # Set flag after successful discovery
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred while requesting {exc.request.url!r}: {exc}",
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,  # Use actual status code from response
                detail=f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to discover JWKS URI: {e}",
            )

    async def get_jwks(self) -> dict:
        """
        Fetches and caches the JWKS from the provider.
        """
        if not self._jwks_uri_discovered:
            await self._discover_jwks_uri()

        if not self.jwks_uri:  # Should be set after discovery, but a safeguard
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWKS URI could not be discovered or is empty.",
            )

        cached_jwks = self.cache.get("jwks")
        if cached_jwks:
            return cached_jwks

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.jwks_uri, timeout=5)
                response.raise_for_status()
                jwks_data = response.json()
                self.cache["jwks"] = jwks_data  # Cache the fetched JWKS
                return jwks_data
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred while requesting {exc.request.url!r}: {exc}",
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,  # Use actual status code from response
                detail=f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch JWKS from {self.jwks_uri}: {e}",
            )

    async def get_signing_key(self, token: str) -> str:
        """
        Finds the appropriate signing key for a given JWT.
        It gets the unverified header of the token to find the Key ID (kid),
        then searches the JWKS for a matching key.
        """
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token header: {e}"
            )
            
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing 'kid' (Key ID) in header"
            )

        jwks = await self.get_jwks()
        key = next((key for key in jwks["keys"] if key["kid"] == kid), None)
        
        # If the key is not found, it might be because the IdP has rotated the keys.
        # We clear the cache and try fetching the JWKS again.
        if not key:
            self.cache.clear()
            jwks = await self.get_jwks()
            key = next((key for key in jwks["keys"] if key["kid"] == kid), None)
        
        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Signing key not found for kid '{kid}'"
            )
        
        # PyJWT can construct the public key directly from the JWK dictionary
        return jwt.PyJWK(key).key


# Create a single instance of the client for our application to use.
jwks_client = JwksClient(domain=config.OIDC_DOMAIN)
