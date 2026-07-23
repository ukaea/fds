# Reference Calibration

Diagnostics record *raw* measurements; turning those into physical units means applying **calibration** — coefficient and gain tables that are `Device`-level reference data shared across many shots and re-versioned when an instrument is recalibrated. FDS does not store the coefficient arrays; it models the **relationship**: how a signal declares the calibration it needs, and how the correct *version* is resolved for a given shot.

## Two ways calibration is represented in FDS

- **Referenced** — the producer stores *raw* data and expects consumers to apply coefficients on read. A `Dataset` names calibration *roles*, resolved per shot.
- **Applied** — the producer stores an already-calibrated product. There the coefficient dataset is simply a `prov:used` input to a calibration `Activity` (see [provenance](provenance.md)).

## Versions, roles, and stages

A **calibration version** is a `Device`-level `Dataset` (no `shot_id`) that provides one or more roles, its position in a chain of calibration steps, and declares which shots it covers:

| Field | Description |
| --- | --- |
| `calibration_roles` | The components this version provides, e.g. `["thomson_calibration"]`. |
| `calibration_stage` | Integer position in the chain; lower applies first (gain → wavelength → absolute). `None` for single-stage calibration. |
| `applies_to` | The shots this version covers — same [coverage](reference-geometry.md#coverage) as geometry. |

A `Dataset` declares the roles it uses:

| Field | Description |
| --- | --- |
| `calibration_references` | The calibration roles this `Dataset` needs, e.g. `["thomson_calibration"]`. |

## Chains and resolution

Calibration can resolve to an **ordered chain** rather than a single version, because turning raw counts into physical units may take several steps in a fixed order (e.g. gain, then absolute). Each step is a **stage**, and non-overlap holds **per `(role, stage)`**: within one stage a shot still resolves to exactly one version, but different stages of the same role are *meant* to cover the same shot — that ordered set of stages is the chain.

Reading a `Dataset` with `?include_calibration=true` resolves each `calibration_reference` to the versions covering the shot, sorted by ascending `stage`, and returns them in a `calibration` list. As with geometry, resolution is `Device`-scoped and `storage_options` are vended only when `include_storage_options=true`.

In JSON-LD (`Accept: application/ld+json`), each resolved version is a `dcat:qualifiedRelation` carrying the `fuel:calibration` role — distinct from geometry's edge so a consumer can tell "apply this geometry" from "apply these coefficients" (see ADR-0038, ADR-0039).

## Calibrated geometry

Because the kinds are separate fields on the same `Dataset`, a geometry *version* may itself carry `calibration_references`. Resolution is recursive and anchored to the original `Shot`: resolving a `Dataset` at `Shot` 'S' yields its geometry version, whose own calibration then resolves at that same 'S'.

## Invariants

FDS enforces these on write:

- **`Device`-required, `Device`-level.** Calibration can only be hosted or referenced within a `Device`, and a version must be `Device`-level (no `shot_id`) — it is bulk reference data shared across shots.
- **No overlap per `(role, stage)`.** For a given role and stage, at most one version may cover any shot; different stages of a role may cover the same shot — that ordering is the chain.
- **Reference integrity.** A `Shot` named as a range endpoint must exist and carry a `shot_at`.
- **Shot protection.** A `Shot` used as an explicit member or a range endpoint cannot be deleted, and a `shot_at` change that would create an overlap or orphan an endpoint is rejected.

## Example: a staged Thomson calibration

```text
Device: mast
├── Dataset: thomson_gain       calibration_roles=["thomson_calibration"]  calibration_stage=1  applies_to: shots ["30420","30421"]
├── Dataset: thomson_absolute   calibration_roles=["thomson_calibration"]  calibration_stage=2  applies_to: shots ["30420","30421"]
└── Shot 30420
    └── Dataset: thomson_scattering  calibration_references=["thomson_calibration"]
```

Resolving `thomson_scattering` with `?include_calibration=true` yields the chain **`[thomson_gain, thomson_absolute]`** — gain first (stage 1), then absolute (stage 2).
