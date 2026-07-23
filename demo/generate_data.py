# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "xarray[io]",
#     "numpy",
#     "s3fs",
#     "tqdm",
#     "icechunk",
# ]
# ///
"""Generate and upload demo data for FDS.

- Shot 30420 (real MAST data): Fetched from STFC public S3 if not already in MinIO
- Shot 30421 (real MAST data): Fetched from STFC public S3 if not already in MinIO
- Shot 50000 (synthetic MAST-U data):
    - raw/: 3 restricted NetCDF files (thomson_scattering, charge_exchange, magnetics)
    - analysed/: 1 public IceChunk store with 9 IMAS IDS groups
"""

import os
import tempfile
import warnings

import numpy as np
import s3fs
import xarray as xr
import zarr
from icechunk import Repository, s3_storage
from tqdm import tqdm

warnings.filterwarnings("ignore", message=".*does not have a Zarr V3 specification.*")

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
# Helper: Ensure a real MAST shot is present in MinIO
# ---------------------------------------------------------
def ensure_shot_data(shot_id: str) -> None:
    public_fs = s3fs.S3FileSystem(
        anon=True,
        client_kwargs={"endpoint_url": stfc_endpoint},
    )
    public_base = f"{stfc_bucket}/level2/shots/{shot_id}.zarr"

    if not public_fs.exists(public_base):
        print(f"WARNING: Shot {shot_id} not found on STFC public S3 at {public_base}")
        return

    ids_groups = sorted(
        entry.split("/")[-1]
        for entry in public_fs.ls(public_base, detail=False)
        if public_fs.isdir(entry)
    )

    target = f"{bucket_name}/shots/{shot_id}"
    missing = [g for g in ids_groups if not fs.exists(f"{target}/{g}")]

    if not missing:
        print(f"Shot {shot_id} already in MinIO. Skipping.")
        return

    print(
        f"Fetching shot {shot_id} ({len(missing)} IDS groups) from STFC S3..."
        " (follow progress with: podman compose logs -f data-generator)"
    )

    for ids_name in tqdm(missing, desc=f"Shot {shot_id}", unit="IDS"):
        src_ids = f"{public_base}/{ids_name}"
        dst_ids = f"{target}/{ids_name}"
        files = public_fs.find(src_ids)
        for src_file in tqdm(files, desc=ids_name, unit="file", leave=False):
            rel = src_file[len(src_ids) + 1 :]
            with public_fs.open(src_file, "rb") as src:
                with fs.open(f"{dst_ids}/{rel}", "wb") as dst:
                    dst.write(src.read())
        store = s3fs.S3Map(root=dst_ids, s3=fs, check=False)
        try:
            zarr.consolidate_metadata(store)
        except Exception as e:
            print(f"  Warning: Could not consolidate {ids_name}: {e}")

    print(f"Shot {shot_id} fetched successfully.")


# ---------------------------------------------------------
# 1. Real MAST Data
# ---------------------------------------------------------
ensure_shot_data("30420")
ensure_shot_data("30421")

# ---------------------------------------------------------
# 1b. MAST reference geometry — Thomson chord positions
# ---------------------------------------------------------
# Two device-level geometry versions holding the (R, Z) position of each Thomson
# scattering volume: v1 for shot 30420, v2 for shot 30421 onward (chords
# re-surveyed ~1 cm outward). Referenced by each shot's thomson_scattering
# dataset via the `thomson_positions` role.
geometry_specs = [
    ("thomson_positions_v1", 0.00),
    ("thomson_positions_v2", 0.01),
]
for stem, r_offset in geometry_specs:
    s3_path = f"{bucket_name}/mast/geometry/{stem}.nc"
    if fs.exists(s3_path):
        print(f"Geometry {stem} already exists. Skipping.")
        continue
    print(f"Generating reference geometry {stem}...")
    n_channels = 50
    geom = xr.Dataset(
        {
            "R": ("channel", np.linspace(0.20, 1.40, n_channels) + r_offset),
            "Z": ("channel", np.full(n_channels, 0.015)),
        },
        coords={"channel": np.arange(n_channels)},
        attrs={
            "title": f"MAST Thomson chord positions ({stem})",
            "role": "thomson_positions",
            "device": "mast",
            "units_R": "m",
            "units_Z": "m",
        },
    )
    with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
        geom.to_netcdf(tmp.name)
        fs.put(tmp.name, s3_path)
    print(f"  Written to s3://{s3_path}")

# ---------------------------------------------------------
# 2. Generate Synthetic MAST-U Data (Shot 50000)
# ---------------------------------------------------------
# 2a: Raw diagnostic data — 3 NetCDF files, restricted access
# 2b: Analysed experimental data — IceChunk store with 9 IMAS IDS groups, public
# ---------------------------------------------------------

shot_id = "50000"
rng = np.random.default_rng(42)
time_50000 = np.linspace(0.1, 0.35, 100)  # 100 time points, 0.1–0.35 s

