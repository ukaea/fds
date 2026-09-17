# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "httpx==0.27.2",
# ]
# ///

"""
FDS demo metadata seeder.

Registers all devices, shots, datasets, collections, and provenance records
needed for the demo environment. All functions are idempotent.

Run standalone:
    uv run demo/seed_metadata.py

Import from tests or notebooks:
    from demo.seed_metadata import seed_all
    result = seed_all(base_url, headers)
"""

import os
import time

import httpx

FDS_API_URL_DEFAULT = "http://localhost:8000/api/v1"
KC_TOKEN_URL_DEFAULT = "http://localhost:8080/realms/fds/protocol/openid-connect/token"

SHOT_30420_IDS = [
    "equilibrium",
    "gas_injection",
    "interferometer",
    "magnetics",
    "pf_active",
    "pf_passive",
    "pulse_schedule",
    "soft_x_rays",
    "spectrometer_visible",
    "summary",
    "thomson_scattering",
    "wall",
]
SHOT_30421_IDS = SHOT_30420_IDS + ["charge_exchange"]

MAST_U_IDS_GROUPS = [
    "equilibrium",
    "gas_injection",
    "interferometer",
    "magnetics",
    "pf_active",
    "pf_passive",
    "soft_x_rays",
    "spectrometer_visible",
    "thomson_scattering",
]

MINIO_ENDPOINT = "http://localhost:9000"

# Shots 30420 and 30421 are real MAST data, already published openly by STFC.
# FDS registers them where they are rather than copying them in, which is what a
# catalogue is for: the demo holds no bytes for these shots, and a client reading
# them is sent straight to the public store with anonymous credentials.
STFC_ENDPOINT = "https://s3.echo.stfc.ac.uk"
STFC_BUCKET = "mast"


def get_or_create_source(
    client: httpx.Client,
    base_url: str,
    name: str,
    description: str,
    kind: str,
) -> int:
    body = {"name": name, "description": description, "kind": kind}
    resp = client.post(f"{base_url}/sources/", json=body)
    if resp.status_code == 201:
        return resp.json()["id"]
    if resp.status_code == 409:
        return client.get(f"{base_url}/sources/{name}").json()["id"]
    resp.raise_for_status()
    raise RuntimeError(f"Unexpected {resp.status_code} creating source {name!r}")


