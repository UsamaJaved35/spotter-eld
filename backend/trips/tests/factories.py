"""Synthetic routes for HOS tests.

A two-vertex leg with linear interpolation is exactly a constant-speed drive,
which makes the planner's arithmetic checkable by hand.
"""

from __future__ import annotations

from trips.services.types import METERS_PER_MILE, RouteLeg


def straight_leg(miles: float, mph: float = 55.0) -> RouteLeg:
    """A leg of ``miles`` driven at a constant ``mph``."""
    hours = miles / mph
    # ~69 miles per degree of latitude; keeps the synthetic geometry plausible.
    return RouteLeg(
        coords=[(35.0, -100.0), (35.0 + miles / 69.0, -100.0)],
        cum_dist_m=[0.0, miles * METERS_PER_MILE],
        cum_time_s=[0.0, hours * 3600.0],
    )
