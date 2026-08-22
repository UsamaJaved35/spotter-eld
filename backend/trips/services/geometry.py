"""Interpolation along a routed polyline.

The HOS planner works in the time domain ("stop after 6.5 driving hours") but the
map and the log's Remarks column need a place. These helpers convert between
elapsed driving time, distance travelled, and position, using the per-step
cumulative arrays carried on a :class:`RouteLeg`.
"""

from __future__ import annotations

from bisect import bisect_right
from math import asin, cos, radians, sin, sqrt

from .types import RouteLeg

EARTH_RADIUS_M = 6_371_008.8


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


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between two ``(lat, lon)`` points."""
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, h)))


def build_leg(
    coords: list[tuple[float, float]],
    steps: list[tuple[int, int, float, float]],
) -> RouteLeg:
    """Assemble a :class:`RouteLeg` from a polyline and its routing steps.

    ``steps`` are ``(start_index, end_index, distance_m, duration_s)`` spans into
    ``coords``. Distance and time are distributed *within* each step in
    proportion to the great-circle length of its vertices, so speed varies
    per step (motorway vs. city) instead of being averaged over the whole leg.
    """
    n = len(coords)
    cum_dist = [0.0] * n
    cum_time = [0.0] * n
    dist_acc = 0.0
    time_acc = 0.0

    for start, end, step_dist, step_time in steps:
        start = max(0, min(start, n - 1))
        end = max(start, min(end, n - 1))

        spans = [haversine_m(coords[i], coords[i + 1]) for i in range(start, end)]
        span_total = sum(spans)

        covered = 0.0
        for offset, span in enumerate(spans):
            covered += span
            fraction = (covered / span_total) if span_total > 0 else (offset + 1) / len(spans)
            cum_dist[start + offset + 1] = dist_acc + step_dist * fraction
            cum_time[start + offset + 1] = time_acc + step_time * fraction

        dist_acc += step_dist
        time_acc += step_time

    # Any trailing vertices the steps did not cover (rare, but providers vary).
    for i in range(1, n):
        if cum_dist[i] < cum_dist[i - 1]:
            cum_dist[i] = cum_dist[i - 1]
        if cum_time[i] < cum_time[i - 1]:
            cum_time[i] = cum_time[i - 1]

    return RouteLeg(coords=coords, cum_dist_m=cum_dist, cum_time_s=cum_time)


def simplify(coords: list[tuple[float, float]], tolerance_deg: float = 0.005) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker thinning for map display.

    A cross-country OSRM route carries thousands of vertices; the planner needs
    all of them for accurate interpolation, but the map does not. Simplify only
    on the way out to the client.
    """
    if len(coords) < 3:
        return list(coords)

    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue

        (y0, x0), (y1, x1) = coords[start], coords[end]
        dy, dx = y1 - y0, x1 - x0
        norm = (dx * dx + dy * dy) ** 0.5

        furthest, best = 0.0, None
        for i in range(start + 1, end):
            y, x = coords[i]
            if norm == 0:
                distance = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
            else:
                distance = abs(dx * (y0 - y) - (x0 - x) * dy) / norm
            if distance > furthest:
                furthest, best = distance, i

        if best is not None and furthest > tolerance_deg:
            keep[best] = True
            stack.append((start, best))
            stack.append((best, end))

    return [point for point, kept in zip(coords, keep) if kept]
