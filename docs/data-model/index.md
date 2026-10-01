# Data Model

FDS organises fusion data into a three-level hierarchy, with **Collections** as a first-class grouping mechanism at any level.

## Hierarchy

```text
Global
├── Dataset
├── Collection: (Dataset, Dataset, …)
└── Device  (e.g. MAST, MAST-Upgrade, JET)
    ├── Dataset
    ├── Collection: (Dataset, Dataset, …)
    └── Shot  (a single plasma discharge)
        ├── Dataset
        └── Collection: (Dataset, Dataset, …)
                      └── Collection: (Dataset, Dataset, …)
```

Datasets and Collections can exist at any scope level: Global, Device, or Shot. A Collection can contain other Collections as well as Datasets.

## Scientific metadata

The `scientific_metadata` field on Shot, Dataset and Collection holds a structured list of experimental conditions. Each entry is a `{name, value, unit, description}` property:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Property identifier (e.g. `plasma_current`) |
| `value` | any | Yes | Any JSON-compatible type: number, string, boolean, or list |
| `unit` | string | No | Unit for physical quantities (e.g. `MA`, `T`) |
| `description` | string | No | Free-text explanation |
| `extent` | object | No | Optional 1D range that localises the property on one named axis, making it an *annotation* (see below) |

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

### Annotations

A property may carry an optional `extent`: a 1D range on one named axis of the data, making it an *annotation*. Time is the common case (an H-mode window, a disruption), but the axis can be any dimension the store has, such as frequency for an MHD mode. A property with no `extent` is a plain scalar property.

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

Only 1D localisation can be stored in the metadata. Multi-dimensional regions (a mask, a 2D shape) and dense series (every ELM in a shot) are referenced as [annotation datasets](reference-datasets.md#annotation-datasets).

A `time` extent projects to a [W3C Time](https://www.w3.org/TR/owl-time/) `time:Interval` in JSON-LD; an extent on any other axis projects to a numeric range.

### Finding annotated records

Shot, Dataset and Collection list endpoints accept a `property` parameter that filters on `scientific_metadata`, in one of two forms:

| Form | Meaning | Example |
| --- | --- | --- |
| `name` | The property is present, whatever its value | `?property=disruption` |
| `name:value` | The property is present with this value | `?property=confinement_mode:H-mode` |

```text
GET /v1/devices/mast/shots?property=disruption
GET /v1/devices/mast/shots?property=confinement_mode:H-mode
```

Repeat the parameter to give more than one. Whether that broadens or narrows the result depends on whether you repeat the same property:

- **The same property with different values matches a shot with any of them.**
- **Different properties must all match.**

```text
GET /v1/devices/mast/shots?property=heating:SS Beam&property=heating:SW Beam
```

Shots heated by either beam, because both values are `heating`.

```text
GET /v1/devices/mast/shots?property=disruption&property=elm
```

Only shots that had both, because `disruption` and `elm` are different properties.

The two combine, so this asks for shots on either beam that also had a disruption:

```text
GET /v1/devices/mast/shots?property=heating:SS Beam&property=heating:SW Beam&property=disruption
```

This is what ticking two values in one filter and one in another means.

Requiring *several values of one property at once*, such as a shot that was in L-mode and later in H-mode, is a different question. It needs nesting that a query string cannot express.

Only the first `:` separates name from value, so a value may itself contain one (`?property=mode:n=1:tearing` looks for the value `n=1:tearing`). A trailing separator with no value is rejected: omit it to filter on presence alone.

Values are compared against the text you supply or its natural type, so `?property=disruption:true` matches a stored boolean `true` as well as the string `"true"`.

`property_min` and `property_max` bound a numeric value:

```text
GET /v1/devices/mast/shots?property_min=plasma_current_max:700000
GET /v1/devices/mast/shots?property_min=plasma_current_max:700000&property_max=plasma_current_max:900000
```

Bounds combine with AND and with any `property` filter. A record whose value for that name is not a number is skipped rather than matched.

Dataset lists additionally accept `name`, plus `shot_property`, which filters on an annotation carried by the dataset's *parent shot* rather than the dataset itself. That answers questions spanning both levels in one request:

```text
GET /v1/devices/mastu/datasets?name=equilibrium&shot_property=elm
```

Datasets that belong to no shot never match a `shot_property` filter. Annotation names are not validated, so a name that nothing uses returns an empty list rather than an error.

### Discovering what to filter on

Annotation names are an open vocabulary, so a device's shots tell you what they can be filtered by:

```text
GET /v1/devices/mast/shots/properties
```

```json
{
  "total": 5300,
  "annotations": [
    {"name": "flat_top", "records": 5300, "distinct": 1, "values": ["true"]},
    {"name": "campaign", "records": 5300, "distinct": 6, "values": ["M5", "M6", "M7", "M8", "M9", "M9a"]},
    {"name": "plasma_current_max", "records": 5300, "distinct": 5267, "unit": "A"}
  ]
}
```

Each entry gives the number of shots carrying that name, the number of distinct values it takes, and its **kind**:

| kind | what it is | how to filter it |
| --- | --- | --- |
| `term` | a value drawn from a vocabulary | equality, with `property` |
| `quantity` | a magnitude on a scale | range, with `property_min` / `property_max` |
| `text` | prose written for a human | not filterable; never listed |

A producer sets `kind` on the property to say what a value is. When they have not, FDS infers it from the values in scope: a handful of repeated values is a term whether or not those values are numbers, a number that differs on nearly every record is a quantity, and text that is near-unique per record is prose. [Scientific Metadata](scientific-metadata.md) covers what to declare and how each kind is presented.

A `term`'s values appear only when there are at most `max_values` of them, 20 by default and at most 200. Above that, fetch them a page at a time:

```text
GET /v1/devices/mast/shots/properties/objective/values?q=conditioning
```

That returns each matching value with the number of shots carrying it, most common first. `unit` appears only when every record agrees on one, and `min`/`max` are set for quantities. A property carrying an extent also reports the `dimension` it is localised on, which makes it an annotation: a claim about a region of the data rather than about the shot as a whole.

`total` counts the shots you may read, and the endpoint accepts the same `property` parameter as the listing, so a filtered scope can be counted exactly:

```text
GET /v1/devices/mast/shots/properties?property=campaign:M9
```

Values a caller is not permitted to read never appear, so two callers can see different properties over the same device.

## URL structure

```text
GET /v1/devices/{device}/shots/{shot_id}/datasets/{name}
GET /v1/devices/{device}/shots/{shot_id}/collections/{name}
GET /v1/devices/{device}/shots/{shot_id}/datasets          # list, one shot
GET /v1/devices/{device}/datasets                          # list, whole device
GET /v1/datasets/id/{id}                                   # stable ID-based lookup
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
