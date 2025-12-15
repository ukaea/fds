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

    @property
    def db_url(self) -> str:
        return f"sqlite:///./{self.db_name}"


config = Config()