def register_devices_and_shots(client: httpx.Client, base_url: str) -> None:
    for device in [
        {
            "name": "mast",
            "title": "MAST",
            "description": "Mega Ampere Spherical Tokamak (MAST)",
            "type": "tokamak",
            "access_level": "public",
        },
        {
            "name": "mastu",
            "title": "MAST Upgrade",
            "description": "Mega Ampere Spherical Tokamak Upgrade (MAST-U)",
            "type": "tokamak",
            "access_level": "public",
        },
    ]:
        resp = client.post(f"{base_url}/devices/", json=device)
        if resp.status_code not in (201, 409):
            resp.raise_for_status()

    # shot_at is required for reference-geometry/calibration resolution: shot-range
    # coverage (e.g. "from shot 30421 onward") is evaluated against shot timestamps.
    # Shot 30421 also carries features on its own axes, for the feature-overlay demo in
    # explore.py: two on the time base (an H-mode window and a disruption, in seconds
    # relative to t=0) and one on the frequency axis (an MHD mode). Time is not
    # privileged, so the mode does not fall on the IP-vs-time trace.
    # `elm` is the fourth: its presence and rough window are annotated inline, while the
    # train's individual event times are too many for the catalogue and live in the
    # annotation dataset registered by register_mast_annotations, tied to this annotation by
    # the shared name. Appended last — explore.py indexes the first three by position.
    features_30421 = [
        {
            "name": "confinement_mode",
            "value": "H-mode",
            "extent": {"dimension": "time", "start": 0.20, "end": 0.45, "unit": "s"},
        },
        {
            "name": "disruption",
            "value": True,
            "extent": {"dimension": "time", "start": 0.606, "unit": "s"},
        },
        {
            "name": "mode",
            "value": "n=1 tearing",
            "extent": {
                "dimension": "frequency",
                "start": 12000,
                "end": 18000,
                "unit": "Hz",
            },
        },
        {
            "name": "elm",
            "value": "type-I",
            "description": "ELM train through the H-mode window; event times are in "
            "the elm_times annotation dataset.",
            "extent": {"dimension": "time", "start": 0.205, "end": 0.45, "unit": "s"},
        },
    ]
    # The two MAST-U shots are a matched pair for catalogue filtering: 50000 ran up in
    # L-mode, transitioned to H-mode and ELMed; 50001 never left L-mode, so has no ELMs
    # to annotate. Both carry an equilibrium dataset, so a filter for "equilibrium
    # datasets from ELMy MAST-U shots" has something to exclude as well as return.
    #
    # 50000 carries `confinement_mode` twice, which is the ordinary case: a mode holds
    # over a window, not over a shot. It is also what makes the transition query
    # meaningful, since each annotation is matched against the whole list
    # independently: asking for L-mode and H-mode together finds the shot that was in
    # both at some point, which is 50000 alone.
    features_50000 = [
        {
            "name": "confinement_mode",
            "value": "L-mode",
            "extent": {"dimension": "time", "start": 0.10, "end": 0.18, "unit": "s"},
        },
        {
            "name": "confinement_mode",
            "value": "H-mode",
            "extent": {"dimension": "time", "start": 0.18, "end": 0.33, "unit": "s"},
        },
        {
            "name": "elm",
            "value": "type-I",
            "extent": {"dimension": "time", "start": 0.19, "end": 0.33, "unit": "s"},
        },
    ]
    features_50001 = [
        {
            "name": "confinement_mode",
            "value": "L-mode",
            "extent": {"dimension": "time", "start": 0.10, "end": 0.29, "unit": "s"},
        },
    ]
    for device_name, shot_id, shot_at, sci_meta in [
        ("mast", "30420", "2008-04-17T14:23:45", None),
        ("mast", "30421", "2008-04-17T15:41:22", features_30421),
        ("mastu", "50000", None, features_50000),
        ("mastu", "50001", None, features_50001),
    ]:
        shot = {"id": shot_id, "access_level": "public", "device_name": device_name}
        if shot_at is not None:
            shot["shot_at"] = shot_at
        if sci_meta is not None:
            shot["scientific_metadata"] = sci_meta
        resp = client.post(f"{base_url}/devices/{device_name}/shots", json=shot)
        if resp.status_code not in (201, 409):
            resp.raise_for_status()


# Annotations on the *data* rather than on the plasma, so a dataset listing has
# something of its own to filter on: the shot's annotations say what happened in
# the discharge, these say what happened to the recording of it. Both live in
# scientific_metadata and both answer to ?annotation, at their own level.
DATASET_FEATURES_30421 = {
    "thomson_scattering": [
        {
            "name": "laser_dropout",
            "value": True,
            "description": "Laser failed to fire; no profiles in this window.",
            "extent": {"dimension": "time", "start": 0.31, "end": 0.34, "unit": "s"},
        }
    ],
    "soft_x_rays": [
        {
            "name": "saturated_channel",
            "value": "HCAM_12",
            "description": "Channel railed through the disruption.",
            "extent": {"dimension": "time", "start": 0.60, "end": 0.62, "unit": "s"},
        }
    ],
}


def register_mast_datasets(client: httpx.Client, base_url: str) -> None:
    for device, shot_id, ids_list in [
        ("mast", "30420", SHOT_30420_IDS),
        ("mast", "30421", SHOT_30421_IDS),
    ]:
        for ids_name in ids_list:
            meta: dict[str, object] = {
                "name": ids_name,
                "url": (f"s3://{STFC_BUCKET}/level2/shots/{shot_id}.zarr/{ids_name}"),
                "endpoint_url": STFC_ENDPOINT,
                "access_level": "public",
                "title": f"{ids_name.replace('_', ' ').title()} (Shot {shot_id})",
                "media_type": "application/x-zarr",
            }
            # thomson_scattering resolves its chord positions and calibration chain
            # from the versioned device-level references registered below.
            if ids_name == "thomson_scattering":
                meta["geometry_references"] = ["thomson_positions"]
                meta["calibration_references"] = ["thomson_calibration"]
            if shot_id == "30421" and ids_name in DATASET_FEATURES_30421:
                meta["scientific_metadata"] = DATASET_FEATURES_30421[ids_name]
            resp = client.post(
                f"{base_url}/devices/{device}/shots/{shot_id}/datasets", json=meta
            )
            if resp.status_code not in (201, 409):
                resp.raise_for_status()


