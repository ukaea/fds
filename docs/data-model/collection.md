# Collection

A named, citable group of Datasets.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short name, unique within its scope (e.g. `analysed-data`, `jintrac-30420-56`) |
| `title` | string | No | Human-readable title |
| `persistent_identifier` | string | No | A DOI or other persistent identifier registered for the collection. See [Persistent identifiers](../dcat-jsonld.md#persistent-identifiers) |
| `issued` | date | No | When the collection was formally published, the date a citation gives (`dct:issued`). Not when FDS listed it |
| `access_level` | enum | No | Effective access level (inherited if not set) |
| `root_url` | string | No | Access root for all physical data in this collection (`dcat:accessURL`) |
| `activity_id` | integer | No | The Activity this collection bundles, if any. See [Making an Activity discoverable](#making-an-activity-discoverable) |
| `scientific_metadata` | list | No | What this collection is about, see [Scientific metadata](index.md#scientific-metadata) |
| `replaces` | list | No | Ids of the collections this one replaces, filed in the same device and shot. See [A pass repeated](#a-pass-repeated) |
| `replaced_by` | list | Read-only | Ids of the collections that replace this one, giving only those you may read |

## Making an Activity discoverable

A Collection carries `scientific_metadata` like a Shot or a Dataset, and its list endpoints take the same `property` filter. That is how an Activity, such as a simulation run, becomes something you can search for.

An Activity's outputs are always reachable as the datasets carrying its `activity_id`, so a bundle is never required. It is what you create when you want the Activity itself to be findable and citable. Set `activity_id` to the Activity and record what it was about:

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

Then the Activity answers a catalogue question, across every device and shot:

```http
GET /v1/collections?activity_type=simulation&property=confinement_mode:H-mode
```

An Activity that models no real shot, such as a predictive scenario, belongs to the device it models, not to an invented shot. Register its outputs and its bundle under `/devices/{device}`. The bundle is then listed with the device's collections, and the query above finds it. The bundle of a run that models no particular device is a global collection.

If you do not bundle an Activity, its claims belong on its output datasets instead, and the Activity itself is not searchable. That is a choice, not a gap: FDS records what a producer asserts and never infers claims they did not make.

The same field on a hand-curated collection describes what the selection was chosen for rather than what an Activity generated. The shape and the query are identical; `activity_id` tells the two apart.

Collections support nesting (a Collection can contain other Collections) and a Dataset can belong to multiple Collections. The Dataset's URI is independent of its collection membership, so adding or moving a dataset never changes its URL.

Nest a child with `POST /collections/{parent_id}/collections/{child_id}`. Nesting returns 422 if it would create a cycle: a collection cannot contain itself, directly or through other collections. A child may belong to multiple parents as long as that does not create a cycle.

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

## A pass repeated

A processing chain, such as an inter-shot scheduler, runs several codes over a shot, and each code's run is its own Activity. Nothing records the chain's run as a whole, so a collection on the shot is where everything it generated is grouped: its `activity_id` stays unset, since it spans several Activities.

When the chain runs again over the same shot, a repass, register a new collection for the new pass and list the earlier one in `replaces`. Leave the earlier collection as it is: it stays the record of what that pass generated, and can still be cited.

```json
{
  "name": "analysed-2",
  "title": "MAST-U Shot 50000: Analysed Experimental Data, Second Pass",
  "replaces": [3]
}
```

If the repass regenerated only some datasets, add the ones it left unchanged to the new collection as well, so it holds the whole pass.

Collection listings and property summaries leave out a collection when you may read a collection that replaces it; add `include_replaced=true` to list it as well. The rules are those for [datasets](versions.md#when-the-data-changes): the replacement is filed in the same device and shot, several collections may replace one and one may replace several, and a collection cannot replace itself or one that already replaces it. A collection that replaces another needs no `activity_id`.

A collection you chose by hand, such as the datasets behind a paper, holds the versions you chose. A repass does not change it; edit it yourself if it should hold newer versions.

## Listing collections

| Route | Returns |
| --- | --- |
| `GET /collections` | Every collection in the catalogue |
| `GET /devices/{device}/collections` | Every collection the device hosts, shot-level and device-level |
| `GET /devices/{device}/shots/{shot}/collections` | The collections of one shot |

As with [datasets](dataset.md#listing-datasets), a collection is attached to a shot, to a device as a whole, or to neither, in which case it is global. The first two routes list all of these by default. Add `scope` to list only one kind: `global` (only `GET /collections` accepts this), `device` or `shot`.

```bash
curl "$API/collections?scope=global"               # global collections
curl "$API/devices/mast/collections?scope=device"  # mast's device-level collections
```

Every collection listing can also be filtered by the Activity each collection bundles, the one its `activity_id` names:

| Parameter | Lists the collections that bundle |
| --- | --- |
| `activity_id` | This Activity |
| `activity_type` | Activities of this type, such as `simulation` |
| `source` | Activities carried out by the source with this name, such as `jintrac` |

```text
GET /v1/collections?activity_type=simulation     # every simulation run that has a bundle
GET /v1/devices/mast/collections?source=jintrac  # JINTRAC simulations on mast
GET /v1/collections?activity_id=12               # Activity 12's bundle
```

A bundle can also hold datasets its Activity did not generate, such as the Activity's inputs. To list only what Activity 12 generated, use `GET /v1/datasets?activity_id=12`.

A collection is left out of every listing when you may read a collection that replaces it, unless you add `include_replaced=true`. See [A pass repeated](#a-pass-repeated).

A collection read includes `activity`, a summary of the Activity it bundles, in the same form as on a [dataset read](dataset.md#recording-a-datasets-provenance). Each dataset inlined in the read carries a summary of its own Activity.

To see what the collections in a listing can be filtered by, ask for its property summary: `GET /collections/properties` or `GET /devices/{device}/collections/properties`. Each takes the same filters as its listing and answers in the same form as the [shot summary](index.md#discovering-what-to-filter-on).

These routes take the name `properties`, so a global or device-level collection with that name cannot be read by name. Read it by id instead, with `GET /collections/id/{id}`.

## Reading members

A collection read inlines its first 100 member Datasets as `datasets` and its first 100 child Collections as `child_collections`, ordered by id. Children are listed without their own members.

A larger collection is read in pages:

```http
GET /v1/collections/{id}/datasets?offset=100&limit=100
GET /v1/collections/{id}/collections?offset=100&limit=100
```

Both are ordered by id and take at most 1000 per page. A page shorter than `limit` is the last.
