class DeviceNotFoundError(ValueError):
    """Raised when a device is not found in the database."""
    pass


class ShotContextError(ValueError):
    """Raised when a shot is accessed in an incorrect context (e.g. wrong device)."""
    pass


class ForbiddenError(Exception):
    """Raised when a user does not have permission to perform an action."""
    pass


class UnauthorizedError(Exception):
    """Raised when a user is not authenticated."""
    pass


class ResourceNotFoundError(ValueError):
    """General exception for resources not found."""
    pass


class FDSValidationError(ValueError):
    """Raised when data validation fails in the service layer."""
    pass


class ConflictError(ValueError):
    """Raised when there is a conflict between provided identifiers (e.g. URL vs Body)."""
    pass
