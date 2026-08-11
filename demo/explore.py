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
# ]
# ///

import marimo

__generated_with = "0.23.14"
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
    **[http://localhost:4001](http://localhost:4001)**.

    **Prerequisite:** a populated FDS instance. The demo stack seeds itself on startup;
    to reseed manually run `uv run demo/seed_metadata.py`.
    """)
    return


@app.cell
def _():
    import time

    import httpx
    import marimo as mo
    import xarray as xr
    from dask.distributed import Client, LocalCluster

    return Client, LocalCluster, httpx, mo, time, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Environment
    """)
    return


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
    return


@app.cell
def _(KEYCLOAK_URL, httpx, mo):
    _resp = httpx.post(
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
    _resp.raise_for_status()
    _token = _resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {_token}", "Content-Type": "application/json"}
    mo.callout(mo.md("Authenticated with Keycloak."), kind="success")
    return (headers,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Attempting Unauthorised Access — [docs](http://localhost:4001/access-control/#what-fds-does-not-do)

    FDS is a metadata catalog — bucket access policies are enforced by the object store.
    Opening a `restricted` dataset directly without credentials fails at the storage layer.
    """)
    return


@app.cell
def _(MINIO_URL, xr):
    _url = "s3://fds-data/shots/50000/raw/thomson_scattering.nc"
    print(f"Attempting anonymous access to {_url}...")
    try:
        xr.open_dataset(
            _url,
            engine="h5netcdf",
            storage_options={
                "anon": True,
                "client_kwargs": {"endpoint_url": MINIO_URL},
            },
        )
        print("Unexpected success — bucket policy may not be applied.")
    except PermissionError as e:
        print(f"Expected PermissionError: {e}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Credential Vending with `include_storage_options` — [docs](http://localhost:4001/access-control/#credential-vending-sts-token-pattern)

    FDS vends short-lived STS tokens at query time. The client requests a dataset with
    `include_storage_options=true` and uses the embedded dict directly — no long-lived
    keys are ever handled by the client.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    _meta = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/datasets/thomson-raw",
        headers=headers,
        params={"include_storage_options": True},
    ).json()[0]

    print(f"url: {_meta['url']}")
    print(f"storage_options keys: {list(_meta['storage_options'].keys())}")

    _ds = xr.open_dataset(
        _meta["url"], engine="h5netcdf", storage_options=_meta["storage_options"]
    )
    _ds
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Real MAST Data — Shot 30421 Equilibrium

    Opening real IMAS-structured Zarr data from MAST shot 30421 via FDS-vended storage options.
    Public datasets return anonymous-compatible credentials; no auth header required.
    """)
    return


@app.cell
def _(FDS_API_URL, httpx, xr):
    _meta = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
        params={"include_storage_options": True},
    ).json()[0]

    _ds = xr.open_dataset(
        _meta["url"], engine="zarr", storage_options=_meta["storage_options"]
    )
    _ds
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Resolving Reference Geometry — [docs](http://localhost:4001/data-model/reference-datasets/#reference-geometry)

    `thomson_scattering` references the `thomson_positions` role. Reading it with
    `?include_geometry=true` resolves the reference to the geometry version valid for
    each shot — shot 30420 → `v1`, shot 30421 → `v2` — returned under a `geometry`
    field. Open the resolved dataset to read the (R, Z) chord positions.

    See [Reference Geometry](http://localhost:4001/data-model/reference-datasets/#reference-geometry).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    _geometry_ds = None
    for _shot in ("30420", "30421"):
        _signal = httpx.get(
            f"{FDS_API_URL}/devices/mast/shots/{_shot}/datasets/thomson_scattering",
            headers=headers,
            params={"include_geometry": True, "include_storage_options": True},
        ).json()[0]
        _geom = _signal.get("geometry")[0]

        _geometry_ds = xr.open_dataset(
            _geom["url"], engine="h5netcdf", storage_options=_geom["storage_options"]
        )
        _r = _geometry_ds["R"].values

        print(
            f"  shot {_shot} -> {_geom['name']}: "
            f"R {_r[0]:.2f}..{_r[-1]:.2f} m across "
            f"{_geometry_ds.sizes['channel']} channels"
        )
    _geometry_ds
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Resolving Reference Calibration — [docs](http://localhost:4001/data-model/reference-datasets/#reference-calibration)

    `thomson_scattering` also references the `thomson_calibration` role. Reading it
    with `?include_calibration=true` resolves the reference to the ordered chain —
    `[thomson_gain, thomson_absolute]` — under a `calibration` field. Unlike geometry
    (one version per role), calibration is a chain of stages applied in order.

    See [Reference Calibration](http://localhost:4001/data-model/reference-datasets/#reference-calibration).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    _calibration_ds = None
    _signal = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30420/datasets/thomson_scattering",
        headers=headers,
        params={"include_calibration": True, "include_storage_options": True},
    ).json()[0]
    _chain = _signal.get("calibration") or []
    print(f"  chain: {' -> '.join(_c['name'] for _c in _chain) or '(none)'}")
    for _c in _chain:
        _calibration_ds = xr.open_dataset(
            _c["url"], engine="h5netcdf", storage_options=_c["storage_options"]
        )
        _coeff = _calibration_ds["coefficient"].values
        print(
            f"  {_c['name']}: coefficient "
            f"{_coeff[0]:.3g}..{_coeff[-1]:.3g} across "
            f"{_calibration_ds.sizes['channel']} channels"
        )
    _calibration_ds
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. Parallel `icechunk` Reads (Dask) — [docs](http://localhost:4001/access-control/#bulk-access-the-credential-manifest)

    The **Credential Manifest** pattern at scale. All datasets in the MAST-U `icechunk` store
    are fetched in one request with embedded `storage_options`. A 4-worker Dask cluster
    reads each IDS group concurrently — FDS resolves and deduplicates all tokens server-side.
    """)
    return


@app.cell
def _(Client, FDS_API_URL, LocalCluster, httpx, time):
    _collection = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/collections/analysed"
    ).json()
    _root_url = _collection["root_url"]

    _all_datasets = httpx.get(
        f"{FDS_API_URL}/devices/mastu/shots/50000/datasets",
        params={"include_storage_options": "true"},
    ).json()
    _icechunk_datasets = [
        d
        for d in _all_datasets
        if d.get("media_type") == "application/vnd.icechunk+zarr"
    ]

    def read_group_mean(root_url, group_name, storage_options):
        from urllib.parse import urlparse

        import numpy as np
        import zarr
        from icechunk import Repository, s3_storage

        parsed = urlparse(root_url)
        opts = {k: v for k, v in (storage_options or {}).items() if v is not None}
        storage = s3_storage(
            bucket=parsed.netloc,
            prefix=parsed.path.strip("/"),
            **opts,
        )
        repo = Repository.open(storage=storage)
        session = repo.readonly_session(branch="main")
        time_arr = zarr.open_array(
            store=session.store, path=f"{group_name}/time", mode="r"
        )
        return float(np.mean(np.asarray(time_arr)))

    print(f"Reading {len(_icechunk_datasets)} IDS groups from {_root_url}")
    t0 = time.time()
    with LocalCluster(
        n_workers=4, threads_per_worker=1, dashboard_address=None
    ) as _cluster:
        with Client(_cluster) as _client:
            _futures = [
                _client.submit(
                    read_group_mean, _root_url, d["name"], d.get("storage_options")
                )
                for d in _icechunk_datasets
            ]
            _results = _client.gather(_futures)

    print(f"Completed in {time.time() - t0:.2f}s")
    for _d, _mean_t in zip(_icechunk_datasets, _results):
        print(f"  {_d['name']:30s}  mean(time) = {_mean_t:.4f} s")
    return


if __name__ == "__main__":
    app.run()
