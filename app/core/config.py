from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrustedIdP(BaseModel):
    issuer: str
    allowed_scopes: list[str] = ["*"]


class Config(BaseSettings):
    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fds"
    debug: bool = False
    db_user: str = ""
    db_password: str = ""
    db_name: str = "fds.db"

    # OIDC/JWT related settings
    OIDC_AUDIENCE: str = ""

    # Multi-IdP Configuration
    TRUSTED_IDPS: list[TrustedIdP] = []

    # Storage Provider Settings
    CREDENTIAL_TOKEN_DURATION: int = 3600  # Default 1 hour

    # --- S3 (STS) ---
    STS_ROLE_ARN: str = ""  # The role to assume for vending tokens
    STS_ENDPOINT_URL: str | None = None  # Optional: for MinIO/Ceph
    STS_REGION: str = "us-east-1"

    # --- Azure ---
    AZURE_STORAGE_ACCOUNT: str | None = None
    AZURE_TENANT_ID: str | None = None
    AZURE_CLIENT_ID: str | None = None
    AZURE_CLIENT_SECRET: str | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///./{self.db_name}"


config = Config()
