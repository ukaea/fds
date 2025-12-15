from fastapi import HTTPException
from starlette import status


def create_unauthorized_exception(
    detail: str = "Not authenticated", authenticate_header: str = "Bearer"
) -> HTTPException:
    """
    Creates a standard HTTPException for 401 Unauthorized errors.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": authenticate_header},
    )
