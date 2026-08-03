from enum import Enum


class AccessLevel(str, Enum):
    """
    Access level for an entity.

    - PUBLIC: Metadata visible to everyone; credentials vended to anyone
      (anonymous-compatible).
    - EMBARGOED: Metadata discoverable by everyone; credentials vended only to
      authorised users.
    - RESTRICTED: Metadata visible only to authorised users; credentials vended
      only to authorised users.
    """

    PUBLIC = "public"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"
