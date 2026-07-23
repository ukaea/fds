# Data Model

FDS organises fusion data into a three-level hierarchy, with **Collections** as a first-class grouping mechanism at any level. See [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md) for the full rationale.

## Hierarchy

```text
Global
├── Dataset
├── Collection — (Dataset, Dataset, …)
└── Device  (e.g. MAST, MAST-Upgrade, JET)
    ├── Dataset
    ├── Collection — (Dataset, Dataset, …)
    └── Shot  (a single plasma discharge)
        ├── Dataset
        └── Collection — (Dataset, Dataset, …)
                      └── Collection — (Dataset, Dataset, …)
```

Datasets and Collections can exist at any scope level — Global, Device, or Shot. A Collection can contain other Collections as well as Datasets.

## Core entities

### Device

Represents a physical machine or facility.

| Field | Description |
| --- | --- |
| `name` | Unique slug (e.g. `mast`, `mast-upgrade`) |
| `title` | Human-readable label |
| `description` | Extended description |
| `type` | Machine type (`tokamak`, `stellarator`, …) |
| `publisher` | Institution making the device catalog available (`dct:publisher`) |
| `creator` | Person or team responsible for the device (`dct:creator`) |
| `access_level` | Default access level inherited by Shots and Datasets |

### Shot

A single plasma discharge on a Device. This is the primary discovery entity in a fusion catalogue.

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Shot number (e.g. `30421`) |
| `device_name` | string | Parent device |
| `shot_at` | datetime | When the plasma discharge began — distinct from `created_at` (the catalogue record timestamp) |
| `shot_end` | datetime | When the discharge ended (optional) |
| `shot_duration` | float | Discharge duration in seconds (optional); must equal `shot_end − shot_at` when both are set |
| `description` | string | Extended description |
| `publisher` | string | Institution making the data available (`dct:publisher`) |
| `creator` | string | Person or team who conducted the experiment (`dct:creator`) |
| `access_level` | enum | `public`, `embargoed`, or `restricted`; overrides device default if set |
| `required_scopes` | list[string] | OAuth scopes required when access is `restricted` |
| `allowed_idps` | list[string] | Trusted identity-provider issuers; inherits from device if null |
| `scientific_metadata` | list | Experimental conditions — see [Scientific metadata](#scientific-metadata) below |

A Shot has no stored `title`; its JSON-LD representation synthesises one as `Shot {id}`.

### Dataset

The core discovery object. A **Dataset** is the abstract metadata entity describing *what* the data is. A **Distribution** is a concrete physical access path describing *how* to retrieve it. A Dataset can exist without any distributions (metadata-only registration) and distributions can be added later via `POST /datasets/{id}/distributions`.

| Field | Description |
| --- | --- |
| `name` | Slug within its scope (e.g. `equilibrium`) |
| `url` | Physical location (`s3://`, `gs://`, `az://`) — from the primary Distribution, absent if none exists yet |
| `media_type` | MIME type of the primary distribution (e.g. `application/x-zarr`) |
| `format` | Optional format label (e.g. `NetCDF4`) |
| `level` | Numeric processing level: `0` = raw, `1` = calibrated, `2` = processed, `3` = modelled |
| `quality_flag` | Free-form quality annotation (e.g. `good`, `suspect`) — no controlled vocabulary, see [ADR-0030](../adrs/0030-controlled-vocabularies.md) |
| `access_level` | `public`, `embargoed`, or `restricted` |
| `publisher` | Institution making the data available (`dct:publisher`) |
| `creator` | Person or team who produced the dataset (`dct:creator`) |
| `temporal_start` | Start of the measurement window (mapped to `dct:temporal` → `dct:PeriodOfTime`) |
| `temporal_end` | End of the measurement window |
| `scientific_metadata` | Diagnostic-specific parameters — see [Scientific metadata](#scientific-metadata) below |
| `activity_id` | FK to the Activity that produced this dataset (provenance) |

A `Dataset` can also link to **reference geometry** — a `Dataset` declares its related geometry via `geometry_references`, or a `Device`-level `Dataset` *provides* geometry via `geometry_roles` and `applies_to`. See [Reference Geometry](reference-geometry.md).

The same machinery carries **reference calibration**: a `Dataset` names the calibration it needs via `calibration_references`, and a `Device`-level `Dataset` provides it via `calibration_roles`, `calibration_stage`, and `applies_to`. Unlike geometry, calibration can resolve to an ordered chain of stages. See [Reference Calibration](reference-calibration.md).

### Distribution

A Distribution is a physical access path for a Dataset — it describes *how* to retrieve the data.

| Field | Description |
| --- | --- |
| `url` | Download or access URL (e.g. `s3://fds-data/shots/30421/equilibrium`) |
| `media_type` | IANA media type (e.g. `application/x-zarr`, `application/x-hdf5`) |
| `format` | Human-readable format label (e.g. `NetCDF4`, `HDF5`) |
| `endpoint_url` | Storage endpoint, used for credential vending |
| `access_level` | Override access policy for this distribution |

In most cases a Dataset will have exactly one Distribution, and you won't need to think about the distinction. The Dataset endpoints return the primary distribution's `url`, `media_type`, and `format` inlined directly on the Dataset response — there is nothing extra to fetch.

Multiple distributions are supported when the same underlying data is available in more than one form — for example, as both Zarr and HDF5, or through multiple access endpoints. All distributions of a given Dataset must be scientifically interchangeable; different data belongs in a separate Dataset. Additional distributions can be registered via `POST /datasets/{id}/distributions`.

### Collection

A named, citable group of Datasets (maps to `dcat:Catalog`).

| Field | Description |
| --- | --- |
| `name` | Slug within its scope (e.g. `experiment-data`, `jintrac-v220922`) |
| `title` | Human-readable title |
| `access_level` | Effective access level (inherited if not set) |
| `root_url` | Access root for all physical data in this collection (`dcat:accessURL`) |
| `activity_id` | FK to the Activity that produced this collection |

Collections support nesting (a Collection can contain other Collections) and a Dataset can belong to multiple Collections. The Dataset's URI is independent of its collection membership — adding or moving a dataset never changes its URL. See [ADR-0024](../adrs/0024-multi-tier-hierarchy-with-collections.md).

### Activity

Records a computation or measurement event that produced a Dataset or Collection. The primary provenance object (maps to `prov:Activity`).

| Field | Description |
| --- | --- |
| `source_id` | The Source (code or diagnostic) that ran (`prov:wasAssociatedWith`) |
| `source_version` | Version of the source used |
| `activity_type` | Controlled vocabulary: `measurement`, `simulation`, `analysis`, `calibration` |
| `parameters` | Run-specific key-value parameters (opaque provenance bag) |
| `started_at` | When execution began |
| `ended_at` | When execution completed |

See [Provenance](provenance.md) and [ADR-0025](../adrs/0025-prov-o-agent-activity-separation.md).

## Scientific metadata

The `scientific_metadata` field on Shot and Dataset holds a structured list of experimental conditions. Each entry is a `{name, value, unit, description}` property:

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Property identifier (e.g. `plasma_current`) |
| `value` | yes | Any JSON-compatible type: number, string, boolean, or list |
| `unit` | no | Unit for physical quantities (e.g. `MA`, `T`) |
| `description` | no | Optional free-text explanation |

```json
"scientific_metadata": [
  {"name": "plasma_current", "value": 0.8, "unit": "MA"},
  {"name": "toroidal_field", "value": -0.5, "unit": "T"},
  {"name": "confinement_mode", "value": "H-mode"},
  {"name": "heating_schemes", "value": ["NBI", "ECRH"]},
  {"name": "disrupted", "value": false}
]
```

In JSON-LD, these are mapped to `schema:additionalProperty` / `schema:PropertyValue` nodes, making them indexable by Google Dataset Search. See [Semantic Metadata](dcat-jsonld.md) and [ADR-0031](../adrs/0031-scientific-metadata.md).

## URL structure

```text
GET /api/v1/devices/{device}/shots/{shot_id}/datasets/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/collections/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/datasets          # list
GET /api/v1/datasets/id/{id}                                   # stable ID-based lookup
```

Datasets and Collections are siblings at each scope level. A Collection does not appear in a Dataset's path.

## Example: MAST shot 30421

```text
Device: mast
└── Shot: 30421
    │   shot_at: 2008-11-18T14:32:00Z
    │   creator: "MAST Team"
    │   scientific_metadata:
    │     - {name: "plasma_current", value: 0.4, unit: "MA"}
    │     - {name: "confinement_mode", value: "L-mode"}
    ├── Dataset: equilibrium   (level=2, EFIT reconstruction)
    ├── Dataset: magnetics      (level=1, calibrated IDS)
    ├── Dataset: thomson_scattering
    ├── … (10 more IDS datasets)
    └── Collection: experiment-data
        └── (all 13 IDS datasets above)
```