def register_mast_geometry(client: httpx.Client, base_url: str) -> None:
    """Register versioned device-level Thomson chord-position geometry on 'mast'.

    Two versions of the ``thomson_positions`` role: v1 covers shot 30420, v2
    (re-surveyed positions) covers shot 30421 onward. Each shot's
    thomson_scattering dataset resolves to the version valid for it. Idempotent.
    """
    versions = [
        {
            "name": "thomson_positions_v1",
            "version": "1",
            "geometry_roles": ["thomson_positions"],
            "applies_to": {"shots": ["30420"]},
            "url": "s3://fds-data/mast/geometry/thomson_positions_v1.nc",
            "endpoint_url": MINIO_ENDPOINT,
            "media_type": "application/x-netcdf",
            "access_level": "public",
            "title": "MAST Thomson chord positions (v1, shot 30420)",
        },
        {
            "name": "thomson_positions_v2",
            "version": "2",
            "geometry_roles": ["thomson_positions"],
            "applies_to": {"shot_ranges": [{"from_shot": "30421"}]},
            "url": "s3://fds-data/mast/geometry/thomson_positions_v2.nc",
            "endpoint_url": MINIO_ENDPOINT,
            "media_type": "application/x-netcdf",
            "access_level": "public",
            "title": "MAST Thomson chord positions (v2, from shot 30421)",
        },
    ]
    for version in versions:
        resp = client.post(f"{base_url}/devices/mast/datasets", json=version)
        if resp.status_code not in (201, 409):
            resp.raise_for_status()


def register_mast_calibration(client: httpx.Client, base_url: str) -> None:
    """Register the staged device-level Thomson calibration chain on 'mast'.

    Two versions of the ``thomson_calibration`` role at successive stages:
    thomson_gain (stage 1) then thomson_absolute (stage 2). Non-overlap holds
    per (role, stage), so both cover shots 30420 and 30421; resolving a signal's
    reference returns them in stage order. Idempotent.
    """
    versions = [
        {
            "name": "thomson_gain",
            "version": "1",
            "calibration_roles": ["thomson_calibration"],
            "calibration_stage": 1,
            "applies_to": {"shots": ["30420", "30421"]},
            "url": "s3://fds-data/mast/calibration/thomson_gain.nc",
            "endpoint_url": MINIO_ENDPOINT,
            "media_type": "application/x-netcdf",
            "access_level": "public",
            "title": "MAST Thomson gain calibration (stage 1)",
        },
        {
            "name": "thomson_absolute",
            "version": "1",
            "calibration_roles": ["thomson_calibration"],
            "calibration_stage": 2,
            "applies_to": {"shots": ["30420", "30421"]},
            "url": "s3://fds-data/mast/calibration/thomson_absolute.nc",
            "endpoint_url": MINIO_ENDPOINT,
            "media_type": "application/x-netcdf",
            "access_level": "public",
            "title": "MAST Thomson absolute calibration (stage 2)",
        },
    ]
    for version in versions:
        resp = client.post(f"{base_url}/devices/mast/datasets", json=version)
        if resp.status_code not in (201, 409):
            resp.raise_for_status()


def register_mast_annotations(client: httpx.Client, base_url: str) -> None:
    """Register the shot-frame ELM annotation for MAST shot 30421.

    A feature annotation is an ordinary Dataset marked with ``annotates``, naming
    the feature it localises. Its subject fixes its frame: this one belongs to the
    shot (``shot_id`` set, no ``subject_dataset_id``), so its event times are on
    the shot's own time base and a Shot read with ``?include_annotations=true``
    resolves it. The name matches the shot's inline ``elm`` annotation, which carries the
    feature's presence and rough window. Idempotent.

    Seeded after the experiment-data collections so it is not swept into them:
    that collection lists the diagnostics acquired during the shot, and an
    annotation is not one of them.
    """
    annotation = {
        "name": "elm_times",
        "annotates": "elm",
        "level": 2,
        "url": "s3://fds-data/shots/30421/annotations/elm_times.nc",
        "endpoint_url": MINIO_ENDPOINT,
        "media_type": "application/x-netcdf",
        "access_level": "public",
        "title": "ELM event times (MAST shot 30421)",
        "description": (
            "Times of each ELM in the shot's H-mode window, on the shot's time "
            "base. Too many events to annotate inline, so the shot annotates the "
            "train's presence and window and this dataset holds the individual times."
        ),
    }
    resp = client.post(f"{base_url}/devices/mast/shots/30421/datasets", json=annotation)
    if resp.status_code not in (201, 409):
        resp.raise_for_status()


