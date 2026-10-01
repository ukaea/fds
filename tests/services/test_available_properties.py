import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.available_properties import AvailableProperties, AvailableProperty
from app.models.device import DeviceCreate
from app.models.identity import ANONYMOUS_USER
from app.models.policy import AccessLevel
from app.models.scientific_metadata import Extent, MetadataKind, ScientificProperty
from app.models.shot import ShotCreate
from app.services.device_service import DeviceService
from app.services.exceptions import FDSValidationError
from app.services.shot_service import ShotService

MAST = "MAST"
MAST_U = "MAST-U"


def prop(properties: AvailableProperties, name: str) -> AvailableProperty:
    """The one prop with this name. Absence is a test failure, not a value."""
    match = next((f for f in properties.properties if f.name == name), None)
    assert match is not None, f"no prop named {name!r} in {names(properties)}"
    return match


def names(properties: AvailableProperties) -> set[str]:
    return {f.name for f in properties.properties}


def seed(session: Session, user: AuthenticatedUser, device: str, shots) -> None:
    """Create ``device`` and the given ``(shot_id, kwargs)`` shots under it."""
    DeviceService(session).create(
        DeviceCreate(name=device, type="Tokamak", access_level=AccessLevel.PUBLIC),
        user,
    )
    service = ShotService(session)
    for shot_id, kwargs in shots:
        service.create(ShotCreate(id=shot_id, device_name=device, **kwargs), user)


# --- Counting and enumeration -------------------------------------------------


@pytest.fixture(name="catalogue")
def catalogue_fixture(session: Session, admin_user: AuthenticatedUser) -> None:
    """One device whose shots exercise every shape the aggregate has to handle."""
    seed(
        session,
        admin_user,
        MAST,
        [
            # Unannotated: scientific_metadata is NULL. Counts towards total,
            # contributes to no prop.
            ("30420", {"access_level": AccessLevel.PUBLIC}),
            (
                "30421",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M9"),
                        ScientificProperty(name="current", value=500630.7, unit="A"),
                        ScientificProperty(
                            name="flat_top",
                            value=True,
                            extent=Extent(dimension="time", start=0.06, end=0.27),
                        ),
                    ],
                },
            ),
            (
                "30422",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M9"),
                        ScientificProperty(name="current", value=508396.4, unit="A"),
                    ],
                },
            ),
            (
                "30423",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M5"),
                        # The same name twice on one shot: one record, two values.
                        ScientificProperty(name="mode", value="L-mode"),
                        ScientificProperty(name="mode", value="H-mode"),
                    ],
                },
            ),
        ],
    )


@pytest.mark.usefixtures("catalogue")
def test_total_counts_every_shot_including_unannotated(session: Session) -> None:
    properties = ShotService(session).available_properties(MAST)
    assert properties.total == 4


@pytest.mark.usefixtures("catalogue")
def test_records_counts_shots_not_annotation_entries(session: Session) -> None:
    """Shot 30423 carries `mode` twice: one record, two distinct values."""
    mode = prop(ShotService(session).available_properties(MAST), "mode")
    assert mode.records == 1
    assert mode.distinct == 2


@pytest.mark.usefixtures("catalogue")
def test_values_are_enumerated_and_sorted_under_the_cap(session: Session) -> None:
    campaign = prop(ShotService(session).available_properties(MAST), "campaign")
    assert campaign.records == 3
    assert campaign.distinct == 2
    assert campaign.values == ["M5", "M9"]


@pytest.mark.usefixtures("catalogue")
def test_values_omitted_over_the_cap(session: Session) -> None:
    campaign = prop(
        ShotService(session).available_properties(MAST, max_values=1), "campaign"
    )
    assert campaign.distinct == 2
    assert campaign.values is None


@pytest.mark.usefixtures("catalogue")
def test_raising_the_cap_enumerates_a_previously_omitted_name(
    session: Session,
) -> None:
    service = ShotService(session)
    assert (
        prop(service.available_properties(MAST, max_values=1), "current").values is None
    )
    current = prop(service.available_properties(MAST, max_values=50), "current")
    assert current.values == ["500630.7", "508396.4"]


@pytest.mark.usefixtures("catalogue")
def test_max_values_zero_keeps_counts_and_drops_every_value(session: Session) -> None:
    properties = ShotService(session).available_properties(MAST, max_values=0)
    assert all(f.values is None for f in properties.properties)
    assert prop(properties, "campaign").distinct == 2


@pytest.mark.usefixtures("catalogue")
def test_booleans_are_rendered_as_the_filter_matches_them(session: Session) -> None:
    """`flat_top` stores JSON true; the filter compares against the text 'true'."""
    flat_top = prop(ShotService(session).available_properties(MAST), "flat_top")
    assert flat_top.values == ["true"]


