# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.22.4",
#     "httpx==0.27.2",
#     "s3fs==2026.1.0",
#     "xarray[parallel]==2025.12.0",
#     "zarr==3.1.5",
#     "pyzmq>=27.1.0",
# ]
# ///

import marimo

__generated_with = "0.23.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import time

    import httpx
    import marimo as mo
    import xarray as xr
    from dask.distributed import Client, LocalCluster

    return Client, LocalCluster, httpx, json, mo, time, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # FDS Demonstration

    Full annotated walkthrough: **[http://localhost:4001/demo/walkthrough/](http://localhost:4001/demo/walkthrough/)**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""## 1. Setup and Environment""")
    return


@app.cell
def _():
    FDS_API_URL = "http://localhost:8000/api/v1"
    KEYCLOAK_URL = "http://localhost:8080/realms/fds/protocol/openid-connect/token"
    MINIO_URL = "http://localhost:9000"

    print("Environment configured.")
    return FDS_API_URL, KEYCLOAK_URL, MINIO_URL


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 2. Authentication — [docs](http://localhost:4001/demo/walkthrough/#2-authentication)"""
    )
    return


@app.cell
def _(KEYCLOAK_URL, httpx):
    auth_payload = {
        "client_id": "fds-client",
        "client_secret": "fds-client-secret",
        "username": "admin",
        "password": "password",
        "grant_type": "password",
        "scope": "openid profile fds-admin",
    }

    auth_response = httpx.post(KEYCLOAK_URL, data=auth_payload)
    auth_response.raise_for_status()
    token = auth_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("Successfully authenticated with Keycloak.")
    return (headers,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 2b. Registering Devices and Shots — [docs](http://localhost:4001/demo/walkthrough/#2b-registering-devices-and-shots)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    def register(endpoint, payload, label):
        resp = httpx.post(f"{FDS_API_URL}{endpoint}", json=payload, headers=headers)
        if resp.status_code == 201:
            print(f"  {label}: Created")
        elif resp.status_code == 409:
            print(f"  {label}: Already exists")
        else:
            print(f"  {label}: FAILED ({resp.status_code}) {resp.text}")
        return resp

    # 1. Register Devices
    print("Registering Devices...")
    register(
        "/devices/",
        {
            "name": "mast",
            "description": "Mega Ampere Spherical Tokamak (MAST)",
            "type": "tokamak",
            "access_level": "public",
        },
        "mast",
    )
    register(
        "/devices/",
        {
            "name": "mast-upgrade",
            "description": "Mega Ampere Spherical Tokamak Upgrade (MAST-U)",
            "type": "tokamak",
            "access_level": "public",
        },
        "mast-upgrade",
    )

    # 2. Register Shots
    print("Registering Shots...")
    register(
        "/devices/mast/shots",
        {
            "id": "30420",
            "access_level": "public",
            "device_name": "mast",
        },
        "mast/30420",
    )
    register(
        "/devices/mast/shots",
        {
            "id": "30421",
            "access_level": "public",
            "device_name": "mast",
        },
        "mast/30421",
    )
    register(
        "/devices/mast-upgrade/shots",
        {
            "id": "50000",
            "access_level": "public",
            "device_name": "mast-upgrade",
        },
        "mast-upgrade/50000",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 3. Registering Real Datasets — [docs](http://localhost:4001/demo/walkthrough/#3-registering-real-mast-datasets)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # IDS groups per shot (matching what generate_data.py uploaded)
    shot_30420_ids = [
        "equilibrium",
        "gas_injection",
        "interferometer",
        "magnetics",
        "pf_active",
        "pf_passive",
        "pulse_schedule",
        "soft_x_rays",
        "spectrometer_visible",
        "summary",
        "thomson_scattering",
        "wall",
    ]
    shot_30421_ids = shot_30420_ids + ["charge_exchange"]

    def register_ids_datasets(device, shot_id, ids_list):
        print(f"Registering {len(ids_list)} datasets for {device}/shots/{shot_id}...")
        for ids_name in ids_list:
            meta = {
                "name": ids_name,
                "level": 2,
                "url": f"s3://fds-data/shots/{shot_id}/{ids_name}",
                "access_level": "public",
                "title": f"{ids_name.replace('_', ' ').title()} — Shot {shot_id}",
                "media_type": "application/x-zarr",
            }
            resp = httpx.post(
                f"{FDS_API_URL}/devices/{device}/shots/{shot_id}/datasets",
                json=meta,
                headers=headers,
            )
            status = (
                "OK"
                if resp.status_code in (201, 409)
                else f"FAILED ({resp.status_code})"
            )
            print(f"  {ids_name}: {status}")

    register_ids_datasets("mast", "30420", shot_30420_ids)
    register_ids_datasets("mast", "30421", shot_30421_ids)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""### 3.1. Grouping into Experiment Data Collections — [docs](http://localhost:4001/demo/walkthrough/#31-grouping-into-experiment-data-collections)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # Create / retrieve the Intershot Scheduler source
    _r = httpx.post(
        f"{FDS_API_URL}/sources/",
        headers=headers,
        json={
            "name": "intershot-scheduler",
            "description": "Automated inter-shot data acquisition scheduler",
        },
    )
    scheduler_source_id = (
        _r.json()["id"]
        if _r.status_code == 201
        else httpx.get(
            f"{FDS_API_URL}/sources/intershot-scheduler", headers=headers
        ).json()["id"]
    )

    # Realistic acquisition timestamps for these MAST shots
    _shot_timestamps = {
        "30420": "2008-04-17T14:23:45",
        "30421": "2008-04-17T15:41:22",
    }

    for _shot_id, _started_at in _shot_timestamps.items():
        _existing = httpx.get(
            f"{FDS_API_URL}/devices/mast/shots/{_shot_id}/collections/experiment-data",
            headers=headers,
        )
        if _existing.status_code == 200:
            print(
                f"Shot {_shot_id}: Experiment Data collection already registered, skipping."
            )
            continue

        # Activity — records the acquisition run for this shot
        _act = httpx.post(
            f"{FDS_API_URL}/activities/",
            headers=headers,
            json={
                "source_id": scheduler_source_id,
                "activity_type": "ACQUISITION",
                "source_version": "intershot-scheduler-v1",
                "parameters": {"shot_id": _shot_id},
                "started_at": _started_at,
                "ended_at": _started_at,
            },
        )
        _act_id = _act.json()["id"]

        # Collection — groups all raw IDS datasets for this shot
        _col = httpx.post(
            f"{FDS_API_URL}/devices/mast/shots/{_shot_id}/collections",
            headers=headers,
            json={
                "name": "experiment-data",
                "title": "Experiment Data",
                "description": f"Raw IDS datasets acquired during MAST shot {_shot_id}.",
                "access_level": "public",
                "activity_id": _act_id,
            },
        )
        _col_id = _col.json()["id"]

        # Add all datasets for this shot to the collection.
        # Section 3.1 runs before the JINTRAC section, so at this point only
        # the raw IDS datasets exist.
        _datasets = httpx.get(
            f"{FDS_API_URL}/devices/mast/shots/{_shot_id}/datasets",
            headers=headers,
        ).json()
        for _ds in _datasets:
            httpx.post(
                f"{FDS_API_URL}/collections/{_col_id}/datasets/{_ds['id']}",
                headers=headers,
            )

        print(
            f"Shot {_shot_id}: Experiment Data collection created (id={_col_id}), "
            f"{len(_datasets)} datasets added, activity id={_act_id}."
        )

    return (scheduler_source_id,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""### 3.2. Recording Provenance — [docs](http://localhost:4001/concepts/provenance/)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # 1. Create the Source (Agent) — EFIT is used across many tokamaks, so it's a global source.
    source_meta = {
        "name": "efit",
        "description": "EFIT equilibrium reconstruction code",
    }

    print("Creating Global Source: efit...")
    resp_source = httpx.post(
        f"{FDS_API_URL}/sources/", json=source_meta, headers=headers
    )

    if resp_source.status_code == 201:
        source_id = resp_source.json()["id"]
        print(f"Source created with ID: {source_id}")
    elif resp_source.status_code == 409:
        print("Source already exists, fetching...")
        resp_get_source = httpx.get(f"{FDS_API_URL}/sources/efit", headers=headers)
        if resp_get_source.status_code == 200:
            source_id = resp_get_source.json()["id"]
            print(f"Found existing source with ID: {source_id}")
        else:
            print(f"Could not fetch source: {resp_get_source.status_code}")
            source_id = None
    else:
        print(f"Failed to create source: {resp_source.status_code} {resp_source.text}")
        source_id = None

    # 2. Create an Activity recording this specific EFIT run.
    activity_id = None
    if source_id:
        activity_meta = {
            "source_id": source_id,
            "activity_type": "ANALYSIS",
            "source_version": "efit-v2.8",
            "parameters": {"run_id": "30421-efit-standard"},
            "started_at": "2024-01-15T10:00:00",
            "ended_at": "2024-01-15T10:12:34",
        }
        print("Creating Activity for EFIT run on shot 30421...")
        resp_activity = httpx.post(
            f"{FDS_API_URL}/activities/", json=activity_meta, headers=headers
        )
        if resp_activity.status_code == 201:
            activity_id = resp_activity.json()["id"]
            print(f"Activity created with ID: {activity_id}")
        else:
            print(
                f"Failed to create activity: {resp_activity.status_code} {resp_activity.text}"
            )

    def attach_activity(activity_meta, dataset_path):
        """Create an Activity and attach it to a dataset, skipping if already recorded."""
        resp_ds = httpx.get(f"{FDS_API_URL}/{dataset_path}", headers=headers)
        if resp_ds.status_code != 200:
            print(f"  Dataset not found: {resp_ds.status_code}")
            return
        ds_list = resp_ds.json()
        if not ds_list:
            print("  Dataset not found (empty list).")
            return
        ds = ds_list[0]
        if ds.get("activity_id"):
            print(f"  Already has Activity {ds['activity_id']}, skipping.")
            return

        resp = httpx.post(
            f"{FDS_API_URL}/activities/", json=activity_meta, headers=headers
        )
        if resp.status_code != 201:
            print(f"  Failed to create activity: {resp.status_code} {resp.text}")
            return
        act_id = resp.json()["id"]
        print(f"  Activity created with ID: {act_id}")

        resp_patch = httpx.patch(
            f"{FDS_API_URL}/datasets/{ds['id']}",
            json={"activity_id": act_id},
            headers=headers,
        )
        if resp_patch.status_code == 200:
            print(f"  Attached Activity {act_id} to Dataset {ds['id']}.")
        else:
            print(
                f"  Failed to update dataset: {resp_patch.status_code} {resp_patch.text}"
            )

    if source_id:
        print("Recording provenance for shot 30421 equilibrium...")
        attach_activity(
            {
                "source_id": source_id,
                "activity_type": "ANALYSIS",
                "source_version": "efit-v2.8",
                "parameters": {"run_id": "30421-efit-standard"},
                "started_at": "2024-01-15T10:00:00",
                "ended_at": "2024-01-15T10:12:34",
            },
            "devices/mast/shots/30421/datasets/equilibrium",
        )

        print("Recording provenance for shot 30420 equilibrium...")
        attach_activity(
            {
                "source_id": source_id,
                "activity_type": "ANALYSIS",
                "source_version": "efit-v2.8",
                "parameters": {"run_id": "30420-efit-standard"},
                "started_at": "2024-01-14T09:22:00",
                "ended_at": "2024-01-14T09:34:51",
            },
            "devices/mast/shots/30420/datasets/equilibrium",
        )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""### 3.3. Semantic Metadata (JSON-LD) — [docs](http://localhost:4001/concepts/dcat-jsonld/)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx, json):
    # Resolve dataset ID first — name-based endpoints return a list
    _ds_list = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium", headers=headers
    ).json()
    eq_id = _ds_list[0]["id"]
    jsonld_url = f"{FDS_API_URL}/datasets/id/{eq_id}"

    print(f"Requesting JSON-LD from: {jsonld_url}")
    ld_headers = headers.copy()
    ld_headers["Accept"] = "application/ld+json"

    jld_resp = httpx.get(jsonld_url, headers=ld_headers)

    if jld_resp.status_code == 200:
        print("Successfully retrieved JSON-LD:")
        print(json.dumps(jld_resp.json(), indent=2))
    else:
        print(f"Failed to retrieve JSON-LD: {jld_resp.status_code} {jld_resp.text}")
    return (jld_resp,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""#### Distribution nodes in the JSON-LD response""")
    return


@app.cell
def _(jld_resp, json):
    if jld_resp.status_code == 200:
        body = jld_resp.json()
        distributions = body.get("dcat:distribution", [])
        if distributions:
            print(f"Dataset URI:  {body.get('@id')}")
            print(f"Default downloadURL: {body.get('dcat:downloadURL')}")
            print(f"\n{len(distributions)} distribution(s):")
            print(json.dumps(distributions, indent=2))
        else:
            print("No dcat:distribution nodes found in response.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""### 3b. Registering Synthetic Shot (MAST-Upgrade) — [docs](http://localhost:4001/demo/walkthrough/#3b-mast-upgrade-synthetic-datasets)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # Register 50 Public Signals
    print("Registering 50 Public Signals for MAST-Upgrade Shot 50000...")
    for i in range(50):
        meta = {
            "name": f"signal_{i:02d}",
            "level": 1,
            "shot_id": "50000",
            "device_name": "mast-upgrade",
            "url": f"s3://fds-data/shots/50000/signals/signal_{i:02d}",
            "access_level": "public",
            "title": f"Public Signal {i}",
            "media_type": "application/x-zarr",
        }
        httpx.post(
            f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets",
            json=meta,
            headers=headers,
        )

    # Register 10 Restricted Signals
    print("Registering 10 Restricted Signals for MAST-Upgrade Shot 50000...")
    for i in range(10):
        meta = {
            "name": f"restricted_{i:02d}",
            "level": 1,
            "shot_id": "50000",
            "device_name": "mast-upgrade",
            "url": f"s3://fds-data/shots/50000/restricted/data_{i:02d}",
            "access_level": "restricted",
            "title": f"Restricted Data {i}",
            "media_type": "application/x-zarr",
        }
        httpx.post(
            f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets",
            json=meta,
            headers=headers,
        )

    print("MAST-Upgrade Shot 50000 registration complete.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 4. Collections — JINTRAC Integrated Modelling — [docs](http://localhost:4001/demo/walkthrough/#4-collections-jintrac-integrated-modelling)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # If the collection already exists this run has already been registered — skip.
    _existing = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers=headers,
    )
    if _existing.status_code == 200:
        jintrac_collection_id = _existing.json()["id"]
        print(
            f"JINTRAC run already registered (collection id={jintrac_collection_id}), skipping."
        )
    else:
        # Source (the code)
        _r = httpx.post(
            f"{FDS_API_URL}/sources/",
            headers=headers,
            json={"name": "jintrac", "description": "Integrated modelling code"},
        )
        jintrac_source_id = (
            _r.json()["id"]
            if _r.status_code == 201
            else httpx.get(f"{FDS_API_URL}/sources/jintrac", headers=headers).json()[
                "id"
            ]
        )

        # Activity (this specific run, with timestamps and parameters)
        _r = httpx.post(
            f"{FDS_API_URL}/activities/",
            headers=headers,
            json={
                "source_id": jintrac_source_id,
                "source_version": "v220922",
                "activity_type": "SIMULATION",
                "parameters": {
                    "run_id": "30420-jintrac-v220922",
                    "transport_model": "NCLASS",
                },
                "started_at": "2024-03-10T14:00:00",
                "ended_at": "2024-03-10T16:47:22",
            },
        )
        jintrac_activity_id = _r.json()["id"]

        # prov:used — record which measured datasets were consumed as inputs
        for _ids in ["equilibrium", "magnetics", "thomson_scattering"]:
            _ds_id = httpx.get(
                f"{FDS_API_URL}/devices/mast/shots/30420/datasets/{_ids}",
                headers=headers,
            ).json()[0]["id"]
            httpx.post(
                f"{FDS_API_URL}/activities/{jintrac_activity_id}/inputs/{_ds_id}",
                headers=headers,
            )

        # Output datasets — one per IDS, each linked to the Activity via prov:wasGeneratedBy
        jintrac_dataset_ids = []
        for _stem in ["equilibrium", "core_profiles", "core_sources"]:
            _r = httpx.post(
                f"{FDS_API_URL}/devices/mast/shots/30420/datasets",
                headers=headers,
                json={
                    "name": _stem,
                    "title": f"JINTRAC {_stem.replace('_', ' ').title()} — Shot 30420",
                    "level": 3,
                    "url": f"s3://fds-data/shots/30420/jintrac/{_stem}.nc",
                    "media_type": "application/netcdf",
                    "format": "NetCDF4",
                    "access_level": "public",
                    "activity_id": jintrac_activity_id,
                },
            )
            jintrac_dataset_ids.append(_r.json()["id"])

        # Collection — groups all outputs into a single citable unit
        _r = httpx.post(
            f"{FDS_API_URL}/devices/mast/shots/30420/collections",
            headers=headers,
            json={
                "name": "jintrac-v220922",
                "title": "JINTRAC Integrated Modelling — Shot 30420",
                "description": "JINTRAC transport simulation outputs: equilibrium, core profiles, and heat sources.",
                "access_level": "public",
                "activity_id": jintrac_activity_id,
            },
        )
        jintrac_collection_id = _r.json()["id"]
        for _id in jintrac_dataset_ids:
            httpx.post(
                f"{FDS_API_URL}/collections/{jintrac_collection_id}/datasets/{_id}",
                headers=headers,
            )
        print(f"Source:     jintrac  (id={jintrac_source_id})")
        print(
            f"Activity:   id={jintrac_activity_id}  inputs: equilibrium, magnetics, thomson_scattering"
        )
        print(f"Datasets:   {jintrac_dataset_ids}")
        print(f"Collection: jintrac-v220922  (id={jintrac_collection_id})")

    return (jintrac_collection_id,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""### 4a. Inspecting the Collection""")
    return


@app.cell
def _(FDS_API_URL, headers, httpx, jintrac_collection_id):
    _col = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers=headers,
    ).json()
    print(f"{_col['title']}  (id={jintrac_collection_id})")
    print(f"access_level: {_col['effective_access_level']}")
    for _ds in _col.get("datasets") or []:
        print(f"  {_ds['name']}  [{_ds['format']}]  {_ds['url']}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""### 4b. Collection as `dcat:Catalog` (JSON-LD) — [docs](http://localhost:4001/concepts/dcat-jsonld/#collection-as-dcatcatalog)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx, json):
    _ld = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers={**headers, "accept": "application/ld+json"},
    ).json()
    print(json.dumps(_ld, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 5. Attempting Unauthorised Access — [docs](http://localhost:4001/concepts/access-control/#what-fds-does-not-do)"""
    )
    return


@app.cell
def _(MINIO_URL, xr):
    url = "s3://fds-data/shots/50000/restricted/data_00"
    print(f"Attempting to open restricted dataset at {url} without credentials...")

    try:
        xr.open_dataset(
            url,
            engine="zarr",
            storage_options={"client_kwargs": {"endpoint_url": MINIO_URL}},
        )
        print("Success (Unexpected! You might have AWS keys set locally)")
    except Exception as e:
        print(f"Caught expected error: {e}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 6. Secure Consumption with `include_storage_options` — [docs](http://localhost:4001/concepts/access-control/#credential-vending-sts-token-pattern)"""
    )
    return


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    ds_meta = httpx.get(
        f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets/restricted_00",
        headers=headers,
        params={"include_storage_options": True},
    ).json()[0]

    xr.open_dataset(
        ds_meta["url"], engine="zarr", storage_options=ds_meta["storage_options"]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""## 7. Single Dataset Access — real MAST equilibrium, shot 30421""")
    return


@app.cell
def _(FDS_API_URL, httpx, xr):
    eq_dataset = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
        params={"include_storage_options": True},
    ).json()[0]

    xr.open_dataset(
        eq_dataset["url"],
        engine="zarr",
        storage_options=eq_dataset["storage_options"],
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""## 8. High-Throughput Parallel Analysis (Dask) — [docs](http://localhost:4001/concepts/access-control/#bulk-access-the-credential-manifest)"""
    )
    return


@app.cell
def _(Client, FDS_API_URL, LocalCluster, headers, httpx, time):
    # 1. Setup Dask Cluster (Reuse or Create)
    try:
        client = Client.current()
        print(f"Using existing Dask Cluster: {client}")
    except ValueError:
        cluster = LocalCluster(
            n_workers=4, threads_per_worker=1, dashboard_address=None
        )
        client = Client(cluster)
        print(f"Created Dask Cluster: {client}")

    # 2. Worker Function (local imports required — marimo module wrappers can't be pickled)
    def process_signal_mean(url, storage_options):
        import xarray as xr

        ds = xr.open_dataset(url, engine="zarr", storage_options=storage_options)
        return ds["val"].values.mean()

    # 3. The "Grand Finale": Fetch Credentials & Compute in Parallel
    def run_benchmark():
        print("\n--- Starting Full Workflow Benchmark ---")
        start_time = time.time()

        # A. Request Datasets with native storage_options configured
        print("1. Requesting Datasets for Shot 50000...")
        datasets_new = httpx.get(
            f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets",
            headers=headers,
            params={"include_storage_options": "true"},
        ).json()

        print(f"   -> Received {len(datasets_new)} datasets.")

        # B. Distribute Work
        print("2. Distributing tasks to Dask Cluster...")
        local_futures = []
        for ds_meta in datasets_new:
            if ds_meta.get("storage_options") and (
                "signal_" in ds_meta["name"] or "restricted" in ds_meta["name"]
            ):
                local_futures.append(
                    client.submit(
                        process_signal_mean,
                        ds_meta["url"],
                        ds_meta["storage_options"],
                    )
                )

        # C. Compute
        bench_results = client.gather(local_futures)
        end_time = time.time()

        print("\n--- Benchmark Complete ---")
        print(
            f"Processed {len(bench_results)} datasets in {end_time - start_time:.2f} seconds."
        )
        print(f"Average Mean Value: {sum(bench_results) / len(bench_results):.4f}")

    run_benchmark()

    # 4. Cleanup Dask Cluster
    client.close()
    if "cluster" in locals():
        cluster.close()
    return


if __name__ == "__main__":
    app.run()