def register_experiment_data_collections(
    client: httpx.Client, base_url: str, scheduler_source_id: int
) -> dict[str, int]:
    """Returns {shot_id: collection_id} for shots 30420 and 30421."""
    result: dict[str, int] = {}
    shot_timestamps = {"30420": "2008-04-17T14:23:45", "30421": "2008-04-17T15:41:22"}

    for shot_id, started_at in shot_timestamps.items():
        existing = client.get(
            f"{base_url}/devices/mast/shots/{shot_id}/collections/experiment-data"
        )
        if existing.status_code == 200:
            result[shot_id] = existing.json()["id"]
            continue

        act = client.post(
            f"{base_url}/activities/",
            json={
                "source_id": scheduler_source_id,
                "activity_type": "measurement",
                "source_version": "intershot-scheduler-v1",
                "parameters": {"shot_id": shot_id},
                "started_at": started_at,
                "ended_at": started_at,
            },
        )
        act.raise_for_status()
        act_id = act.json()["id"]

        col = client.post(
            f"{base_url}/devices/mast/shots/{shot_id}/collections",
            json={
                "name": "experiment-data",
                "title": "Experiment Data",
                "description": f"Raw IDS datasets acquired during MAST shot {shot_id}.",
                "access_level": "public",
                "activity_id": act_id,
            },
        )
        col.raise_for_status()
        col_id = col.json()["id"]

        datasets = client.get(
            f"{base_url}/devices/mast/shots/{shot_id}/datasets"
        ).json()
        for ds in datasets:
            client.post(f"{base_url}/collections/{col_id}/datasets/{ds['id']}")

        result[shot_id] = col_id

    return result


def _attach_activity_to_dataset(
    client: httpx.Client,
    base_url: str,
    activity_meta: dict,
    device: str,
    shot_id: str,
    dataset_name: str,
) -> None:
    ds_list = client.get(
        f"{base_url}/devices/{device}/shots/{shot_id}/datasets/{dataset_name}"
    ).json()
    if not ds_list:
        return
    ds = ds_list[0]
    if ds.get("activity_id"):
        return
    act = client.post(f"{base_url}/activities/", json=activity_meta)
    act.raise_for_status()
    client.patch(
        f"{base_url}/datasets/{ds['id']}", json={"activity_id": act.json()["id"]}
    )


def register_efit_provenance(
    client: httpx.Client, base_url: str, scheduler_source_id: int
) -> int:
    """Registers EFIT source + analysis activities for equilibrium datasets.

    The inter-shot scheduler orchestrates these automated between-shot analyses,
    so each run associates the scheduler (orchestrator) and records EFIT acting
    on its behalf. Returns the EFIT source_id.
    """
    source_id = get_or_create_source(
        client, base_url, "efit", "EFIT equilibrium reconstruction code", "software"
    )
    # The inter-shot scheduler orchestrated these runs; EFIT acted on its behalf.
    orchestration = {
        "agents": [{"source_id": scheduler_source_id, "role": "orchestrator"}],
        "delegations": [
            {
                "subordinate_source_id": source_id,
                "responsible_source_id": scheduler_source_id,
            }
        ],
    }

    _attach_activity_to_dataset(
        client,
        base_url,
        {
            "source_id": source_id,
            "activity_type": "analysis",
            "source_version": "efit-v2.8",
            "parameters": {"run_id": "30421-efit-standard"},
            "started_at": "2024-01-15T10:00:00",
            "ended_at": "2024-01-15T10:12:34",
            **orchestration,
        },
        "mast",
        "30421",
        "equilibrium",
    )

    _attach_activity_to_dataset(
        client,
        base_url,
        {
            "source_id": source_id,
            "activity_type": "analysis",
            "source_version": "efit-v2.8",
            "parameters": {"run_id": "30420-efit-standard"},
            "started_at": "2024-01-14T09:22:00",
            "ended_at": "2024-01-14T09:34:51",
            **orchestration,
        },
        "mast",
        "30420",
        "equilibrium",
    )

    return source_id


