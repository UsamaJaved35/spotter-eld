"""Hours-of-Service planner tests.

Every expectation traces to the FMCSA Interstate Truck Driver's Guide to Hours
of Service (49 CFR 395), cited per test.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from trips.services.hos import DEFAULT_RULES, HosRules, plan_trip
from trips.services.types import DutyStatus, StopKind
from trips.tests.factories import straight_leg

START = datetime(2026, 3, 2, 6, 0)  # Monday 06:00, matching the guide's example


def drive_hours(segments) -> float:
    return sum(s.hours for s in segments if s.status is DutyStatus.D)


def kinds(segments) -> list[StopKind]:
    return [s.kind for s in segments]


def driving_before(segments, kind: StopKind) -> float:
    """Cumulative driving hours logged before the first segment of ``kind``."""
    total = 0.0
    for seg in segments:
        if seg.kind is kind:
            return total
        if seg.status is DutyStatus.D:
            total += seg.hours
    raise AssertionError(f"no {kind} segment found")


def driving_since_last_interruption(segments, kind: StopKind) -> float:
    """Driving hours since the last >=30-minute non-driving spell, at ``kind``.

    This is what the break clock actually measures: 395.3(a)(3)(ii) counts
    driving since the last consecutive half hour off the wheel, whether that was
    logged off duty, on duty, or in the sleeper berth.
    """
    total = 0.0
    for seg in segments:
        if seg.kind is kind:
            return total
        if seg.status is DutyStatus.D:
            total += seg.hours
        elif seg.hours >= DEFAULT_RULES.break_hours - 1e-9:
            total = 0.0
    raise AssertionError(f"no {kind} segment found")


def test_short_trip_needs_no_break_or_rest():
    """Under 8 driving hours and inside the 14-hour window: nothing inserted."""
    plan = plan_trip(straight_leg(100), straight_leg(100), cycle_used_hours=0, start_at=START)

    assert StopKind.BREAK30 not in kinds(plan.segments)
    assert StopKind.REST10 not in kinds(plan.segments)
    assert drive_hours(plan.segments) == pytest.approx(200 / 55, abs=1e-6)
    # 1 hour each for pickup and dropoff, per the brief's assumptions.
    on_duty = [s for s in plan.segments if s.status is DutyStatus.ON]
    assert sum(s.hours for s in on_duty) == pytest.approx(2.0)


def test_thirty_minute_break_after_eight_cumulative_driving_hours():
    """395.3(a)(3)(ii): break required after 8 *cumulative* driving hours."""
    plan = plan_trip(straight_leg(50), straight_leg(500), cycle_used_hours=0, start_at=START)

    assert driving_since_last_interruption(plan.segments, StopKind.BREAK30) == pytest.approx(8.0)
    brk = next(s for s in plan.segments if s.kind is StopKind.BREAK30)
    assert brk.hours == pytest.approx(0.5)


def test_ten_hour_rest_after_eleven_driving_hours():
    """395.3(a)(3): 11-hour driving limit, then 10 consecutive hours off."""
    plan = plan_trip(straight_leg(50), straight_leg(800), cycle_used_hours=0, start_at=START)

    assert driving_before(plan.segments, StopKind.REST10) == pytest.approx(11.0)
    rest = next(s for s in plan.segments if s.kind is StopKind.REST10)
    assert rest.hours == pytest.approx(10.0)
    assert rest.status is DutyStatus.SB


def test_fourteen_hour_window_can_bind_before_the_driving_limit():
    """395.3(a)(2): no driving after the 14th hour, even with driving time left.

    Loading is stretched to 7 hours so non-driving work eats the window: with
    ~0.9 hours driven to the pickup, only ~6.1 of the 14 hours remain for
    driving -- well short of the 11-hour limit.
    """
    rules = HosRules(pickup_hours=7.0)
    plan = plan_trip(
        straight_leg(50), straight_leg(900), cycle_used_hours=0, start_at=START, rules=rules
    )

    rest = next(s for s in plan.segments if s.kind is StopKind.REST10)
    assert driving_before(plan.segments, StopKind.REST10) < 11.0
    # The window opened at START and must be exhausted when the rest begins.
    assert rest.start - START == timedelta(hours=14)


def test_fuel_stop_at_least_every_thousand_miles():
    """Brief's assumption: fuelling at least once every 1,000 miles."""
    plan = plan_trip(straight_leg(100), straight_leg(2300), cycle_used_hours=0, start_at=START)

    fuel = [s for s in plan.segments if s.kind is StopKind.FUEL]
    assert len(fuel) >= 2

    # No 1,000-mile stretch may pass without one.
    miles = 0.0
    for seg in plan.segments:
        if seg.kind is StopKind.FUEL:
            miles = 0.0
        miles += seg.miles
        assert miles <= 1000.0 + 1e-6


