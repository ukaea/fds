from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUser(BaseModel):
    """
    Canonical in-memory representation of an authenticated user.
    Decoupled from FastAPI to allow usage in CLI/Scripts.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable pseudonymous user identifier used internally.")
    scopes: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            "Trusted and issuer-filtered authorization scopes for the user. Stored "
            "as an immutable tuple so user identities are safe to reuse."
        ),
    )
    issuer: str | None = Field(
        default=None,
        description=(
            "OIDC issuer URL from the validated access token. Null for anonymous users."
        ),
    )

    def is_admin(self) -> bool:
        return "fds-admin" in self.scopes

    @property
    def is_anonymous(self) -> bool:
        return self.id == "anonymous"


ANONYMOUS_USER = AuthenticatedUser(id="anonymous")