def register_thomson_instrument_provenance(client: httpx.Client, base_url: str) -> int:
    """Registers the Thomson scattering system as a kind=instrument Source and an
    acquisition Activity that *used* it, naming no agent.

    A diagnostic is a tool, not something that bears responsibility, so it projects
    to a prov:Entity the acquisition used (role=instrument), never an agent the run
    was associated with. Returns the instrument's source_id.
    """
    instrument_id = get_or_create_source(
        client,
        base_url,
        "thomson-scattering-system",
        "MAST Thomson scattering diagnostic",
        kind="instrument",
    )
    _attach_activity_to_dataset(
        client,
        base_url,
        {
            "activity_type": "measurement",
            "instruments": [instrument_id],
        },
        "mast",
        "30421",
        "thomson_scattering",
    )
    return instrument_id


def register_mast_upgrade_datasets(
    client: httpx.Client, base_url: str
) -> dict[str, int]:
    """Registers MAST-U shot 50000 raw + analysed collections. Returns {raw_collection_id, analysed_collection_id}."""

    # Raw diagnostics (restricted NetCDF)
    existing = client.get(
        f"{base_url}/devices/mastu/shots/50000/collections/raw-diagnostics"
    )
    if existing.status_code == 200:
        raw_collection_id = existing.json()["id"]
    else:
        raw_col = client.post(
            f"{base_url}/devices/mastu/shots/50000/collections",
            json={
                "name": "raw-diagnostics",
                "title": "MAST-U Shot 50000: Raw Diagnostic Data",
                "description": "Unprocessed raw outputs from MAST-U diagnostic systems.",
                "access_level": "restricted",
            },
        )
        raw_col.raise_for_status()
        raw_collection_id = raw_col.json()["id"]

        for name, stem in [
            ("thomson-raw", "thomson_scattering"),
            ("charge-exchange-raw", "charge_exchange"),
            ("magnetics-raw", "magnetics"),
        ]:
            ds = client.post(
                f"{base_url}/devices/mastu/shots/50000/datasets",
                json={
                    "name": name,
                    "title": f"MAST-U {stem.replace('_', ' ').title()} Raw (Shot 50000)",
                    "url": f"s3://fds-data/shots/50000/raw/{stem}.nc",
                    "endpoint_url": MINIO_ENDPOINT,
                    "media_type": "application/netcdf",
                    "format": "NetCDF4",
                    "access_level": "restricted",
                },
            )
            ds.raise_for_status()
            client.post(
                f"{base_url}/collections/{raw_collection_id}/datasets/{ds.json()['id']}"
            )

    # Analysed experimental data (public, IceChunk)
    existing = client.get(f"{base_url}/devices/mastu/shots/50000/collections/analysed")
    if existing.status_code == 200:
        analysed_collection_id = existing.json()["id"]
    else:
        analysed_col = client.post(
            f"{base_url}/devices/mastu/shots/50000/collections",
            json={
                "name": "analysed",
                "title": "MAST-U Shot 50000: Analysed Experimental Data",
                "description": (
                    "Post-processed MAST-U diagnostic data in IMAS IDS format, "
                    "stored as a single IceChunk repository. Each IDS is a group "
                    "within the shared store."
                ),
                "access_level": "public",
                "root_url": "s3://fds-data/shots/50000/analysed/",
            },
        )
        analysed_col.raise_for_status()
        analysed_collection_id = analysed_col.json()["id"]

        for ids_name in MAST_U_IDS_GROUPS:
            ds = client.post(
                f"{base_url}/devices/mastu/shots/50000/datasets",
                json={
                    "name": ids_name,
                    "title": f"MAST-U {ids_name.replace('_', ' ').title()} (Shot 50000)",
                    "url": f"s3://fds-data/shots/50000/analysed/{ids_name}",
                    "endpoint_url": MINIO_ENDPOINT,
                    "media_type": "application/vnd.icechunk+zarr",
                    "format": "icechunk",
                    "access_level": "public",
                },
            )
            ds.raise_for_status()
            client.post(
                f"{base_url}/collections/{analysed_collection_id}/datasets/{ds.json()['id']}"
            )

    register_mast_upgrade_50001(client, base_url)

    return {
        "raw_collection_id": raw_collection_id,
        "analysed_collection_id": analysed_collection_id,
    }


