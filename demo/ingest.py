# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.23.2",
#     "httpx==0.27.2",
# ]
# ///

import marimo

__generated_with = "0.23.14"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # FDS — Registering Data

    This notebook walks through all the ways to register data in FDS: devices, shots,
    datasets, collections, and provenance activities.

    Full docs: **[http://localhost:4001/demo/ingest/](http://localhost:4001/demo/ingest/)**

    There is also a plain script that can be run to populate a fresh demo instance:
    ```bash
    uv run demo/seed_metadata.py
    ```
    """)
    return


@app.cell
def _():
    import httpx
    import marimo as mo

    # `seed_metadata` is a sibling module (demo/seed_metadata.py). Import it directly
    # rather than as `demo.seed_metadata`: marimo runs the notebook with its own dir
    # (demo/) on sys.path, not the repo root, so the `demo` package isn't resolvable.
    from seed_metadata import (
        get_admin_headers,
        get_or_create_source,
        register_devices_and_shots,
        register_efit_provenance,
        register_experiment_data_collections,
        register_jintrac_collection,
        register_mast_datasets,
        register_mast_upgrade_datasets,
    )

    return (
        get_admin_headers,
        get_or_create_source,
        httpx,
        mo,
        register_devices_and_shots,
        register_efit_provenance,
        register_experiment_data_collections,
        register_jintrac_collection,
        register_mast_datasets,
        register_mast_upgrade_datasets,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Environment
    """)
    return


@app.cell
def _(mo):
    fds_url_input = mo.ui.text(
        value="http://localhost:8000/api/v1", label="FDS API URL", full_width=True
    )
    kc_url_input = mo.ui.text(
        value="http://localhost:8080/realms/fds/protocol/openid-connect/token",
        label="Keycloak token URL",
        full_width=True,
    )
    mo.vstack([fds_url_input, kc_url_input])
    return fds_url_input, kc_url_input


@app.cell
def _(fds_url_input, kc_url_input):
    FDS_API_URL = fds_url_input.value
    KEYCLOAK_URL = kc_url_input.value
    return FDS_API_URL, KEYCLOAK_URL


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Authentication — [docs](http://localhost:4001/demo/ingest/#2-authentication)
    """)
    return


@app.cell
def _(KEYCLOAK_URL, get_admin_headers, mo):
    headers = get_admin_headers(KEYCLOAK_URL, retries=1)
    mo.callout(mo.md("Authenticated with Keycloak."), kind="success")
    return (headers,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2b. Devices & Shots — [docs](http://localhost:4001/demo/ingest/#2b-devices-and-shots)
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, mo, register_devices_and_shots):
    with httpx.Client(headers=headers, timeout=30.0) as _client:
        register_devices_and_shots(_client, FDS_API_URL)
    mo.callout(
        mo.md(
            "Devices and shots registered: **mast** (30420, 30421), **mast-upgrade** (50000)."
        ),
        kind="success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. MAST Datasets — [docs](http://localhost:4001/demo/ingest/#3-mast-datasets)

    12 IDS groups per shot registered as individual `application/x-zarr` datasets.
    Each group lives at `s3://fds-data/shots/{shot_id}/{ids_name}`.
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, mo, register_mast_datasets):
    with httpx.Client(headers=headers, timeout=60.0) as _client:
        register_mast_datasets(_client, FDS_API_URL)
    mo.callout(
        mo.md("MAST datasets registered for shots 30420 and 30421."), kind="success"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.1 Experiment Data Collections — [docs](http://localhost:4001/demo/ingest/#31-experiment-data-collections)

    All `Datasets` for each shot are grouped into an **Experiment Data** collection.
    Each collection is linked to a `measurement` activity from the intershot scheduler,
    recording when and how the data was collected.

    **Source → Activity → Collection** is the core provenance pattern.
    """)
    return


@app.cell
def _(
    FDS_API_URL,
    get_or_create_source,
    headers,
    httpx,
    mo,
    register_experiment_data_collections,
):
    with httpx.Client(headers=headers, timeout=60.0) as _client:
        _sched_id = get_or_create_source(
            _client,
            FDS_API_URL,
            "intershot-scheduler",
            "Automated inter-shot data acquisition scheduler",
        )
        _cols = register_experiment_data_collections(_client, FDS_API_URL, _sched_id)
    mo.callout(
        mo.md(
            f"Experiment Data collections created: shot 30420 → id={_cols['30420']}, shot 30421 → id={_cols['30421']}"
        ),
        kind="success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.2 EFIT Provenance — [docs](http://localhost:4001/concepts/provenance/)

    The EFIT equilibrium reconstruction code is registered as a **Source**. An **Activity**
    records the specific run on each shot, then is attached to the equilibrium dataset via
    `activity_id` (`prov:wasGeneratedBy`).

    See [ADR-0025](http://localhost:4001/adrs/0025-prov-o-agent-activity-separation/).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, mo, register_efit_provenance):
    with httpx.Client(headers=headers, timeout=30.0) as _client:
        _efit_id = register_efit_provenance(_client, FDS_API_URL)
    mo.callout(
        mo.md(
            f"EFIT source registered (id={_efit_id}). Activities attached to equilibrium on shots 30420 and 30421."
        ),
        kind="success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3b. MAST-U Shot 50000 — [docs](http://localhost:4001/demo/ingest/#3b-mast-u-shot-50000)

    Shot 50000 demonstrates two access tiers and how one can use `icechunk` to store versioned `Datasets`:

    - **raw-diagnostics** — 3 `restricted` NetCDF files (unprocessed diagnostic outputs)
    - **analysed** — 9 `public` IDS datasets as groups in a single `icechunk` store, with a shared `root_url`
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, mo, register_mast_upgrade_datasets):
    with httpx.Client(headers=headers, timeout=60.0) as _client:
        _mu = register_mast_upgrade_datasets(_client, FDS_API_URL)
    mo.callout(
        mo.md(
            f"MAST-U collections registered:\n"
            f"- raw-diagnostics (restricted) id={_mu['raw_collection_id']}\n"
            f"- analysed (public, `icechunk`) id={_mu['analysed_collection_id']}"
        ),
        kind="success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Downstream Modelling Example — [docs](http://localhost:4001/demo/ingest/#4-jintrac-integrated-modelling)

    Full provenance cycle for a simulation run:

    1. **Source** — `jintrac` (the code)
    2. **Activity** — this specific run (version, timestamps, parameters)
    3. **`prov:used`** — inputs recorded: equilibrium, magnetics, thomson_scattering
    4. **Output datasets** — linked via `activity_id` (`prov:wasGeneratedBy`)
    5. **Collection** — groups all outputs as a citable unit

    See [Provenance](http://localhost:4001/concepts/provenance/) and [ADR-0025](http://localhost:4001/adrs/0025-prov-o-agent-activity-separation/).
    """)
    return


@app.cell
def _(FDS_API_URL, headers, httpx, mo, register_jintrac_collection):
    with httpx.Client(headers=headers, timeout=60.0) as _client:
        _jintrac = register_jintrac_collection(_client, FDS_API_URL)
    mo.callout(
        mo.md(
            f"JINTRAC run registered:\n"
            f"- Source: jintrac\n"
            f"- Activity id={_jintrac['activity_id']} (inputs: equilibrium, magnetics, thomson_scattering)\n"
            f"- Collection jintrac-v220922 id={_jintrac['collection_id']}"
        ),
        kind="success",
    )
    return


if __name__ == "__main__":
    app.run()
