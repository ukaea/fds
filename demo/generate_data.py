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
# 1. Upload Real MAST Data (Shot 30421)
# ---------------------------------------------------------
source_dir = Path("/source_data/30421")
real_target = f"{bucket_name}/shots/30421"

if fs.exists(real_target):
    print("Shot 30421 already exists in MinIO. Skipping upload.")
else:
    if not source_dir.exists() or not any(source_dir.iterdir()):
        print("Source data not found locally. Downloading via s3fs...")
        source_dir.mkdir(parents=True, exist_ok=True)
        # Use an anonymous filesystem for the public bucket
        remote_fs = s3fs.S3FileSystem(
            anon=True, client_kwargs={"endpoint_url": "https://s3.echo.stfc.ac.uk"}
        )
        try:
            remote_fs.get(
                "mast/level2/shots/30421.zarr/equilibrium",
                str(source_dir / "equilibrium"),
                recursive=True,
            )
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading data: {e}")

    if source_dir.exists():
        print(f"Uploading Shot 30421 from {source_dir}...")
        # Recursively upload all files
        for local_file in sorted(source_dir.rglob("*")):
            if local_file.is_file():
                rel_path = local_file.relative_to(source_dir)
                s3_key = f"{real_target}/{rel_path}"
                fs.put(str(local_file), s3_key)
        print("Shot 30421 uploaded successfully.")

        # Consolidate metadata for the equilibrium subgroup
        print("Consolidating metadata for equilibrium...")
        eq_store = s3fs.S3Map(root=f"{real_target}/equilibrium", s3=fs, check=False)
        zarr.consolidate_metadata(eq_store)
        print("Metadata consolidated.")
    else:
        print(f"WARNING: Source data not found at {source_dir}")

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
