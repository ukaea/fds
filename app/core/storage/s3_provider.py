import json
from importlib import import_module
from typing import Any

from app.core.config import config
from app.models.file_access import S3Credentials
from app.models.storage_options import StorageLocation, parse_storage_url
from app.services.exceptions import ConfigurationError

boto3: Any = None
try:
    boto3 = import_module("boto3")
except ImportError:
    pass


class S3CredentialProvider:
    """
    S3/STS Implementation.
    """

    def __init__(self, provider_config):
        self._provider_config = provider_config
        self._sts_client = None

    @property
    def sts_client(self):
        if not self._sts_client:
            if boto3 is None:
                raise ConfigurationError(
                    "boto3 is not installed. "
                    "Please install the 's3' optional dependency: pip install 'fds[s3]'"
                )

            pc = self._provider_config
            sts_url = pc.sts_endpoint_url or pc.endpoint_url
            kwargs: dict[str, Any] = {
                "region_name": pc.sts_region,
                "endpoint_url": sts_url,
            }
            if pc.sts_access_key_id:
                kwargs["aws_access_key_id"] = pc.sts_access_key_id
                kwargs["aws_secret_access_key"] = pc.sts_secret_access_key
            self._sts_client = boto3.client("sts", **kwargs)
        return self._sts_client

    def generate_credentials(
        self, urls: list[str], session_name: str
    ) -> dict[str, S3Credentials]:
        """
        Assumes the configured STS role and returns temporary credentials.
        The policy is dynamically generated to allow access only to the URLs given.
        URLs that are not S3 are skipped.

        Response format: Map of URL -> credentials
        """
        if "*" in urls:
            raise ConfigurationError(
                "Wildcard access '*' is not supported by S3Provider."
            )

        locations = {
            url: location
            for url in urls
            if (location := parse_storage_url(url)) and location.backend == "s3"
        }
        if not locations:
            return {}

        role_arn = self._provider_config.sts_role_arn

        # 1. Construct Policy
        policy_json = self._construct_policy(list(locations.values()))

        # 2. Assume Role
        try:
            response = self.sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                Policy=policy_json,
                DurationSeconds=config.CREDENTIAL_TOKEN_DURATION,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to assume STS role '{role_arn}': {e}"
            ) from e

        # 3. Map to Model
        creds = response["Credentials"]
        credential_object = S3Credentials(
            access_key_id=creds["AccessKeyId"],
            secret_access_key=creds["SecretAccessKey"],
            session_token=creds["SessionToken"],
            expiration=creds["Expiration"],
            endpoint_url=self._provider_config.endpoint_url,
            region=self._provider_config.region,
        )

        # 4. Return URL-Keyed Credential Map
        # STS credentials are bucket-agnostic (one token works for all allowed buckets).
        return dict.fromkeys(locations, credential_object)

    def _construct_policy(self, locations: list[StorageLocation]) -> str:
        """
        Constructs a JSON IAM Policy string.
        """
        return json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowReadData",
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Resource": [
                            arn
                            for location in locations
                            for arn in self._to_arns(location)
                        ],
                    },
                    {
                        "Sid": "AllowListBucket",
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": list(
                            {
                                f"arn:aws:s3:::{location.bucket}"
                                for location in locations
                            }
                        ),
                        "Condition": {
                            "StringLike": {
                                "s3:prefix": [
                                    self._to_prefix(location) for location in locations
                                ]
                            }
                        },
                    },
                ],
            },
            separators=(",", ":"),
        )

    def _to_arns(self, location: StorageLocation) -> list[str]:
        clean = f"arn:aws:s3:::{location.bucket}/{location.key}".rstrip("/")
        if clean.endswith("*"):
            return [clean]
        # Grant both the exact-object ARN (NetCDF / blob file URLs) and the
        # prefix ARN with /* (Zarr store / IceChunk group URLs). The caller's
        # access pattern determines which one matches.
        return [clean, f"{clean}/*"]

    def _to_prefix(self, location: StorageLocation) -> str:
        if location.key:
            return f"{location.key.rstrip('/')}/*"
        return "*"
