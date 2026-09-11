# Datasets & Distributions

The core discovery object. A **Dataset** is the abstract metadata entity describing *what* the set of data is. A **Distribution** is a concrete physical access path describing *how* to retrieve it. A Dataset can exist without any distributions (metadata-only registration) and distributions can be added later via `POST /datasets/{id}/distributions`.

## Dataset

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Short name, unique within its scope (e.g. `equilibrium`) |
| `url` | string | No | Physical location (`s3://`, `gs://`, `az://`), taken from the primary Distribution and absent if none exists yet |
| `media_type` | string | No | MIME type of the primary distribution (e.g. `application/x-zarr`) |
| `format` | string | No | Format label (e.g. `NetCDF4`) |
| `level` | integer | No | Numeric processing level. No controlled vocabulary, so set it only where the producer has a meaning for it |
| `quality_flag` | string | No | Free-form quality annotation (e.g. `good`, `suspect`), no controlled vocabulary |
| `access_level` | enum | No | `public`, `embargoed`, or `restricted` |
| `publisher` | string | No | Institution making the data available (`dct:publisher`) |
| `creator` | string | No | Person or team who produced the dataset (`dct:creator`) |
| `temporal_start` | datetime | No | Start of the measurement window (mapped to `dct:temporal`, a `dct:PeriodOfTime`) |
| `temporal_end` | datetime | No | End of the measurement window |
| `scientific_metadata` | list | No | Diagnostic-specific parameters, see [Scientific metadata](index.md#scientific-metadata) below |
| `activity_id` | integer | No | FK to the Activity that produced this dataset (provenance) |
| `derived_from` | list | No | Upstream entities this dataset was built from, see below |
| `annotates` | string | No | For a feature annotation dataset: the feature it localises (see [Feature annotations](reference-datasets.md#feature-annotations)) |
| `subject_dataset_id` | integer | No | For a dataset-frame annotation: the source dataset it localises a feature in |

### Recording a dataset's provenance

`activity_id` says which run produced a dataset. `derived_from` says which data it was built from, and the two are independent: a run may consume several inputs while any one output depends on only some of them. FDS never guesses that link, so a derivation is only ever recorded because someone asserted it.

The upstream does not have to be registered in FDS. Identify it however you can, falling back to a free-text label and/or description only
in the worst cases:

| Field | Use |
| --- | --- |
| `source_dataset_id` | the upstream is a registered FDS Dataset |
| `source_identifier` | it has a DOI, a URL, or another persistent identifier |
| `source_label`, `source_description` | free text, when it can only be named or described |

Give `source_dataset_id` or `source_identifier`, not both, since a registered dataset is already referenced by its own address. Every entry needs at least one of the three. A label and a description may accompany any of them.

A DOI is understood bare (`10.5281/zenodo.123`), prefixed (`doi:10.5281/...`), or as a full URL. Handle (`hdl:`), Software Heritage (`swh:`) and URNs are understood too. Anything else is recorded exactly as given, and simply not treated as resolvable.

```json
"derived_from": [
  {"source_dataset_id": 42},
  {"source_identifier": "10.5281/zenodo.123", "source_label": "Upstream on Zenodo"},
  {"source_label": "Legacy tape", "source_description": "Recovered from a 1998 archive"}
]
```

Derivations can also be maintained afterwards:

```http
POST   /api/v1/datasets/{id}/derivations
GET    /api/v1/datasets/{id}/derivations
DELETE /api/v1/datasets/{id}/derivations/{derivation_id}
```

### Following the chain

`derivations` answers one hop. To get the whole ancestry in one request, ask for the lineage:

```http
GET /api/v1/datasets/{id}/lineage
```

Each upstream is nested under the dataset that asserted it. Only registered datasets have upstreams to nest, so an external or described-only upstream is always a leaf.

```json
{
  "dataset_id": 51,
  "name": "t_e_profile",
  "derived_from": [
    {
      "dataset_id": 42,
      "name": "raw_thomson",
      "derived_from": [
        {"identifier": "10.5281/zenodo.123", "label": "Upstream on Zenodo"}
      ]
    }
  ]
}
```

A dataset is expanded once per response. Reach it a second time, either because two paths lead to the same ancestor or because the derivations form a loop, and it appears as a stub marked `seen` carrying only its id. Look it up under its first occurrence for the full record. Two other flags mark a branch that stops early: `restricted`, where you do not have read access to the upstream, and `missing`, where the upstream has since been deleted. A node with none of the three is complete.

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

A `Dataset` can also link to **reference geometry**. A `Dataset` declares the geometry it needs via `geometry_references`, or a `Device`-level `Dataset` *provides* geometry via `geometry_roles` and `applies_to`. The same machinery carries **reference calibration**: a `Dataset` names the calibration it needs via `calibration_references`, and a `Device`-level `Dataset` provides it via `calibration_roles`, `calibration_stage`, and `applies_to`. Unlike geometry, calibration can resolve to an ordered chain of stages. See [Reference Datasets](reference-datasets.md).

### Listing and filtering

The dataset lists accept a `name` filter, an `annotation` filter on the dataset's own `scientific_metadata`, and a `shot_annotation` filter on an annotation carried by its *parent shot*:

```text
GET /api/v1/devices/mastu/datasets?name=equilibrium
GET /api/v1/devices/mastu/datasets?name=equilibrium&shot_annotation=elm
```

The second form answers a question spanning both levels ("equilibrium datasets from shots that had an ELM train") in one request. Datasets that don't belong to a shot never match a `shot_annotation` filter. Shot- and device-scoped dataset lists accept `annotation` on the same terms. See [Finding annotated records](index.md#finding-annotated-records).

## Distribution

A Distribution is a physical access path for a Dataset, describing *how* to retrieve the data.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `url` | string | Yes | Download or access URL (e.g. `s3://fds-data/shots/30421/equilibrium`) |
| `media_type` | string | No | IANA media type (e.g. `application/x-zarr`, `application/x-hdf5`) |
| `format` | string | No | Human-readable format label (e.g. `NetCDF4`, `HDF5`) |
| `endpoint_url` | string | No | Storage endpoint, used for credential vending |
| `access_level` | enum | No | Override access policy for this distribution |

In most cases a Dataset will have exactly one Distribution, and you won't need to think about the distinction. The Dataset endpoints return the primary distribution's `url`, `media_type`, and `format` inlined directly on the Dataset response, so there is nothing extra to fetch.

Multiple distributions are supported when the same underlying data is available in more than one form, for example as both Zarr and HDF5, or through multiple access endpoints. All distributions of a given Dataset must be scientifically interchangeable; different data belongs in a separate Dataset. Additional distributions can be registered via `POST /datasets/{id}/distributions`.
