"""Hours-of-Service planner for a property-carrying driver on the 70hr/8day cycle.

Implements the limits set out in 49 CFR 395 and summarised in FMCSA's
*Interstate Truck Driver's Guide to Hours of Service*:

* 11-hour driving limit within a 14-consecutive-hour window -- 395.3(a)(2)-(3)
* 30-minute break after 8 *cumulative* driving hours -- 395.3(a)(3)(ii)
* 70 on-duty hours in 8 days, reset by 34 consecutive hours off -- 395.3(b)-(c)

Pure functions over :class:`RouteLeg` inputs: no Django, no HTTP, no clock. That
keeps the part that has to be *correct* fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import geometry
from .types import METERS_PER_MILE, DutySegment, DutyStatus, RouteLeg, StopKind

EPS = 1e-9


@dataclass(frozen=True)
class HosRules:
    """Regulatory limits, plus the two durations the brief left open.

    Defaults match the assessment's stated assumptions. Exposed as a dataclass so
    tests can construct edge cases (and so the numbers are stated in one place
    rather than scattered as literals).
    """

    max_drive_hours: float = 11.0
    max_window_hours: float = 14.0
    drive_hours_before_break: float = 8.0
    break_hours: float = 0.5
    rest_hours: float = 10.0
    restart_hours: float = 34.0
    cycle_limit_hours: float = 70.0
    fuel_interval_miles: float = 1000.0
    #: Not specified by the brief; assumed and surfaced in the UI.
    fuel_hours: float = 0.5
    pickup_hours: float = 1.0
    dropoff_hours: float = 1.0


DEFAULT_RULES = HosRules()


@dataclass
class TripPlan:
    segments: list[DutySegment] = field(default_factory=list)
    total_miles: float = 0.0
    total_drive_hours: float = 0.0
    cycle_used_start: float = 0.0
    cycle_used_end: float = 0.0

    @property
    def start_at(self) -> datetime:
        return self.segments[0].start

    @property
    def end_at(self) -> datetime:
        return self.segments[-1].end

    @property
    def total_duration_hours(self) -> float:
        return (self.end_at - self.start_at).total_seconds() / 3600.0


class _Simulation:
    """Carries the four HOS clocks while walking the route."""

    def __init__(self, start_at: datetime, cycle_used_hours: float, rules: HosRules):
        self.rules = rules
        self.clock = start_at
        self.window_start = start_at
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0
        self.cycle_used = cycle_used_hours
        self.miles_since_fuel = 0.0
        self.segments: list[DutySegment] = []
        self.total_miles = 0.0

    # -- clock helpers -------------------------------------------------

    @property
    def window_elapsed(self) -> float:
        return (self.clock - self.window_start).total_seconds() / 3600.0

    def _append(
        self,
        status: DutyStatus,
        hours: float,
        kind: StopKind,
        note: str,
        position: tuple[float, float] | None,
        miles: float = 0.0,
    ) -> None:
        if hours <= EPS:
            return
        end = self.clock + timedelta(hours=hours)
        self.segments.append(
            DutySegment(
                status=status,
                start=self.clock,
                end=end,
                kind=kind,
                note=note,
                lat=position[0] if position else None,
                lon=position[1] if position else None,
                miles=miles,
            )
        )
        self.clock = end

        # A break from driving may be taken on duty, off duty, or in the sleeper
        # berth, so any consecutive half hour of not-driving clears the clock --
        # loading, fuelling and paperwork all count. 395.3(a)(3)(ii).
        if status is not DutyStatus.D and hours >= self.rules.break_hours - EPS:
            self.drive_since_break = 0.0

    # -- the events the planner can emit -------------------------------

    def take_break(self, position) -> None:
        """30 minutes off duty to satisfy 395.3(a)(3)(ii)."""
        self._append(
            DutyStatus.OFF,
            self.rules.break_hours,
            StopKind.BREAK30,
            "30-minute break - 8 cumulative driving hours reached",
            position,
        )

    def take_rest(self, position, reason: str) -> None:
        """10 consecutive hours off, which reopens the driving window."""
        self._append(DutyStatus.SB, self.rules.rest_hours, StopKind.REST10, reason, position)
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0
        self.window_start = self.clock

    def take_restart(self, position) -> None:
        """34 consecutive hours off, resetting the 70-hour cycle -- 395.3(c)."""
        self._append(
            DutyStatus.OFF,
            self.rules.restart_hours,
            StopKind.RESTART34,
            "34-hour restart - 70-hour cycle limit reached",
            position,
        )
        self.cycle_used = 0.0
        self.drive_in_window = 0.0
        self.drive_since_break = 0.0
        self.window_start = self.clock

    def take_fuel(self, position) -> None:
        """Fuelling, logged on duty (not driving).

        The guide explicitly allows a fuel stop to satisfy the 30-minute break
        when it is consecutive, so it clears the break clock too.
        """
        self._append(
            DutyStatus.ON,
            self.rules.fuel_hours,
            StopKind.FUEL,
            "Fuel stop - 1,000 miles since last fuelling",
            position,
        )
        self.cycle_used += self.rules.fuel_hours
        self.miles_since_fuel = 0.0

    def do_work(self, hours: float, kind: StopKind, note: str, position) -> None:
        """On-duty-not-driving: consumes the window and the cycle, not the 11 hours."""
        self._append(DutyStatus.ON, hours, kind, note, position)
        self.cycle_used += hours

    def do_drive(self, hours: float, miles: float, position) -> None:
        self._append(DutyStatus.D, hours, StopKind.DRIVE, "Driving", position, miles=miles)
        self.drive_in_window += hours
        self.drive_since_break += hours
        self.cycle_used += hours
        self.miles_since_fuel += miles
        self.total_miles += miles


def _drive_leg(sim: _Simulation, leg: RouteLeg) -> None:
    """Advance along one leg, interrupting whenever a limit binds."""
    r = sim.rules
    driven_s = 0.0
    total_s = leg.total_time_s

    while total_s - driven_s > EPS:
        here = geometry.point_at_time(leg, driven_s)

        # Guard clauses: a clock is already spent, so rest before driving on.
        if sim.cycle_used >= r.cycle_limit_hours - EPS:
            sim.take_restart(here)
            continue
        if sim.drive_in_window >= r.max_drive_hours - EPS:
            sim.take_rest(here, "10-hour rest - 11-hour driving limit reached")
            continue
        if sim.window_elapsed >= r.max_window_hours - EPS:
            sim.take_rest(here, "10-hour rest - 14-hour driving window closed")
            continue
        if sim.drive_since_break >= r.drive_hours_before_break - EPS:
            sim.take_break(here)
            continue
        if sim.miles_since_fuel >= r.fuel_interval_miles - EPS:
            sim.take_fuel(here)
            continue

        # Otherwise drive up to whichever limit bites first.
        options = [
            r.max_drive_hours - sim.drive_in_window,
            r.drive_hours_before_break - sim.drive_since_break,
            r.max_window_hours - sim.window_elapsed,
            r.cycle_limit_hours - sim.cycle_used,
            (total_s - driven_s) / 3600.0,
            _hours_to_next_fuel(sim, leg, driven_s),
        ]
        chunk = min(options)
        if chunk <= EPS:
            # Defensive: a guard above should have fired. Rest to make progress.
            sim.take_rest(here, "10-hour rest - no driving time available")
            continue

        next_driven_s = min(driven_s + chunk * 3600.0, total_s)
        miles = (
            geometry.distance_at_time(leg, next_driven_s)
            - geometry.distance_at_time(leg, driven_s)
        ) / METERS_PER_MILE
        sim.do_drive((next_driven_s - driven_s) / 3600.0, miles, here)
        driven_s = next_driven_s


def _hours_to_next_fuel(sim: _Simulation, leg: RouteLeg, driven_s: float) -> float:
    """Driving hours until the 1,000-mile fuelling interval is due."""
    remaining_miles = sim.rules.fuel_interval_miles - sim.miles_since_fuel
    target_m = geometry.distance_at_time(leg, driven_s) + remaining_miles * METERS_PER_MILE
    if target_m >= leg.total_dist_m:
        return float("inf")  # refuel on a later leg, not this one
    return (geometry.time_at_distance(leg, target_m) - driven_s) / 3600.0


def plan_trip(
    to_pickup: RouteLeg,
    to_dropoff: RouteLeg,
    cycle_used_hours: float,
    start_at: datetime,
    rules: HosRules = DEFAULT_RULES,
) -> TripPlan:
    """Simulate the whole trip and return an ordered, gap-free duty log.

    The driver comes on duty at ``start_at``, drives to the pickup, loads for an
    hour, drives to the dropoff, and unloads for an hour -- with breaks, rests,
    fuel stops and restarts inserted wherever the regulations require them.
    """
    sim = _Simulation(start_at, cycle_used_hours, rules)

    _drive_leg(sim, to_pickup)
    _ensure_on_duty_capacity(sim, to_pickup.end, rules.pickup_hours)
    sim.do_work(rules.pickup_hours, StopKind.PICKUP, "Pickup - loading", to_pickup.end)

    _drive_leg(sim, to_dropoff)
    _ensure_on_duty_capacity(sim, to_dropoff.end, rules.dropoff_hours)
    sim.do_work(rules.dropoff_hours, StopKind.DROPOFF, "Dropoff - unloading", to_dropoff.end)

    return TripPlan(
        segments=sim.segments,
        total_miles=sim.total_miles,
        total_drive_hours=sum(s.hours for s in sim.segments if s.status is DutyStatus.D),
        cycle_used_start=cycle_used_hours,
        cycle_used_end=sim.cycle_used,
    )


def _ensure_on_duty_capacity(sim: _Simulation, position, hours: float) -> None:
    """A 34-hour restart is required if the cycle cannot absorb the coming work.

    Loading and unloading are on-duty time and count against the 70-hour cycle,
    so a driver who is out of hours has to restart before doing them.
    """
    if sim.cycle_used + hours > sim.rules.cycle_limit_hours + EPS:
        sim.take_restart(position)
