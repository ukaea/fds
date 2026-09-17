# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.23.2",
#     "httpx==0.27.2",
#     "s3fs==2026.1.0",
#     "xarray[io, parallel]==2025.12.0",
#     "icechunk",
#     "pyzmq>=27.1.0",
#     "h5py",
#     "matplotlib",
#     "scipy",
# ]
# ///

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # FDS — Reading Data

    The parts of reading data back from FDS that are best seen running live: access
    enforcement at the storage layer, credential vending, opening real data with
    `xarray`, and high-throughput parallel reads.

    The metadata side — content negotiation, DCAT/JSON-LD, and provenance graphs — is
    documented with copy-pasteable examples in the concept pages:
    **[https://ukaea.github.io/fds](https://ukaea.github.io/fds)**.

    **Prerequisite:** a populated FDS instance. The demo stack seeds itself on startup;
    to reseed manually run `uv run demo/seed_metadata.py`.
    """)


@app.cell
def _():
    import time

    import httpx
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import xarray as xr
    from dask.distributed import Client, LocalCluster
    from matplotlib.colors import LogNorm
    from scipy.signal import stft

    return Client, LocalCluster, LogNorm, httpx, mo, np, plt, stft, time, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Environment
    """)


@app.cell
def _(mo):
    fds_url_input = mo.ui.text(
        value="http://localhost:8000/api/v1", label="FDS API URL", full_width=True
    )
    kc_url_input = mo.ui.text(
        value="http://localhost:8080/realms/fds/protocol/openid-connect/token",
        label="Keycloak token URL",
        full_width=True,
    )
    minio_url_input = mo.ui.text(
        value="http://localhost:9000", label="MinIO URL", full_width=True
    )
    mo.vstack([fds_url_input, kc_url_input, minio_url_input])
    return fds_url_input, kc_url_input, minio_url_input


@app.cell
def _(fds_url_input, kc_url_input, minio_url_input):
    FDS_API_URL = fds_url_input.value
    KEYCLOAK_URL = kc_url_input.value
    MINIO_URL = minio_url_input.value
    return FDS_API_URL, KEYCLOAK_URL, MINIO_URL


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Authentication
    """)


@app.cell
def _(KEYCLOAK_URL, httpx, mo):
    token_response = httpx.post(
        KEYCLOAK_URL,
        data={
            "client_id": "fds-client",
            "client_secret": "fds-client-secret",
            "username": "admin",
            "password": "password",
            "grant_type": "password",
            "scope": "openid profile fds-admin",
        },
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    mo.callout(mo.md("Authenticated with Keycloak."), kind="success")
    return (headers,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Attempting Unauthorised Access — [docs](https://ukaea.github.io/fds/access-control/#what-fds-does-not-do)

    FDS is a metadata catalog — bucket access policies are enforced by the object store.
    Opening a `restricted` dataset directly without credentials fails at the storage layer.
    """)


@app.cell
def _(MINIO_URL, xr):
    restricted_url = "s3://fds-data/shots/50000/raw/thomson_scattering.nc"
    print(f"Attempting anonymous access to {restricted_url}...")
    try:
        xr.open_dataset(
            restricted_url,
            engine="h5netcdf",
            storage_options={
                "anon": True,
                "client_kwargs": {"endpoint_url": MINIO_URL},
            },
        )
        print("Unexpected success — bucket policy may not be applied.")
    except PermissionError as permission_error:
        print(f"Expected PermissionError: {permission_error}")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Credential Vending with `include_storage_options` — [docs](https://ukaea.github.io/fds/access-control/#credential-vending-sts-token-pattern)

    FDS vends short-lived STS tokens at query time. The client requests a dataset with
    `include_storage_options=true` and uses the embedded dict directly — no long-lived
    keys are ever handled by the client.
    """)


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    raw_meta = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/datasets/thomson-raw",
        headers=headers,
        params={"include_storage_options": True},
    ).json()[0]

    print(f"url: {raw_meta['url']}")
    print(f"storage_options keys: {list(raw_meta['storage_options'].keys())}")

    raw_dataset = xr.open_dataset(
        raw_meta["url"], engine="h5netcdf", storage_options=raw_meta["storage_options"]
    )
    raw_dataset


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Real MAST Data — Shot 30421 Equilibrium

    Opening real IMAS-structured Zarr data from MAST shot 30421 via FDS-vended storage options.
    Public datasets return anonymous-compatible credentials; no auth header required.
    """)