def register_mast_upgrade_50001(client: httpx.Client, base_url: str) -> None:
    """Register MAST-U shot 50001's analysed data.

    The L-mode counterpart to 50000: same equilibrium dataset name, no ELM annotation, so a
    annotation filter over MAST-U equilibrium datasets returns 50000 and not this one.
    """
    existing = client.get(f"{base_url}/devices/mastu/shots/50001/collections/analysed")
    if existing.status_code == 200:
        return

    collection = client.post(
        f"{base_url}/devices/mastu/shots/50001/collections",
        json={
            "name": "analysed",
            "title": "MAST-U Shot 50001: Analysed Experimental Data",
            "description": (
                "Post-processed MAST-U diagnostic data in IMAS IDS format, stored as "
                "a single IceChunk repository. This L-mode discharge was reconstructed "
                "for equilibrium and magnetics only."
            ),
            "access_level": "public",
            "root_url": "s3://fds-data/shots/50001/analysed/",
        },
    )
    collection.raise_for_status()
    collection_id = collection.json()["id"]

    for ids_name in ["equilibrium", "magnetics"]:
        ds = client.post(
            f"{base_url}/devices/mastu/shots/50001/datasets",
            json={
                "name": ids_name,
                "title": f"MAST-U {ids_name.replace('_', ' ').title()} (Shot 50001)",
                "level": 2,
                "url": f"s3://fds-data/shots/50001/analysed/{ids_name}",
                "endpoint_url": MINIO_ENDPOINT,
                "media_type": "application/vnd.icechunk+zarr",
                "format": "icechunk",
                "access_level": "public",
            },
        )
        ds.raise_for_status()
        client.post(
            f"{base_url}/collections/{collection_id}/datasets/{ds.json()['id']}"
        )


def register_jintrac_collection(
    client: httpx.Client, base_url: str
) -> dict[str, int | None]:
    """Registers JINTRAC source, simulation activity, output datasets, and collection. Returns {collection_id, activity_id, source_id}."""
    existing = client.get(
        f"{base_url}/devices/mast/shots/30420/collections/jintrac-v220922"
    )
    if existing.status_code == 200:
        col = existing.json()
        return {
            "collection_id": col["id"],
            "activity_id": col["activity_id"],
            "source_id": None,
        }

    source_id = get_or_create_source(
        client, base_url, "jintrac", "Integrated modelling code", "software"
    )

    act = client.post(
        f"{base_url}/activities/",
        json={
            "source_id": source_id,
            "source_version": "v220922",
            "activity_type": "simulation",
            "parameters": {
                "run_id": "30420-jintrac-v220922",
                "transport_model": "NCLASS",
            },
            "started_at": "2024-03-10T14:00:00",
            "ended_at": "2024-03-10T16:47:22",
        },
    )
    act.raise_for_status()
    activity_id = act.json()["id"]

    for ids_name in ["equilibrium", "magnetics", "thomson_scattering"]:
        ds_id = client.get(
            f"{base_url}/devices/mast/shots/30420/datasets/{ids_name}"
        ).json()[0]["id"]
        client.post(f"{base_url}/activities/{activity_id}/inputs/{ds_id}")

    dataset_ids = []
    for stem in ["equilibrium", "core_profiles", "core_sources"]:
        ds = client.post(
            f"{base_url}/devices/mast/shots/30420/datasets",
            json={
                "name": stem,
                "title": f"JINTRAC {stem.replace('_', ' ').title()} (Shot 30420)",
                "url": f"s3://fds-data/shots/30420/jintrac/{stem}.nc",
                "endpoint_url": MINIO_ENDPOINT,
                "media_type": "application/netcdf",
                "format": "NetCDF4",
                "access_level": "public",
                "activity_id": activity_id,
            },
        )
        ds.raise_for_status()
        dataset_ids.append(ds.json()["id"])

    col = client.post(
        f"{base_url}/devices/mast/shots/30420/collections",
        json={
            "name": "jintrac-v220922",
            "title": "JINTRAC Integrated Modelling (Shot 30420)",
            "description": "JINTRAC transport simulation outputs: equilibrium, core profiles, and heat sources.",
            "access_level": "public",
            "activity_id": activity_id,
            # What the run simulated, as opposed to what the shot measured. This
            # is what makes the run findable as a run: the bundle answers
            # ?annotation=confinement_mode:H-mode, the Activity never does.
            "scientific_metadata": [
                {
                    "name": "confinement_mode",
                    "value": "H-mode",
                    "description": "Simulated confinement regime.",
                },
                {"name": "transport_model", "value": "NCLASS"},
            ],
        },
    )
    col.raise_for_status()
    collection_id = col.json()["id"]

    for ds_id in dataset_ids:
        client.post(f"{base_url}/collections/{collection_id}/datasets/{ds_id}")

    return {
        "collection_id": collection_id,
        "activity_id": activity_id,
        "source_id": source_id,
    }


