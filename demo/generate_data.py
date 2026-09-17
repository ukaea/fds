# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "xarray[io]",
#     "numpy",
#     "s3fs",
#     "icechunk",
# ]
# ///
"""Generate and upload demo data for FDS.

Only data that has to be local is generated here. Shots 30420 and 30421 are real
MAST data, already public at the STFC object store, and are registered by
reference rather than copied in: see ``seed_metadata.py``.

- Shot 50000 (synthetic MAST-U data):
    - raw/: 3 restricted NetCDF files (thomson_scattering, charge_exchange, magnetics)
    - analysed/: 1 public IceChunk store with 9 IMAS IDS groups
- MAST reference geometry and calibration, and the shot 30421 ELM annotation:
  synthetic, and written here because they are the writable side of the demo.
"""

import os
import tempfile
import warnings

import numpy as np
import s3fs
import xarray as xr
import zarr
from icechunk import Repository, s3_storage

warnings.filterwarnings("ignore", message=".*does not have a Zarr V3 specification.*")

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
# 1c. MAST reference calibration — a staged Thomson chain
# ---------------------------------------------------------
# Two device-level calibration versions providing the `thomson_calibration`
# role at successive stages: stage 1 (gain) then stage 2 (absolute). Both cover
# shots 30420 and 30421; resolving the signal returns them in stage order.
calibration_specs = [
    ("thomson_gain", 1, "gain"),
    ("thomson_absolute", 2, "absolute"),
]
for stem, stage, kind in calibration_specs:
    s3_path = f"{bucket_name}/mast/calibration/{stem}.nc"
    if fs.exists(s3_path):
        print(f"Calibration {stem} already exists. Skipping.")
        continue
    print(f"Generating reference calibration {stem} (stage {stage})...")
    n_channels = 50
    # Per-channel coefficient applied at this stage.
    coeff = (
        1.0 + 0.05 * np.sin(np.linspace(0, np.pi, n_channels))
        if kind == "gain"
        else np.full(n_channels, 3.2e18)  # absolute scaling to m^-3
    )
    cal = xr.Dataset(
        {"coefficient": ("channel", coeff)},
        coords={"channel": np.arange(n_channels)},
        attrs={
            "title": f"MAST Thomson {kind} calibration ({stem})",
            "role": "thomson_calibration",
            "stage": stage,
            "device": "mast",
        },
    )
    with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
        cal.to_netcdf(tmp.name)
        fs.put(tmp.name, s3_path)
    print(f"  Written to s3://{s3_path}")

# ---------------------------------------------------------
# 1d. MAST feature annotation — ELM times for shot 30421
# ---------------------------------------------------------
# The shot's inline `elm` annotation says an ELM train happened and roughly when; the
# train itself is a dense 1D series, too many events for the catalogue, so it
# lives here and is registered as a shot-frame annotation dataset. Coordinates
# are on the shot's own time base, the frame its subject fixes. Synthetic:
# a ~120 Hz train through the H-mode window the shot is annotated with.
elm_s3_path = f"{bucket_name}/shots/30421/annotations/elm_times.nc"
if fs.exists(elm_s3_path):
    print("ELM annotation for shot 30421 already exists. Skipping.")
else:
    print("Generating ELM annotation for shot 30421...")
    elm_rng = np.random.default_rng(30421)
    elm_times = np.arange(0.205, 0.45, 1 / 120)
    elm_times = elm_times + elm_rng.normal(0, 8e-4, elm_times.size)
    elms = xr.Dataset(
        {
            "elm_time": ("event", elm_times),
            "d_alpha_peak": ("event", 1.0 + elm_rng.gamma(2.0, 0.4, elm_times.size)),
        },
        coords={"event": np.arange(elm_times.size)},
        attrs={
            "title": "ELM event times (MAST shot 30421)",
            "annotates": "elm",
            "device": "mast",
            "shot": "30421",
            "frame": "shot",
            "units_elm_time": "s",
        },
    )
    with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
        elms.to_netcdf(tmp.name)
        fs.put(tmp.name, elm_s3_path)
    print(f"  Written to s3://{elm_s3_path} ({elm_times.size} events)")

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

# 2c. A second MAST-U shot, deliberately without an ELM train.
# Shot 50000 ran up in L-mode, transitioned to H-mode and ELMed; 50001 never left
# L-mode, so it has no ELMs to annotate. The pair is what lets a catalogue filter
# demonstrate exclusion rather than just returning everything. Only the two IDS
# groups the contrast needs.
shot_id_50001 = "50001"
time_50001 = np.linspace(0.1, 0.29, 80)
analysed_prefix_50001 = f"shots/{shot_id_50001}/analysed"

if fs.exists(f"{bucket_name}/{analysed_prefix_50001}/repo"):
    print(f"Analysed IceChunk store for shot {shot_id_50001} already exists. Skipping.")
else:
    print(f"Generating analysed IceChunk store for shot {shot_id_50001}...")

    storage_50001 = s3_storage(
        bucket=bucket_name,
        prefix=analysed_prefix_50001,
        endpoint_url=minio_url,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region="us-east-1",
        allow_http=True,
        force_path_style=True,
    )
    repo_50001 = Repository.create(storage=storage_50001)
    session_50001 = repo_50001.writable_session("main")
    root_50001 = zarr.open_group(store=session_50001.store, mode="w")

    eq_50001 = root_50001.require_group("equilibrium")
    eq_50001.create_array("time", data=time_50001)
    eq_50001.create_array("psi", data=rng.standard_normal((80, 50)))
    eq_50001.create_array("r_boundary", data=rng.uniform(0.2, 1.8, (80, 64)))
    eq_50001.create_array("z_boundary", data=rng.uniform(-1.5, 1.5, (80, 64)))

    mag_50001 = root_50001.require_group("magnetics")
    mag_50001.create_array("time", data=time_50001)
    mag_50001.create_array("flux_loop", data=rng.uniform(-1, 1, (80, 12)))
    mag_50001.create_array("b_field_probe", data=rng.uniform(-2, 2, (80, 20)))

    session_50001.commit(
        "MAST-U shot 50001 analysed experimental data — initial commit"
    )
    print(f"  IceChunk store written to s3://{bucket_name}/{analysed_prefix_50001}")


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
            "title": "JINTRAC Equilibrium (Shot 30420)",
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
            "title": "JINTRAC Core Profiles (Shot 30420)",
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
            "title": "JINTRAC Core Sources (Shot 30420)",
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
