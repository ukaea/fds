# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.19.4",
#     "requests==2.32.5",
#     "s3fs==2026.1.0",
#     "xarray[parallel]==2025.12.0",
#     "zarr==3.1.5",
# ]
# ///

import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import time

    import marimo as mo
    import requests
    import s3fs
    import xarray as xr
    import zarr
    from dask.distributed import Client, LocalCluster

    return Client, LocalCluster, json, mo, requests, s3fs, time, xr, zarr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # FDS Demonstration: Zarr & Xarray with Marimo

    This notebook demonstrates how FDS acts as a metadata and access service for scientific data.

    **Workflow:**

    1. Authenticate with Keycloak to get an OIDC identity.
    2. Register a pre-existing Zarr dataset in the FDS catalog.
    3. Exchange the OIDC token for temporary S3 credentials via FDS.
    4. Consume the data using xarray, authenticated by the vended credentials.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Setup and Environment

    We'll define the URLs for our services. In the local demo environment, these point to the containers running in Podman/Docker.
    """)
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
    mo.md(r"""
    ## 2. Authentication

    We'll login to Keycloak to get a JWT. We're using the `admin` user configured in our realm export.
    """)
    return


@app.cell
def _(KEYCLOAK_URL, requests):
    auth_payload = {
        "client_id": "fds-client",
        "client_secret": "fds-client-secret",
        "username": "admin",
        "password": "password",
        "grant_type": "password",
        "scope": "openid profile fds-admin",
    }

    auth_response = requests.post(KEYCLOAK_URL, data=auth_payload)
    auth_response.raise_for_status()
    token = auth_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("Successfully authenticated with Keycloak.")
    return (headers,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2b. Registering Device and Shots

    Before we can register datasets, we must ensure the `Device` and `Shot` contexts exist in the Metadata Catalog.
    We will register the **MAST** tokamak with shots **30421** (real data) and **50000** (synthetic data).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # 1. Register Device
    device_meta = {
        "name": "mast",
        "description": "Mega Ampere Spherical Tokamak (MAST)",
        "type": "tokamak",
    }
    print("Registering Device: mast...")
    resp_device = requests.post(
        f"{FDS_API_URL}/devices/", json=device_meta, headers=headers
    )
    if resp_device.status_code in (201, 409):
        print("Device registered.")
    else:
        print(
            f"Device registration failed: {resp_device.status_code} {resp_device.text}"
        )

    # 2. Register Shot 30421 (Real MAST Data)
    shot_30421_meta = {"id": "30421", "access_level": "public", "device_name": "mast"}
    print("Registering Shot: 30421...")
    resp_shot_30421 = requests.post(
        f"{FDS_API_URL}/devices/mast/shots/", json=shot_30421_meta, headers=headers
    )
    if resp_shot_30421.status_code in (201, 409):
        print("Shot 30421 registered.")
    else:
        print(
            f"Shot 30421 registration failed: {resp_shot_30421.status_code} {resp_shot_30421.text}"
        )

    # 3. Register Shot 50000 (Synthetic Data)
    shot_50000_meta = {"id": "50000", "access_level": "public", "device_name": "mast"}
    print("Registering Shot: 50000...")
    resp_shot_50000 = requests.post(
        f"{FDS_API_URL}/devices/mast/shots/", json=shot_50000_meta, headers=headers
    )
    if resp_shot_50000.status_code in (201, 409):
        print("Shot 50000 registered.")
    else:
        print(
            f"Shot 50000 registration failed: {resp_shot_50000.status_code} {resp_shot_50000.text}"
        )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Registering the Real Dataset

    A Zarr v3 dataset from MAST Shot 30421 is stored at `s3://fds-data/shots/30421/level2/equilibrium`.
    This was pre-loaded into MinIO. We'll now register it in FDS.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, json, requests):
    dataset_metadata = {
        "name": "equilibrium",
        "level": 2,
        "data_url": "s3://fds-data/shots/30421/level2/equilibrium",
        "access_level": "public",
        "title": "MAST Shot 30421 EFit Equilibrium",
        "media_type": "application/x-zarr",
    }

    ds_response = requests.post(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets",
        json=dataset_metadata,
        headers=headers,
    )
    if ds_response.status_code == 201:
        print("Dataset registered in FDS catalog.")
    else:
        print(f"Dataset status: {ds_response.status_code}")

    print(json.dumps(ds_response.json(), indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.2. Linking Data to a Source (Provenance)

    FDS tracks **Provenance** by linking Datasets to the Sources (instruments or codes) that produced them.
    Here we register the **EFIT** equilibrium reconstruction code and link our equilibrium dataset to it.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # 1. Create the Source (Code) as a Global Source
    # EFIT is a general-purpose equilibrium reconstruction code used across many
    # tokamaks (MAST, DIII-D, NSTX, KSTAR, etc.), so it belongs as a global source.
    # Device-scoped sources are for physical hardware tied to a specific machine.
    source_meta = {
        "name": "efit",
        "description": "EFIT equilibrium reconstruction code",
    }

    print("Creating Global Source: efit...")
    resp_source = requests.post(
        f"{FDS_API_URL}/sources/", json=source_meta, headers=headers
    )

    if resp_source.status_code == 201:
        source_id = resp_source.json()["id"]
        print(f"Source created with ID: {source_id}")
    elif resp_source.status_code == 409:
        print("Source already exists, fetching...")
        resp_get_source = requests.get(f"{FDS_API_URL}/sources/efit", headers=headers)
        if resp_get_source.status_code == 200:
            source_id = resp_get_source.json()["id"]
            print(f"Found existing source with ID: {source_id}")
        else:
            print(f"Could not fetch source: {resp_get_source.status_code}")
            source_id = None
    else:
        print(f"Failed to create source: {resp_source.status_code} {resp_source.text}")
        source_id = None

    # 2. Link Dataset to Source
    resp_get_dataset = requests.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
        headers=headers,
    )

    if resp_get_dataset.status_code == 200:
        dataset_id = resp_get_dataset.json()["id"]

        if source_id and dataset_id:
            link_meta = {
                "source_id": source_id,
                "activity_type": "ANALYSIS",
                "source_version": "efit-v2.8",
                "parameters": {"run_id": "30421-efit-standard"},
            }

            print(f"Linking Dataset {dataset_id} to Source {source_id}...")
            resp_link = requests.post(
                f"{FDS_API_URL}/datasets/{dataset_id}/sources",
                json=link_meta,
                headers=headers,
            )

            if resp_link.status_code == 201:
                print("Provenance link created successfully.")
                print(resp_link.json())
            else:
                print(f"Failed to link: {resp_link.status_code} {resp_link.text}")
    else:
        print(f"Dataset not found: {resp_get_dataset.status_code}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.3. Semantic Metadata (JSON-LD)

    FDS supports Content Negotiation to satisfy FAIR principles. By requesting `application/ld+json`, we can retrieve the **JSON-LD** representation of the dataset, which maps our internal model to standard ontologies like **DCAT** and **PROV**.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, json, requests):
    # Request JSON-LD for the dataset we just registered
    jsonld_url = f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium"

    print(f"Requesting JSON-LD from: {jsonld_url}")
    ld_headers = headers.copy()
    ld_headers["Accept"] = "application/ld+json"

    jld_resp = requests.get(jsonld_url, headers=ld_headers)

    if jld_resp.status_code == 200:
        print("Successfully retrieved JSON-LD:")
        print(json.dumps(jld_resp.json(), indent=2))
    else:
        print(f"Failed to retrieve JSON-LD: {jld_resp.status_code} {jld_resp.text}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3b. Registering the Synthetic Shot (Extended Demo)

    We also register a large number of datasets (simulating Shot 50000) to demonstrate multi-token vending.
    These datasets correspond to what `demo/generate_data.py` created.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # Register 50 Public Signals
    print("Registering 50 Public Signals for Shot 50000...")
    for i in range(50):
        meta = {
            "name": f"signal_{i:02d}",
            "level": 1,
            "shot_id": "50000",
            "device_name": "mast",
            "data_url": f"s3://fds-data/shots/50000/signals/signal_{i:02d}",
            "access_level": "public",
            "title": f"Public Signal {i}",
            "media_type": "application/x-zarr",
        }
        requests.post(
            f"{FDS_API_URL}/devices/mast/shots/50000/datasets",
            json=meta,
            headers=headers,
        )

    # Register 10 Restricted Signals
    print("Registering 10 Restricted Signals for Shot 50000...")
    for i in range(10):
        meta = {
            "name": f"restricted_{i:02d}",
            "level": 1,
            "shot_id": "50000",
            "device_name": "mast",
            "data_url": f"s3://fds-data/shots/50000/restricted/data_{i:02d}",
            "access_level": "restricted",
            "title": f"Restricted Data {i}",
            "media_type": "application/x-zarr",
        }
        requests.post(
            f"{FDS_API_URL}/devices/mast/shots/50000/datasets",
            json=meta,
            headers=headers,
        )

    print("Synthetic Shot registration complete.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Attempting Unauthorized Access

    Before we get our temporary credentials, let's see what happens if we try to access the data directly using `s3fs` without any authentication. This should fail because the bucket is not public.
    """)
    return