def get_admin_headers(
    kc_token_url: str, *, retries: int = 24, delay: float = 5.0
) -> dict[str, str]:
    """Fetch admin auth headers from Keycloak, retrying until it is ready.

    Shared by the standalone seeder (``__main__``) and the ingest notebook.
    """
    token_data = {
        "client_id": "fds-client",
        "client_secret": "fds-client-secret",
        "username": "admin",
        "password": "password",
        "grant_type": "password",
        "scope": "openid profile fds-admin",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(kc_token_url, data=token_data)
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"Waiting for Keycloak (attempt {attempt}/{retries}): {e}")
            time.sleep(delay)
    else:
        raise RuntimeError("Keycloak did not become ready in time.")

    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def seed_all(base_url: str, headers: dict[str, str]) -> dict:
    """Seed the full demo dataset. Idempotent, safe to call multiple times. Returns a summary of IDs."""
    with httpx.Client(headers=headers, timeout=60.0) as client:
        register_devices_and_shots(client, base_url)
        register_mast_datasets(client, base_url)
        register_mast_geometry(client, base_url)
        register_mast_calibration(client, base_url)

        scheduler_id = get_or_create_source(
            client,
            base_url,
            "intershot-scheduler",
            "Automated inter-shot data acquisition scheduler",
            "software",
        )
        experiment_collections = register_experiment_data_collections(
            client, base_url, scheduler_id
        )
        register_mast_annotations(client, base_url)
        efit_source_id = register_efit_provenance(client, base_url, scheduler_id)
        thomson_instrument_id = register_thomson_instrument_provenance(client, base_url)
        mast_upgrade = register_mast_upgrade_datasets(client, base_url)
        jintrac = register_jintrac_collection(client, base_url)

        eq_id = client.get(
            f"{base_url}/devices/mast/shots/30421/datasets/equilibrium"
        ).json()[0]["id"]

    return {
        "mast_30420_experiment_collection_id": experiment_collections["30420"],
        "mast_30421_experiment_collection_id": experiment_collections["30421"],
        "efit_source_id": efit_source_id,
        "thomson_instrument_source_id": thomson_instrument_id,
        "mast_upgrade_raw_collection_id": mast_upgrade["raw_collection_id"],
        "mast_upgrade_analysed_collection_id": mast_upgrade["analysed_collection_id"],
        "jintrac_collection_id": jintrac["collection_id"],
        "jintrac_activity_id": jintrac["activity_id"],
        "mast_30421_equilibrium_id": eq_id,
    }


if __name__ == "__main__":
    fds_url = os.environ.get("FDS_API_URL", FDS_API_URL_DEFAULT)
    kc_url = os.environ.get("KEYCLOAK_URL", KC_TOKEN_URL_DEFAULT)

    print(f"Seeding FDS at {fds_url}...")
    headers = get_admin_headers(kc_url)
    result = seed_all(fds_url, headers)
    print("Done. Summary:")
    for k, v in result.items():
        print(f"  {k}: {v}")
