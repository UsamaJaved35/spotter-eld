"""Orchestration: turn four form inputs into a routed, HOS-compliant trip plan.

Geocode the three places, route the two legs, simulate the duty clocks, name
every stop, then fold the result into one JSON payload the React app renders as
a map, an itinerary and a stack of daily log sheets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import geometry
from .hos import DEFAULT_RULES, TripPlan, plan_trip
from .logsheets import build_daily_logs
from .routing import GeocodingError, get_routing_service
from .types import DutySegment, DutyStatus, GeoPoint, StopKind

logger = logging.getLogger(__name__)

#: Vertices are thinned to roughly this angular tolerance before being sent to
#: the browser (~200 m), which keeps a cross-country payload small.
MAP_TOLERANCE_DEG = 0.002

#: Segment kinds that are real places on the map, rather than a span of driving.
STOP_KINDS = {
    StopKind.PICKUP,
    StopKind.DROPOFF,
    StopKind.FUEL,
    StopKind.BREAK30,
    StopKind.REST10,
    StopKind.RESTART34,
}


@dataclass
class TripRequest:
    current_location: str
    pickup_location: str
    dropoff_location: str
    cycle_used_hours: float
    start_at: datetime
    driver_name: str = ""
    carrier_name: str = ""
    main_office: str = ""
    truck_number: str = ""
    shipping_doc: str = ""


def round_to_quarter_hour(moment: datetime) -> datetime:
    """The printed grid is marked in 15-minute increments; start on one."""
    minute = (moment.minute // 15) * 15
    return moment.replace(minute=minute, second=0, microsecond=0)


def build_trip(request: TripRequest) -> dict:
    """Plan the trip and return the full JSON-serialisable payload."""
    service = get_routing_service()

    current = _geocode(service, request.current_location, "current location")
    pickup = _geocode(service, request.pickup_location, "pickup location")
    dropoff = _geocode(service, request.dropoff_location, "dropoff location")

    to_pickup = service.route(current, pickup)
    to_dropoff = service.route(pickup, dropoff)

    plan = plan_trip(
        to_pickup,
        to_dropoff,
        cycle_used_hours=request.cycle_used_hours,
        start_at=request.start_at,
    )

    _name_locations(service, plan.segments, current, pickup, dropoff)
    daily_logs = build_daily_logs(plan.segments)

    return {
        "inputs": {
            "current_location": request.current_location,
            "pickup_location": request.pickup_location,
            "dropoff_location": request.dropoff_location,
            "cycle_used_hours": request.cycle_used_hours,
            "start_at": request.start_at.isoformat(),
            "driver_name": request.driver_name,
            "carrier_name": request.carrier_name,
            "main_office": request.main_office,
            "truck_number": request.truck_number,
            "shipping_doc": request.shipping_doc,
        },
        "places": {
            "current": _place(current),
            "pickup": _place(pickup),
            "dropoff": _place(dropoff),
        },
        "route": {
            "provider": service.active,
            "legs": [
                _leg_payload(to_pickup, "Current location to pickup"),
                _leg_payload(to_dropoff, "Pickup to dropoff"),
            ],
        },
        "segments": [_segment_payload(s) for s in plan.segments],
        "stops": _stops_payload(plan.segments),
        "daily_logs": [_daily_log_payload(log) for log in daily_logs],
        "summary": _summary(plan, daily_logs, request),
        "assumptions": _assumptions(),
    }


# -- geocoding ---------------------------------------------------------


def _geocode(service, query: str, field: str) -> GeoPoint:
    try:
        return service.geocode(query)
    except GeocodingError as exc:
        raise GeocodingError(f"Could not find the {field} {query!r}. Try adding a state.") from exc


def _name_locations(service, segments: list[DutySegment], *known: GeoPoint) -> None:
    """Reverse-geocode each distinct stop so Remarks can name a city and state.

    395.8 requires the city/town and state abbreviation at every change of duty
    status. Only distinct coordinates are looked up, and the endpoints reuse the
    labels already resolved by the forward geocode.
    """
    wanted: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    for segment in segments:
        if segment.lat is None or segment.lon is None:
            continue
        key = (round(segment.lat, 3), round(segment.lon, 3))
        if key not in seen:
            seen.add(key)
            wanted.append((segment.lat, segment.lon))

    try:
        names = service.reverse_many(wanted)
    except Exception:  # noqa: BLE001 - a missing place name must not fail the trip
        logger.warning("Reverse geocoding failed; falling back to coordinates", exc_info=True)
        names = [f"{lat:.3f}, {lon:.3f}" for lat, lon in wanted]

    lookup = {
        (round(lat, 3), round(lon, 3)): name for (lat, lon), name in zip(wanted, names)
    }

    for segment in segments:
        if segment.lat is None or segment.lon is None:
            continue
        segment.location = lookup.get((round(segment.lat, 3), round(segment.lon, 3)), "")


# -- payload shaping ---------------------------------------------------


def _place(point: GeoPoint) -> dict:
    return {"lat": point.lat, "lon": point.lon, "label": point.label}


def _leg_payload(leg, name: str) -> dict:
    return {
        "name": name,
        "miles": round(leg.total_miles, 1),
        "hours": round(leg.total_time_s / 3600.0, 2),
        "coords": [
            [round(lat, 5), round(lon, 5)]
            for lat, lon in geometry.simplify(leg.coords, MAP_TOLERANCE_DEG)
        ],
    }


def _segment_payload(segment: DutySegment) -> dict:
    return {
        "status": segment.status.value,
        "kind": segment.kind.value,
        "start": segment.start.isoformat(),
        "end": segment.end.isoformat(),
        "hours": round(segment.hours, 3),
        "miles": round(segment.miles, 1),
        "note": segment.note,
        "location": segment.location,
        "lat": segment.lat,
        "lon": segment.lon,
    }


def _stops_payload(segments: list[DutySegment]) -> list[dict]:
    """The places worth pinning on the map, in order."""
    stops: list[dict] = []
    for index, segment in enumerate(segments):
        if segment.kind not in STOP_KINDS:
            continue
        stops.append(
            {
                "index": index,
                "kind": segment.kind.value,
                "label": _STOP_LABELS[segment.kind],
                "location": segment.location,
                "lat": segment.lat,
                "lon": segment.lon,
                "arrive": segment.start.isoformat(),
                "depart": segment.end.isoformat(),
                "hours": round(segment.hours, 2),
                "note": segment.note,
            }
        )
    return stops


_STOP_LABELS = {
    StopKind.PICKUP: "Pickup",
    StopKind.DROPOFF: "Dropoff",
    StopKind.FUEL: "Fuel",
    StopKind.BREAK30: "30-min break",
    StopKind.REST10: "10-hour rest",
    StopKind.RESTART34: "34-hour restart",
}


def _daily_log_payload(log) -> dict:
    return {
        "date": log.date.isoformat(),
        "entries": [
            {
                "status": e.status.value,
                "start_hour": round(e.start_hour, 4),
                "end_hour": round(e.end_hour, 4),
                "kind": e.kind.value,
                "note": e.note,
                "location": e.location,
            }
            for e in log.entries
        ],
        "remarks": [
            {
                "hour": round(r.hour, 4),
                "location": r.location,
                "note": r.note,
                "status": r.status.value,
            }
            for r in log.remarks
        ],
        "totals": {status.value: log.totals.get(status, 0.0) for status in DutyStatus},
        "total_hours": round(log.total_hours, 2),
        "total_miles": log.total_miles,
    }


def _summary(plan: TripPlan, daily_logs, request: TripRequest) -> dict:
    counts: dict[str, int] = {}
    for segment in plan.segments:
        if segment.kind in STOP_KINDS:
            counts[segment.kind.value] = counts.get(segment.kind.value, 0) + 1

    return {
        "total_miles": round(plan.total_miles, 1),
        "total_drive_hours": round(plan.total_drive_hours, 2),
        "total_duration_hours": round(plan.total_duration_hours, 2),
        "start_at": plan.start_at.isoformat(),
        "end_at": plan.end_at.isoformat(),
        "log_sheet_count": len(daily_logs),
        "cycle_used_start": round(plan.cycle_used_start, 2),
        "cycle_used_end": round(plan.cycle_used_end, 2),
        "cycle_remaining": round(DEFAULT_RULES.cycle_limit_hours - plan.cycle_used_end, 2),
        "stop_counts": counts,
    }


def _assumptions() -> list[str]:
    r = DEFAULT_RULES
    return [
        f"Property-carrying driver on the {r.cycle_limit_hours:.0f}-hour/8-day cycle, no adverse driving conditions.",
        f"{r.max_drive_hours:.0f}-hour driving limit inside a {r.max_window_hours:.0f}-hour window; "
        f"{r.rest_hours:.0f} consecutive hours off to reset it.",
        f"30-minute break after {r.drive_hours_before_break:.0f} cumulative driving hours "
        "(may be taken on duty, off duty or in the sleeper berth).",
        f"Fuel stop at least every {r.fuel_interval_miles:,.0f} miles, logged as "
        f"{r.fuel_hours * 60:.0f} minutes on duty (duration assumed; the brief specifies only frequency).",
        f"{r.pickup_hours:.0f} hour on duty for pickup and {r.dropoff_hours:.0f} hour for dropoff.",
        "Cycle hours already used are treated as a starting balance that only accumulates: the "
        "prior 8 days are not known, so nothing rolls off. A 34-hour restart clears it.",
        "Times are shown in the driver's home-terminal time, as 395.8 requires.",
    ]
