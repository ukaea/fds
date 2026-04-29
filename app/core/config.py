from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrustedIdP(BaseModel):
    issuer: str
    allowed_scopes: list[str] = ["*"]

    @field_validator("issuer")
    @classmethod
    def normalize_issuer(cls, issuer: str) -> str:
        normalized = issuer.strip().rstrip("/")
        if not normalized:
            raise ValueError("issuer must be non-empty and not whitespace-only")
        return normalized


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
    catalog_uri: str = Field(
        default="http://localhost:8000", validation_alias="FDS_CATALOG_URI"
    )
    debug: bool = Field(default=False, validation_alias="FDS_DEBUG")
    ENVIRONMENT: str = Field(default="dev", validation_alias="FDS_ENVIRONMENT")
    LOG_LEVEL: str = Field(default="INFO", validation_alias="FDS_LOG_LEVEL")

    # Database Settings
    db_user: str = Field(default="", validation_alias="FDS_DB_USER")
    db_password: str = Field(default="", validation_alias="FDS_DB_PASSWORD")
    db_name: str = Field(default="fds.db", validation_alias="FDS_DB_NAME")

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
        return f"sqlite:///./{self.db_name}"


config = Config()
