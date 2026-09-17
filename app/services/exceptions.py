class DeviceNotFoundError(ValueError):
    """Raised when a device is not found in the database."""


class ShotContextError(ValueError):
    """Raised when a shot is accessed in an incorrect context (e.g. wrong device)."""


class ForbiddenError(Exception):
    """Raised when a user does not have permission to perform an action."""


class UnauthorizedError(Exception):
    """Raised when a user is not authenticated."""


class ResourceNotFoundError(ValueError):
    """General exception for resources not found."""


class FDSValidationError(ValueError):
    """Raised when data validation fails in the service layer."""


class ConflictError(ValueError):
    """Raised when there is a conflict between provided identifiers (e.g. URL vs Body)."""


class ConfigurationError(ValueError):
    """Raised when the service is misconfigured (e.g. missing STS role)."""
