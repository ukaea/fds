# Collection

A named, citable group of Datasets.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short name, unique within its scope (e.g. `analysed-data`, `jintrac-30420-56`) |
| `title` | string | No | Human-readable title |
| `access_level` | enum | No | Effective access level (inherited if not set) |
| `root_url` | string | No | Access root for all physical data in this collection (`dcat:accessURL`) |
| `activity_id` | integer | No | FK to the Activity that produced this collection |
| `scientific_metadata` | list | No | What this collection is about, see [Scientific metadata](index.md#scientific-metadata) |

## Making a run discoverable

A Collection carries `scientific_metadata` like a Shot or a Dataset, and its list endpoints take the same `annotation` filter. That is how a simulation run becomes something you can search for.

A run's outputs are always reachable as the datasets carrying its `activity_id`, so a bundle is never required. It is what you create when you want the run itself to be findable and citable. Set `activity_id` to the run and record what the run was about:

```json
{
  "name": "jintrac-30420-56",
  "activity_id": 12,
  "scientific_metadata": [
    {"name": "confinement_mode", "value": "H-mode"},
    {"name": "plasma_current", "value": 0.4, "unit": "MA"}
  ]
}
```

Then the run answers a catalogue question:

```http
GET /api/v1/devices/mast/shots/30420/collections?annotation=confinement_mode:H-mode
```

If you do not bundle a run, its claims belong on its output datasets instead, and the run is not searchable as a run. That is a choice, not a gap: FDS records what a producer asserts and never infers claims they did not make.

The same field on a hand-curated collection describes what the selection was chosen for rather than what a run produced. The shape and the query are identical; `activity_id` tells the two apart.

Collections support nesting (a Collection can contain other Collections) and a Dataset can belong to multiple Collections. The Dataset's URI is independent of its collection membership, so adding or moving a dataset never changes its URL.

Create a Collection, then add its member Datasets by id, one bodyless `POST` per dataset:

=== "curl"

    ```bash
    COLLECTION_ID=$(curl -s -X POST "$API/devices/mast/shots/30421/collections" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "experiment-data", "title": "Experiment Data", "access_level": "public"}' \
      | jq -r .id)

    # 12 15 18 are the ids of the datasets to group
    for DATASET_ID in 12 15 18; do
      curl -X POST "$API/collections/$COLLECTION_ID/datasets/$DATASET_ID" \
        -H "Authorization: Bearer $TOKEN"
    done
    ```

=== "Python (requests)"

    ```python
    col = requests.post(
        f"{API}/devices/mast/shots/30421/collections",
        headers=headers,
        json={
            "name": "experiment-data",
            "title": "Experiment Data",
            "access_level": "public",
        },
    ).json()

    # 12, 15, 18 are the ids of the datasets to group
    for dataset_id in [12, 15, 18]:
        requests.post(
            f"{API}/collections/{col['id']}/datasets/{dataset_id}", headers=headers
        )
    ```

=== "Python (httpx)"

    ```python
    col = httpx.post(
        f"{API}/devices/mast/shots/30421/collections",
        headers=headers,
        json={
            "name": "experiment-data",
            "title": "Experiment Data",
            "access_level": "public",
        },
    ).json()

    # 12, 15, 18 are the ids of the datasets to group
    for dataset_id in [12, 15, 18]:
        httpx.post(f"{API}/collections/{col['id']}/datasets/{dataset_id}", headers=headers)
    ```

=== "JavaScript (fetch)"

    ```javascript
    const col = await (
      await fetch(`${API}/devices/mast/shots/30421/collections`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "experiment-data",
          title: "Experiment Data",
          access_level: "public",
        }),
      })
    ).json();

    // 12, 15, 18 are the ids of the datasets to group
    for (const datasetId of [12, 15, 18]) {
      await fetch(`${API}/collections/${col.id}/datasets/${datasetId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${TOKEN}` },
      });
    }
    ```
