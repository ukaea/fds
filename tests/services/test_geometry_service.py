"""Reference-geometry resolution and validation."""

from datetime import datetime

import pytest
from sqlmodel import Session

from app.models.coverage import Coverage, DateRange, ShotRange
from app.models.dataset import DatasetCreate, DatasetUpdate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.services.device_service import DeviceService
from app.services.exceptions import ConflictError, FDSValidationError
from app.services.shot_service import ShotService

pytestmark = pytest.mark.usefixtures("device")


def test_resolve_explicit_shot(geometry, make_version, get_shot):
    version = make_version("v", ["pos"], Coverage(shots=["100"]))
    assert geometry.resolve(get_shot("100"), ["pos"])["pos"].id == version.id
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"] is None


def test_resolve_shot_range(geometry, make_version, get_shot):
    coverage = Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="200")])
    version = make_version("v", ["pos"], coverage)
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"].id == version.id
    # The endpoint shot is inclusive.
    assert geometry.resolve(get_shot("200"), ["pos"])["pos"].id == version.id
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"] is None


def test_resolve_date_range(geometry, make_version, get_shot):
    coverage = Coverage(
        date_ranges=[
            DateRange(from_date=datetime(2008, 1, 1), to_date=datetime(2009, 1, 1))
        ]
    )
    version = make_version("v", ["pos"], coverage)
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"].id == version.id
    # Half-open: a shot at the exact end date is not covered.
    assert geometry.resolve(get_shot("200"), ["pos"])["pos"] is None
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"] is None


def test_resolve_open_ended_shot_range(geometry, make_version, get_shot):
    coverage = Coverage(shot_ranges=[ShotRange(from_shot="200")])
    version = make_version("v", ["pos"], coverage)
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"].id == version.id
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"] is None


def test_resolve_open_ended_date_range(geometry, make_version, get_shot):
    coverage = Coverage(date_ranges=[DateRange(from_date=datetime(2009, 1, 1))])
    version = make_version("v", ["pos"], coverage)
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"].id == version.id
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"] is None


def test_resolve_uncovered_shot(geometry, make_version, get_shot):
    make_version("v", ["pos"], Coverage(shots=["100"]))
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"] is None


def test_resolve_undated_shot_explicit_only(geometry, make_version, get_shot):
    explicit = make_version("explicit", ["pos"], Coverage(shots=["undated"]))
    make_version(
        "ranged",
        ["other"],
        Coverage(date_ranges=[DateRange(from_date=datetime(2000, 1, 1))]),
    )
    undated = get_shot("undated")
    assert geometry.resolve(undated, ["pos"])["pos"].id == explicit.id
    # A range never covers an undated shot.
    assert geometry.resolve(undated, ["other"])["other"] is None


def test_resolve_multiple_references(geometry, make_version, get_shot):
    thomson = make_version("thomson", ["thomson"], Coverage(shots=["150"]))
    bolo = make_version("bolo", ["bolometer"], Coverage(shots=["150"]))
    resolved = geometry.resolve(get_shot("150"), ["thomson", "bolometer"])
    assert resolved["thomson"].id == thomson.id
    assert resolved["bolometer"].id == bolo.id


def test_resolve_multi_role_bundle(geometry, make_version, get_shot):
    bundle = make_version("bundle", ["thomson", "bolometer"], Coverage(shots=["150"]))
    resolved = geometry.resolve(get_shot("150"), ["thomson", "bolometer"])
    assert resolved["thomson"].id == bundle.id
    assert resolved["bolometer"].id == bundle.id


def test_resolve_carve_out_blip(geometry, make_version, get_shot):
    surrounding = make_version(
        "surrounding",
        ["pos"],
        Coverage(
            shot_ranges=[
                ShotRange(from_shot="100", to_shot="150"),
                ShotRange(from_shot="201", to_shot="300"),
            ]
        ),
    )
    blip = make_version("blip", ["pos"], Coverage(shots=["200"]))
    assert geometry.resolve(get_shot("200"), ["pos"])["pos"].id == blip.id
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"].id == surrounding.id
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"].id == surrounding.id


def test_global_geometry_roles_rejected(make_global_version):
    coverage = Coverage(date_ranges=[DateRange(from_date=datetime(2008, 1, 1))])
    with pytest.raises(FDSValidationError):
        make_global_version("a", ["pos"], coverage)


def test_global_geometry_references_rejected(datasets, admin_user):
    with pytest.raises(FDSValidationError):
        datasets.create(
            DatasetCreate(
                name="global_signal",
                level=2,
                geometry_references=["pos"],
                url="s3://signals/global.zarr",
            ),
            user=admin_user,
        )


def test_shot_level_geometry_version_rejected(make_version):
    with pytest.raises(FDSValidationError):
        make_version("shot_level_geom", ["pos"], Coverage(shots=["150"]), shot_id="150")


def test_shot_level_signal_may_reference_geometry(
    geometry, make_version, make_signal, get_shot
):
    version = make_version("geom", ["pos"], Coverage(shots=["150"]))
    assert make_signal(["pos"]).id is not None
    assert geometry.resolve(get_shot("150"), ["pos"])["pos"].id == version.id


