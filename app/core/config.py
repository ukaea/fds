from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    # Configuration for Pydantic Settings
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fds"
    debug: bool = False
    db_user: str = ""
    db_password: str = ""
    db_name: str = "fds.db"

    # OIDC/JWT related settings
    OIDC_DOMAIN: str = ""
    OIDC_AUDIENCE: str = ""
    OIDC_PROTOCOL: str = "https"

    # Storage Provider Settings
    # --- S3 (STS) ---
    STS_ROLE_ARN: str = ""  # The role to assume for vending tokens
    STS_ENDPOINT_URL: str | None = None  # Optional: for MinIO/Ceph
    STS_REGION: str = "us-east-1"
    STS_TOKEN_DURATION: int = 3600  # Default 1 hour

    # --- Azure (Future) ---
    # AZURE_TENANT_ID: str = ""

    @property
    def db_url(self) -> str:
        return f"sqlite:///./{self.db_name}"


config = Config()
