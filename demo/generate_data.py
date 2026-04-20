# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "xarray",
#     "numpy",
#     "s3fs",
#     "zarr",
#     "netCDF4",
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

stfc_endpoint = "https://s3.echo.stfc.ac.uk"
stfc_bucket = "mast"

print(f"Connecting to MinIO at {minio_url}...")
fs = s3fs.S3FileSystem(
    key=access_key, secret=secret_key, client_kwargs={"endpoint_url": minio_url}
)


# ---------------------------------------------------------
# Helper: Fetch a shot from STFC public S3 into MinIO
# ---------------------------------------------------------
def fetch_shot_from_stfc(shot_id: str) -> bool:
    public_fs = s3fs.S3FileSystem(
        anon=True,
        client_kwargs={"endpoint_url": stfc_endpoint},
    )
    public_base = f"{stfc_bucket}/level2/shots/{shot_id}.zarr"

    if not public_fs.exists(public_base):
        print(f"  Shot {shot_id} not found on STFC public S3 at {public_base}")
        return False

    ids_groups = sorted(
        entry.split("/")[-1]
        for entry in public_fs.ls(public_base, detail=False)
        if public_fs.isdir(entry)
    )
    print(f"  Fetching {len(ids_groups)} IDS groups for shot {shot_id} from STFC S3...")

    target = f"{bucket_name}/shots/{shot_id}"
    for ids_name in ids_groups:
        src_ids = f"{public_base}/{ids_name}"
        dst_ids = f"{target}/{ids_name}"
        for src_file in public_fs.find(src_ids):
            rel = src_file[len(src_ids) + 1 :]
            with public_fs.open(src_file, "rb") as src:
                with fs.open(f"{dst_ids}/{rel}", "wb") as dst:
                    dst.write(src.read())
        store = s3fs.S3Map(root=dst_ids, s3=fs, check=False)
        try:
            zarr.consolidate_metadata(store)
        except Exception as e:
            print(f"  Warning: Could not consolidate {ids_name}: {e}")

    print(f"  Shot {shot_id} fetched from STFC S3 successfully.")
    return True


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
        print(
            f"  Local source data not found at {source_dir}. Fetching from STFC public S3..."
        )
        fetch_shot_from_stfc(shot_id)
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


# ---------------------------------------------------------
# 3. Generate JINTRAC Integrated Modelling Outputs (Shot 30420)
# ---------------------------------------------------------
# These represent three IMAS IDSs produced by a JINTRAC simulation that used
# the measured equilibrium, magnetics, and Thomson scattering from shot 30420
# as boundary conditions.  The data is synthetic but shaped like real IDS output.

jintrac_base = f"{bucket_name}/shots/30420/jintrac"

if fs.exists(jintrac_base):
    print("JINTRAC outputs for shot 30420 already exist. Skipping generation.")
else:
    print("Generating JINTRAC integrated modelling outputs for shot 30420...")

    rho = np.linspace(0, 1, 50)  # normalised toroidal flux coordinate
    time = np.linspace(0.1, 0.35, 20)  # seconds

    # ---- equilibrium IDS ------------------------------------------------
    # Poloidal flux on (R, Z) grid at each time slice
    R = np.linspace(0.2, 0.8, 64)
    Z = np.linspace(-0.5, 0.5, 64)
    psi = np.exp(-((R[None, :, None] - 0.5) ** 2 + Z[None, None, :] ** 2) / 0.08) * (
        1 + 0.05 * np.random.randn(len(time), len(R), len(Z))
    )
    eq_ds = xr.Dataset(
        {
            "psi": (["time", "R", "Z"], psi.astype("float32")),
        },
        coords={"time": time, "R": R, "Z": Z},
        attrs={
            "title": "JINTRAC Equilibrium — Shot 30420",
            "description": (
                "Time-dependent poloidal flux map from JINTRAC integrated modelling "
                "run on MAST shot 30420."
            ),
            "IDS": "equilibrium",
            "source": "JINTRAC v220922",
        },
    )

    # ---- core_profiles IDS ----------------------------------------------
    # Electron temperature and density, ion temperature on (time, rho) grid
    Te = 2000 * (1 - rho**2) ** 1.5 * (1 + 0.02 * np.random.randn(len(time), len(rho)))
    ne = 5e19 * (1 - 0.8 * rho**2) * (1 + 0.02 * np.random.randn(len(time), len(rho)))
    Ti = Te * (1.05 + 0.1 * rho)
    cp_ds = xr.Dataset(
        {
            "electron_temperature": (["time", "rho"], Te.astype("float32")),
            "electron_density": (["time", "rho"], ne.astype("float32")),
            "ion_temperature": (["time", "rho"], Ti.astype("float32")),
        },
        coords={"time": time, "rho": rho},
        attrs={
            "title": "JINTRAC Core Profiles — Shot 30420",
            "description": (
                "Electron temperature, electron density, and ion temperature profiles "
                "from JINTRAC integrated modelling run on MAST shot 30420."
            ),
            "IDS": "core_profiles",
            "source": "JINTRAC v220922",
            "units_electron_temperature": "eV",
            "units_electron_density": "m^-3",
            "units_ion_temperature": "eV",
        },
    )

    # ---- core_sources IDS -----------------------------------------------
    # Electron and ion heat sources (W/m³) on (time, rho) grid
    Qe = (
        2e6
        * np.exp(-((rho - 0.3) ** 2) / 0.05)
        * (1 + 0.03 * np.random.randn(len(time), len(rho)))
    )
    Qi = (
        1.5e6
        * np.exp(-((rho - 0.35) ** 2) / 0.06)
        * (1 + 0.03 * np.random.randn(len(time), len(rho)))
    )
    cs_ds = xr.Dataset(
        {
            "electron_heat_source": (["time", "rho"], Qe.astype("float32")),
            "ion_heat_source": (["time", "rho"], Qi.astype("float32")),
        },
        coords={"time": time, "rho": rho},
        attrs={
            "title": "JINTRAC Core Sources — Shot 30420",
            "description": (
                "Electron and ion volumetric heat sources from JINTRAC integrated "
                "modelling run on MAST shot 30420."
            ),
            "IDS": "core_sources",
            "source": "JINTRAC v220922",
            "units_electron_heat_source": "W m^-3",
            "units_ion_heat_source": "W m^-3",
        },
    )

    # Upload each IDS as a NetCDF4 file via a local temporary file
    for name, ids_ds in [
        ("equilibrium", eq_ds),
        ("core_profiles", cp_ds),
        ("core_sources", cs_ds),
    ]:
        s3_path = f"{jintrac_base}/{name}.nc"
        print(f"  Writing {name}.nc to {s3_path}...")
        with fs.open(s3_path, "wb") as f:
            ids_ds.to_netcdf(f, engine="netcdf4")

    print("JINTRAC outputs generated and uploaded.")

print("All data tasks finished.")
