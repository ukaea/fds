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


# ---------------------------------------------------------
# Extended Multi-Token Demo Data Generation (Mega Shot 12345)
# ---------------------------------------------------------
print("Generating Mega Shot 12345 (60+ Datasets)...")
shot_id = "12345"


def create_dataset(name, path, title):
    # Reuse random data
    data = np.random.rand(10, 10)
    ds = xr.Dataset(
        {"val": (["x", "y"], data)}, coords={"x": np.arange(10), "y": np.arange(10)}
    )
    ds.attrs["title"] = title

    s3_path_full = f"{bucket_name}/{path}"
    print(f"Writing {name} to {s3_path_full}...")
    store = s3fs.S3Map(root=s3_path_full, s3=fs, check=False)
    # Using consolidated=True helps xarray read it efficiently
    ds.to_zarr(store=store, mode="w", consolidated=True)


# 50 Public Signals
for i in range(50):
    create_dataset(
        f"signal_{i:02d}",
        f"shots/{shot_id}/signals/signal_{i:02d}",
        f"Public Signal {i}",
    )

# 10 Restricted Signals
for i in range(10):
    create_dataset(
        f"restricted_{i:02d}",
        f"shots/{shot_id}/restricted/data_{i:02d}",
        f"Restricted Data {i}",
    )

print("Data generation complete.")
