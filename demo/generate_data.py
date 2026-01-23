# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "xarray",
#     "numpy",
#     "s3fs",
#     "zarr",
# ]
# ///
import os

import numpy as np
import s3fs
import xarray as xr

# Configuration from environment
minio_url = os.environ.get("MINIO_URL", "http://minio:9000")
access_key = os.environ.get("AWS_ACCESS_KEY_ID", "admin")
secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "password")
bucket_name = "fds-data"
path = "shots/001/zarr_data"

print(f"Connecting to MinIO at {minio_url}...")
fs = s3fs.S3FileSystem(
    key=access_key, secret=secret_key, client_kwargs={"endpoint_url": minio_url}
)

# Create a synthetic dataset
print("Generating synthetic Xarray dataset...")
data = np.random.rand(10, 20)
ds = xr.Dataset(
    {"temperature": (["x", "y"], data)}, coords={"x": np.arange(10), "y": np.arange(20)}
)
ds.attrs["title"] = "Mock Plasma Temperature"

# Write to Zarr
s3_path = f"{bucket_name}/{path}"
print(f"Writing dataset to {s3_path}...")
store = s3fs.S3Map(root=s3_path, s3=fs, check=False)
ds.to_zarr(store=store, mode="w", consolidated=True)

print("Data generation complete.")
