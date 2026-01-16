from datetime import datetime

from pydantic import BaseModel


class S3Credentials(BaseModel):
    """
    Temporary S3/STS Access Credentials.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime
