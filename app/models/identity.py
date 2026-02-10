from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """
    Canonical in-memory representation of an authenticated user.
    Decoupled from FastAPI to allow usage in CLI/Scripts.
    """

    id: str
    scopes: list[str] = []

    def is_admin(self) -> bool:
        return "fds-admin" in self.scopes

    @property
    def is_anonymous(self) -> bool:
        return self.id == "anonymous"


ANONYMOUS_USER = AuthenticatedUser(id="anonymous", scopes=[])
