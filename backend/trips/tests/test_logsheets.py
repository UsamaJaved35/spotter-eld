"""Log-sheet builder tests, anchored on FMCSA's own worked example."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from trips.services.logsheets import build_daily_logs
from trips.services.types import DutySegment, DutyStatus, StopKind

DAY = date(2021, 4, 9)


def seg(status, start_h, end_h, note="", location="", miles=0.0):
    base = datetime(2021, 4, 9)
    return DutySegment(
        status=status,
        start=base + timedelta(hours=start_h),
        end=base + timedelta(hours=end_h),
        kind=StopKind.DRIVE if status is DutyStatus.D else StopKind.OFF_DUTY,
        note=note,
        location=location,
        miles=miles,
    )


def john_doe_segments():
    """The completed log on p.18-19 of the Driver's Guide.

    John Doe runs Richmond, VA to Newark, NJ on 04/09/2021, 350 miles.
    """
    D, ON, OFF, SB = DutyStatus.D, DutyStatus.ON, DutyStatus.OFF, DutyStatus.SB
    return [
        seg(OFF, 0, 6, "Off duty", "Richmond, VA"),
        seg(ON, 6, 7.5, "Load, dispatch, pre-trip", "Richmond, VA"),
        seg(D, 7.5, 9, "Driving", "Richmond, VA", miles=90),
        seg(ON, 9, 9.5, "Fuel", "Fredericksburg, VA"),
        seg(D, 9.5, 12, "Driving", "Fredericksburg, VA", miles=110),
        seg(OFF, 12, 13, "Lunch", "Baltimore, MD"),
        seg(D, 13, 15, "Driving", "Baltimore, MD", miles=95),
        seg(ON, 15, 15.5, "Delivery stop", "Philadelphia, PA"),
        seg(D, 15.5, 16, "Driving", "Philadelphia, PA", miles=20),
        seg(SB, 16, 17.75, "Sleeper berth", "Cherry Hill, NJ"),
        seg(D, 17.75, 19, "Driving", "Cherry Hill, NJ", miles=35),
        seg(ON, 19, 21, "Post-trip and paperwork", "Newark, NJ"),
        seg(OFF, 21, 24, "Off duty", "Newark, NJ"),
    ]


def test_john_doe_totals_match_the_published_log():
    """The guide prints Off 10, SB 1.75, Driving 7.75, On 4.5 -- summing to 24."""
    logs = build_daily_logs(john_doe_segments())

    assert len(logs) == 1
    totals = logs[0].totals
    assert totals[DutyStatus.OFF] == pytest.approx(10.0)
    assert totals[DutyStatus.SB] == pytest.approx(1.75)
    assert totals[DutyStatus.D] == pytest.approx(7.75)
    assert totals[DutyStatus.ON] == pytest.approx(4.5)
    assert logs[0].total_hours == pytest.approx(24.0)
    assert logs[0].total_miles == pytest.approx(350)


def test_john_doe_remarks_name_every_duty_change():
    """Remarks must carry the city and state at each change of duty status."""
    logs = build_daily_logs(john_doe_segments())
    places = [r.location for r in logs[0].remarks]

    for expected in [
        "Richmond, VA",
        "Fredericksburg, VA",
        "Baltimore, MD",
        "Philadelphia, PA",
        "Cherry Hill, NJ",
        "Newark, NJ",
    ]:
        assert expected in places


def test_overnight_segment_is_split_across_two_sheets():
    base = datetime(2026, 3, 2, 22, 0)
    segments = [
        DutySegment(
            status=DutyStatus.D,
            start=base,
            end=base + timedelta(hours=4),  # 22:00 -> 02:00
            kind=StopKind.DRIVE,
            note="Driving",
            location="Amarillo, TX",
            miles=220,
        )
    ]
    logs = build_daily_logs(segments)

    assert [log.date for log in logs] == [date(2026, 3, 2), date(2026, 3, 3)]
    assert logs[0].totals[DutyStatus.D] == pytest.approx(2.0)
    assert logs[1].totals[DutyStatus.D] == pytest.approx(2.0)
    # Miles are apportioned by time across the split.
    assert logs[0].total_miles == pytest.approx(110)
    assert logs[1].total_miles == pytest.approx(110)


def test_every_sheet_is_padded_to_a_full_24_hours():
    base = datetime(2026, 3, 2, 6, 0)
    segments = [
        DutySegment(
            status=DutyStatus.D,
            start=base,
            end=base + timedelta(hours=3),
            kind=StopKind.DRIVE,
            location="Tulsa, OK",
            miles=165,
        )
    ]
    logs = build_daily_logs(segments)

    assert logs[0].total_hours == pytest.approx(24.0)
    assert logs[0].totals[DutyStatus.OFF] == pytest.approx(21.0)
    # The grid must be covered end to end with no holes.
    assert logs[0].entries[0].start_hour == 0.0
    assert logs[0].entries[-1].end_hour == 24.0
    for a, b in zip(logs[0].entries, logs[0].entries[1:]):
        assert a.end_hour == pytest.approx(b.start_hour)


def test_multi_day_trip_produces_a_sheet_per_calendar_day():
    from trips.services.hos import plan_trip
    from trips.tests.factories import straight_leg

    plan = plan_trip(
        straight_leg(120), straight_leg(1750), cycle_used_hours=12, start_at=datetime(2026, 3, 2, 6, 0)
    )
    logs = build_daily_logs(plan.segments)

    assert len(logs) == 4  # 03-02 through 03-05
    for log in logs:
        assert log.total_hours == pytest.approx(24.0), f"{log.date} does not total 24"
    assert sum(log.total_miles for log in logs) == pytest.approx(plan.total_miles)
