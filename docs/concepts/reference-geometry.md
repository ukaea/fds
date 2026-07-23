# Reference Geometry

Diagnostics measure *quantities*, but analysis of those measurements often benefits from knowing *where* it was taken: bolometer chord endpoints, magnetic-probe positions, Thomson channel major radii, the wall and divertor contours. `Te[channel, time]` can be more useful when each `channel` is linked to its `R, Z` position.

This geometry is **`Device`-level data** — identical across many shots, and only occasionally re-versioned when hardware moves or is re-surveyed. FDS does not store the geometry arrays themselves, the same way it does not store the measurement data; it models the **relationship**: how a signal declares the geometry it needs, and how the correct *version* is resolved for a given shot.

## Versions and roles

A **geometry version** is an ordinary `Device`-level `Dataset` (no `shot_id`) that provides one or more **roles** and declares which shots it covers:

| Field | Description |
| --- | --- |
| `geometry_roles` | The components this version provides, e.g. `["thomson_positions"]`. A bundled store may provide several. |
| `applies_to` | The shots this version covers — see [Coverage](#coverage). |

A `Dataset` declares the roles it uses — not versions:

| Field | Description |
| --- | --- |
| `geometry_references` | The geometry roles this `Dataset` needs, e.g. `["thomson_positions"]`. |

Because a `Dataset` names *roles*, re-versioning geometry is just adding another `Device`-level dataset — no `Dataset` or `Shot` changes.

## Coverage

`applies_to` covers the union of three selectors:

| Selector | Meaning |
| --- | --- |
| `shots` | Explicit shot ids. |
| `shot_ranges` | `{from_shot, to_shot}`, inclusive; omit `to_shot` for open-ended. |
| `date_ranges` | `{from_date, to_date}`, half-open; omit `to_date` for open-ended. |

Shot-range endpoints are resolved to their `shot_at` at read time, and date ranges are literal, so correcting a shot's timestamp automatically updates coverage.

## Resolution

Reading a `Dataset` with `?include_geometry=true` resolves each of its `geometry_references` to the geometry version whose `applies_to` covers the `Dataset`'s shot, and returns them in a `geometry` list — each an ordinary dataset reference with its own `url` and `storage_options` (vended only when `include_storage_options=true` is also set). Two references landing on one bundled version are de-duplicated.

Resolution is **`Device`-scoped**: only versions belonging to the `Shot`'s own `Device` are candidates.

In JSON-LD (`Accept: application/ld+json`), the `Dataset` links to each resolved version with a `dcat:qualifiedRelation` — a reified `dcat:Relationship` whose `dcat:hadRole` is the FuEL role concept `fuel:geometry`, with the related version under `dct:relation`. That related node exposes its resolved window as `dct:temporal`.

## Invariants

FDS enforces, on write:

- **`Device`-required, `Device`-level.** Geometry can only be hosted or referenced within a `Device`, and a version must be `Device`-level (no `shot_id`) — geometry is one or many `Dataset`s shared across shots.
- **No overlap.** A set of Thomson data for a given shot can't claim a reference to multiple versions of Thomson geometry.
- **Reference integrity.** If you claim a version of your geometry data is valid from shots 20 - 100, `Shot` 100 **must exist** and have a timestamp in the `shot_at` field.
- **Shot protection.** A `Shot` used as an explicit member or a range endpoint cannot be deleted, and a `shot_at` change that would create an overlap or orphan an endpoint is rejected.

## Example: MAST Thomson positions

```text
Device: mast
├── Dataset: thomson_positions_v1   geometry_roles=["thomson_positions"]  applies_to: shots ["30420"]
├── Dataset: thomson_positions_v2   geometry_roles=["thomson_positions"]  applies_to: shot_ranges [{from_shot: "30421"}]
├── Shot 30420
│   └── Dataset: thomson_scattering  geometry_references=["thomson_positions"]
└── Shot 30421
    └── Dataset: thomson_scattering  geometry_references=["thomson_positions"]
```

Resolving `thomson_scattering` for shot 30420 yields **v1**; for shot 30421 (and later), **v2** — the chords were re-surveyed between the two shots.
