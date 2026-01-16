#!/bin/sh
set -e

# Wait for MinIO to be ready
until mc alias set local http://minio:9000 admin password; do
  echo "Waiting for MinIO..."
  sleep 1
done

# Create bucket
mc mb local/fds-data || true

# Create a policy for STS and general access
cat <<EOF > /tmp/fds-policy.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:*"
            ],
            "Resource": [
                "arn:aws:s3:::fds-data",
                "arn:aws:s3:::fds-data/*"
            ]
        }
    ]
}
EOF

mc admin policy create local fds-policy /tmp/fds-policy.json

# Create service account for fds
# Note: In mc, we use 'mc admin user add' for users, and service accounts are managed differently.
# For simplicity, we'll create a user 'fds-sa' and attach the policy.
mc admin user add local fds-sa fds-sa-secret
mc admin policy attach local fds-policy --user fds-sa

echo "MinIO setup complete."