@app.cell
def _(FDS_API_URL, httpx, xr):
    equilibrium_meta = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
        params={"include_storage_options": True},
    ).json()[0]

    equilibrium_dataset = xr.open_dataset(
        equilibrium_meta["url"],
        engine="zarr",
        storage_options=equilibrium_meta["storage_options"],
    )
    equilibrium_dataset


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Resolving Reference Geometry — [docs](https://ukaea.github.io/fds/data-model/reference-datasets/#reference-geometry)

    `thomson_scattering` references the `thomson_positions` role. Reading it with
    `?include_geometry=true` resolves the reference to the geometry version valid for
    each shot — shot 30420 → `v1`, shot 30421 → `v2` — returned under a `geometry`
    field. Open the resolved dataset to read the (R, Z) chord positions.

    See [Reference Geometry](https://ukaea.github.io/fds/data-model/reference-datasets/#reference-geometry).
    """)


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    geometry_dataset = None
    for geometry_shot in ("30420", "30421"):
        thomson = httpx.get(
            f"{FDS_API_URL}/devices/mast/shots/{geometry_shot}/datasets/thomson_scattering",
            headers=headers,
            params={"include_geometry": True, "include_storage_options": True},
        ).json()[0]
        geometry = thomson["geometry"][0]

        geometry_dataset = xr.open_dataset(
            geometry["url"],
            engine="h5netcdf",
            storage_options=geometry["storage_options"],
        )
        radii = geometry_dataset["R"].values

        print(
            f"  shot {geometry_shot} -> {geometry['name']}: "
            f"R {radii[0]:.2f}..{radii[-1]:.2f} m across "
            f"{geometry_dataset.sizes['channel']} channels"
        )
    geometry_dataset


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Resolving Reference Calibration — [docs](https://ukaea.github.io/fds/data-model/reference-datasets/#reference-calibration)

    `thomson_scattering` also references the `thomson_calibration` role. Reading it
    with `?include_calibration=true` resolves the reference to the ordered chain —
    `[thomson_gain, thomson_absolute]` — under a `calibration` field. Unlike geometry
    (one version per role), calibration is a chain of stages applied in order.

    See [Reference Calibration](https://ukaea.github.io/fds/data-model/reference-datasets/#reference-calibration).
    """)


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    calibration_dataset = None
    thomson_signal = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30420/datasets/thomson_scattering",
        headers=headers,
        params={"include_calibration": True, "include_storage_options": True},
    ).json()[0]
    calibration_chain = thomson_signal.get("calibration") or []
    chain_names = " -> ".join(stage["name"] for stage in calibration_chain)
    print(f"  chain: {chain_names or '(none)'}")
    for stage in calibration_chain:
        calibration_dataset = xr.open_dataset(
            stage["url"], engine="h5netcdf", storage_options=stage["storage_options"]
        )
        coefficients = calibration_dataset["coefficient"].values
        print(
            f"  {stage['name']}: coefficient "
            f"{coefficients[0]:.3g}..{coefficients[-1]:.3g} across "
            f"{calibration_dataset.sizes['channel']} channels"
        )
    calibration_dataset


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. Overlaying Features on a Signal — [docs](https://ukaea.github.io/fds/data-model/#feature-annotation)

    Shot 30421 carries *features* in its `scientific_metadata`: an H-mode window and a
    disruption on the `time` axis, and an MHD `mode` on the `frequency` axis. Each is an
    ordinary property with a 1D `extent` whose `start`/`end` are coordinates on the named
    axis, so a client drops the time features straight onto the plasma-current trace it
    plots against time. FDS does no conversion and asserts no shared time base: aligning a
    shot-level feature to a diagnostic's axis is the consumer's call.

    Time is not privileged. We first overlay the two time features on the plasma-current
    trace (a shaded span where the extent has an `end`, a marker line where it is a
    point). The `mode` extent is on `frequency`, so it belongs on a different axis: we
    then plot a Mirnov-coil spectrogram and overlay the mode as a band on its frequency
    axis. The consumer picks the axis; FDS just states where each feature sits.
    """)


@app.cell
def _(FDS_API_URL, httpx):
    # A shot's features live in its scientific_metadata list. Fetch the shot and pull
    # that list out so we can look at it.
    shot = httpx.get(f"{FDS_API_URL}/devices/mast/shots/30421").json()
    shot["scientific_metadata"]
    return (shot,)


@app.cell
def _(FDS_API_URL, httpx, plt, shot, xr):
    # Open the plasma-current trace. "ip" is a 1D signal over the
    # shot's time axis, so the time features drop straight onto it.
    summary_meta = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/summary",
        params={"include_storage_options": True},
    ).json()[0]
    summary_dataset = xr.open_dataset(
        summary_meta["url"],
        engine="zarr",
        storage_options=summary_meta["storage_options"],
    )

    # Plot the current, with the axis in scientific notation (it runs to ~1e5 A).
    current_figure, current_axes = plt.subplots()
    summary_dataset["ip"].plot(ax=current_axes)
    current_axes.set_ylabel("plasma current (A)")
    current_axes.ticklabel_format(axis="y", style="scientific", scilimits=(0, 0))

    # The two time features go straight onto this trace.
    h_mode = shot["scientific_metadata"][0]
    disruption = shot["scientific_metadata"][1]

    # The H-mode window spans a time range, so shade the band between start and end.
    current_axes.axvspan(
        h_mode["extent"]["start"],
        h_mode["extent"]["end"],
        alpha=0.2,
        color="C1",
        label=f"{h_mode['name']} = {h_mode['value']}",
    )

    # The disruption is a single instant (no end), so draw a vertical line at its start.
    current_axes.axvline(
        disruption["extent"]["start"],
        color="C3",
        linestyle="--",
        label=f"{disruption['name']} = {disruption['value']}",
    )

    current_axes.set_title("MAST 30421 plasma current with features overlaid")
    current_axes.legend(loc="upper right", fontsize="small")
    current_figure


@app.cell
def _(FDS_API_URL, LogNorm, httpx, np, plt, shot, stft, xr):
    # The MHD mode feature is on the frequency axis, so it belongs on a spectrogram.
    # Open the magnetics dataset and take one OMV Mirnov coil, a fast magnetic pickup
    # that resolves mode activity in the kHz range.
    magnetics_meta = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/magnetics",
        params={"include_storage_options": True},
    ).json()[0]
    magnetics_dataset = xr.open_dataset(
        magnetics_meta["url"],
        engine="zarr",
        storage_options=magnetics_meta["storage_options"],
    )

    # Compute the short-time Fourier transform of the coil signal.
    mirnov_signal = magnetics_dataset["b_field_pol_probe_omv_voltage"].isel(
        b_field_pol_probe_omv_channel=1
    )
    sample_rate = 1.0 / (
        magnetics_dataset["time_mirnov"][1] - magnetics_dataset["time_mirnov"][0]
    )
    frequencies, segment_times, transform = stft(
        np.asarray(mirnov_signal), fs=int(sample_rate), nperseg=2000, nfft=2000
    )

    spectrogram_figure, spectrogram_axes = plt.subplots(figsize=(9, 4))
    mesh = spectrogram_axes.pcolormesh(
        segment_times,
        frequencies / 1000,
        np.abs(transform),
        shading="nearest",
        cmap="jet",
        norm=LogNorm(vmin=1e-5),
    )
    spectrogram_axes.set_ylim(0, 50)
    spectrogram_axes.set_xlabel("time (s)")
    spectrogram_axes.set_ylabel("frequency (kHz)")
    spectrogram_figure.colorbar(mesh, ax=spectrogram_axes)

    # Overlay the MHD mode as a band across its frequency extent (start..end, in kHz).
    mhd_mode = shot["scientific_metadata"][2]
    mode_start_khz = mhd_mode["extent"]["start"] / 1000
    mode_end_khz = mhd_mode["extent"]["end"] / 1000
    spectrogram_axes.axhspan(
        mode_start_khz,
        mode_end_khz,
        facecolor="none",
        edgecolor="white",
        linewidth=1.5,
        linestyle="--",
        label=f"{mhd_mode['name']} = {mhd_mode['value']}",
    )
    spectrogram_axes.set_title("MAST 30421 Mirnov spectrogram with MHD mode overlaid")
    spectrogram_axes.legend(loc="upper right", fontsize="small")
    spectrogram_figure


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 9. Finding Data by Feature — [docs](https://ukaea.github.io/fds/data-model/#finding-annotated-records)

    Section 8 showed what a feature *is*. This is what makes it useful: the same annotations are
    a filter on the catalogue, so a question about the plasma becomes a single request and
    no bulk data is opened to answer it.

    `?annotation=disruption` matches any record carrying that annotation, and
    `?annotation=elm:type-I` matches a particular value. Repeat the parameter to require
    several at once. Dataset lists also take `shot_annotation`, which filters on an
    annotation carried by the dataset's *parent shot*, and that is what lets one query
    span both levels.
    """)


