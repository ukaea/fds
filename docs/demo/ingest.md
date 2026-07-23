# Demo — Registering Data

The `demo/ingest.py` notebook walks through all the ways to register data in FDS.
Run it interactively with:

```bash
uvx marimo edit demo/ingest.py --sandbox
```

Or seed a running demo instance non-interactively:

```bash
uv run demo/seed_metadata.py
```

The docker-compose `metadata-seeder` service can run `seed_metadata.py` for you on startup — it is opt-in via the `seed` profile (`podman compose --profile seed up`). A plain `up` leaves FDS empty so you can populate it live with this notebook.

---

## 2. Authentication

FDS delegates identity to Keycloak. The notebook obtains a JWT using the OIDC Resource Owner Password flow:

```python
token = httpx.post(KEYCLOAK_URL, data={
    "client_id": "fds-client",
    "client_secret": "fds-client-secret",
    "username": "admin",
    "password": "password",
    "grant_type": "password",
    "scope": "openid profile fds-admin",
}).json()["access_token"]
```

See [Access Control → Authentication](../concepts/access-control.md#authentication) and [ADR-0007](../adrs/0007-externalized-identity-and-trust-registry.md).

---

## 2b. Devices and Shots

Before datasets can be registered, their parent **Device** and **Shot** contexts must exist.
The demo registers:

- **MAST** with shots **30420** and **30421** (real IMAS-structured Zarr data from STFC)
- **MAST-Upgrade** with shot **50000** (synthetic data for access-restriction demos)

See [Data Model](../concepts/data-model.md).

---

## 3. MAST Datasets

Real IMAS-structured Zarr data from two MAST shots is pre-loaded in MinIO by the `data-generator`
service. Each IDS group is registered as a separate `application/x-zarr` dataset:

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

### 3.1 Experiment Data Collections

All IDS datasets for each shot are grouped into an **Experiment Data** collection linked to
a `measurement` activity from the **Intershot Scheduler** source. This records that the data
was automatically collected between shots.

**Pattern:** `Source → Activity → Collection`

See [Data Model → Collection](../concepts/data-model.md#collection) and [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md).

### 3.2 EFIT Provenance

The **EFIT** equilibrium reconstruction code is registered as a Source, then an Activity records
the specific run parameters and timestamps for each shot. The activity is attached to the
equilibrium dataset via `activity_id` (`prov:wasGeneratedBy`).

See [Provenance](../concepts/provenance.md) and [ADR-0025](../adrs/0025-prov-o-agent-activity-separation.md).

### 3.3 Reference Geometry

Two device-level **Thomson chord position** geometry versions are registered on `mast`, both providing the role `thomson_positions`: `v1` covers shot `30420`, and `v2` (re-surveyed positions) covers shot `30421` onward. Each shot's `thomson_scattering` dataset references the role via `geometry_references`, so reads resolve to the version valid for that shot. Shot-range coverage (`from_shot: 30421`) is evaluated against `shot_at`, so shots must be registered with a timestamp.

```python
POST /api/v1/devices/mast/datasets
{
  "name": "thomson_positions_v2",
  "level": 0,
  "geometry_roles": ["thomson_positions"],
  "applies_to": {"shot_ranges": [{"from_shot": "30421"}]},
  "url": "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
  "media_type": "application/x-netcdf",
  "access_level": "public"
}
```

See [Reference Geometry](../concepts/reference-geometry.md). Resolving the reference on read is shown in [Explore](explore.md).

### 3b. MAST-U Shot 50000

Shot 50000 demonstrates two access tiers and the IceChunk collection model ([ADR-0029](../adrs/0029-icechunk-collection-model.md)):

**raw-diagnostics** (restricted):

- 3 NetCDF files: thomson-raw, charge-exchange-raw, magnetics-raw
- Access level: `restricted` — requires authenticated token + FDS STS credential vending

**analysed** (public, IceChunk):

- 9 IDS datasets as groups in a single IceChunk repository
- Shared `root_url: s3://fds-data/shots/50000/analysed/`
- Access level: `public`

---

## 4. JINTRAC Integrated Modelling

A JINTRAC transport simulation run on MAST shot 30420 demonstrates the full provenance cycle:

1. **Source** — `jintrac` (the simulation code, registered once globally)
2. **Activity** — this specific run (version `v220922`, timestamps, parameters)
3. **`prov:used`** — input datasets recorded: equilibrium, magnetics, thomson_scattering
4. **Output datasets** — `core_profiles`, `core_sources`, `equilibrium` (level 3), each with `activity_id`
5. **Collection** — `jintrac-v220922` groups all outputs as a citable unit

See [Provenance](../concepts/provenance.md), [ADR-0025](../adrs/0025-prov-o-agent-activity-separation.md),
and [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md).

---

After populating data, continue with [Explore](explore.md) to see how clients read it back.
