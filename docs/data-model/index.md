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

The `scientific_metadata` field on Shot, Dataset and Collection holds a structured list of experimental conditions. Each entry is a `{name, value, unit, description}` property:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Property identifier (e.g. `plasma_current`) |
| `value` | any | Yes | Any JSON-compatible type: number, string, boolean, or list |
| `unit` | string | No | Unit for physical quantities (e.g. `MA`, `T`) |
| `description` | string | No | Free-text explanation |
| `extent` | object | No | Optional 1D range that localises the property on one named axis, making it a *feature* (see below) |

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

### Feature annotation

A property may carry an optional `extent`: a 1D range on one named axis of the data, making it a *feature*. Time is the common case (an H-mode window, a disruption), but the axis can be any dimension the store has, such as frequency for an MHD mode. A property with no `extent` is a plain scalar property.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `dimension` | string | Yes | The axis the range is on (e.g. `time`, `frequency`, `x`); free text, not validated against the store |
| `start` | number | Yes | Coordinate on that axis, in the axis's own frame (may be negative) |
| `end` | number | No | Range end; omit for a point (a single instant or slice) |
| `unit` | string | No | Unit of `start`/`end` on that axis (e.g. `s`, `Hz`) |

```json
"scientific_metadata": [
  {"name": "confinement_mode", "value": "H-mode", "extent": {"dimension": "time", "start": 1.0, "end": 2.0}},
  {"name": "disruption", "value": true, "extent": {"dimension": "time", "start": 3.4}},
  {"name": "mode", "value": "n=1 tearing", "extent": {"dimension": "frequency", "start": 8000, "end": 12000, "unit": "Hz"}}
]
```

`start`/`end` are coordinates on the named axis, in that axis's own frame, so a consumer overlays them directly on the axis it plots the signal against. Time is not privileged: aligning a shot-level `time` extent to a particular diagnostic's axis is the consumer's job and is not guaranteed, since processing may put that diagnostic on a different base. A Shot can declare `t0_at`, the wall-clock instant of its relative `t=0`, so a provider can communicate the offset from `shot_at`; FDS stores it but never uses it to convert event times or to assume two datasets share a time base.

Only 1D localisation can be stored in the metadata. Multi-dimensional regions (a mask, a 2D shape) and dense series (every ELM in a shot) are referenced as [feature annotations](reference-datasets.md#feature-annotations).

A `time` extent projects to a [W3C Time](https://www.w3.org/TR/owl-time/) `time:Interval` in JSON-LD; an extent on any other axis projects to a numeric range.

### Finding annotated records

Shot, Dataset and Collection list endpoints accept an `annotation` parameter that filters on `scientific_metadata`, in one of two forms:

| Form | Meaning | Example |
| --- | --- | --- |
| `name` | The property is present, whatever its value | `?annotation=disruption` |
| `name:value` | The property is present with this value | `?annotation=confinement_mode:H-mode` |

```text
GET /api/v1/devices/mast/shots?annotation=disruption
GET /api/v1/devices/mast/shots?annotation=confinement_mode:H-mode
```

Repeat the parameter to require several annotations at once. They combine with AND, so this returns only shots carrying both:

```text
GET /api/v1/devices/mast/shots?annotation=disruption&annotation=elm
```

Only the first `:` separates name from value, so a value may itself contain one (`?annotation=mode:n=1:tearing` looks for the value `n=1:tearing`). A trailing separator with no value is rejected: omit it to filter on presence alone.

Values are compared against the text you supply or its natural type, so `?annotation=disruption:true` matches a stored boolean `true` as well as the string `"true"`.

Dataset lists additionally accept `name`, plus `shot_annotation`, which filters on an annotation carried by the dataset's *parent shot* rather than the dataset itself. That answers questions spanning both levels in one request:

```text
GET /api/v1/devices/mastu/datasets?name=equilibrium&shot_annotation=elm
```

Datasets that belong to no shot never match a `shot_annotation` filter. Annotation names are not validated, so a name that nothing uses returns an empty list rather than an error.

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
