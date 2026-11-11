# Activity

Records a computation or measurement event that generated a Dataset or Collection. The primary provenance object (maps to `prov:Activity`).

An Activity is whatever process generated the data. It may be a direct measurement of the plasma, for raw data; a processing chain, or a repass of that chain over Datasets it has processed before; a single run of an analysis script; a simulation run; or a calibration. `activity_type` says which kind it is: `measurement`, `analysis`, `simulation` or `calibration`. Each time a process runs is a separate Activity, so a repass is a new Activity even when it uses the same code at the same version.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_id` | integer | No | The agent that carried the Activity out, its executor |
| `source_version` | string | No | Version of the source used |
| `activity_type` | enum | No | Controlled vocabulary: `measurement`, `simulation`, `analysis`, `calibration` |
| `parameters` | object | No | Key-value parameters of this Activity (opaque provenance bag) |
| `started_at` | datetime | No | When execution began |
| `ended_at` | datetime | No | When execution completed |
| `inputs` | list of integer | No | Ids of the Datasets the Activity consumed |
| `instruments` | list of integer | No | Ids of the `instrument` Sources the Activity used |
| `agents` | list of object | No | Further agents, each `{source_id, role}` |
| `delegations` | list of object | No | Which agent acted on behalf of which |

`source_id` is optional. A raw acquisition may name no agent at all, only the instrument it used.

## Who may read an Activity

An Activity has no access level of its own. Anyone who may read a dataset it generated, or a collection that bundles it, may read the Activity with its instruments, agents and delegations, and is answered 403 otherwise. Only a global admin may read an Activity that has neither yet. An Activity's inputs are listed only as far as the caller may read each one, in its JSON-LD as well as at `GET /v1/activities/{id}/inputs`.

## Agents and their roles

An Activity may involve more than one agent. The executor is `source_id`; `agents` adds others, each with a role saying what it did:

| Role | Meaning |
| --- | --- |
| `executor` | carried the Activity out |
| `orchestrator` | coordinated the Activity without executing it, for example an inter-shot scheduler |

An agent holds one role per Activity, so a source listed in `agents` may not also be the executor, and may not appear twice.

`delegations` records that one agent acted under another's authority for this Activity, for example an analysis code started by a scheduler. Both ends must be agents of the Activity, either the executor or a member of `agents`. This is a statement about responsibility, not data flow, so a scheduler that coordinates work but produces no data stays out of the lineage entirely.

A single request can declare the whole Activity: what it consumed, what it used, who was involved, and who answered to whom.

=== "curl"

    ```bash
    # $SOURCE_ID is the id of a registered Source
    curl -X POST "$API/activities/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"source_id": '"$SOURCE_ID"', "source_version": "efit-v2.8",
           "activity_type": "analysis", "parameters": {"run_id": "30421-efit-standard"},
           "started_at": "2024-01-15T10:00:00", "ended_at": "2024-01-15T10:12:34",
           "inputs": [3, 7], "instruments": [21],
           "agents": [{"source_id": 5, "role": "orchestrator"}],
           "delegations": [{"subordinate_source": '"$SOURCE_ID"',
                            "responsible_source": 5}]}'
    ```

=== "Python (requests)"

    ```python
    activity = requests.post(
        f"{API}/activities/",
        headers=headers,
        json={
            "source_id": source_id,
            "source_version": "efit-v2.8",
            "activity_type": "analysis",
            "parameters": {"run_id": "30421-efit-standard"},
            "started_at": "2024-01-15T10:00:00",
            "ended_at": "2024-01-15T10:12:34",
            "inputs": [3, 7],
            "instruments": [21],
            "agents": [{"source_id": scheduler_id, "role": "orchestrator"}],
            "delegations": [
                {"subordinate_source": source_id, "responsible_source": scheduler_id}
            ],
        },
    ).json()
    ```

=== "Python (httpx)"

    ```python
    activity = httpx.post(
        f"{API}/activities/",
        headers=headers,
        json={
            "source_id": source_id,
            "source_version": "efit-v2.8",
            "activity_type": "analysis",
            "parameters": {"run_id": "30421-efit-standard"},
            "started_at": "2024-01-15T10:00:00",
            "ended_at": "2024-01-15T10:12:34",
            "inputs": [3, 7],
            "instruments": [21],
            "agents": [{"source_id": scheduler_id, "role": "orchestrator"}],
            "delegations": [
                {"subordinate_source": source_id, "responsible_source": scheduler_id}
            ],
        },
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const activity = await (
      await fetch(`${API}/activities/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId,
          source_version: "efit-v2.8",
          activity_type: "analysis",
          parameters: { run_id: "30421-efit-standard" },
          started_at: "2024-01-15T10:00:00",
          ended_at: "2024-01-15T10:12:34",
          inputs: [3, 7],
          instruments: [21],
          agents: [{ source_id: schedulerId, role: "orchestrator" }],
          delegations: [
            { subordinate_source: sourceId, responsible_source: schedulerId },
          ],
        }),
      })
    ).json();
    ```

Each part can also be maintained afterwards, which suits a pipeline that registers an Activity first and resolves its inputs later:

```http
POST   /v1/activities/{id}/inputs/{dataset_id}
POST   /v1/activities/{id}/instruments/{source_id}
POST   /v1/activities/{id}/agents/{source_id}?role=orchestrator
POST   /v1/activities/{id}/delegations/{subordinate_source_id}/{responsible_source_id}
DELETE /v1/activities/{id}/inputs/{dataset_id}
```

`DELETE` works the same way for instruments, agents and delegations. An agent cannot be removed while a delegation still names it; remove the delegation first.

Output Datasets and Collections reference the Activity by setting their `activity_id`, and the listings filter on it:

```text
GET /v1/datasets?activity_id={id}      # the datasets the Activity generated
GET /v1/collections?activity_id={id}   # the Activity's bundle
```

There is no listing of activities: find an Activity through its bundle or its outputs. See [Provenance](../provenance.md) for how these fit together.