@app.cell
def _(FDS_API_URL, httpx):
    # "Show me MAST shots that disrupted."
    # The disruption is an annotation on the shot, so this is a pure catalogue query.
    mast_shots_url = f"{FDS_API_URL}/devices/mast/shots"

    all_mast_shots = httpx.get(mast_shots_url).json()
    disrupted_shots = httpx.get(
        mast_shots_url, params={"annotation": "disruption"}
    ).json()

    print(f"all MAST shots:  {[row['id'] for row in all_mast_shots]}")
    print(f"?annotation=disruption: {[row['id'] for row in disrupted_shots]}")


@app.cell
def _(FDS_API_URL, httpx):
    # Presence alone cannot pick out H-mode, because `confinement_mode` is present on
    # L-mode shots too. Equality can, but a mode holds over a *window*, not over a
    # shot: 50000 ran up in L-mode and transitioned at 0.18 s, so it carries
    # `confinement_mode` twice and answers to both values. 50001 never left L-mode.
    #
    # Each annotation is matched against the whole list independently, so repeating
    # the parameter asks for a shot carrying every one of them somewhere. That is what
    # makes the last two lines different questions, and the fourth a useful one:
    # L-mode AND H-mode is the query for a transition.
    mastu_shots_url = f"{FDS_API_URL}/devices/mastu/shots"

    def shot_ids(annotation):
        response = httpx.get(mastu_shots_url, params={"annotation": annotation})
        return [hit["id"] for hit in response.json()]

    print("confinement_mode        ", shot_ids("confinement_mode"))
    print("confinement_mode:H-mode ", shot_ids("confinement_mode:H-mode"))
    print("confinement_mode:L-mode ", shot_ids("confinement_mode:L-mode"))
    print(
        "L-mode AND H-mode       ",
        shot_ids(["confinement_mode:L-mode", "confinement_mode:H-mode"]),
    )
    print("L-mode AND elm          ", shot_ids(["confinement_mode:L-mode", "elm"]))


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    That last line is worth reading twice. It returns 50000, whose ELMs were in
    H-mode, not in the L-mode window before the transition. Both annotations hold for
    the shot, so the shot matches; neither the query nor the filter says they held
    *at the same time*.

    The filter selects records, not moments. Every annotation carries its window in
    the result, so the co-location is yours to check, and asking the catalogue to
    check it (`elm` **during** `confinement_mode:L-mode`) needs comparison operators
    over extents, which this first slice does not have.
    """)


@app.cell
def _(FDS_API_URL, httpx):
    # "Give me the equilibrium datasets from ELMy MAST-U shots."
    # This spans two levels: `elm` is an annotation on the *shot*, `equilibrium` is the
    # dataset's name. `shot_annotation` joins them on the device listing, so it stays one
    # request rather than a shot query followed by a request per shot.
    #
    # MAST-U seeds a matched pair: 50000 reached H-mode and had an ELM train, 50001
    # stayed in L-mode. Both carry an equilibrium dataset, so the filter has something
    # to exclude as well as something to return.
    datasets_url = f"{FDS_API_URL}/devices/mastu/datasets"
    equilibrium_query = {"name": "equilibrium"}

    all_equilibrium = httpx.get(datasets_url, params=equilibrium_query).json()
    elmy_equilibrium = httpx.get(
        datasets_url, params={**equilibrium_query, "shot_annotation": "elm"}
    ).json()

    print("every MAST-U equilibrium dataset:")
    for equilibrium_row in all_equilibrium:
        print(f"  shot {equilibrium_row['shot_id']}   {equilibrium_row['title']}")

    print("\n...from ELMy shots only (&shot_annotation=elm):")
    for elmy_row in elmy_equilibrium:
        print(f"  shot {elmy_row['shot_id']}   {elmy_row['title']}")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 10. Parallel `icechunk` Reads (Dask) — [docs](https://ukaea.github.io/fds/access-control/#bulk-access-the-credential-manifest)

    The **Credential Manifest** pattern at scale. All datasets in the MAST-U `icechunk` store
    are fetched in one request with embedded `storage_options`. A 4-worker Dask cluster
    reads each IDS group concurrently — FDS resolves and deduplicates all tokens server-side.
    """)