def test_seventy_hour_cycle_triggers_a_thirty_four_hour_restart():
    """395.3(b)/(c): no driving past 70 hours in 8 days; 34 hours off resets it."""
    plan = plan_trip(straight_leg(100), straight_leg(900), cycle_used_hours=68, start_at=START)

    restart = next(s for s in plan.segments if s.kind is StopKind.RESTART34)
    assert restart.hours == pytest.approx(34.0)
    assert restart.status is DutyStatus.OFF
    # Only 2 hours of the cycle remained, so no more than that may be worked
    # before the restart.
    on_duty_before = 0.0
    for seg in plan.segments:
        if seg.kind is StopKind.RESTART34:
            break
        if seg.status in (DutyStatus.D, DutyStatus.ON):
            on_duty_before += seg.hours
    assert on_duty_before <= 2.0 + 1e-6

    # ...and the driver gets going again afterwards.
    after = plan.segments[plan.segments.index(restart) + 1 :]
    assert any(s.status is DutyStatus.D for s in after)
    assert plan.cycle_used_end < DEFAULT_RULES.cycle_limit_hours


def test_driver_starting_at_the_cycle_limit_restarts_before_driving():
    plan = plan_trip(straight_leg(100), straight_leg(100), cycle_used_hours=70, start_at=START)

    assert plan.segments[0].kind is StopKind.RESTART34
    assert plan.cycle_used_end < 70


def test_segments_are_contiguous_and_ordered():
    """No gaps or overlaps -- the log grid depends on this."""
    plan = plan_trip(straight_leg(300), straight_leg(1800), cycle_used_hours=40, start_at=START)

    for previous, nxt in zip(plan.segments, plan.segments[1:]):
        assert previous.end == nxt.start
        assert previous.end > previous.start


@pytest.mark.parametrize(
    "first,second,cycle",
    [(20, 40, 0), (300, 1800, 40), (100, 2300, 10), (60, 700, 68), (5, 60, 69.5)],
)
def test_no_limit_is_ever_exceeded(first, second, cycle):
    """Replay the plan and assert the four clocks stay legal throughout."""
    plan = plan_trip(
        straight_leg(first), straight_leg(second), cycle_used_hours=cycle, start_at=START
    )
    r = DEFAULT_RULES

    drive_in_window = 0.0
    drive_since_break = 0.0
    window_start = plan.segments[0].start
    cycle_used = cycle

    for seg in plan.segments:
        if seg.status is DutyStatus.D:
            drive_in_window += seg.hours
            drive_since_break += seg.hours
            cycle_used += seg.hours
            window_elapsed = (seg.end - window_start).total_seconds() / 3600.0

            assert drive_in_window <= r.max_drive_hours + 1e-6
            assert drive_since_break <= r.drive_hours_before_break + 1e-6
            assert window_elapsed <= r.max_window_hours + 1e-6
            assert cycle_used <= r.cycle_limit_hours + 1e-6
        else:
            if seg.status is DutyStatus.ON:
                cycle_used += seg.hours
                assert cycle_used <= r.cycle_limit_hours + 1e-6
            if seg.hours >= r.restart_hours - 1e-9:
                cycle_used = 0.0
                drive_in_window = drive_since_break = 0.0
                window_start = seg.end
            elif seg.hours >= r.rest_hours - 1e-9 and seg.status is not DutyStatus.ON:
                drive_in_window = drive_since_break = 0.0
                window_start = seg.end
            elif seg.hours >= r.break_hours - 1e-9:
                # On duty, off duty or sleeper -- any of them satisfies the break.
                drive_since_break = 0.0