@pytest.mark.usefixtures("catalogue")
def test_unit_is_carried_through(session: Session) -> None:
    assert prop(ShotService(session).available_properties(MAST), "current").unit == "A"
    assert (
        prop(ShotService(session).available_properties(MAST), "campaign").unit is None
    )


@pytest.mark.usefixtures("catalogue")
def test_enumerable_names_sort_first_then_by_distinct_then_name(
    session: Session,
) -> None:
    properties = ShotService(session).available_properties(MAST, max_values=2)
    # current has 2 distinct values but is over the cap of... no: 2 <= 2, so it
    # enumerates. Cap at 1 to push it into the presence-only group.
    properties = ShotService(session).available_properties(MAST, max_values=1)
    names = [f.name for f in properties.properties]
    assert names[0] == "flat_top"  # 1 distinct, enumerable
    assert set(names[1:]) == {"campaign", "current", "mode"}
    assert all(f.values is None for f in properties.properties[1:])


@pytest.mark.usefixtures("catalogue")
def test_property_filter_narrows_total_and_properties(session: Session) -> None:
    properties = ShotService(session).available_properties(
        MAST, properties=["campaign:M9"]
    )
    assert properties.total == 2
    # Within this narrowed scope `campaign` is M9 on both shots, so it no longer
    # divides anything and is not offered. `current` still does.
    assert "campaign" not in names(properties)
    assert prop(properties, "current").distinct == 2


@pytest.mark.usefixtures("catalogue")
def test_max_values_out_of_range_raises(session: Session) -> None:
    service = ShotService(session)
    with pytest.raises(FDSValidationError):
        service.available_properties(MAST, max_values=-1)
    with pytest.raises(FDSValidationError):
        service.available_properties(MAST, max_values=10_000)


def test_properties_are_scoped_to_one_device(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    common = [ScientificProperty(name="campaign", value="M9")]
    seed(
        session,
        admin_user,
        MAST,
        [
            ("1", {"access_level": AccessLevel.PUBLIC, "scientific_metadata": common}),
            (
                "2",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M8")
                    ],
                },
            ),
        ],
    )
    seed(
        session,
        admin_user,
        MAST_U,
        [
            (
                "2",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="MU01")
                    ],
                },
            )
        ],
    )
    assert prop(ShotService(session).available_properties(MAST), "campaign").values == [
        "M8",
        "M9",
    ]


def test_a_device_with_no_shots_has_no_properties(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    seed(session, admin_user, MAST, [])
    properties = ShotService(session).available_properties(MAST)
    assert properties.total == 0
    assert properties.properties == []


# --- Access control -----------------------------------------------------------
#
# The aggregate reads no rows, so the per-row check the listing used to run has
# nothing to run against. These are the tests that fail if the policy allow-list
# is dropped.


@pytest.fixture(name="mixed_access")
def mixed_access_fixture(session: Session, admin_user: AuthenticatedUser) -> None:
    """One public shot and one restricted shot, each with a value the other lacks."""
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                "30419",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M4")
                    ],
                },
            ),
            (
                "30420",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M5")
                    ],
                },
            ),
            (
                "30421",
                {
                    "access_level": AccessLevel.RESTRICTED,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="SECRET-CAMPAIGN"),
                        ScientificProperty(name="classified", value="yes"),
                    ],
                },
            ),
        ],
    )


@pytest.mark.usefixtures("mixed_access")
def test_restricted_values_are_absent_for_anonymous(session: Session) -> None:
    properties = ShotService(session).available_properties(MAST, user=ANONYMOUS_USER)

    assert properties.total == 2
    campaign = prop(properties, "campaign")
    assert campaign.values == ["M4", "M5"]
    assert campaign.records == 2
    assert campaign.distinct == 2
    # The restricted shot's other annotation does not even appear as a name.
    assert "classified" not in names(properties)


@pytest.mark.usefixtures("mixed_access")
def test_restricted_values_are_present_for_an_entitled_caller(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    properties = ShotService(session).available_properties(MAST, user=admin_user)

    assert properties.total == 3
    assert prop(properties, "campaign").values == ["M4", "M5", "SECRET-CAMPAIGN"]
    assert "classified" in names(properties)


def test_required_scopes_gate_values(
    session: Session, admin_user: AuthenticatedUser, mast_admin_user: AuthenticatedUser
) -> None:
    """Exercises the non-null jsonb comparison in the policy clause."""
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                "30419",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M4")
                    ],
                },
            ),
            (
                "30420",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="M5")
                    ],
                },
            ),
            (
                "30421",
                {
                    "access_level": AccessLevel.RESTRICTED,
                    "required_scopes": ["mast_admin"],
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="GATED")
                    ],
                },
            ),
        ],
    )
    service = ShotService(session)

    scopeless = AuthenticatedUser(id="someone", scopes=())
    assert prop(
        service.available_properties(MAST, user=scopeless), "campaign"
    ).values == ["M4", "M5"]
    assert prop(
        service.available_properties(MAST, user=mast_admin_user), "campaign"
    ).values == ["GATED", "M4", "M5"]


