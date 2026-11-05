# Changes & Versions

FDS holds records about data, not the data itself. When something changes, what you do in FDS depends on what changed:

| What changed | What you do | The record's id, address and DOI |
| --- | --- | --- |
| Something a record says is wrong or missing | [Update the record](#correcting-a-record) | Stay the same |
| The data itself | [Register a new Dataset that replaces the old one](#when-the-data-changes) | The new Dataset has its own, and the old one keeps its own |
| Only the format or schema the data is stored in | [Add a distribution](#the-same-data-in-another-form) | Stay the same |
| Reference geometry or calibration | [Register a new version](#versions-of-reference-data) | The new version has its own |

This is how DOIs are normally used: correcting a record's metadata keeps its DOI, and different data gets a DOI of its own.

## Correcting a record

Update a record to fix or complete what it says, such as its description, licence, title or access level. The record keeps its id and its address, so links to it, and a DOI registered for it, lead to the corrected record.

To correct dataset 13's description and add its licence:

=== "curl"

    ```bash
    curl -X PATCH "$API/datasets/13" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"description": "EFIT equilibrium reconstruction, magnetics only.",
           "license": "CC-BY-4.0"}'
    ```

=== "Python (requests)"

    ```python
    requests.patch(
        f"{API}/datasets/13",
        headers=headers,
        json={
            "description": "EFIT equilibrium reconstruction, magnetics only.",
            "license": "CC-BY-4.0",
        },
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.patch(
        f"{API}/datasets/13",
        headers=headers,
        json={
            "description": "EFIT equilibrium reconstruction, magnetics only.",
            "license": "CC-BY-4.0",
        },
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/datasets/13`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        description: "EFIT equilibrium reconstruction, magnetics only.",
        license: "CC-BY-4.0",
      }),
    });
    ```

Only the fields you send change, and the response is the updated dataset. Devices, shots, collections, sources and activities are corrected in the same way, each at its own address.

**A dataset stays where it was registered.** FDS refuses to move a dataset to another device or shot, and answers `403`:

```json
{"detail": "Cannot move a dataset between shots"}
```

**FDS keeps only the current record.** The audit trail records each change: who made it, when, and which fields it changed:

```json
{"actor_id": "a09841d9...e8e60", "actor_issuer": "urn:fds:local", "resource_type": "dataset",
 "operation": "update", "id": 13, "name": "equilibrium",
 "changed_fields": ["description", "license"], "event": "dataset.update", "level": "info",
 "logger": "fds.audit", "timestamp": "2026-10-19T12:02:09.877085Z"}
```

It records the old and new values only for the fields that control access: `access_level`, `required_scopes` and `allowed_idps`. For any other field it records that the field changed, not what it said before. See [Logging & Auditing](../logging.md).

**A collection's members are part of the collection's record.** Adding a dataset to a collection, or removing one, changes the collection in place. It keeps its id and DOI, and the audit trail records each dataset added or removed.

## When the data changes

Data that differs is a new version, even when it describes the same thing. Register it as a new Dataset that lists the Datasets it replaces in `replaces`, and leave the old ones as they are. Each version keeps its own Activity, provenance, properties and DOI, and stays findable and citable.

**An Activity repeated or reprocessed.** A repass of a processing chain, or an analysis rerun with a fix, is a new [Activity](activity.md). Register its output with that Activity as its `activity_id`, and the dataset it replaces in `replaces`:

```json
{
  "name": "equilibrium",
  "url": "s3://fds-data/shots/30421/efit-1.5/equilibrium",
  "activity_id": 21,
  "replaces": [13]
}
```

Dataset 13 then lists the new dataset, 58, in `replaced_by`.

**Listings leave out replaced datasets.** A shot's datasets, a device's, a lookup by name and the property filters leave out a dataset when you may read a dataset that replaces it. If you may not read any of its replacements, it is still listed, as the newest version you can see, and its `replaced_by` is empty. Add `include_replaced=true` to list the replaced ones as well:

```http
GET /v1/devices/mast/shots/30421/datasets/equilibrium
GET /v1/devices/mast/shots/30421/datasets/equilibrium?include_replaced=true
```

The first returns dataset 58, and the second 13 and 58.

**Versions can branch.** Two Activities can each replace the same dataset, for example one with a new calibration and one with a new fitting method, and neither replaces the other. One dataset can also replace several. A listing shows every dataset that nothing replaces:

```text
13 ──replaced by──▶ 58 ──replaced by──▶ 71       listed: 71
13 ──replaced by──▶ 58                           listed: 58 and 64
   └──replaced by─▶ 64