@app.cell
def _(MINIO_URL, s3fs, xr):
    # This should fail because we haven't provided credentials to s3fs
    fs_unauth = s3fs.S3FileSystem(
        anon=False,
        client_kwargs={"endpoint_url": MINIO_URL},
    )

    s3_path = "fds-data/shots/30421/level2/equilibrium"
    print(f"Attempting to open dataset at {s3_path} without credentials...")
    try:
        store_unauth = s3fs.S3Map(root=s3_path, s3=fs_unauth, check=False)
        xr.open_zarr(store=store_unauth)
        print(
            "Success (Unexpected! This might happen if you have AWS_ACCESS_KEY_ID set in your environment)"
        )
    except Exception as e:
        print(f"Caught expected error: {e}")
    return (s3_path,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Retrieving Temporary Access Credentials

    Exchange the OIDC identity for S3-specific temporary credentials.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # Request credentials for Shot 50000 (multi-token demo)
    creds_response = requests.post(
        f"{FDS_API_URL}/file-access/credentials",
        json={"shot_id": "50000", "device_name": "mast"},
        headers=headers,
    )

    creds_response.raise_for_status()
    manifest = creds_response.json()

    print(f"Received Manifest with {len(manifest['tokens'])} tokens.")
    print(f"Total resources mapped: {len(manifest['resource_map'])}")

    # Also get credentials for Shot 30421 (Real Data Demo)
    creds_real_resp = requests.post(
        f"{FDS_API_URL}/file-access/credentials",
        json={"shot_id": "30421", "device_name": "mast"},
        headers=headers,
    )
    creds_real_resp.raise_for_status()
    manifest_real = creds_real_resp.json()

    # Extract the first token's credentials for the real data demo
    token_real = manifest_real["tokens"][0]
    s3_creds = list(token_real["credentials"].values())[0]
    return manifest, s3_creds


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Secure Consumption with Multi-Token Vending

    We iterate over the datasets we want to read, automatically selecting the correct token from the manifest.
    """)
    return


@app.cell
def _(MINIO_URL, manifest, xr, zarr):
    # Load a selection of signals and restricted data from Shot 50000
    datasets_to_load = [
        "s3://fds-data/shots/50000/signals/signal_00",
        "s3://fds-data/shots/50000/signals/signal_25",
        "s3://fds-data/shots/50000/signals/signal_49",
        "s3://fds-data/shots/50000/restricted/data_00",
    ]

    loaded_data = {}

    for url in datasets_to_load:
        if url not in manifest["resource_map"]:
            print(f"Skipping {url} - No credentials vended (Access Denied?)")
            continue

        # 1. Lookup Token
        token_idx = manifest["resource_map"][url]
        token_payload = manifest["tokens"][token_idx]
        creds_map = token_payload["credentials"]
        creds = list(creds_map.values())[0]

        # 2. Open Zarr v3 store with vended credentials
        try:
            store = zarr.storage.FsspecStore.from_url(
                url,
                storage_options=dict(
                    key=creds["access_key_id"],
                    secret=creds["secret_access_key"],
                    token=creds["session_token"],
                    client_kwargs={"endpoint_url": MINIO_URL},
                ),
            )
            ds = xr.open_zarr(store=store, zarr_format=3, consolidated=False)
            loaded_data[url] = ds
            print(f"Successfully loaded {url} using Token #{token_idx}")
        except Exception as e:
            print(f"Failed to load {url}: {e}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Single Dataset Access (Detailed View)

    Now we use `xarray` + `s3fs` to read the real MAST data — the Level 2 Equilibrium reconstruction from Shot 30421.
    """)
    return