@app.cell
def _(Client, FDS_API_URL, LocalCluster, httpx, time):
    analysed_collection = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/collections/analysed"
    ).json()
    store_root_url = analysed_collection["root_url"]

    shot_datasets = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/datasets",
        params={"include_storage_options": "true"},
    ).json()
    icechunk_datasets = [
        dataset
        for dataset in shot_datasets
        if dataset.get("media_type") == "application/vnd.icechunk+zarr"
    ]

    def read_group_mean(root_url, group_name, storage_options):
        from urllib.parse import urlparse

        import numpy as np
        import zarr
        from icechunk import Repository, s3_storage

        parsed = urlparse(root_url)
        options = {
            key: value
            for key, value in (storage_options or {}).items()
            if value is not None
        }
        storage = s3_storage(
            bucket=parsed.netloc,
            prefix=parsed.path.strip("/"),
            **options,
        )
        repo = Repository.open(storage=storage)
        session = repo.readonly_session(branch="main")
        time_array = zarr.open_array(
            store=session.store, path=f"{group_name}/time", mode="r"
        )
        return float(np.mean(np.asarray(time_array)))

    print(f"Reading {len(icechunk_datasets)} IDS groups from {store_root_url}")
    start_time = time.time()
    with (
        LocalCluster(
            n_workers=4, threads_per_worker=1, dashboard_address=None
        ) as cluster,
        Client(cluster) as dask_client,
    ):
        futures = [
            dask_client.submit(
                read_group_mean,
                store_root_url,
                dataset["name"],
                dataset.get("storage_options"),
            )
            for dataset in icechunk_datasets
        ]
        mean_times = dask_client.gather(futures)

    print(f"Completed in {time.time() - start_time:.2f}s")
    for dataset, mean_time in zip(icechunk_datasets, mean_times):
        print(f"  {dataset['name']:30s}  mean(time) = {mean_time:.4f} s")


if __name__ == "__main__":
    app.run()
