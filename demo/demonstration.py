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

__generated_with = "0.19.7"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import time

    import marimo as mo
    import requests
    import s3fs
    import xarray as xr
    from dask.distributed import Client, LocalCluster

    return Client, LocalCluster, json, mo, requests, s3fs, time, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # fds Demonstration: Zarr & Xarray with Marimo

    This notebook demonstrates how fds acts as a metadata and access service for scientific data.
    Workflow:

    Authenticate with Keycloak to get an OIDC identity.
    Register a pre-existing Zarr dataset in the fds catalog.
    Exchange the OIDC token for temporary S3 credentials via fds.
    Consume the data using xarray, authenticated by the vended credentials.
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
    ## 2b. Registering Device and Shot

    Before we can register datasets, we must ensure the `Device` and `Shot` contexts exist in the Metadata Catalog.
    We will register "tokamak-1" and Shot "12345".
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # 1. Register Devices
    tokamak_meta = {
        "name": "tokamak-1",
        "description": "Primary Demo Device",
        "type": "tokamak",
    }
    mast_upgrade_meta = {
        "name": "mast_upgrade",
        "description": "MAST Upgrade",
        "type": "tokamak",
    }

    print("Registering Devices...")
    for dev in [tokamak_meta, mast_upgrade_meta]:
        resp = requests.post(f"{FDS_API_URL}/devices/", json=dev, headers=headers)
        if resp.status_code in (201, 409):
            print(f"Device {dev['name']} registered.")
        else:
            print(f"Device registration failed: {resp.status_code} {resp.text}")

    # 2. Register Shots
    # Shot 30420 (Real Data) on tokamak-1
    shot_30420 = {
        "id": "30420",
        "access_level": "public",
        "device_name": "tokamak-1",
    }
    # Shot 50000 (Synthetic High-Throughput) on mast_upgrade
    shot_50000 = {
        "id": "50000",
        "access_level": "public",
        "device_name": "mast_upgrade",
    }

    print("Registering Shots...")
    for shot in [shot_30420, shot_50000]:
        resp = requests.post(
            f"{FDS_API_URL}/devices/{shot['device_name']}/shots/",
            json=shot,
            headers=headers,
        )
        if resp.status_code in (201, 409):
            print(f"Shot {shot['id']} registered.")
        else:
            print(
                f"Shot {shot['id']} registration failed: {resp.status_code} {resp.text}"
            )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Registering the Existing Dataset

    A Zarr dataset was pre-generated at `s3://fds-data/shots/001/zarr_data` during the environment setup. We'll now register it in `fds`.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, json, requests):
    dataset_metadata = {
        "name": "plasma-summary",
        "level": 1,
        "data_url": "s3://fds-data/shots/30420/summary",  # Points to the summary subgroup
        "access_level": "public",
        "title": "MAST Shot 30420 Summary",
        "media_type": "application/x-zarr",
    }

    ds_response = requests.post(
        f"{FDS_API_URL}/devices/tokamak-1/shots/30420/datasets",
        json=dataset_metadata,
        headers=headers,
    )
    # Note: If it already exists from a previous run, this might fail unless we handle it.
    # For a demo, we assume a fresh start or we can catch the 409 if fds returns one.
    if ds_response.status_code == 201:
        print("Dataset 'plasma-summary' registered in FDS catalog.")
    else:
        print(f"Dataset status: {ds_response.status_code}")

    print(json.dumps(ds_response.json(), indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.2. Linking Data to a Source (Provenance)

    FDS tracks **Provenance** by linking Datasets to the Sources (instruments or codes) that produced them.
    Here we register the **Thomson Scattering** diagnostic and link our dataset to it.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, requests):
    # 1. Create the Source (Diagnostic Instrument) linked to Tokamak-1
    source_meta = {
        "name": "mast_summary",
        "description": "Summary data synthesis for MAST",
    }

    print("Creating Source: mast_summary on tokamak-1...")
    # Use device-scoped endpoint
    resp_source = requests.post(
        f"{FDS_API_URL}/devices/tokamak-1/sources", json=source_meta, headers=headers
    )

    if resp_source.status_code == 201:
        source_id = resp_source.json()["id"]
        print(f"Source created with ID: {source_id}")
    elif resp_source.status_code == 409:
        # Fetch existing if it already exists
        print("Source already exists.")
        resp_get_source = requests.get(
            f"{FDS_API_URL}/devices/tokamak-1/sources", headers=headers
        )
        if resp_get_source.status_code == 200:
            # Find the source in the list
            sources = resp_get_source.json()
            found = next((s for s in sources if s["name"] == "mast_summary"), None)
            if found:
                source_id = found["id"]
            else:
                source_id = None
        else:
            print(f"Could not fetch existing sources: {resp_get_source.status_code}")
            source_id = None
    else:
        print(f"Failed to create source: {resp_source.status_code} {resp_source.text}")
        source_id = None

    # 2. Link Dataset to Source
    resp_get_dataset = requests.get(
        f"{FDS_API_URL}/devices/tokamak-1/shots/30420/datasets/plasma-summary",
        headers=headers,
    )

    if resp_get_dataset.status_code == 200:
        dataset_id = resp_get_dataset.json()["id"]

        if source_id and dataset_id:
            link_meta = {
                "source_id": source_id,
                "activity_type": "SIMULATION",  # Summary data is often derived
                "source_version": "v1.0",
                "parameters": {"run_date": "2025-01-10"},
            }

            print(f"Linking Dataset {dataset_id} to Source {source_id}...")
            resp_link = requests.post(
                f"{FDS_API_URL}/datasets/{dataset_id}/sources",
                json=link_meta,
                headers=headers,
            )

            if resp_link.status_code == 201:
                print("Provenance link created successfully.")
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
    jsonld_url = f"{FDS_API_URL}/devices/tokamak-1/shots/30420/datasets/plasma-summary"

    print(f"Requesting JSON-LD from: {jsonld_url}")
    # Note bindings: We want 'application/ld+json'
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
    ### 3b. Registering the "Mega Shot" (Extended Demo)

    We also register a large number of datasets (simulating Shot 12345) to demonstrate multi-token vending.
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
            "device_name": "mast_upgrade",
            "data_url": f"s3://fds-data/shots/50000/signals/signal_{i:02d}",
            "access_level": "public",
            "title": f"Public Signal {i}",
            "media_type": "application/x-zarr",
        }
        requests.post(
            f"{FDS_API_URL}/devices/mast_upgrade/shots/50000/datasets",
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
            "device_name": "mast_upgrade",
            "data_url": f"s3://fds-data/shots/50000/restricted/data_{i:02d}",
            "access_level": "restricted",
            "title": f"Restricted Data {i}",
            "media_type": "application/x-zarr",
        }
        requests.post(
            f"{FDS_API_URL}/devices/mast_upgrade/shots/50000/datasets",
            json=meta,
            headers=headers,
        )

    print("MAST Upgrade Shot 50000 registration complete.")
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

    s3_path = "fds-data/shots/30420/summary"
    print(f"Attempting to open dataset at {s3_path} without credentials...")
    try:
        # 1. Map the store without credentials
        store_unauth = s3fs.S3Map(root=s3_path, s3=fs_unauth, check=False)
        # 2. Try to open with xarray
        xr.open_zarr(store=store_unauth, consolidated=True)
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
    # Request credentials for the entire Shot 50000 (High-Throughput)
    # This shot has ~60 datasets, so we expect multiple tokens.
    creds_response = requests.post(
        f"{FDS_API_URL}/file-access/credentials",
        json={"shot_id": "50000", "device_name": "mast_upgrade"},
        headers=headers,
    )

    creds_response.raise_for_status()
    manifest = creds_response.json()

    print(f"Received Manifest for Shot 50000 with {len(manifest['tokens'])} tokens.")
    print(f"Total resources mapped: {len(manifest['resource_map'])}")

    # Also get credentials specifically for Shot 30420 (Real Data Demo)
    # This supports the cell below that expects 's3_creds'
    creds_real_resp = requests.post(
        f"{FDS_API_URL}/file-access/credentials",
        json={"shot_id": "30420", "device_name": "tokamak-1"},
        headers=headers,
    )
    creds_real_resp.raise_for_status()
    manifest_real = creds_real_resp.json()

    # Extract the first token's credentials
    token_real = manifest_real["tokens"][0]
    # Get the credentials dictionary (first value in the map, regardless of bucket)
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
def _(MINIO_URL, manifest, s3fs, xr):
    # Let's say we want to load 5 specific signals and 1 restricted data
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
        # The provider returns a Map[Bucket, Credentials].
        # For S3, they are identical for the session, so we take the first one.
        creds_map = token_payload["credentials"]
        creds = list(creds_map.values())[0]

        # 2. Setup FS
        fs = s3fs.S3FileSystem(
            key=creds["access_key_id"],
            secret=creds["secret_access_key"],
            token=creds["session_token"],
            client_kwargs={"endpoint_url": MINIO_URL},
        )

        # 3. Read
        path = url.replace("s3://", "")
        # Note: s3fs expects bucket/path
        # But 'path' here might include bucket if url was s3://bucket/...
        # Let's clean it up.
        # Our URLs in DB typically are s3://bucket/path.

        try:
            store = s3fs.S3Map(root=path, s3=fs, check=False)
            ds = xr.open_zarr(store=store, consolidated=True)
            loaded_data[url] = ds
            print(f"Successfully loaded {url} using Token #{token_idx}")
        except Exception as e:
            print(f"Failed to load {url}: {e}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Single Dataset Access (Detailed View)

    Now we use `xarray` + `s3fs` to read the single dataset (Shot 001) we registered earlier.
    """)
    return


@app.cell
def _(MINIO_URL, s3_creds, s3_path, s3fs, xr):
    # 1. Setup the filesystem with vended credentials
    fs_single = s3fs.S3FileSystem(
        key=s3_creds["access_key_id"],
        secret=s3_creds["secret_access_key"],
        token=s3_creds["session_token"],
        client_kwargs={"endpoint_url": MINIO_URL},
    )

    # 2. Open the Zarr store
    # Note: Our s3_path input from previous cells was for unauth check.
    # Here we are using Shot 30420 Summary
    s3_path_real = "fds-data/shots/30420/summary"
    store_single = s3fs.S3Map(root=s3_path_real, s3=fs_single, check=False)

    print(f"Opening dataset at {s3_path_real}...")
    ds_single = xr.open_zarr(store=store_single, consolidated=True)

    # Display dataset info
    print(ds_single)
    # Return 'ip' (plasma current) if available
    if "ip" in ds_single:
        print("\nPlasma Current (ip) Mean:", ds_single["ip"].mean().values)

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
    s3fs,
    time,
    xr,
):
    # 1. Setup Dask Cluster (Reuse or Create)
    try:
        # Check if a client already exists
        client = Client.current()
        print(f"Using existing Dask Cluster: {client}")
    except ValueError:
        cluster = LocalCluster(
            n_workers=4, threads_per_worker=1, dashboard_address=None
        )
        client = Client(cluster)
        print(f"Created Dask Cluster: {client}")

    # 2. Worker Function
    def process_signal_mean(url, token_payload, endpoint):
        creds = list(token_payload["credentials"].values())[0]
        fs = s3fs.S3FileSystem(
            key=creds["access_key_id"],
            secret=creds["secret_access_key"],
            token=creds["session_token"],
            client_kwargs={"endpoint_url": endpoint},
        )
        store = s3fs.S3Map(root=url.replace("s3://", ""), s3=fs, check=False)
        ds = xr.open_zarr(store=store, consolidated=True)
        return ds["val"].values.mean()

    # 3. The "Grand Finale": Fetch Credentials & Compute in Parallel
    def run_benchmark():
        print("\n--- Starting Full Workflow Benchmark ---")
        start_time = time.time()

        # A. Request Credentials (Refetching to prove speed)
        print("1. Requesting Credentials for Shot 50000...")
        # Use a local variable name to avoid collision
        bench_resp = requests.post(
            f"{FDS_API_URL}/file-access/credentials",
            json={"shot_id": "50000", "device_name": "mast_upgrade"},
            headers=headers,
        )
        bench_resp.raise_for_status()
        manifest_new = bench_resp.json()
        print(
            f"   -> Received {len(manifest_new['tokens'])} tokens mapping {len(manifest_new['resource_map'])} resources."
        )

        # B. Distribute Work
        print("2. Distributing 60 tasks to Dask Cluster...")
        # Filter for all signals (public + restricted)
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
