# Source

A Source is a global, reusable registry entry for the things that produce data: analysis codes, diagnostic systems, schedulers, people and organisations.

A Source is not one kind of thing in the provenance graph. Its `kind` decides what it becomes, which is why a diagnostic and an analysis code are registered the same way but appear differently in the lineage.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Unique identifier for the source (e.g. `efit`, `jintrac`) |
| `description` | string | No | Extended description of the code or diagnostic |
| `kind` | enum | Yes | `software`, `instrument`, `person`, or `organization`. See below |
| `device_name` | string | No | Optionally scope the source to a device; global if omitted |

## Kinds

| `kind` | Example | Becomes | How it attaches to a run |
| --- | --- | --- | --- |
| `software` | EFIT, JINTRAC, a scheduler | a software agent | associated with the run, carrying a role |
| `instrument` | a Thomson scattering system | an entity | the run *used* it, in the `instrument` role |
| `person` | an operator, a principal investigator | a person | associated with, or attributed the data |
| `organization` | a diagnostic group, a facility | an organisation | associated with, or delegated to |

In particular, specifying when a source is an `instrument` is important. A diagnostic is a tool, not something that bears responsibility for a result, so it is an entity a run *used* rather than an agent the run was associated with. Because an instrument is an entity, measured data needs a run to attach it to. There is no direct link from a dataset to the instrument that produced it.

Register it once; reuse it across every run:

=== "curl"

    ```bash
    curl -X POST "$API/sources/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "efit", "description": "EFIT equilibrium reconstruction code",
           "kind": "software"}'
    ```

=== "Python (requests)"

    ```python
    source = requests.post(
        f"{API}/sources/",
        headers=headers,
        json={
            "name": "efit",
            "description": "EFIT equilibrium reconstruction code",
            "kind": "software",
        },
    ).json()
    ```

=== "Python (httpx)"

    ```python
    source = httpx.post(
        f"{API}/sources/",
        headers=headers,
        json={
            "name": "efit",
            "description": "EFIT equilibrium reconstruction code",
            "kind": "software",
        },
    ).json()
    ```

=== "JavaScript (fetch)"

    ```javascript
    const source = await (
      await fetch(`${API}/sources/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "efit",
          description: "EFIT equilibrium reconstruction code",
          kind: "software",
        }),
      })
    ).json();
    ```

See [Provenance](../provenance.md) for how a Source connects to the Activities (runs) and the Datasets they produce.
