from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """
    Placeholder for user data extracted from the JWT.
    Decoupled from FastAPI to allow usage in CLI/Scripts.
    """

    id: str
    scopes: list[str] = []

    def is_admin(self) -> bool:
        return "fds-admin" in self.scopes
