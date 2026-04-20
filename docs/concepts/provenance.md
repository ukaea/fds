# Provenance

FDS tracks provenance using the **PROV-O ontology**, making the origin of every dataset auditable and reproducible. The model is defined in [ADR-0025](../adrs/0025-prov-o-agent-activity-separation.md) (superseding [ADR-0004](../adrs/0004-prov-o-activity-mapping-for-provenance.md)).

## Core concepts

FDS maps cleanly onto three PROV-O primitives:

| PROV-O term | FDS entity | Description |
|---|---|---|
| `prov:Agent` / `prov:SoftwareAgent` | **Source** | The system or code that *can* produce data (e.g. EFIT, JINTRAC, an intershot scheduler) |
| `prov:Activity` | **Activity** | A *specific execution* of a Source — with timestamps, version, and parameters |
| `prov:Entity` | **Dataset** / **Collection** | The data produced |

### Source (`prov:Agent`)

A Source is a global, reusable entity. It represents a diagnostic system, analysis code, or automated process — not a specific run.

```json
{
  "name": "efit",
  "description": "EFIT equilibrium reconstruction code"
}
```

### Activity (`prov:Activity`)

An Activity records a *specific execution* of a Source. It is a first-class table — not a join row — and carries:

- Which Source ran (`source_id`)
- The version used (`source_version`)
- Run parameters (`parameters` — arbitrary JSON)
- Start and end timestamps

```json
{
  "source_id": "...",
  "source_version": "efit-v2.8",
  "activity_type": "ANALYSIS",
  "parameters": {"run_id": "30421-efit-standard"},
  "started_at": "2024-01-15T10:00:00",
  "ended_at": "2024-01-15T10:12:34"
}
```

`activity_type` is one of `ACQUISITION`, `ANALYSIS`, or `SIMULATION`.

## Relationships

```
Dataset  ──prov:wasGeneratedBy──►  Activity  ──prov:wasAssociatedWith──►  Source
                                       │
                                  prov:used
                                       │
                                       ▼
                                   Dataset (input)
```

- A **Dataset** carries a FK `activity_id` → the Activity that produced it.
- An **Activity** carries a FK `source_id` → the Source (agent) that ran.
- The `ActivityInput` join records which Datasets an Activity *consumed* as inputs (`prov:used`).
- A **Collection** also carries `activity_id`, so a set of outputs from a single run can be cited as a unit.

## Example: JINTRAC simulation

```
Source: jintrac  (PROV-O: prov:SoftwareAgent)

Activity: 30420-jintrac-v220922
  source:    jintrac  v220922
  type:      SIMULATION
  started:   2024-03-10T14:00:00
  ended:     2024-03-10T16:47:22
  inputs:    equilibrium, magnetics, thomson_scattering  (prov:used)

Outputs (prov:wasGeneratedBy → the Activity above):
  Dataset: equilibrium   (level=3, s3://…/jintrac/equilibrium.nc)
  Dataset: core_profiles (level=3, s3://…/jintrac/core_profiles.nc)
  Dataset: core_sources  (level=3, s3://…/jintrac/core_sources.nc)

Collection: jintrac-v220922
  activity_id → same Activity
  members:    the three datasets above
```

## Querying provenance

The standard JSON response includes `activity_id` on each Dataset. To get the full PROV-O graph as linked data, request `application/ld+json` — see [Semantic Metadata](dcat-jsonld.md).

```http
GET /api/v1/datasets/id/{uuid}
Accept: application/ld+json
```

The response contains `prov:wasGeneratedBy`, `prov:wasAssociatedWith`, and input dataset references as proper PROV-O triples.
