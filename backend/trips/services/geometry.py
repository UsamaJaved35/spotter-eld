"""Interpolation along a routed polyline.

The HOS planner works in the time domain ("stop after 6.5 driving hours") but the
map and the log's Remarks column need a place. These helpers convert between
elapsed driving time, distance travelled, and position, using the per-step
cumulative arrays carried on a :class:`RouteLeg`.
"""

from __future__ import annotations

from bisect import bisect_right

from .types import RouteLeg


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _locate(values: list[float], target: float) -> tuple[int, float]:
    """Return ``(index, fraction)`` such that ``target`` lies between
    ``values[index]`` and ``values[index + 1]``.

    ``fraction`` is 0.0 at ``values[index]`` and 1.0 at ``values[index + 1]``.
    Clamps to the ends rather than raising, so callers can pass a target that
    marginally overshoots because of floating-point drift.
    """
    if target <= values[0]:
        return 0, 0.0
    if target >= values[-1]:
        return len(values) - 2, 1.0

    i = bisect_right(values, target) - 1
    i = min(i, len(values) - 2)
    span = values[i + 1] - values[i]
    if span <= 0:
        # Zero-length step (stationary vertices); snap to its start.
        return i, 0.0
    return i, (target - values[i]) / span


def point_at_time(leg: RouteLeg, seconds: float) -> tuple[float, float]:
    """Position ``seconds`` of driving into the leg."""
    i, f = _locate(leg.cum_time_s, seconds)
    (lat_a, lon_a), (lat_b, lon_b) = leg.coords[i], leg.coords[i + 1]
    return (_lerp(lat_a, lat_b, f), _lerp(lon_a, lon_b, f))


def point_at_distance(leg: RouteLeg, meters: float) -> tuple[float, float]:
    """Position ``meters`` into the leg."""
    i, f = _locate(leg.cum_dist_m, meters)
    (lat_a, lon_a), (lat_b, lon_b) = leg.coords[i], leg.coords[i + 1]
    return (_lerp(lat_a, lat_b, f), _lerp(lon_a, lon_b, f))


def distance_at_time(leg: RouteLeg, seconds: float) -> float:
    """Metres covered after ``seconds`` of driving."""
    i, f = _locate(leg.cum_time_s, seconds)
    return _lerp(leg.cum_dist_m[i], leg.cum_dist_m[i + 1], f)


def time_at_distance(leg: RouteLeg, meters: float) -> float:
    """Driving seconds needed to cover ``meters``."""
    i, f = _locate(leg.cum_dist_m, meters)
    return _lerp(leg.cum_time_s[i], leg.cum_time_s[i + 1], f)


def slice_coords(leg: RouteLeg, from_s: float, to_s: float) -> list[tuple[float, float]]:
    """The polyline actually driven between two elapsed-driving-time marks.

    Used to colour each driving segment separately on the map.
    """
    if to_s <= from_s:
        return []
    start = point_at_time(leg, from_s)
    end = point_at_time(leg, to_s)
    i_start, _ = _locate(leg.cum_time_s, from_s)
    i_end, _ = _locate(leg.cum_time_s, to_s)
    middle = leg.coords[i_start + 1 : i_end + 1]
    return [start, *middle, end]
