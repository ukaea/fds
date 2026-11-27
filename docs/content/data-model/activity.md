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
| `outputs` | list of object | No | Datasets the Activity generated, created with it. Each takes the fields of a new [Dataset](dataset.md) except `activity_id` |

`source_id` is optional. A raw acquisition may name no agent at all, only the instrument it used.

## Who may read an Activity

An Activity has no access level of its own. Anyone who may read a dataset it generated, or a collection that bundles it, may read the Activity with its instruments, agents and delegations, and is answered 403 otherwise. Only `fds-admin` may read an Activity that has neither yet. An Activity's inputs are listed only as far as the caller may read each one, in its JSON-LD as well as at `GET /v1/activities/{id}/inputs`, and its Sources likewise. Writing an Activity follows its records too: see [Activities](../access-control.md#activities).

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

## Creating its outputs with it

`outputs` creates the Datasets the Activity generated in the same request. Each entry takes the fields of a new Dataset except `activity_id`, which is set to the new Activity. The Activity, its links and its outputs are saved together. If any part is refused, for example an output whose name is already taken on its shot, or a shot that doesn't exist, nothing is saved and the response gives the reason. A pipeline that loses its connection during the request can check whether the outputs exist, and if they don't, send the request again.

```json
{
  "source_id": 12,
  "source_version": "efit-v2.8",
  "activity_type": "analysis",
  "inputs": [3, 7],
  "outputs": [
    {"name": "equilibrium", "device_name": "mast", "shot_id": "30421",
     "version": "2", "replaces": [41]}
  ]
}
```

The response is the Activity, with `outputs` listing the new Datasets' ids in the order the request listed them:

```json
{"id": 88, "source_id": 12, "activity_type": "analysis", "...": "...", "outputs": [512]}
```

An output that is a new version of an earlier Dataset lists it in `replaces`, as described in [Dataset versions](versions.md).

## Changing an Activity afterwards

Each part except the outputs can also be maintained afterwards, which suits a pipeline that registers an Activity first and resolves its inputs later:

```http
POST   /v1/activities/{id}/inputs/{dataset_id}
POST   /v1/activities/{id}/instruments/{source_id}
POST   /v1/activities/{id}/agents/{source_id}?role=orchestrator
POST   /v1/activities/{id}/delegations/{subordinate_source_id}/{responsible_source_id}
DELETE /v1/activities/{id}/inputs/{dataset_id}
```

`DELETE` works the same way for instruments, agents and delegations. An agent cannot be removed while a delegation still names it; remove the delegation first.

A Dataset created on its own, and a Collection, reference the Activity by setting their `activity_id`. The listings filter on it, whichever way the Dataset was created:

```text
GET /v1/datasets?activity_id={id}      # the datasets the Activity generated
GET /v1/collections?activity_id={id}   # the Activity's bundle
```

There is no listing of activities: find an Activity through its bundle or its outputs. See [Provenance](../provenance.md) for how these fit together.
