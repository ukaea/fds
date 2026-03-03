# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.19.4",
#     "httpx==0.27.2",
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

    import httpx
    import marimo as mo
    import xarray as xr
    from dask.distributed import Client, LocalCluster

    return Client, LocalCluster, httpx, json, mo, time, xr


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # FDS Demonstration: Zarr & Xarray with Marimo

    This notebook demonstrates how FDS acts as a metadata and access service for scientific data.

    **Workflow:**

    1. Authenticate with Keycloak to get an OIDC identity.
    2. Register a pre-existing Zarr dataset in the FDS catalog.
    3. Query the catalog for the dataset, requesting `include_storage_options=true`.
    4. Consume the data using xarray natively, authenticated by the embedded credentials.
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
    mo.md(r"""
    ## 2b. Registering Device and Shots

    Before we can register datasets, we must ensure the `Device` and `Shot` contexts exist in the Metadata Catalog.
    We will register the **MAST** tokamak with shots **30421** (real data) and **50000** (synthetic data).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx):
    # 1. Register Device
    device_meta = {
        "name": "mast",
        "description": "Mega Ampere Spherical Tokamak (MAST)",
        "type": "tokamak",
    }
    print("Registering Device: mast...")
    resp_device = httpx.post(
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
    resp_shot_30421 = httpx.post(
        f"{FDS_API_URL}/devices/mast/shots", json=shot_30421_meta, headers=headers
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
    resp_shot_50000 = httpx.post(
        f"{FDS_API_URL}/devices/mast/shots", json=shot_50000_meta, headers=headers
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

    A Zarr v3 dataset from MAST Shot 30421 is stored at `s3://fds-data/shots/30421/equilibrium`.
    This was pre-loaded into MinIO. We'll now register it in FDS.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, json):
    dataset_metadata = {
        "name": "equilibrium",
        "level": 2,
        "data_url": "s3://fds-data/shots/30421/equilibrium",
        "access_level": "public",
        "title": "MAST Shot 30421 EFit Equilibrium",
        "media_type": "application/x-zarr",
    }

    ds_response = httpx.post(
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
def _(FDS_API_URL, headers, httpx):
    # 1. Create the Source (Code) as a Global Source
    # EFIT is a general-purpose equilibrium reconstruction code used across many
    # tokamaks (MAST, DIII-D, NSTX, KSTAR, etc.), so it belongs as a global source.
    # Device-scoped sources are for physical hardware tied to a specific machine.
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

    # 2. Link Dataset to Source
    resp_get_dataset = httpx.get(
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
            resp_link = httpx.post(
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
def _(FDS_API_URL, headers, httpx, json):
    # Request JSON-LD for the dataset we just registered
    jsonld_url = f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium"

    print(f"Requesting JSON-LD from: {jsonld_url}")
    ld_headers = headers.copy()
    ld_headers["Accept"] = "application/ld+json"

    jld_resp = httpx.get(jsonld_url, headers=ld_headers)

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
def _(FDS_API_URL, headers, httpx):
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
        httpx.post(
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
        httpx.post(
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

    Before we fetch credentials from FDS, let's see what happens if we attempt to access a dataset directly using native `xarray` without providing authentication.

    We will try to read a dataset we categorized as `restricted` in FDS. It is important to note that FDS is purely a metadata catalog—it does not manage or enforce physical bucket policies on the underlying object store!

    Because the data owner has configured access to this dataset in their bucket to be restricted, native access will fail without proper AWS keys. FDS bridges this gap by securely vending temporary STS tokens for authorized users, saving them from managing long-lived AWS credentials manually.
    """)
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
    mo.md(r"""
    ## 5. Secure Consumption with Data-Driven Configuration

    Instead of manually vending and managing tokens, we simply fetch the datasets from FDS with `include_storage_options=true`. The API evaluates our permissions and automatically calculates and embeds the necessary STS endpoint URLs and temporary keys directly into the JSON response!
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, xr):
    ds_meta = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/50000/datasets/restricted_00",
        headers=headers,
        params={"include_storage_options": True},
    ).json()

    xr.open_dataset(
        ds_meta["data_url"], engine="zarr", storage_options=ds_meta["storage_options"]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Single Dataset Access (Detailed View)

    Now we use `xarray` to read some real MAST data — the Level 2 Equilibrium reconstruction from Shot 30421.
    """)
    return


@app.cell
def _(FDS_API_URL, httpx, xr):
    eq_dataset = httpx.get(
        f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
        params={"include_storage_options": True},
    ).json()

    xr.open_dataset(
        eq_dataset["data_url"],
        engine="zarr",
        storage_options=eq_dataset["storage_options"],
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. High-Throughput Parallel Analysis (Dask)

    FDS facilitates parallel analysis by resolving tokens server-side. We simply pass the `storage_options` dictionary to our worker functions.
    """)
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
            f"{FDS_API_URL}/devices/mast/shots/50000/datasets",
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
                        ds_meta["data_url"],
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
    return


if __name__ == "__main__":
    app.run()