@app.cell
def _(MINIO_URL, s3_creds, s3_path, xr, zarr):
    # 1. Build a Zarr v3 FsspecStore with vended credentials
    store_single = zarr.storage.FsspecStore.from_url(
        f"s3://{s3_path}",
        storage_options=dict(
            key=s3_creds["access_key_id"],
            secret=s3_creds["secret_access_key"],
            token=s3_creds["session_token"],
            client_kwargs={"endpoint_url": MINIO_URL},
        ),
    )

    # 2. Open with xarray (Zarr v3)
    print(f"Opening dataset at {s3_path}...")
    ds_single = xr.open_zarr(store=store_single, zarr_format=3, consolidated=False)

    ds_single
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. High-Throughput Parallel Analysis (Dask)

    FDS facilitates parallel analysis by vending a manifest of tokens that can be distributed to workers.
    Here, we use `dask.distributed` to read and process signals in parallel.
    """)
    return


@app.cell
def _(
    Client,
    FDS_API_URL,
    LocalCluster,
    MINIO_URL,
    headers,
    requests,
    time,
    xr,
    zarr,
):
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
    def process_signal_mean(url, token_payload, endpoint):
        import xarray as xr
        import zarr

        creds = list(token_payload["credentials"].values())[0]
        store = zarr.storage.FsspecStore.from_url(
            url,
            storage_options=dict(
                key=creds["access_key_id"],
                secret=creds["secret_access_key"],
                token=creds["session_token"],
                client_kwargs={"endpoint_url": endpoint},
            ),
        )
        ds = xr.open_zarr(store=store, zarr_format=3, consolidated=False)
        return ds["val"].values.mean()

    # 3. The "Grand Finale": Fetch Credentials & Compute in Parallel
    def run_benchmark():
        print("\n--- Starting Full Workflow Benchmark ---")
        start_time = time.time()

        # A. Request Credentials
        print("1. Requesting Credentials for Shot 50000...")
        bench_resp = requests.post(
            f"{FDS_API_URL}/file-access/credentials",
            json={"shot_id": "50000", "device_name": "mast"},
            headers=headers,
        )
        bench_resp.raise_for_status()
        manifest_new = bench_resp.json()
        print(
            f"   -> Received {len(manifest_new['tokens'])} tokens mapping {len(manifest_new['resource_map'])} resources."
        )

        # B. Distribute Work
        print("2. Distributing 60 tasks to Dask Cluster...")
        bench_urls = [
            u
            for u in manifest_new["resource_map"].keys()
            if "signal_" in u or "restricted" in u
        ]

        local_futures = []
        for u in bench_urls:
            idx = manifest_new["resource_map"][u]
            local_futures.append(
                client.submit(
                    process_signal_mean, u, manifest_new["tokens"][idx], MINIO_URL
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
    return


if __name__ == "__main__":
    app.run()
