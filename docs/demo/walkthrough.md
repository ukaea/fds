# Demo Walkthrough

The demonstration notebook (`demo/demonstration.py`) is a [Marimo](https://marimo.io/) reactive notebook that exercises the full FDS workflow against the local demo environment. Run it with:

```bash
uvx marimo edit demo/demonstration.py --sandbox
```

Or as a non-interactive script:

```bash
uv run demo/demonstration.py
```

The sections below annotate each step.

---

## 1. Environment setup

```python
FDS_API_URL = "http://localhost:8000/api/v1"
KEYCLOAK_URL = "http://localhost:8080/realms/fds/protocol/openid-connect/token"
MINIO_URL = "http://localhost:9000"
```

The demo environment is entirely local. No external services are contacted.

---

## 2. Authentication

FDS delegates identity to Keycloak. The notebook obtains a JWT using the OIDC Resource Owner Password flow (convenient for scripting; production clients use the Authorization Code flow):

```python
auth_payload = {
    "client_id": "fds-client",
    "client_secret": "fds-client-secret",
    "username": "admin",
    "password": "password",
    "grant_type": "password",
    "scope": "openid profile fds-admin",
}
token = httpx.post(KEYCLOAK_URL, data=auth_payload).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
```

The resulting JWT is included in all subsequent FDS requests. FDS validates it against Keycloak's JWKS endpoint.

See [Access Control → Authentication](../concepts/access-control.md#authentication) and [ADR-0007](../adrs/0007-externalized-identity-and-trust-registry.md).

---

## 2b. Registering Devices and Shots

Before datasets can be registered, their parent **Device** and **Shot** contexts must exist in the catalog. The notebook registers:

- **MAST** with shots **30420** and **30421** (real IMAS-structured Zarr data)
- **MAST-Upgrade** with shot **50000** (synthetic data for access-restriction demos)

See [Data Model](../concepts/data-model.md).

---

## 3. Registering real MAST datasets

Real IMAS-structured Zarr data from two MAST shots is pre-loaded in MinIO. Each IDS group (e.g. `equilibrium`, `magnetics`, `thomson_scattering`) is registered as a separate Dataset:

```python
POST /api/v1/devices/mast/shots/30421/datasets
{
  "name": "equilibrium",
  "level": 2,
  "url": "s3://fds-data/shots/30421/equilibrium",
  "media_type": "application/x-zarr",
  "access_level": "public"
}
```

### 3.1 Grouping into Experiment Data collections

All IDS datasets for each shot are grouped into an **Experiment Data** Collection linked to an `ACQUISITION` Activity produced by the **Intershot Scheduler** source. This records that these datasets were automatically collected between shots.

See [Data Model → Collection](../concepts/data-model.md#collection) and [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md).

### 3.2 Recording provenance (Activity)

The **EFIT** equilibrium reconstruction code is registered as a Source, then an Activity records the specific run on each shot. The Activity is attached to the equilibrium dataset via `activity_id`.

See [Provenance](../concepts/provenance.md) and [ADR-0025](../adrs/0025-prov-o-agent-activity-separation.md).

### 3.3 Semantic metadata (JSON-LD)

Requesting the equilibrium dataset with `Accept: application/ld+json` returns a `dcat:Dataset` document with a nested `dcat:Distribution` and embedded `prov:wasGeneratedBy` triples.

See [Semantic Metadata](../concepts/dcat-jsonld.md) and [ADR-0009](../adrs/0009-content-negotiation-for-dcat.md).

### 3b. MAST-Upgrade synthetic datasets

50 public and 10 restricted synthetic datasets are registered under MAST-Upgrade shot 50000 to demonstrate the access control and credential vending features.

---

## 4. Collections — JINTRAC integrated modelling

A synthetic JINTRAC run on MAST shot 30420 demonstrates the full provenance + collection workflow:

1. **Source** registered: `jintrac`
2. **Activity** created with timestamps, version (`v220922`), and parameters
3. **`prov:used`** inputs recorded: equilibrium, magnetics, thomson_scattering
4. **Output datasets** registered (`core_profiles`, `core_sources`, `equilibrium` at level 3), each linked to the Activity via `activity_id`
5. **Collection** `jintrac-v220922` created, grouping all outputs — citable as a unit

### 4a & 4b — Inspecting the collection

```python
GET /api/v1/devices/mast/shots/30420/collections/jintrac-v220922
# standard JSON: datasets inlined

GET /api/v1/devices/mast/shots/30420/collections/jintrac-v220922
Accept: application/ld+json
# dcat:Catalog with dcat:dataset references and prov:wasGeneratedBy
```

---

## 5. Attempting unauthorised access

FDS is a metadata catalog — it does not manage bucket policies. The demo shows what happens when a client tries to open a `restricted` dataset directly with xarray, without credentials:

```python
xr.open_dataset("s3://fds-data/shots/50000/restricted/data_00", engine="zarr",
                storage_options={"client_kwargs": {"endpoint_url": MINIO_URL}})
# → raises an exception (anonymous access denied by MinIO)
```

See [Access Control](../concepts/access-control.md#what-fds-does-not-do).

---

## 6. Secure consumption with `include_storage_options`

FDS vends short-lived STS tokens at query time. The client requests a dataset with `include_storage_options=true` and uses the embedded `storage_options` dict directly:

```python
ds_meta = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets/restricted_00",
    params={"include_storage_options": True},
    headers=headers,
).json()[0]

xr.open_dataset(ds_meta["url"], engine="zarr", storage_options=ds_meta["storage_options"])
```

No long-lived keys are handled by the client. See [Access Control → Credential vending](../concepts/access-control.md#credential-vending-sts-token-pattern).

---

## 7. Single dataset access — real MAST data

Demonstrates opening real IMAS Zarr data (MAST equilibrium, shot 30421) via FDS-vended credentials:

```python
eq = httpx.get(
    f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
    params={"include_storage_options": True},
).json()[0]

xr.open_dataset(eq["url"], engine="zarr", storage_options=eq["storage_options"])
```

---

## 8. Parallel reads from the IceChunk collection (Dask)

Each IDS group in the shared IceChunk store for MAST-Upgrade shot 50000 is read by a separate Dask worker. This demonstrates that multiple readers can open the same IceChunk repository concurrently without coordination.

The `analysed` collection is fetched to get the IceChunk `root_url`, then all analysed datasets are fetched in one request (with `include_storage_options=true`) so FDS resolves and vends the credentials server-side. Each `application/vnd.icechunk+zarr` dataset is dispatched as a future to a 4-worker `LocalCluster`:

```python
# 1. Fetch the collection to get the IceChunk root_url
collection = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/collections/analysed"
).json()
root_url = collection["root_url"]

# 2. Fetch all analysed datasets (public — no auth header needed)
all_datasets = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets",
    params={"include_storage_options": "true"},
).json()
icechunk_datasets = [
    d for d in all_datasets
    if d.get("media_type") == "application/vnd.icechunk+zarr"
]

# 3. Worker: open the IceChunk store and read one IDS group.
def read_group_mean(root_url, group_name, storage_options):
    from urllib.parse import urlparse

    import numpy as np
    import zarr
    from icechunk import Repository, s3_storage

    parsed = urlparse(root_url)
    opts = {k: v for k, v in (storage_options or {}).items() if v is not None}
    storage = s3_storage(bucket=parsed.netloc, prefix=parsed.path.strip("/"), **opts)
    repo = Repository.open(storage=storage)
    session = repo.readonly_session(branch="main")
    time_arr = zarr.open_array(store=session.store, path=f"{group_name}/time", mode="r")
    return float(np.mean(np.asarray(time_arr)))

# 4. Dispatch — one future per IDS group across a 4-worker cluster
with LocalCluster(n_workers=4, threads_per_worker=1, dashboard_address=None) as cluster:
    with Client(cluster) as client:
        futures = [
            client.submit(read_group_mean, root_url, d["name"], d.get("storage_options"))
            for d in icechunk_datasets
        ]
        results = client.gather(futures)
```

See [Access Control → Credential vending](../concepts/access-control.md#credential-vending-sts-token-pattern) and [ADR-0029](../adrs/0029-icechunk-collection-model.md).
