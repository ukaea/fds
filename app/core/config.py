from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrustedIdP(BaseModel):
    """An issuer whose tokens FDS accepts, and where to find the keys that signed them.

    By default FDS discovers the keys: it fetches ``{issuer}/.well-known/
    openid-configuration`` and then the ``jwks_uri`` it advertises. The two
    optional fields override that:

    ``jwks_uri`` names the key endpoint directly, for when FDS reaches the
    issuer at a different address from the one in the token (a container
    network, say, where the token says ``https://auth.example.org`` but FDS
    should call ``http://keycloak:8080``).

    ``jwks_file`` reads the keys from a local file, so no identity provider has
    to be running at all. Tokens are then minted offline by whoever holds the
    matching private key. See the Operations documentation: this is a
    bootstrap, automation and break-glass path, not a way for people to log in.
    """

    issuer: str
    allowed_scopes: list[str] = ["*"]
    jwks_uri: str | None = None
    jwks_file: Path | None = None

    @field_validator("issuer")
    @classmethod
    def normalize_issuer(cls, issuer: str) -> str:
        normalized = issuer.strip().rstrip("/")
        if not normalized:
            raise ValueError("issuer must be non-empty and not whitespace-only")
        return normalized

    @model_validator(mode="after")
    def one_key_source(self) -> "TrustedIdP":
        if self.jwks_uri and self.jwks_file:
            raise ValueError(
                f"'{self.issuer}' sets both jwks_uri and jwks_file; "
                "keys come from one place"
            )
        return self


class S3StorageProvider(BaseModel):
    """Configuration for one S3-compatible storage endpoint.

    ``endpoint_url`` is the client-accessible URL and acts as the lookup key
    that matches ``Distribution.endpoint_url``.  ``None`` means standard AWS S3
    (no custom endpoint).

    ``sts_endpoint_url`` is the URL the FDS *server* uses for ``AssumeRole``
    calls.  It may differ from ``endpoint_url`` when internal and external URLs
    for the same system differ (e.g. a containerised demo where the server can
    reach MinIO directly by service name).  Defaults to ``endpoint_url``.

    ``sts_access_key_id`` / ``sts_secret_access_key`` are optional; when
    absent boto3 falls back to its standard credential chain (environment
    variables, IAM instance role, etc.).
    """

    type: Literal["s3"] = "s3"
    endpoint_url: str | None
    region: str
    sts_endpoint_url: str | None = None
    sts_role_arn: str
    sts_region: str = "us-east-1"
    sts_access_key_id: str | None = None
    sts_secret_access_key: str | None = None


class GCSStorageProvider(BaseModel):
    """Configuration for a Google Cloud Storage endpoint (placeholder)."""

    type: Literal["gcs"] = "gcs"
    endpoint_url: str | None = None


class AzureStorageProvider(BaseModel):
    """Configuration for an Azure Blob Storage endpoint."""

    type: Literal["azure"] = "azure"
    endpoint_url: str | None = None
    storage_account: str


StorageProvider = Annotated[
    S3StorageProvider | GCSStorageProvider | AzureStorageProvider,
    Field(discriminator="type"),
]


class Config(BaseSettings):
    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application Settings
    app_name: str = Field(default="fds", validation_alias="FDS_APP_NAME")
    debug: bool = Field(default=False, validation_alias="FDS_DEBUG")
    ENVIRONMENT: str = Field(default="dev", validation_alias="FDS_ENVIRONMENT")
    LOG_LEVEL: str = Field(default="INFO", validation_alias="FDS_LOG_LEVEL")
    # "json", "console", or "" to follow ENVIRONMENT.
    LOG_FORMAT: str = Field(default="", validation_alias="FDS_LOG_FORMAT")

    # Database Settings. FDS runs on PostgreSQL; there is no other backend.
    db_host: str = Field(default="localhost", validation_alias="FDS_DB_HOST")
    db_port: int = Field(default=5432, validation_alias="FDS_DB_PORT")
    db_user: str = Field(default="fds", validation_alias="FDS_DB_USER")
    db_password: str = Field(default="", validation_alias="FDS_DB_PASSWORD")
    db_name: str = Field(default="fds", validation_alias="FDS_DB_NAME")
    # A complete URL, which wins over the parts above when set.
    db_url_override: str = Field(default="", validation_alias="FDS_DB_URL")

    # OIDC/JWT Settings
    OIDC_AUDIENCE: str = Field(default="", validation_alias="FDS_OIDC_AUDIENCE")

    # Multi-IdP Configuration
    TRUSTED_IDPS: list[TrustedIdP] = Field(
        default=[], validation_alias="FDS_TRUSTED_IDPS"
    )

    @field_validator("TRUSTED_IDPS")
    @classmethod
    def validate_trusted_idps(cls, idps: list[TrustedIdP]) -> list[TrustedIdP]:
        seen: set[str] = set()
        for idp in idps:
            if idp.issuer in seen:
                raise ValueError(
                    f"TRUSTED_IDPS contains a duplicate issuer: '{idp.issuer}'"
                )
            seen.add(idp.issuer)
        return idps

    # Storage Providers
    CREDENTIAL_TOKEN_DURATION: int = Field(
        default=3600, validation_alias="FDS_CREDENTIAL_TOKEN_DURATION"
    )
    STORAGE_PROVIDERS: list[StorageProvider] = Field(
        default=[], validation_alias="FDS_STORAGE_PROVIDERS"
    )

    @property
    def db_url(self) -> str:
        """The PostgreSQL URL, with credentials escaped.

        Overridden wholesale by FDS_DB_URL when set, which is how the tests
        point at a throwaway database.
        """
        if self.db_url_override:
            return self.db_url_override
        credentials = quote(self.db_user, safe="")
        if self.db_password:
            credentials += ":" + quote(self.db_password, safe="")
        return (
            f"postgresql+psycopg://{credentials}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


config = Config()
