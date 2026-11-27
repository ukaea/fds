from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUser(BaseModel):
    """
    Canonical in-memory representation of an authenticated user.
    Decoupled from FastAPI to allow usage in CLI/Scripts.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable pseudonymous user identifier used internally.")
    roles: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            "The user's roles, as their token carried them and their issuer is "
            "allowed to grant them. Stored as an immutable tuple so user identities "
            "are safe to reuse."
        ),
    )
    issuer: str | None = Field(
        default=None,
        description=(
            "OIDC issuer URL from the validated access token. Null for anonymous users."
        ),
    )

    def is_admin(self) -> bool:
        return "fds-admin" in self.roles

    @property
    def is_anonymous(self) -> bool:
        return self.id == "anonymous"


ANONYMOUS_USER = AuthenticatedUser(id="anonymous")
