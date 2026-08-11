# Reference Datasets

Some context a measurement needs isn't stored on the measurement itself: *where* in the machine it was taken (**geometry**), and *how* to turn raw counts into physical units (**calibration**). This is `Device`-level reference data, shared across many shots and only re-versioned when hardware moves or an instrument is recalibrated.

As wth all `Dataset`s, FDS does not store these arrays - it models the **relationship**. Both flavours work the same way: a `Device`-level `Dataset` *provides* one or more **roles** and declares which shots it covers (`applies_to`); a `Dataset` names the roles it *needs*; on read, FDS resolves each reference to the version valid for that dataset's shot.

## Reference geometry

Bolometer chord endpoints, magnetic-probe positions, Thomson channel major radii — geometry that makes a measurement like `Te[channel, time]` useful by linking each `channel` to its `R, Z` position.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `geometry_roles` | list of string | No | Roles a `Device`-level version *provides*, e.g. `["thomson_positions"]` |
| `geometry_references` | list of string | No | Roles a `Dataset` *needs* — set when the signal is registered (see [Dataset](dataset.md)) |
| `applies_to` | object | No | Which shots a version covers (below) |

**Coverage.** `applies_to` is the union of three selectors:

| Selector | Meaning |
| --- | --- |
| `shots` | Explicit shot ids, e.g. `["30420"]` |
| `shot_ranges` | `{from_shot, to_shot}`, inclusive; omit `to_shot` for open-ended |
| `date_ranges` | `{from_date, to_date}`, half-open; omit `to_date` for open-ended |

Range endpoints resolve to their `shot_at` at read time, so correcting a shot's timestamp updates coverage automatically.

### Register a version

A version is an ordinary `Device`-level `Dataset` (no shot) that provides the role and declares its coverage — here, positions valid from shot 30421 onward:

=== "curl"

    ```bash
    curl -X POST "$API/devices/mast/datasets" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "thomson_positions_v2",
           "geometry_roles": ["thomson_positions"],
           "applies_to": {"shot_ranges": [{"from_shot": "30421"}]},
           "url": "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
           "media_type": "application/x-netcdf", "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    requests.post(
        f"{API}/devices/mast/datasets",
        headers=headers,
        json={
            "name": "thomson_positions_v2",
            "geometry_roles": ["thomson_positions"],
            "applies_to": {"shot_ranges": [{"from_shot": "30421"}]},
            "url": "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
            "media_type": "application/x-netcdf",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.post(
        f"{API}/devices/mast/datasets",
        headers=headers,
        json={
            "name": "thomson_positions_v2",
            "geometry_roles": ["thomson_positions"],
            "applies_to": {"shot_ranges": [{"from_shot": "30421"}]},
            "url": "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
            "media_type": "application/x-netcdf",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/devices/mast/datasets`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "thomson_positions_v2",
        geometry_roles: ["thomson_positions"],
        applies_to: { shot_ranges: [{ from_shot: "30421" }] },
        url: "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
        media_type: "application/x-netcdf",
        access_level: "public",
      }),
    });
    ```

Re-versioning is just registering another `Device`-level dataset. No `Shot` or signal `Dataset` changes.

### Resolve on read

A signal that lists the role in `geometry_references` resolves it with `?include_geometry=true`. FDS returns the version whose coverage includes the signal's shot in a `geometry` list — each an ordinary dataset reference (`storage_options` vended only when `include_storage_options=true`):

=== "curl"

    ```bash
    curl "$API/devices/mast/shots/30421/datasets/thomson_scattering?include_geometry=true&include_storage_options=true"
    ```

=== "Python (requests)"

    ```python
    signal = requests.get(
        f"{API}/devices/mast/shots/30421/datasets/thomson_scattering",
        params={"include_geometry": True, "include_storage_options": True},
    ).json()[0]
    geometry = signal["geometry"]  # shot 30421 → thomson_positions_v2
    ```

=== "Python (httpx)"

    ```python
    signal = httpx.get(
        f"{API}/devices/mast/shots/30421/datasets/thomson_scattering",
        params={"include_geometry": True, "include_storage_options": True},
    ).json()[0]
    geometry = signal["geometry"]  # shot 30421 → thomson_positions_v2
    ```

=== "JavaScript (fetch)"

    ```javascript
    const signal = await (
      await fetch(
        `${API}/devices/mast/shots/30421/datasets/thomson_scattering` +
          `?include_geometry=true&include_storage_options=true`,
      )
    ).json();
    const geometry = signal[0].geometry; // shot 30421 → thomson_positions_v2
    ```

Resolution is `Device`-scoped — only versions on the shot's own `Device` are candidates. In JSON-LD, each resolved version is a `dcat:qualifiedRelation` carrying the `fuel:geometry` role.

## Reference calibration

Turning raw counts into physical units, via coefficient and gain tables. Same machinery as geometry, with one addition: calibration can resolve to an **ordered chain** rather than a single version.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `calibration_roles` | list of string | No | Roles a `Device`-level version provides, e.g. `["thomson_calibration"]` |
| `calibration_references` | list of string | No | Roles a `Dataset` needs |
| `calibration_stage` | integer | No | Position in the chain; lower applies first (gain → absolute). `None` for single-stage |
| `applies_to` | object | No | Coverage — same selectors as geometry |

Non-overlap holds **per `(role, stage)`**: within one stage a shot resolves to exactly one version, but different stages of the same role are *meant* to cover the same shot — that ordered set is the chain.

### Register a staged version

Each stage is its own `Device`-level dataset. Here, stage 1 of a two-step Thomson chain (register `thomson_absolute` at `calibration_stage: 2` the same way):

=== "curl"

    ```bash
    curl -X POST "$API/devices/mast/datasets" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "thomson_gain",
           "calibration_roles": ["thomson_calibration"], "calibration_stage": 1,
           "applies_to": {"shots": ["30420", "30421"]},
           "url": "s3://fds-data/mast/calibration/thomson_gain.nc",
           "media_type": "application/x-netcdf", "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    requests.post(
        f"{API}/devices/mast/datasets",
        headers=headers,
        json={
            "name": "thomson_gain",
            "calibration_roles": ["thomson_calibration"],
            "calibration_stage": 1,
            "applies_to": {"shots": ["30420", "30421"]},
            "url": "s3://fds-data/mast/calibration/thomson_gain.nc",
            "media_type": "application/x-netcdf",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.post(
        f"{API}/devices/mast/datasets",
        headers=headers,
        json={
            "name": "thomson_gain",
            "calibration_roles": ["thomson_calibration"],
            "calibration_stage": 1,
            "applies_to": {"shots": ["30420", "30421"]},
            "url": "s3://fds-data/mast/calibration/thomson_gain.nc",
            "media_type": "application/x-netcdf",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/devices/mast/datasets`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "thomson_gain",
        calibration_roles: ["thomson_calibration"],
        calibration_stage: 1,
        applies_to: { shots: ["30420", "30421"] },
        url: "s3://fds-data/mast/calibration/thomson_gain.nc",
        media_type: "application/x-netcdf",
        access_level: "public",
      }),
    });
    ```

### Resolve the chain

Reading a signal with `?include_calibration=true` resolves its `calibration_references` to every version covering the shot, sorted by ascending `calibration_stage`, in a `calibration` list:

```json
{
  "name": "thomson_scattering",
  "calibration": [
    { "name": "thomson_gain", "calibration_stage": 1, "url": "s3://…/thomson_gain.nc" },
    { "name": "thomson_absolute", "calibration_stage": 2, "url": "s3://…/thomson_absolute.nc" }
  ]
}
```

Apply the chain in order. As with geometry, resolution is `Device`-scoped and each resolved version carries the `fuel:calibration` role in JSON-LD. A geometry version may itself carry `calibration_references` — resolution recurses, anchored to the original shot.

## Find the registered versions

`GET /devices/{device}/datasets` lists everything a device hosts, its shots' datasets included. A reference version is registered at `Device` level, so `scope=device` narrows the listing to the datasets it sits among:

```bash
curl "$API/devices/mast/datasets?scope=device"
```

That is the listing to reach for when you want to see which versions of a role exist and what each one covers. `scope=device` is a filter on the hierarchy, so it returns any other `Device`-level `Dataset` too; the versions are the ones carrying `geometry_roles` or `calibration_roles`. See [Datasets](dataset.md#listing-datasets) for the other scopes.

## Rules FDS enforces

- **`Device`-level only.** A version must have no `shot_id` and is hosted within a `Device`; resolution never crosses devices.
- **No overlap.** At most one geometry version per role covers a shot; for calibration, at most one per `(role, stage)`.
- **Shot integrity.** A shot named in coverage must exist and carry a `shot_at`; it can't be deleted while referenced, and a `shot_at` change that would create an overlap or orphan a range endpoint is rejected.

## Feature annotations

Some features are too big or too numerous for an inline [`extent`](index.md#feature-annotation): a multi-dimensional region (a UFO's outline in (x, y), a per-frame mask), or a dense 1D series (every ELM in a shot). These are bulk data, so FDS models them as a relationship, like geometry and calibration, but with a difference: an annotation is not a `Device`-level version pulled by role. It is a `Dataset` that localises a feature and names its **subject** directly, resolved on read.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `annotates` | string | No | The feature this dataset localises (e.g. `elm`). Marks the dataset as an annotation and matches the inline annotation of the same `name` on its subject |
| `subject_dataset_id` | integer | No | For a dataset-frame annotation: the source `Dataset` it localises a feature in |
| `applies_to` | object | No | For a device-frame annotation: which shots it covers (same selectors as geometry) |

An annotation's coordinates live in its subject's frame, and FDS never re-frames them. The subject fixes the frame:

| Frame | How it is declared | Example |
| --- | --- | --- |
| **Dataset** | `subject_dataset_id` names the source dataset | A UFO mask in a specific camera signal |
| **Shot** | the annotation `Dataset` belongs to the shot (`shot_id`) | An ELM-time array on the shot's time base |
| **Device** | device-level (`shot_id` null) with `applies_to` | A camera dead-region across a campaign |

### Resolve on read

`?include_annotations=true` resolves a subject's annotations into an `annotations` field, off by default. Resolution stays within the subject's frame:

- a **Dataset** read returns the annotations whose `subject_dataset_id` is that dataset;
- a **Shot** read returns the annotation datasets belonging to it, plus the device-level annotations whose `applies_to` covers it.

A Dataset read does not fold in its parent Shot's annotations: that would present shot-frame events as if they belonged on the diagnostic's axis, a time-base consistency FDS does not assert. A consumer overlaying a shot's events across many diagnostics fetches the shot's annotation and aligns to each dataset itself.

In JSON-LD, each resolved annotation is a `dcat:qualifiedRelation` carrying the `fuel:annotation` role, alongside geometry and calibration.