def test_cross_device_same_role_window_allowed(
    session: Session, datasets, make_version, admin_user
):
    window = Coverage(shots=["150"])
    make_version("mast_ver", ["pos"], window)
    # Same role and shot id on a second device is a separate scope, so no conflict.
    DeviceService(session).create(DeviceCreate(name="NSTX", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(id="150", device_name="NSTX", shot_at=datetime(2008, 6, 1)),
        admin_user,
    )
    datasets.create(
        DatasetCreate(
            name="nstx_ver",
            level=0,
            device_name="NSTX",
            geometry_roles=["pos"],
            applies_to=window,
            url="s3://geometry/nstx.nc",
        ),
        user=admin_user,
    )


def test_overlap_explicit_ids_rejected(make_version):
    make_version("a", ["pos"], Coverage(shots=["100"]))
    with pytest.raises(FDSValidationError):
        make_version("b", ["pos"], Coverage(shots=["100"]))


def test_duplicate_version_is_conflict_not_overlap(make_version):
    """Re-registering the identical version reads as a duplicate (409), not the
    coverage-overlap validation error (422) a *differently named* version covering
    the same shot raises — the version would otherwise trivially overlap itself."""
    make_version("v", ["pos"], Coverage(shots=["100"]))
    with pytest.raises(ConflictError):
        make_version("v", ["pos"], Coverage(shots=["100"]))


def test_overlap_intervals_rejected(make_version):
    make_version(
        "a",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="200")]),
    )
    with pytest.raises(FDSValidationError):
        make_version(
            "b",
            ["pos"],
            Coverage(shot_ranges=[ShotRange(from_shot="150", to_shot="300")]),
        )


def test_overlap_explicit_inside_interval_rejected(make_version):
    make_version(
        "a",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="300")]),
    )
    with pytest.raises(FDSValidationError):
        make_version("b", ["pos"], Coverage(shots=["200"]))


def test_adjacent_windows_allowed(make_version):
    make_version(
        "a",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="200")]),
    )
    # Starts at shot 201, the day after shot 200 — touching but not overlapping.
    make_version(
        "b",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="201", to_shot="300")]),
    )


def test_touching_date_windows_allowed(make_version):
    make_version(
        "a",
        ["pos"],
        Coverage(
            date_ranges=[
                DateRange(from_date=datetime(2008, 1, 1), to_date=datetime(2009, 1, 1))
            ]
        ),
    )
    make_version(
        "b",
        ["pos"],
        Coverage(
            date_ranges=[
                DateRange(from_date=datetime(2009, 1, 1), to_date=datetime(2010, 1, 1))
            ]
        ),
    )


def test_same_shot_different_role_allowed(make_version):
    make_version("a", ["thomson"], Coverage(shots=["100"]))
    make_version("b", ["bolometer"], Coverage(shots=["100"]))


def test_missing_range_endpoint_rejected(make_version):
    coverage = Coverage(shot_ranges=[ShotRange(from_shot="999")])
    with pytest.raises(FDSValidationError):
        make_version("a", ["pos"], coverage)


def test_endpoint_without_shot_at_rejected(make_version):
    coverage = Coverage(shot_ranges=[ShotRange(from_shot="undated")])
    with pytest.raises(FDSValidationError):
        make_version("a", ["pos"], coverage)


def test_shot_at_edit_into_window_rejected(make_version, update_shot):
    make_version(
        "ranged",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="150")]),
    )
    make_version("explicit", ["pos"], Coverage(shots=["300"]))
    # Moving shot 300 into the ranged window would make it covered by both.
    with pytest.raises(FDSValidationError):
        update_shot("300", shot_at=datetime(2008, 3, 1))


def test_harmless_shot_at_edit_allowed(make_version, update_shot):
    make_version(
        "ranged",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="150")]),
    )
    make_version("explicit", ["pos"], Coverage(shots=["300"]))
    updated = update_shot("300", shot_at=datetime(2011, 1, 1))
    assert updated.shot_at == datetime(2011, 1, 1)


def test_delete_explicit_member_rejected(make_version, delete_shot):
    make_version("explicit", ["pos"], Coverage(shots=["300"]))
    with pytest.raises(FDSValidationError):
        delete_shot("300")


def test_delete_range_endpoint_rejected(make_version, delete_shot):
    make_version(
        "ranged",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="150")]),
    )
    with pytest.raises(FDSValidationError):
        delete_shot("100")


def test_delete_unreferenced_shot_allowed(make_version, delete_shot):
    make_version("explicit", ["pos"], Coverage(shots=["300"]))
    assert delete_shot("150") is True


def test_update_version_excludes_self_from_overlap(
    datasets, geometry, make_version, get_shot, admin_user
):
    version = make_version(
        "v",
        ["pos"],
        Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="150")]),
    )
    # Widening the same version must not conflict with itself.
    datasets.update(
        id=version.id,
        obj_in=DatasetUpdate(
            applies_to=Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="300")])
        ),
        user=admin_user,
    )
    assert geometry.resolve(get_shot("300"), ["pos"])["pos"].id == version.id
