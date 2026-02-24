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
import shutil
import numpy as np
import s3fs
import xarray as xr

# Configuration
minio_url = os.environ.get("MINIO_URL", "http://localhost:9000")
access_key = os.environ.get("AWS_ACCESS_KEY_ID", "admin")
secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "password")
bucket_name = "fds-data"

# Real Data Path (mounted in container or local)
container_source_path = "/source_data/30420.zarr"
local_source_path = "/Users/nathan/fair-mast/data/zarr/30420.zarr"

if os.path.exists(container_source_path):
    real_source_path = container_source_path
elif os.path.exists(local_source_path):
    real_source_path = local_source_path
else:
    real_source_path = None
    print("WARNING: Could not find real data at /source_data or local path.")

real_target_key = "shots/30420"

print(f"Connecting to MinIO at {minio_url}...")
fs = s3fs.S3FileSystem(
    key=access_key, secret=secret_key, client_kwargs={"endpoint_url": minio_url}
)

# ---------------------------------------------------------
# 1. Upload Real MAST Data (Shot 30420)
# ---------------------------------------------------------
target_full_path = f"{bucket_name}/{real_target_key}"
if fs.exists(target_full_path):
    print(f"Real data already exists at {target_full_path}. Skipping upload.")
else:
    print(f"Uploading real data from {real_source_path} to {target_full_path}...")
    if os.path.exists(real_source_path):
        # s3fs.put with recursive=True is the standard way to upload a directory
        fs.put(real_source_path, target_full_path, recursive=True)
        print("Upload complete.")
    else:
        print(
            f"WARNING: Source data not found at {real_source_path}. Is the volume mounted?"
        )

# ---------------------------------------------------------
# 2. Synthetic "Mega Shot" (Shot 50000 - MAST Upgrade)
# ---------------------------------------------------------
shot_id = "50000"
synth_base_path = f"{bucket_name}/shots/{shot_id}"

if fs.exists(synth_base_path):
    print(f"Synthetic data for Shot {shot_id} already exists. Skipping generation.")
else:
    print(f"Generating Shot {shot_id} (MAST Upgrade Demo)...")

    def create_dataset(name, path, title):
        data = np.random.rand(10, 10)
        ds = xr.Dataset(
            {"val": (["x", "y"], data)}, coords={"x": np.arange(10), "y": np.arange(10)}
        )
        ds.attrs["title"] = title

        s3_path_full = f"{bucket_name}/{path}"
        print(f"Writing {name} to {s3_path_full}...")
        store = s3fs.S3Map(root=s3_path_full, s3=fs, check=False)
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
    print("Synthetic data generation complete.")

print("All data tasks finished.")