# 2a. Raw diagnostic NetCDF files
raw_specs = [
    (
        "thomson_scattering",
        {"t_e": (100, 50), "n_e": (100, 50)},
        {"r": np.linspace(0.3, 1.5, 50)},
    ),
    (
        "charge_exchange",
        {"t_i": (100, 30), "rotation": (100, 30)},
        {"r": np.linspace(0.3, 1.2, 30)},
    ),
    ("magnetics", {"flux_loop": (100, 12), "b_field_probe": (100, 20)}, {}),
]
for stem, vars_, extra_coords in raw_specs:
    s3_path = f"{bucket_name}/shots/{shot_id}/raw/{stem}.nc"
    if fs.exists(s3_path):
        print(f"Raw {stem} already exists. Skipping.")
        continue
    print(f"Generating raw {stem}...")
    coords: dict = {"time": time_50000, **extra_coords}
    data_vars = {}
    for var, shape in vars_.items():
        extra_dims = (
            list(extra_coords.keys())[: len(shape) - 1]
            if extra_coords
            else [f"{var}_n"] * (len(shape) - 1)
        )
        data_vars[var] = (["time"] + extra_dims, rng.standard_normal(shape))
    with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
        xr.Dataset(data_vars, coords=coords).to_netcdf(tmp.name)
        fs.put(tmp.name, s3_path)
    print(f"  Written to s3://{s3_path}")

# 2b. Analysed experimental IceChunk store
analysed_prefix = f"shots/{shot_id}/analysed"

if fs.exists(f"{bucket_name}/{analysed_prefix}/repo"):
    print(f"Analysed IceChunk store for shot {shot_id} already exists. Skipping.")
else:
    print(f"Generating analysed IceChunk store for shot {shot_id}...")

    storage = s3_storage(
        bucket=bucket_name,
        prefix=analysed_prefix,
        endpoint_url=minio_url,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region="us-east-1",
        allow_http=True,
        force_path_style=True,
    )
    repo = Repository.create(storage=storage)
    session = repo.writable_session("main")
    root = zarr.open_group(store=session.store, mode="w")

    eq = root.require_group("equilibrium")
    eq.create_array("time", data=time_50000)
    eq.create_array("psi", data=rng.standard_normal((100, 50)))
    eq.create_array("r_boundary", data=rng.uniform(0.2, 1.8, (100, 64)))
    eq.create_array("z_boundary", data=rng.uniform(-1.5, 1.5, (100, 64)))

    gas = root.require_group("gas_injection")
    gas.create_array("time", data=time_50000)
    gas.create_array("flow_rate", data=rng.uniform(0, 1e20, (100, 8)))

    intfm = root.require_group("interferometer")
    intfm.create_array("time", data=time_50000)
    intfm.create_array("n_e_line", data=rng.uniform(1e18, 5e19, (100, 4)))

    mag = root.require_group("magnetics")
    mag.create_array("time", data=time_50000)
    mag.create_array("flux_loop", data=rng.uniform(-1, 1, (100, 12)))
    mag.create_array("b_field_probe", data=rng.uniform(-2, 2, (100, 20)))

    pfa = root.require_group("pf_active")
    pfa.create_array("time", data=time_50000)
    pfa.create_array("current", data=rng.uniform(-30e3, 30e3, (100, 6)))

    pfp = root.require_group("pf_passive")
    pfp.create_array("time", data=time_50000)
    pfp.create_array("current", data=rng.uniform(-5e3, 5e3, (100, 3)))

    sxr = root.require_group("soft_x_rays")
    sxr.create_array("time", data=time_50000)
    sxr.create_array("brightness", data=rng.uniform(0, 1e6, (100, 35)))

    vis = root.require_group("spectrometer_visible")
    vis.create_array("time", data=time_50000)
    vis.create_array("intensity", data=rng.uniform(0, 1e4, (100, 16)))

    ts = root.require_group("thomson_scattering")
    ts.create_array("time", data=time_50000)
    ts.create_array("r", data=np.linspace(0.3, 1.5, 50))
    ts.create_array("t_e", data=rng.uniform(100, 5000, (100, 50)))
    ts.create_array("n_e", data=rng.uniform(1e18, 1e20, (100, 50)))

    session.commit("MAST-U shot 50000 analysed experimental data — initial commit")
    print(f"  IceChunk store written to s3://{bucket_name}/{analysed_prefix}")


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

    # netCDF4 backend requires a real path, not a file-like object
    for name, ids_ds in [
        ("equilibrium", eq_ds),
        ("core_profiles", cp_ds),
        ("core_sources", cs_ds),
    ]:
        s3_path = f"{jintrac_base}/{name}.nc"
        print(f"  Writing {name}.nc to {s3_path}...")
        with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
            ids_ds.to_netcdf(tmp.name, engine="netcdf4")
            fs.put(tmp.name, s3_path)

    print("JINTRAC outputs generated and uploaded.")

print("All data tasks finished.")
