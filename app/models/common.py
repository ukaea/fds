from enum import Enum


class AccessLevel(str, Enum):
    """
    Enum for the access level of an entity.
    - PUBLIC: Accessible to anyone.
    - RESTRICTED: Accessible to authenticated users with general permissions.
    - EMBARGOED: Accessible only to a specific list of users.
    """

    PUBLIC = "public"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"
