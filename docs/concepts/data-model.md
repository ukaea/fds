# Data Model

FDS organises fusion data into a three-level hierarchy, with **Collections** as a first-class grouping mechanism at any level. See [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md) for the full rationale.

## Hierarchy

```
Global
└── Device  (e.g. MAST, MAST-Upgrade, JET)
    └── Shot  (a single plasma discharge)
        ├── Dataset     (a single logical dataset)
        └── Collection  (a named group of datasets)
            └── Dataset
```

Datasets and Collections can also exist at **Device** or **Global** scope when they are not tied to a specific shot — for example, a machine geometry file or a community reference dataset.

## Core entities

### Device

Represents a physical machine or facility.

| Field | Description |
|---|---|
| `name` | Unique slug (e.g. `mast`, `mast-upgrade`) |
| `description` | Human-readable label |
| `type` | Machine type (`tokamak`, `stellarator`, …) |
| `access_level` | Default access level inherited by Shots and Datasets |

### Shot

A single plasma discharge on a Device.

| Field | Description |
|---|---|
| `id` | Shot number (e.g. `30421`) |
| `device_name` | Parent device |
| `access_level` | Overrides device default if set |

### Dataset

The core discovery object. A Dataset is a logical metadata container pointing to a physical data store.

| Field | Description |
|---|---|
| `name` | Slug within its scope (e.g. `equilibrium`) |
| `url` | Physical location (`s3://`, `gs://`, `az://`) |
| `media_type` | MIME type (e.g. `application/x-zarr`) |
| `format` | Optional format label (e.g. `NetCDF4`) |
| `level` | Numeric processing level (1 = raw, 2 = processed, 3 = modelled) |
| `access_level` | `public`, `embargoed`, or `restricted` |
| `activity_id` | FK to the Activity that produced this dataset (provenance) |

!!! note "One Dataset, one Distribution"
    FDS follows the DCAT pattern where a **Dataset** is a conceptual entity and a **Distribution** is a physical access path. The API denormalises these into a single object for convenience — `url` and `media_type` are the default distribution inlined. The full DCAT structure (with separate Distribution nodes) is restored when you request `application/ld+json`.

### Collection

A named, citable group of Datasets (maps to `dcat:Catalog`).

| Field | Description |
|---|---|
| `name` | Slug within its scope (e.g. `experiment-data`, `jintrac-v220922`) |
| `title` | Human-readable title |
| `access_level` | Effective access level (inherited if not set) |
| `activity_id` | FK to the Activity that produced this collection |

Collections support nesting (a Collection can contain other Collections) and a Dataset can belong to multiple Collections. The Dataset's URI is independent of its collection membership — adding or moving a dataset never changes its URL. See [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md).

## URL structure

```
GET /api/v1/devices/{device}/shots/{shot_id}/datasets/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/collections/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/datasets          # list
GET /api/v1/datasets/id/{uuid}                                 # stable ID-based lookup
```

Datasets and Collections are siblings at each scope level. A Collection does not appear in a Dataset's path.

## Example: MAST shot 30421

```
Device: mast
└── Shot: 30421
    ├── Dataset: equilibrium   (level=2, EFIT reconstruction)
    ├── Dataset: magnetics      (level=2, raw IDS)
    ├── Dataset: thomson_scattering
    ├── … (10 more IDS datasets)
    └── Collection: experiment-data
        └── (all 13 IDS datasets above)
```