```

Datasets of the same name that replace nothing and that nothing replaces, such as the equilibria of two different codes, are all listed, told apart by their Activity.

**Replacing is not deriving.** `derived_from` says which data a dataset was made from, and `replaces` says which data it supersedes. A repass usually makes its output again from the same inputs, not from the output it replaces, so it names those inputs in `derived_from` and the earlier output in `replaces`.

FDS checks each link when it is set:

- The replacement is filed in the same device and shot as each dataset it replaces.
- It names the Activity that generated it in `activity_id`. This is also what lets a dataset registered without an Activity be replaced, since two datasets with one name in one place need different Activities.
- A dataset cannot replace itself, or a dataset that already replaces it, directly or through others.

Set `replaces` when registering the new dataset, or afterwards with `PATCH /v1/datasets/{id}`, which sets the whole list: `[]` clears it. Deleting a dataset removes its links. `replaced_by` lists only the replacements you may read.

The replacement is not added to the collections the earlier version is in. Add it as you would any other member, and remove the earlier one if the collection should hold only the newest.

**Data corrected in a store that keeps its history.** An Icechunk repository keeps every earlier snapshot, and a commit stores only the chunks it changed, so the corrected data can go into the same store as the earlier data. Set each distribution's `ref` to the snapshot its record means, so each record keeps leading to its own data:

1. Tag the snapshot the existing dataset describes, and set its distribution's `ref` to the tag:

    ```python
    repo.create_tag("v1", snapshot_id=repo.lookup_branch("main"))
    ```

    ```http
    PATCH /v1/distributions/{distribution_id}

    {"ref": "v1"}
    ```

2. Commit the correction to the store, and tag it so it stays readable after a later correction:

    ```python
    session = repo.writable_session("main")
    # write the corrected groups to session.store
    snapshot = session.commit("Refit Thomson profiles with corrected calibration")
    repo.create_tag("v2", snapshot_id=snapshot)
    ```

3. Register the corrected dataset with the same `url`, its own `ref`, the Activity that generated it and the dataset it replaces:

    ```json
    {
      "name": "thomson_scattering",
      "url": "s3://fds-data/shots/50000/analysed/thomson_scattering",
      "ref": "v2",
      "media_type": "application/vnd.icechunk+zarr",
      "activity_id": 31,
      "replaces": [44]
    }
    ```

Readers of the earlier dataset open the store at `v1`, and readers of the correction at `v2`. Leave the correction's `ref` unset instead if its readers should always get the store's newest data: an Icechunk distribution without a `ref` follows the tip of `main` as the store changes, which suits data meant to keep growing. See [A point in a store's history](dataset.md#a-point-in-a-stores-history).

**A converted copy that lost information.** Converting data to another schema can drop fields, for example a field a newer IMAS Data Dictionary removed. Register the converted copy as a new Dataset, with `derived_from` naming the original. It does not replace the original, since both stay in use:

```json
{
  "name": "equilibrium",
  "url": "s3://fds-data/shots/30421/dd4/equilibrium",
  "media_type": "application/x-zarr",
  "conforms_to": "https://github.com/iterorganization/IMAS-Data-Dictionary/tree/4.0.0",
  "derived_from": [{"source_dataset_id": 13}]
}
```

**Data overwritten at the same address.** A record says where data is, not what it contains. If the files at a distribution's address are overwritten, the record does not change and FDS cannot tell: readers get the new contents under the old record, with its old description and provenance. To keep the old data readable, write the new data to a new address, or into a store that keeps its history with the old state tagged, and register it as a Dataset that replaces the old one.

## The same data in another form

When the information is the same and only the format or schema differs, such as Zarr and HDF5 copies, or IMAS Data Dictionary 3 and 4 copies with nothing lost in conversion, add a distribution to the existing Dataset with `POST /datasets/{id}/distributions`:

```json
{
  "url": "s3://fds-data/shots/30421/dd4/equilibrium",
  "media_type": "application/x-zarr",
  "conforms_to": "https://github.com/iterorganization/IMAS-Data-Dictionary/tree/4.0.0"
}
```

The Dataset keeps its id and DOI, and is found, cited and linked to its provenance once. See [The same data in another schema](dataset.md#the-same-data-in-another-schema).

## Versions of reference data

Reference geometry and calibration are the one place where FDS keeps several versions of the same thing and chooses between them. Each version is a device-level Dataset that says which shots it covers. When hardware moves, register a new version rather than changing the old one:

```text
thomson_positions_v1   provides thomson_positions   covers shots 28000 to 30420
thomson_positions_v2   provides thomson_positions   covers shots from 30421
```

A Thomson dataset on shot 30421 that needs `thomson_positions` is given version 2, and one on shot 30400 is given version 1. Data from older shots keeps the geometry that was true for it. FDS refuses a version whose shots overlap another version of the same role. See [Reference Datasets](reference-datasets.md).

These versions do not replace each other: each is right for its own shots. A corrected version for the same shots does replace the earlier one. Since coverage of one role may not overlap, first edit the earlier version's `applies_to` so it no longer covers those shots, then register the correction with `replaces`.

## Fields that name a version

Several fields hold a version. Only `replaces` orders versions, and FDS does not compare the others:

| Field | What it holds |
| --- | --- |
| Dataset `replaces` | The earlier versions this dataset replaces, published as `dct:replaces` |
| Distribution `ref` | The point in the store's history that holds the data, such as an Icechunk tag |
| Dataset `version` | A label you choose, such as `"2"` or `"2026-10 reprocessing"`, published as `dcat:version`. FDS does not compare or order them. |
| Activity `source_version` | The release of the code or instrument that carried out the Activity |
| Distribution `conforms_to` | The schema a copy follows, such as an IMAS Data Dictionary version |
| `/v1` in API addresses | The version of the API. It is never part of a record's identifier. See [Semantic Metadata](../dcat-jsonld.md) |
