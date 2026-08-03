# Source

A Source is a global, reusable entity — the system or code that *can* produce data (a diagnostic system, analysis code, or automated process).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Unique identifier for the source (e.g. `efit`, `jintrac`) |
| `description` | string | No | Extended description of the code or diagnostic |
| `device_name` | string | No | Optionally scope the source to a device; global if omitted |

Register it once; reuse it across every run:

=== "curl"

    ```bash
    curl -X POST "$API/sources/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "efit", "description": "EFIT equilibrium reconstruction code"}'
    ```

=== "Python (requests)"

    ```python
    source = requests.post(
        f"{API}/sources/",
        headers=headers,
        json={"name": "efit", "description": "EFIT equilibrium reconstruction code"},
    ).json()
    ```

=== "Python (httpx)"

    ```python
    source = httpx.post(
        f"{API}/sources/",
        headers=headers,
        json={"name": "efit", "description": "EFIT equilibrium reconstruction code"},
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
        }),
      })
    ).json();
    ```

See [Provenance](../provenance.md) for how a Source connects to the Activities (runs) and the Datasets they produce.
