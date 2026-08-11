# Provenance

FDS tracks provenance using the **PROV-O ontology**, making the origin of every dataset auditable and reproducible.

## Core concepts

FDS maps cleanly onto three PROV-O primitives:

| PROV-O term | FDS entity | Description |
| --- | --- | --- |
| `prov:Agent` / `prov:SoftwareAgent` | **Source** | The system or code that *can* produce data (e.g. EFIT, JINTRAC, some diagnostic system) |
| `prov:Activity` | **Activity** | A *specific execution* of a Source — with timestamps, version, and parameters |
| `prov:Entity` | **Dataset** / **Collection** | The data produced |

### Source (`prov:Agent`)

A Source is a global, reusable entity. It represents a diagnostic system, analysis code, or automated process — not a specific run.

Register one with a `POST /sources/` — see [Data Model → Source](data-model/source.md) for the fields and a worked example.

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
  "activity_type": "analysis",
  "parameters": {"run_id": "30421-efit-standard"},
  "started_at": "2024-01-15T10:00:00",
  "ended_at": "2024-01-15T10:12:34"
}
```

`activity_type` is one of `measurement`, `simulation`, `analysis`, or `calibration`.

Register one with a `POST /activities/`, referencing the Source it executed — see
[Data Model → Activity](data-model/activity.md) for the full field list and a worked example.

## Relationships

```
Dataset  ──prov:wasGeneratedBy──►  Activity  ──prov:wasAssociatedWith──►  Source
                                       │
                                  prov:used
                                       │
                                       ▼
                                   Dataset (input)
```

- Each **Dataset** records the Activity that produced it (`prov:wasGeneratedBy`).
- Each **Activity** records the Source that ran it (`prov:wasAssociatedWith`).
- An Activity also records the Datasets it *consumed* as inputs (`prov:used`).
- A **Collection** can record a producing Activity too, so the whole output of a single run can be cited as one unit.

Outputs are linked by setting `activity_id` when the Dataset is registered (see
[Data Model → Dataset](data-model/dataset.md)). Inputs are recorded separately — a bodyless
`POST` per consumed Dataset:

=== "curl"

    ```bash
    curl -X POST "$API/activities/$ACTIVITY_ID/inputs/$DATASET_ID" \
      -H "Authorization: Bearer $TOKEN"
    ```

=== "Python (requests)"

    ```python
    requests.post(f"{API}/activities/{activity['id']}/inputs/{dataset_id}", headers=headers)
    ```

=== "Python (httpx)"

    ```python
    httpx.post(f"{API}/activities/{activity['id']}/inputs/{dataset_id}", headers=headers)
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/activities/${activity.id}/inputs/${datasetId}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
    ```

## Example: JINTRAC simulation

```
Source: jintrac  (PROV-O: prov:SoftwareAgent)

Activity: 30420-jintrac-v220922
  source:    jintrac  v220922
  type:      simulation
  started:   2024-03-10T14:00:00
  ended:     2024-03-10T16:47:22
  inputs:    equilibrium, magnetics, thomson_scattering  (prov:used)

Outputs (prov:wasGeneratedBy → the Activity above):
  Dataset: equilibrium   (s3://…/jintrac/equilibrium.nc)
  Dataset: core_profiles (s3://…/jintrac/core_profiles.nc)
  Dataset: core_sources  (s3://…/jintrac/core_sources.nc)

Collection: jintrac-v220922
  activity_id → same Activity
  members:    the three datasets above
```

## Querying provenance

A dataset's standard JSON already carries `activity_id`; the full PROV-O graph (`prov:wasGeneratedBy`, `prov:wasAssociatedWith`, and the inputs it used) is returned as linked data via content negotiation — see [Semantic Metadata → Provenance graph](dcat-jsonld.md#provenance-graph).
