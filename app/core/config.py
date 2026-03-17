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


class Config(BaseSettings):
    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application Settings
    app_name: str = Field(default="fds", validation_alias="FDS_APP_NAME")
    debug: bool = Field(default=False, validation_alias="FDS_DEBUG")

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

    # Storage Provider Settings
    CREDENTIAL_TOKEN_DURATION: int = Field(
        default=3600, validation_alias="FDS_CREDENTIAL_TOKEN_DURATION"
    )

    # --- S3 (STS) ---
    STS_ROLE_ARN: str = Field(default="", validation_alias="FDS_STS_ROLE_ARN")
    STS_ENDPOINT_URL: str | None = Field(
        default=None, validation_alias="FDS_STS_ENDPOINT_URL"
    )
    STS_REGION: str = Field(default="us-east-1", validation_alias="FDS_STS_REGION")

    # --- Azure ---
    AZURE_STORAGE_ACCOUNT: str | None = Field(
        default=None, validation_alias="FDS_AZURE_STORAGE_ACCOUNT"
    )
    AZURE_TENANT_ID: str | None = Field(
        default=None, validation_alias="FDS_AZURE_TENANT_ID"
    )
    AZURE_CLIENT_ID: str | None = Field(
        default=None, validation_alias="FDS_AZURE_CLIENT_ID"
    )
    AZURE_CLIENT_SECRET: str | None = Field(
        default=None, validation_alias="FDS_AZURE_CLIENT_SECRET"
    )

    @property
    def db_url(self) -> str:
        return f"sqlite:///./{self.db_name}"


config = Config()
