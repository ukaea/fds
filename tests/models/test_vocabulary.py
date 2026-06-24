import pytest
from pydantic import ValidationError

from app.models.activity import ActivityCreate, ActivityType, ActivityUpdate


class TestActivityType:
    def test_valid_values(self):
        for value in ("measurement", "simulation", "analysis", "calibration"):
            assert ActivityType(value).value == value

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ActivityType("SIMULATION")

    def test_activity_create_accepts_valid_type(self):
        act = ActivityCreate(source_id=1, activity_type="simulation")  # type: ignore[arg-type]
        assert act.activity_type == ActivityType.SIMULATION

    def test_activity_create_rejects_invalid_type(self):
        with pytest.raises(ValidationError):
            ActivityCreate(source_id=1, activity_type="RUN_1")  # type: ignore[arg-type]

    def test_activity_update_accepts_valid_type(self):
        upd = ActivityUpdate(activity_type="analysis")  # type: ignore[arg-type]
        assert upd.activity_type == ActivityType.ANALYSIS

    def test_null_activity_type_allowed(self):
        act = ActivityCreate(source_id=1)
        assert act.activity_type is None
