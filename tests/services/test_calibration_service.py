"""Reference-calibration resolution and staged-chain validation (ADR-0037).

The resolution selectors, reference integrity, and shot-edit/delete protection
are the shared ADR-0036 engine, exercised by ``test_geometry_service``. These
tests cover only what calibration adds: ordered chains and per-``(role, stage)``
non-overlap.
"""

import pytest

from app.models.dataset import DatasetCreate
from app.models.reference import ReferenceCoverage, ShotRange
from app.services.exceptions import FDSValidationError

pytestmark = pytest.mark.usefixtures("device")

DEVICE = "MAST"


def _create(datasets, admin_user, **kwargs):
    return datasets.create(DatasetCreate(device_name=DEVICE, **kwargs), user=admin_user)


def test_resolve_single_stage(calibration, make_cal_version, get_shot):
    version = make_cal_version(
        "gain", ["gain"], ReferenceCoverage(shots=["150"]), stage=1
    )
    chain = calibration.resolve_chain(get_shot("150"), ["gain"])
    assert [v.id for v in chain["gain"]] == [version.id]
    # resolve() collapses the chain to its single covering version.
    assert calibration.resolve(get_shot("150"), ["gain"])["gain"].id == version.id


def test_resolve_chain_ordered_by_stage(calibration, make_cal_version, get_shot):
    # Register out of stage order to prove the sort, not insertion order.
    absolute = make_cal_version(
        "absolute", ["signal"], ReferenceCoverage(shots=["150"]), stage=3
    )
    gain = make_cal_version(
        "gain", ["signal"], ReferenceCoverage(shots=["150"]), stage=1
    )
    wavelength = make_cal_version(
        "wavelength", ["signal"], ReferenceCoverage(shots=["150"]), stage=2
    )
    chain = calibration.resolve_chain(get_shot("150"), ["signal"])
    assert [v.id for v in chain["signal"]] == [gain.id, wavelength.id, absolute.id]


def test_same_role_different_stage_overlap_allowed(make_cal_version):
    # gain and absolute both cover shot 150 for 'signal' — different stages, no clash.
    make_cal_version("gain", ["signal"], ReferenceCoverage(shots=["150"]), stage=1)
    make_cal_version("absolute", ["signal"], ReferenceCoverage(shots=["150"]), stage=2)


def test_same_role_same_stage_overlap_rejected(make_cal_version):
    make_cal_version("a", ["signal"], ReferenceCoverage(shots=["150"]), stage=1)
    with pytest.raises(FDSValidationError):
        make_cal_version("b", ["signal"], ReferenceCoverage(shots=["150"]), stage=1)


def test_same_stage_interval_overlap_rejected(make_cal_version):
    make_cal_version(
        "a",
        ["signal"],
        ReferenceCoverage(shot_ranges=[ShotRange(from_shot="100", to_shot="200")]),
        stage=1,
    )
    with pytest.raises(FDSValidationError):
        make_cal_version(
            "b",
            ["signal"],
            ReferenceCoverage(shot_ranges=[ShotRange(from_shot="150", to_shot="300")]),
            stage=1,
        )


def test_uncovered_shot_yields_empty_chain(calibration, make_cal_version, get_shot):
    make_cal_version("gain", ["signal"], ReferenceCoverage(shots=["150"]), stage=1)
    assert calibration.resolve_chain(get_shot("300"), ["signal"])["signal"] == []
    assert calibration.resolve(get_shot("300"), ["signal"])["signal"] is None


def test_chain_includes_only_covering_stages(calibration, make_cal_version, get_shot):
    # Stage 1 spans 100–300; stage 2 covers only shot 150. Each stage resolves
    # independently, so shot 300 sees a one-link chain and shot 150 a two-link one.
    gain = make_cal_version(
        "gain",
        ["signal"],
        ReferenceCoverage(shot_ranges=[ShotRange(from_shot="100", to_shot="300")]),
        stage=1,
    )
    absolute = make_cal_version(
        "absolute", ["signal"], ReferenceCoverage(shots=["150"]), stage=2
    )
    at_150 = calibration.resolve_chain(get_shot("150"), ["signal"])["signal"]
    at_300 = calibration.resolve_chain(get_shot("300"), ["signal"])["signal"]
    assert [v.id for v in at_150] == [gain.id, absolute.id]
    assert [v.id for v in at_300] == [gain.id]


def test_calibrated_geometry_resolves_at_anchor_shot(datasets, admin_user):
    # A geometry version that itself references calibration. Including geometry
    # for the signal surfaces that version's calibration, resolved at the
    # signal's shot — the version is device-level and has no shot of its own.
    cal = _create(
        datasets,
        admin_user,
        name="cal",
        level=0,
        calibration_roles=["gain"],
        calibration_stage=1,
        applies_to=ReferenceCoverage(shots=["150"]),
        url="s3://cal/gain.nc",
    )
    geom = _create(
        datasets,
        admin_user,
        name="geom",
        level=0,
        geometry_roles=["pos"],
        calibration_references=["gain"],
        applies_to=ReferenceCoverage(shots=["150"]),
        url="s3://geom/pos.nc",
    )
    signal = _create(
        datasets,
        admin_user,
        name="Te",
        level=2,
        shot_id="150",
        geometry_references=["pos"],
        url="s3://sig/te.zarr",
    )

    model = datasets.to_read_model(signal, include_geometry=True)
    assert [g.id for g in model.geometry] == [geom.id]
    assert [c.id for c in model.geometry[0].calibration] == [cal.id]


def test_reference_cycle_terminates(datasets, admin_user):
    # geom references calibration 'cal'; cal (providing 'cal') references geometry
    # 'pos' back to geom. Resolution must terminate via the cycle guard, emitting
    # the repeated node one level deep but not descending into it again.
    geom = _create(
        datasets,
        admin_user,
        name="geom",
        level=0,
        geometry_roles=["pos"],
        calibration_references=["cal"],
        applies_to=ReferenceCoverage(shots=["150"]),
        url="s3://geom/pos.nc",
    )
    cal = _create(
        datasets,
        admin_user,
        name="cal",
        level=0,
        calibration_roles=["cal"],
        calibration_stage=1,
        geometry_references=["pos"],
        applies_to=ReferenceCoverage(shots=["150"]),
        url="s3://cal/c.nc",
    )
    signal = _create(
        datasets,
        admin_user,
        name="Te",
        level=2,
        shot_id="150",
        geometry_references=["pos"],
        url="s3://sig/te.zarr",
    )

    model = datasets.to_read_model(signal, include_geometry=True)
    nested_geom = model.geometry[0].calibration[0].geometry[0]
    assert model.geometry[0].id == geom.id
    assert model.geometry[0].calibration[0].id == cal.id
    assert nested_geom.id == geom.id
    # The cycle stops here: the repeated geometry node is not descended again.
    assert nested_geom.calibration is None
