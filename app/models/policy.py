from enum import Enum


class AccessLevel(str, Enum):
    """
    Enum for the access level of an entity.
    - PUBLIC: Metadata and Data are accessible to everyone (Open Access).
    - EMBARGOED: Metadata is Public (Discoverable), but Data requires specific authorization.
    - RESTRICTED: Metadata and Data require authorization to access.
    """

    PUBLIC = "public"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"
