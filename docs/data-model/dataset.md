# Datasets & Distributions

The core discovery object. A **Dataset** is the abstract metadata entity describing *what* the set of data is. A **Distribution** is a concrete physical access path describing *how* to retrieve it. A Dataset can exist without any distributions (metadata-only registration) and distributions can be added later via `POST /datasets/{id}/distributions`.

## Dataset

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short name, unique within its scope (e.g. `equilibrium`) |
| `url` | string | No | Physical location (`s3://`, `gs://`, `az://`) — from the primary Distribution, absent if none exists yet |
| `media_type` | string | No | MIME type of the primary distribution (e.g. `application/x-zarr`) |
| `format` | string | No | Format label (e.g. `NetCDF4`) |
| `level` | integer | No | Numeric processing level. No controlled vocabulary, so set it only where the producer has a meaning for it |
| `quality_flag` | string | No | Free-form quality annotation (e.g. `good`, `suspect`) — no controlled vocabulary |
| `access_level` | enum | No | `public`, `embargoed`, or `restricted` |
| `publisher` | string | No | Institution making the data available (`dct:publisher`) |
| `creator` | string | No | Person or team who produced the dataset (`dct:creator`) |
| `temporal_start` | datetime | No | Start of the measurement window (mapped to `dct:temporal` → `dct:PeriodOfTime`) |
| `temporal_end` | datetime | No | End of the measurement window |
| `scientific_metadata` | list | No | Diagnostic-specific parameters — see [Scientific metadata](index.md#scientific-metadata) below |
| `activity_id` | integer | No | FK to the Activity that produced this dataset (provenance) |

Registering a Dataset with a `url` and `media_type` creates its primary Distribution in the
same call:

=== "curl"

    ```bash
    curl -X POST "$API/devices/mast/shots/30421/datasets" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"name": "equilibrium",
           "url": "s3://fds-data/shots/30421/equilibrium",
           "media_type": "application/x-zarr", "access_level": "public"}'
    ```

=== "Python (requests)"

    ```python
    requests.post(
        f"{API}/devices/mast/shots/30421/datasets",
        headers=headers,
        json={
            "name": "equilibrium",
            "url": "s3://fds-data/shots/30421/equilibrium",
            "media_type": "application/x-zarr",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "Python (httpx)"

    ```python
    httpx.post(
        f"{API}/devices/mast/shots/30421/datasets",
        headers=headers,
        json={
            "name": "equilibrium",
            "url": "s3://fds-data/shots/30421/equilibrium",
            "media_type": "application/x-zarr",
            "access_level": "public",
        },
    ).raise_for_status()
    ```

=== "JavaScript (fetch)"

    ```javascript
    await fetch(`${API}/devices/mast/shots/30421/datasets`, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "equilibrium",
        url: "s3://fds-data/shots/30421/equilibrium",
        media_type: "application/x-zarr",
        access_level: "public",
      }),
    });
    ```

## Listing datasets

| Route | Returns |
| --- | --- |
| `GET /datasets` | Every dataset in the catalogue |
| `GET /devices/{device}/datasets` | Every dataset the device hosts, shot-level and device-level |
| `GET /devices/{device}/shots/{shot}/datasets` | The datasets of one shot |

The device listing covers the whole device by default. Narrow it with `scope`:

| `scope` | Returns |
| --- | --- |
| `all` (default) | Every dataset for the device |
| `device` | Datasets belonging to the device as a whole rather than to any one shot |
| `shot` | Datasets attached to one of the device's shots |

```bash
curl "$API/devices/mast/datasets"                # everything mast hosts
curl "$API/devices/mast/datasets?scope=device"   # general device-level Datasets
```

A device-level `Dataset` describes the machine rather than a single experiment. Geometry and calibration data are examples of this.

Listings are paged with `offset` and `limit` (default 100) and returned in a stable order, so paging through a device covers it exactly once. A page can contain fewer than `limit` entries when some datasets are not readable by the caller; an empty page does not mean the end of the results.

A `Dataset` can also link to **reference geometry** — a `Dataset` declares the geometry it needs via `geometry_references`, or a `Device`-level `Dataset` *provides* geometry via `geometry_roles` and `applies_to`. The same machinery carries **reference calibration**: a `Dataset` names the calibration it needs via `calibration_references`, and a `Device`-level `Dataset` provides it via `calibration_roles`, `calibration_stage`, and `applies_to` — and unlike geometry, calibration can resolve to an ordered chain of stages. See [Reference Datasets](reference-datasets.md).

## Distribution

A Distribution is a physical access path for a Dataset — it describes *how* to retrieve the data.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `url` | string | Yes | Download or access URL (e.g. `s3://fds-data/shots/30421/equilibrium`) |
| `media_type` | string | No | IANA media type (e.g. `application/x-zarr`, `application/x-hdf5`) |
| `format` | string | No | Human-readable format label (e.g. `NetCDF4`, `HDF5`) |
| `endpoint_url` | string | No | Storage endpoint, used for credential vending |
| `access_level` | enum | No | Override access policy for this distribution |

In most cases a Dataset will have exactly one Distribution, and you won't need to think about the distinction. The Dataset endpoints return the primary distribution's `url`, `media_type`, and `format` inlined directly on the Dataset response — there is nothing extra to fetch.

Multiple distributions are supported when the same underlying data is available in more than one form — for example, as both Zarr and HDF5, or through multiple access endpoints. All distributions of a given Dataset must be scientifically interchangeable; different data belongs in a separate Dataset. Additional distributions can be registered via `POST /datasets/{id}/distributions`.
