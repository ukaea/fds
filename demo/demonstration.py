# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.19.4",
#     "requests==2.32.5",
#     "s3fs==2026.1.0",
#     "xarray==2025.12.0",
#     "zarr==3.1.5",
# ]
# ///

import marimo

__generated_with = "0.19.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import json

    import marimo as mo
    import requests
    import s3fs
    import xarray as xr

    return json, mo, requests, s3fs, xr


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
    ## 3. Registering the Existing Dataset

    A Zarr dataset was pre-generated at `s3://fds-data/shots/001/zarr_data` during the environment setup. We'll now register it in `fds`.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, json, requests):
    dataset_metadata = {
        "name": "plasma-array-001",
        "level": 1,
        "data_url": "s3://fds-data/shots/001/zarr_data/",
        "access_level": "public",
        "title": "Consolidated Plasma Micrograph",
        "media_type": "application/x-zarr",
    }

    ds_response = requests.post(
        f"{FDS_API_URL}/datasets/", json=dataset_metadata, headers=headers
    )
    # Note: If it already exists from a previous run, this might fail unless we handle it.
    # For a demo, we assume a fresh start or we can catch the 409 if fds returns one.
    if ds_response.status_code == 201:
        print("Dataset registered in FDS catalog.")
    else:
        print(f"Dataset status: {ds_response.status_code}")

    print(json.dumps(ds_response.json(), indent=2))
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

    s3_path = "fds-data/shots/001/zarr_data/"
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
    creds_response = requests.post(f"{FDS_API_URL}/auth/credentials", headers=headers)
    creds_response.raise_for_status()
    s3_creds = creds_response.json()["s3"]

    print("Exchanged OIDC token for temporary S3 credentials.")
    print(f"AccessKeyId: {s3_creds['access_key_id']}")
    print(f"Expiration: {s3_creds['expiration']}")
    return (s3_creds,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6. Secure Consumption with Xarray

    Now we use `xarray` + `s3fs` to read the data, providing the vended credentials from `fds`.
    """)
    return


@app.cell
def _(MINIO_URL, s3_creds, s3_path, s3fs, xr):
    # 1. Setup the filesystem with vended credentials
    fs = s3fs.S3FileSystem(
        key=s3_creds["access_key_id"],
        secret=s3_creds["secret_access_key"],
        token=s3_creds["session_token"],
        client_kwargs={"endpoint_url": MINIO_URL},
    )

    # 2. Open the Zarr store
    store = s3fs.S3Map(root=s3_path, s3=fs, check=False)

    print(f"Opening dataset at {s3_path}...")
    ds = xr.open_zarr(store=store, consolidated=True)

    ds
    return


if __name__ == "__main__":
    app.run()
