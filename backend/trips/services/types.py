"""Shared domain types.

Deliberately free of Django and HTTP so the planning logic can be unit-tested
as pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

METERS_PER_MILE = 1609.344


class DutyStatus(str, Enum):
    """The four rows of the FMCSA record-of-duty-status grid."""

    OFF = "OFF"  # Off Duty
    SB = "SB"  # Sleeper Berth
    D = "D"  # Driving
    ON = "ON"  # On Duty (Not Driving)


#: Machine-readable tag for why a segment exists. Drives map markers and icons.
class StopKind(str, Enum):
    START = "start"
    DRIVE = "drive"
    PICKUP = "pickup"
    DROPOFF = "dropoff"
    FUEL = "fuel"
    BREAK30 = "break30"
    REST10 = "rest10"
    RESTART34 = "restart34"
    OFF_DUTY = "off_duty"


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    label: str = ""

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lon)


@dataclass
class RouteLeg:
    """A routed leg, normalised across providers.

    ``coords`` are ``(lat, lon)`` vertices of the driven polyline. ``cum_dist_m``
    and ``cum_time_s`` are parallel arrays giving cumulative distance/time at each
    vertex, so a stop forced at "6.5 driving hours in" can be placed at a
    geographically correct point rather than by assuming a constant speed.
    """

    coords: list[tuple[float, float]]
    cum_dist_m: list[float]
    cum_time_s: list[float]

    def __post_init__(self) -> None:
        if not (len(self.coords) == len(self.cum_dist_m) == len(self.cum_time_s)):
            raise ValueError(
                "RouteLeg arrays must be the same length: "
                f"coords={len(self.coords)} dist={len(self.cum_dist_m)} time={len(self.cum_time_s)}"
            )
        if len(self.coords) < 2:
            raise ValueError("RouteLeg needs at least two vertices")

    @property
    def total_dist_m(self) -> float:
        return self.cum_dist_m[-1]

    @property
    def total_time_s(self) -> float:
        return self.cum_time_s[-1]

    @property
    def total_miles(self) -> float:
        return self.total_dist_m / METERS_PER_MILE

    @property
    def start(self) -> tuple[float, float]:
        return self.coords[0]

    @property
    def end(self) -> tuple[float, float]:
        return self.coords[-1]


@dataclass
class DutySegment:
    """One continuous span at a single duty status."""

    status: DutyStatus
    start: datetime
    end: datetime
    kind: StopKind
    note: str = ""
    lat: float | None = None
    lon: float | None = None
    location: str = ""  # "City, ST" -- filled in later by reverse geocoding
    miles: float = 0.0  # distance covered (driving segments only)

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0

    def with_location(self, location: str) -> DutySegment:
        self.location = location
        return self
