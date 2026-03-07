# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "xarray",
#     "numpy",
#     "s3fs",
#     "zarr",
# ]
# ///
"""Generate and upload demo data for FDS.

- Shot 30420 (real MAST data): Uploaded from /source_data/30420/
- Shot 30421 (real MAST data): Uploaded from /source_data/30421/
- Shot 50000 (synthetic data): Generated and uploaded programmatically
"""

import os
from pathlib import Path

import numpy as np
import s3fs
import xarray as xr
import zarr

# Configuration
minio_url = os.environ.get("MINIO_URL", "http://localhost:9000")
access_key = os.environ.get("AWS_ACCESS_KEY_ID", "admin")
secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "password")
bucket_name = "fds-data"

print(f"Connecting to MinIO at {minio_url}...")
fs = s3fs.S3FileSystem(
    key=access_key, secret=secret_key, client_kwargs={"endpoint_url": minio_url}
)


# ---------------------------------------------------------
# Helper: Upload a real shot from source_data
# ---------------------------------------------------------
def upload_real_shot(shot_id: str, source_base: str = "/source_data"):
    source_dir = Path(f"{source_base}/{shot_id}")
    target = f"{bucket_name}/shots/{shot_id}"

    if fs.exists(target):
        print(f"Shot {shot_id} already exists in MinIO. Skipping upload.")
        return

    if not source_dir.exists() or not any(source_dir.iterdir()):
        print(f"WARNING: Source data not found at {source_dir}")
        return

    # Discover all IDS groups (subdirectories)
    ids_groups = sorted([d.name for d in source_dir.iterdir() if d.is_dir()])
    print(
        f"Uploading Shot {shot_id} ({len(ids_groups)} IDS groups: {', '.join(ids_groups)})..."
    )

    for local_file in sorted(source_dir.rglob("*")):
        if local_file.is_file():
            rel_path = local_file.relative_to(source_dir)
            s3_key = f"{target}/{rel_path}"
            fs.put(str(local_file), s3_key)

    # Consolidate metadata for each IDS group
    for ids_name in ids_groups:
        ids_path = f"{target}/{ids_name}"
        if fs.exists(ids_path):
            print(f"  Consolidating metadata for {ids_name}...")
            store = s3fs.S3Map(root=ids_path, s3=fs, check=False)
            try:
                zarr.consolidate_metadata(store)
            except Exception as e:
                print(f"  Warning: Could not consolidate {ids_name}: {e}")

    print(f"Shot {shot_id} uploaded successfully.")


# ---------------------------------------------------------
# 1. Upload Real MAST Data
# ---------------------------------------------------------
upload_real_shot("30420")
upload_real_shot("30421")

# ---------------------------------------------------------
# 2. Generate Synthetic Data (Shot 50000)
# ---------------------------------------------------------
shot_id = "50000"
synth_base_path = f"{bucket_name}/shots/{shot_id}"

if fs.exists(synth_base_path):
    print(f"Synthetic data for Shot {shot_id} already exists. Skipping generation.")
else:
    print(f"Generating Shot {shot_id} (Synthetic Demo)...")

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