def test_every_shot_unreadable_yields_an_empty_scope(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """The false() branch: nothing readable, no error, no leaked names."""
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                "30420",
                {
                    "access_level": AccessLevel.RESTRICTED,
                    "scientific_metadata": [
                        ScientificProperty(name="campaign", value="SECRET")
                    ],
                },
            )
        ],
    )
    properties = ShotService(session).available_properties(MAST, user=ANONYMOUS_USER)
    assert properties.total == 0
    assert properties.properties == []


@pytest.mark.usefixtures("mixed_access")
def test_listing_pages_only_over_readable_shots(session: Session) -> None:
    """The access check is a WHERE clause, so a page is not silently short."""
    service = ShotService(session)
    page = service.get_multi_by_device_name(
        MAST, user=ANONYMOUS_USER, offset=0, limit=2
    )
    assert [s.id for s in page] == ["30420", "30419"]

    # Offset 2 is past the end of what anonymous may read: the restricted shot
    # was never in the page to begin with, rather than dropped from it.
    assert (
        service.get_multi_by_device_name(MAST, user=ANONYMOUS_USER, offset=2, limit=2)
        == []
    )


# --- Kinds: declared and inferred ---------------------------------------------


def props(session: Session, user: AuthenticatedUser, entries, device: str = MAST):
    """A device whose shots carry one property each, from ``entries``."""
    seed(
        session,
        user,
        device,
        [
            (
                str(30000 + i),
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [entry],
                },
            )
            for i, entry in enumerate(entries)
        ],
    )


def test_a_numeric_property_with_few_repeated_values_is_a_term(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """The counter-example the ordering exists for.

    `current_range` is a target regime with three options, correctly stored as a
    number with a unit. Reading type before cardinality calls that a quantity
    and offers a slider over three points; reading cardinality first sees a
    vocabulary that happens to be numeric.
    """
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="current_range", value=v, unit="kA")
            for v in [400, 700, 1000] * 10
        ],
    )
    prop_ = prop(ShotService(session).available_properties(MAST), "current_range")

    assert prop_.kind is MetadataKind.TERM
    assert prop_.values == ["400", "700", "1000"]
    assert prop_.unit == "kA"


def test_a_numeric_property_with_a_value_per_record_is_a_quantity(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="plasma_current_max", value=500000.0 + i, unit="A")
            for i in range(40)
        ],
    )
    prop_ = prop(ShotService(session).available_properties(MAST), "plasma_current_max")

    assert prop_.kind is MetadataKind.QUANTITY
    assert prop_.min == 500000.0
    assert prop_.max == 500039.0
    assert prop_.values is None


def test_near_unique_strings_are_prose_and_never_offered(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """Prose describes one record rather than classifying it, so it is not a filter."""
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="postshot_comment", value=f"ran ok, trace {i}")
            for i in range(40)
        ],
    )
    assert "postshot_comment" not in names(
        ShotService(session).available_properties(MAST)
    )


def test_a_repeating_vocabulary_of_long_strings_is_a_term(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """Ratio, not length, separates a vocabulary from prose.

    `objective` runs to hundreds of characters but each value repeats many
    times, so it classifies by how often values recur rather than how long they
    are.
    """
    long_values = [f"{'PLASMA CONDITIONING AND SCAN ' * 4}{i}" for i in range(4)]
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="objective", value=long_values[i % 4])
            for i in range(40)
        ],
    )
    assert (
        prop(ShotService(session).available_properties(MAST), "objective").kind
        is MetadataKind.TERM
    )


def test_a_declared_kind_overrides_inference(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """A provider who knows better is obeyed rather than second-guessed."""
    props(
        session,
        admin_user,
        [
            ScientificProperty(
                name="setting", value=float(i), kind=MetadataKind.TERM, unit="kA"
            )
            for i in range(40)
        ],
    )
    prop_ = prop(ShotService(session).available_properties(MAST), "setting")

    # 40 distinct values with no repeats would infer QUANTITY.
    assert prop_.kind is MetadataKind.TERM


def test_a_declared_text_kind_removes_a_name_from_the_filter(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="note", value="draft", kind=MetadataKind.TEXT)
            for _ in range(30)
        ],
    )
    assert "note" not in names(ShotService(session).available_properties(MAST))


