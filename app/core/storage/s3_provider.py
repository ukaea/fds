import json
from typing import Any

try:
    import boto3
except ImportError:
    boto3 = None

from app.core.config import config
from app.models.file_access import S3Credentials
from app.services.exceptions import ConfigurationError


class S3CredentialProvider:
    """
    S3/STS Implementation.
    """

    def __init__(self):
        self._sts_client = None

    @property
    def sts_client(self):
        if not self._sts_client:
            if boto3 is None:
                raise ConfigurationError(
                    "boto3 is not installed. "
                    "Please install the 's3' optional dependency: pip install 'fds[s3]'"
                )

            self._sts_client = boto3.client(
                "sts",
                region_name=config.STS_REGION,
                endpoint_url=config.STS_ENDPOINT_URL,
            )
        return self._sts_client

    def generate_credentials(
        self, allowed_prefixes: list[str], session_name: str
    ) -> dict[str, Any]:
        """
        Assumes the configured STS role and returns temporary credentials.
        The policy is dynamically generated to allow access only to 'allowed_prefixes'.

        New Response Format: Map of bucket -> credentials
        """
        if not config.STS_ROLE_ARN:
            raise ConfigurationError("STS_ROLE_ARN is not configured.")

        # 1. Construct Policy
        policy_json = self._construct_policy(allowed_prefixes)

        # 2. Assume Role
        try:
            response = self.sts_client.assume_role(
                RoleArn=config.STS_ROLE_ARN,
                RoleSessionName=session_name,
                Policy=policy_json,
                DurationSeconds=config.CREDENTIAL_TOKEN_DURATION,
            )
        except Exception as e:
            # Re-raise with context but preserve original exception for debugging
            raise ConfigurationError(
                f"Failed to assume STS role '{config.STS_ROLE_ARN}': {e}"
            ) from e

        # 3. Map to Model
        creds = response["Credentials"]
        credential_object = S3Credentials(
            access_key_id=creds["AccessKeyId"],
            secret_access_key=creds["SecretAccessKey"],
            session_token=creds["SessionToken"],
            expiration=creds["Expiration"],
        )

        # 4. Return Bucket-Keyed Credential Map
        # STS credentials are bucket-agnostic (one token works for all allowed buckets).
        # However, we return a dict[bucket_name -> credentials] to maintain a consistent
        # interface with other providers (GCS, Azure) that may require per-bucket tokens.
        # Clients extract credentials via: list(result.values())[0]
        #
        # TODO: Multi-Endpoint Support
        # Current limitation: assumes single STS endpoint (config.STS_ENDPOINT_URL).
        # Future work: support multiple S3-compatible endpoints (AWS, MinIO, Ceph)
        # by mapping buckets to their respective STS endpoints and role ARNs.

        if "*" in allowed_prefixes:
            raise ConfigurationError(
                "Wildcard access '*' is not supported by S3Provider."
            )

        buckets = set()
        for prefix in allowed_prefixes:
            # Extract bucket name from s3://bucket/path
            bucket_name = prefix.replace("s3://", "").split("/")[0]
            buckets.add(bucket_name)

        # Map each bucket to the same credential object (STS tokens are global)
        result = {}
        for bucket_name in buckets:
            result[bucket_name] = credential_object

        return result

    def _construct_policy(self, allowed_prefixes: list[str]) -> str:
        """
        Constructs a JSON IAM Policy string.
        """
        if "*" in allowed_prefixes:
            raise ConfigurationError("Wildcard policy generation not supported.")

        return json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "AllowReadData",
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Resource": [
                            self._to_arn(prefix) for prefix in allowed_prefixes
                        ],
                    },
                    {
                        "Sid": "AllowListBucket",
                        "Effect": "Allow",
                        "Action": "s3:ListBucket",
                        "Resource": list(
                            {
                                f"arn:aws:s3:::{prefix.replace('s3://', '').split('/')[0]}"
                                for prefix in allowed_prefixes
                            }
                        ),
                        "Condition": {
                            "StringLike": {
                                "s3:prefix": [
                                    self._to_prefix(prefix)
                                    for prefix in allowed_prefixes
                                ]
                            }
                        },
                    },
                ],
            },
            separators=(",", ":"),
        )

    def _to_arn(self, data_url: str) -> str:
        clean = data_url.replace("s3://", "arn:aws:s3:::")
        if not clean.endswith("*"):
            clean = f"{clean.rstrip('/')}/*"
        return clean

    def _to_prefix(self, data_url: str) -> str:
        parts = data_url.replace("s3://", "").split("/", 1)
        if len(parts) > 1:
            return f"{parts[1].rstrip('/')}/*"
        return "*"
