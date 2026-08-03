# Collection

A named, citable group of Datasets.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short name, unique within its scope (e.g. `analysed-data`, `jintrac-30420-56`) |
| `title` | string | No | Human-readable title |
| `access_level` | enum | No | Effective access level (inherited if not set) |
| `root_url` | string | No | Access root for all physical data in this collection (`dcat:accessURL`) |
| `activity_id` | integer | No | FK to the Activity that produced this collection |

Collections support nesting (a Collection can contain other Collections) and a Dataset can belong to multiple Collections. The Dataset's URI is independent of its collection membership — adding or moving a dataset never changes its URL.

Create a Collection, then add its member Datasets by id — one bodyless `POST` per dataset:

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
        json={"name": "experiment-data", "title": "Experiment Data", "access_level": "public"},
    ).json()

    # 12, 15, 18 are the ids of the datasets to group
    for dataset_id in [12, 15, 18]:
        requests.post(f"{API}/collections/{col['id']}/datasets/{dataset_id}", headers=headers)
    ```

=== "Python (httpx)"

    ```python
    col = httpx.post(
        f"{API}/devices/mast/shots/30421/collections",
        headers=headers,
        json={"name": "experiment-data", "title": "Experiment Data", "access_level": "public"},
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
