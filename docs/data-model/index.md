# Data Model

FDS organises fusion data into a three-level hierarchy, with **Collections** as a first-class grouping mechanism at any level.

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

## Scientific metadata

The `scientific_metadata` field on Shot and Dataset holds a structured list of experimental conditions. Each entry is a `{name, value, unit, description}` property:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Property identifier (e.g. `plasma_current`) |
| `value` | any | Yes | Any JSON-compatible type: number, string, boolean, or list |
| `unit` | string | No | Unit for physical quantities (e.g. `MA`, `T`) |
| `description` | string | No | Free-text explanation |

```json
"scientific_metadata": [
  {"name": "plasma_current", "value": 0.8, "unit": "MA"},
  {"name": "toroidal_field", "value": -0.5, "unit": "T"},
  {"name": "confinement_mode", "value": "H-mode"},
  {"name": "heating_schemes", "value": ["NBI", "ECRH"]},
  {"name": "disrupted", "value": false}
]
```

In JSON-LD, these are mapped to `schema:additionalProperty` / `schema:PropertyValue` nodes, making them indexable by Google Dataset Search. See [Semantic Metadata](../dcat-jsonld.md).

## URL structure

```text
GET /api/v1/devices/{device}/shots/{shot_id}/datasets/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/collections/{name}
GET /api/v1/devices/{device}/shots/{shot_id}/datasets          # list, one shot
GET /api/v1/devices/{device}/datasets                          # list, whole device
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
    ├── Dataset: equilibrium    (EFIT reconstruction)
    ├── Dataset: magnetics      (calibrated IDS)
    ├── Dataset: thomson_scattering
    ├── … (10 more IDS datasets)
    └── Collection: experiment-data
        └── (all 13 IDS datasets above)
```
