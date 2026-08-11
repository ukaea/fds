"""Full-stack feature annotation: 1D extents on scientific_metadata surface via the API.

Shot 30421 is seeded with three features (see ``demo/seed_metadata.py``): an H-mode
window and a disruption on the ``time`` axis, and an MHD mode on ``frequency``.
"""

import pytest

from tests.integration.conftest import FDS_URL

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded_data")]

SHOT_URL = f"{FDS_URL}/devices/mast/shots/30421"
LD_HEADERS = {"Accept": "application/ld+json"}


def test_shot_features_carry_extents(http_client):
    resp = http_client.get(SHOT_URL)
    assert resp.status_code == 200
    by_name = {p["name"]: p for p in resp.json()["scientific_metadata"]}

    # A range on the time axis (the H-mode window) keeps its start and end.
    h_mode = by_name["confinement_mode"]["extent"]
    assert h_mode["dimension"] == "time"
    assert h_mode["end"] is not None

    # A point on the time axis (the disruption) has no end.
    assert by_name["disruption"]["extent"].get("end") is None

    # A feature on a non-time axis (the MHD mode) rides on frequency.
    assert by_name["mode"]["extent"]["dimension"] == "frequency"


def test_extents_project_into_jsonld(http_client):
    resp = http_client.get(SHOT_URL, headers=LD_HEADERS)
    assert resp.status_code == 200
    props = {p["schema:name"]: p for p in resp.json()["schema:additionalProperty"]}

    # The time extent projects to a W3C Time interval; other axes to a numeric range.
    assert props["confinement_mode"]["time:hasTime"]["@type"] == "time:Interval"
    assert "schema:valueReference" in props["mode"]


def test_find_mast_shots_that_disrupted(http_client):
    """Catalogue question one, answered server-side in a single request."""
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots", params={"annotation": "disruption"}
    )

    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_find_equilibrium_datasets_from_elmy_mastu_shots(http_client):
    """Catalogue question two: spans shot annotations and dataset names in one request.

    MAST-U seeds two shots with an equilibrium dataset each: 50000 transitioned to
    H-mode and ELMed, 50001 never left L-mode. The filter must return the first and
    exclude the second, so this asserts what is left out as well as what comes back.
    """
    url = f"{FDS_URL}/devices/mastu/datasets"
    params = {"name": "equilibrium"}

    unfiltered = http_client.get(url, params=params)
    assert unfiltered.status_code == 200
    assert sorted(d["shot_id"] for d in unfiltered.json()) == ["50000", "50001"]

    resp = http_client.get(url, params={**params, "shot_annotation": "elm"})
    assert resp.status_code == 200
    assert [(d["name"], d["shot_id"]) for d in resp.json()] == [
        ("equilibrium", "50000")
    ]


def test_shot_annotation_filter_excludes_the_l_mode_shot(http_client):
    """The exclusion is on the ELM annotation, not on having no metadata at all.

    Both MAST-U shots spent time in L-mode, so that value alone separates nothing;
    only 50000 went on to ELM.
    """
    resp = http_client.get(
        f"{FDS_URL}/devices/mastu/shots",
        params={"annotation": "confinement_mode:L-mode"},
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["50000", "50001"]

    resp = http_client.get(
        f"{FDS_URL}/devices/mastu/shots", params={"annotation": "elm"}
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["50000"]


def test_transition_query_finds_the_shot_that_was_in_both_modes(http_client):
    """A mode holds over a window, so a shot can carry `confinement_mode` twice.

    Each annotation is matched against the whole list independently, so requiring
    both values asks for a shot that was in both at some point: 50000 transitioned,
    50001 never left L-mode.
    """
    resp = http_client.get(
        f"{FDS_URL}/devices/mastu/shots",
        params={"annotation": ["confinement_mode:L-mode", "confinement_mode:H-mode"]},
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["50000"]


def test_filter_by_annotation_value(http_client):
    """H-mode is distinguishable from other confinement modes."""
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots",
        params={"annotation": "confinement_mode:H-mode"},
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]

    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots",
        params={"annotation": "confinement_mode:L-mode"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_unannotated_shots_are_excluded(http_client):
    """Shot 30420 carries no scientific metadata at all."""
    all_shots = http_client.get(f"{FDS_URL}/devices/mast/shots").json()
    assert "30420" in [s["id"] for s in all_shots]

    annotated = http_client.get(
        f"{FDS_URL}/devices/mast/shots", params={"annotation": "disruption"}
    ).json()
    assert "30420" not in [s["id"] for s in annotated]