def test_an_annotation_reports_the_dimension_it_is_localised_on(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """An extent makes a property an annotation: a claim about a region of the data."""
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                str(i),
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": (
                        [
                            ScientificProperty(
                                name="flat_top",
                                value=True,
                                extent=Extent(
                                    dimension="time", start=0.06, end=0.27, unit="s"
                                ),
                            )
                        ]
                        if i % 2
                        else None
                    ),
                },
            )
            for i in range(30)
        ],
    )
    assert prop(
        ShotService(session).available_properties(MAST), "flat_top"
    ).dimension == ("time")


# --- Range filtering ----------------------------------------------------------


def test_ranges_bound_a_numeric_value(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="current", value=float(i * 100), unit="A")
            for i in range(40)
        ],
    )
    service = ShotService(session)

    assert service.available_properties(MAST, minimums=["current:2000"]).total == 20
    assert service.available_properties(MAST, maximums=["current:1900"]).total == 20
    assert (
        service.available_properties(
            MAST, minimums=["current:1000"], maximums=["current:1900"]
        ).total
        == 10
    )


def test_a_range_skips_values_that_are_not_numbers(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """The same name may hold a number on one record and a string on another.

    Casting a stray string to numeric aborts the whole query rather than
    skipping the row, so the comparison is guarded to numeric-looking text.
    """
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                "1",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="current", value=700.0)
                    ],
                },
            ),
            (
                "2",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="current", value="not a number")
                    ],
                },
            ),
        ],
    )
    assert (
        ShotService(session).available_properties(MAST, minimums=["current:100"]).total
        == 1
    )


def test_a_malformed_range_bound_is_rejected(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    seed(session, admin_user, MAST, [])
    service = ShotService(session)
    with pytest.raises(FDSValidationError):
        service.available_properties(MAST, minimums=["current:abc"])
    with pytest.raises(FDSValidationError):
        service.available_properties(MAST, minimums=["current"])


# --- Values sub-resource ------------------------------------------------------


def test_values_are_counted_and_searchable(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    props(
        session,
        admin_user,
        [
            ScientificProperty(name="objective", value=v)
            for v in ["PLASMA CONDITIONING"] * 5
            + ["VESSEL CONDITIONING"] * 3
            + ["FUELLING SCAN"] * 2
        ],
    )
    service = ShotService(session)

    everything = service.property_values(MAST, "objective")
    assert everything.distinct == 3
    # Most common first, so the useful ones are on the first page.
    assert [(v.value, v.records) for v in everything.values] == [
        ("PLASMA CONDITIONING", 5),
        ("VESSEL CONDITIONING", 3),
        ("FUELLING SCAN", 2),
    ]

    searched = service.property_values(MAST, "objective", query="conditioning")
    assert {v.value for v in searched.values} == {
        "PLASMA CONDITIONING",
        "VESSEL CONDITIONING",
    }
    assert searched.distinct == 2


def test_values_respect_access(session: Session, admin_user: AuthenticatedUser) -> None:
    """The values sub-resource is a read of the same records, under the same policy."""
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                "1",
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": [
                        ScientificProperty(name="objective", value="OPEN")
                    ],
                },
            ),
            (
                "2",
                {
                    "access_level": AccessLevel.RESTRICTED,
                    "scientific_metadata": [
                        ScientificProperty(name="objective", value="SECRET")
                    ],
                },
            ),
        ],
    )
    values = ShotService(session).property_values(
        MAST, "objective", user=ANONYMOUS_USER
    )
    assert [v.value for v in values.values] == ["OPEN"]


def test_a_name_on_every_record_with_one_value_is_not_offered(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """A filter that cannot divide the scope is not a filter.

    Every MAST shot records `flat_top: true`, so selecting it returns every
    shot. That it is true of the whole catalogue is worth knowing, but it is a
    fact about the data rather than a way to narrow it.
    """
    props(
        session,
        admin_user,
        [ScientificProperty(name="flat_top", value=True) for _ in range(30)],
    )
    assert "flat_top" not in names(ShotService(session).available_properties(MAST))


def test_the_same_name_is_offered_when_only_some_records_carry_it(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """Coverage is what matters, not the number of values.

    One value on *some* records does divide the scope: it is the difference
    between shots that flat-topped and shots that did not.
    """
    seed(
        session,
        admin_user,
        MAST,
        [
            (
                str(i),
                {
                    "access_level": AccessLevel.PUBLIC,
                    "scientific_metadata": (
                        [ScientificProperty(name="flat_top", value=True)]
                        if i % 2
                        else None
                    ),
                },
            )
            for i in range(30)
        ],
    )
    assert (
        prop(ShotService(session).available_properties(MAST), "flat_top").records == 15
    )
