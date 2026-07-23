# Demo — Reading Data

The `demo/explore.py` notebook demonstrates reading data back from FDS: browsing the catalog,
fetching semantic metadata, access control, credential vending, and high-throughput parallel reads.

**Prerequisite:** data must be registered first. Run [Ingest](ingest.md), or bring the stack up
under the `seed` profile (`podman compose --profile seed up`) to have the `metadata-seeder`
service register it for you.

Run interactively with:

```bash
uvx marimo edit demo/explore.py --sandbox
```

---

## 3. Semantic Metadata (JSON-LD)

Requesting a dataset with `Accept: application/ld+json` returns a `dcat:Dataset` document
with nested `dcat:Distribution` nodes and embedded provenance triples:

```python
GET /api/v1/datasets/id/{eq_id}
Accept: application/ld+json

{
  "@context": {...},
  "@type": "dcat:Dataset",
  "dcat:distribution": [...],
  "prov:wasGeneratedBy": {"@id": "..."}
}
```

See [Semantic Metadata](../concepts/dcat-jsonld.md), [ADR-0009](../adrs/0009-content-negotiation-for-dcat.md),
and [ADR-0019](../adrs/0019-two-tier-schema-driven-semantic-projection.md).

---

## 4. Collection as `dcat:Catalog`

Collections respond to `Accept: application/ld+json` as a `dcat:Catalog`:

```python
GET /api/v1/devices/mast/shots/30420/collections/jintrac-v220922
Accept: application/ld+json

{"@type": "dcat:Catalog", "dcat:dataset": [...]}
```

The JINTRAC collection includes the full provenance graph — `prov:wasGeneratedBy` on each
output dataset points back to the simulation activity.

---

## 5. Attempting Unauthorised Access

FDS is a metadata catalog; access policies are enforced by the object store. Opening a
`restricted` dataset directly without credentials fails at the storage layer:

```python
xr.open_dataset("s3://fds-data/shots/50000/raw/thomson_scattering.nc",
                engine="h5netcdf",
                storage_options={"anon": True, "client_kwargs": {"endpoint_url": MINIO_URL}})
# → PermissionError
```

See [Access Control → What FDS does not do](../concepts/access-control.md#what-fds-does-not-do).

---

## 6. Credential Vending with `include_storage_options`

FDS vends short-lived STS tokens at query time. The client receives `storage_options` embedded
in the dataset response — no long-lived credentials are ever handled by the client:

```python
ds_meta = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets/thomson-raw",
    params={"include_storage_options": True},
    headers=headers,
).json()[0]

xr.open_dataset(ds_meta["url"], engine="h5netcdf", storage_options=ds_meta["storage_options"])
```

See [Access Control → Credential vending](../concepts/access-control.md#credential-vending-sts-token-pattern),
[ADR-0010](../adrs/0010-tiered-data-access-strategy.md), and [ADR-0011](../adrs/0011-credential-manifest-pattern.md).

---

## 7. Real MAST Data

Real IMAS-structured Zarr data (MAST shot 30421, equilibrium) opened via FDS-vended credentials.
Public datasets return anonymous-compatible storage options; no auth token is required:

```python
eq = httpx.get(
    f"{FDS_API_URL}/devices/mast/shots/30421/datasets/equilibrium",
    params={"include_storage_options": True},
).json()[0]

xr.open_dataset(eq["url"], engine="zarr", storage_options=eq["storage_options"])
```

---

## 7b. Resolving Reference Geometry

`thomson_scattering` references the `thomson_positions` role. Reading it with
`?include_geometry=true` resolves the reference to the geometry version valid for each shot —
shot `30420` → `v1`, shot `30421` → `v2` — returned under a `geometry` field. The resolved entry
is an ordinary dataset reference, so it can be opened like any other dataset:

```python
signal = httpx.get(
    f"{FDS_API_URL}/devices/mast/shots/30420/datasets/thomson_scattering",
    params={"include_geometry": True, "include_storage_options": True},
).json()[0]

geom = signal["geometry"][0]  # → thomson_positions_v1 for shot 30420
xr.open_dataset(geom["url"], engine="h5netcdf", storage_options=geom["storage_options"])
```

See [Reference Geometry](../concepts/reference-geometry.md).

---

## 8. Parallel IceChunk Reads (Dask)

Each IDS group in the shared IceChunk store for MAST-Upgrade shot 50000 is read by a separate
Dask worker — multiple readers open the same IceChunk repository concurrently without coordination.
The `analysed` collection is fetched for its `root_url`, then every `application/vnd.icechunk+zarr`
dataset is fetched in one request (with `include_storage_options=true`) so FDS vends the credentials
server-side, and each is dispatched as a future to a 4-worker cluster:

```python
collection = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/collections/analysed"
).json()
root_url = collection["root_url"]

all_datasets = httpx.get(
    f"{FDS_API_URL}/devices/mast-upgrade/shots/50000/datasets",
    params={"include_storage_options": "true"},
).json()
icechunk_datasets = [d for d in all_datasets
                     if d.get("media_type") == "application/vnd.icechunk+zarr"]

with LocalCluster(n_workers=4) as cluster, Client(cluster) as client:
    futures = [client.submit(read_group_mean, root_url, d["name"], d["storage_options"])
               for d in icechunk_datasets]
    results = client.gather(futures)
```

See [Access Control → Credential vending](../concepts/access-control.md#credential-vending-sts-token-pattern)
and [ADR-0029](../adrs/0029-icechunk-collection-model.md).
