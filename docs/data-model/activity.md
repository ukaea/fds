# Activity

Records a computation or measurement event that produced a Dataset or Collection. The primary provenance object (maps to `prov:Activity`).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_id` | integer | Yes | The Source (code or diagnostic) that ran (`prov:wasAssociatedWith`) |
| `source_version` | string | No | Version of the source used |
| `activity_type` | enum | No | Controlled vocabulary: `measurement`, `simulation`, `analysis`, `calibration` |
| `parameters` | object | No | Run-specific key-value parameters (opaque provenance bag) |
| `started_at` | datetime | No | When execution began |
| `ended_at` | datetime | No | When execution completed |

Each Activity is a `POST` recording one run of a Source, referenced by `source_id`:

=== "curl"

    ```bash
    # $SOURCE_ID is the id of a registered Source
    curl -X POST "$API/activities/" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"source_id": '"$SOURCE_ID"', "source_version": "efit-v2.8",
           "activity_type": "analysis", "parameters": {"run_id": "30421-efit-standard"},
           "started_at": "2024-01-15T10:00:00", "ended_at": "2024-01-15T10:12:34"}'
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
        }),
      })
    ).json();
    ```

See [Provenance](../provenance.md) for how an Activity links a Source to the Datasets and Collections it produces (`prov:wasGeneratedBy`) and the inputs it consumed (`prov:used`).
