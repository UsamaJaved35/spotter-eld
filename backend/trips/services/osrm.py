"""Keyless routing via OSRM's public demo server and Nominatim.

Needs no signup, so the app runs out of the box and still has a route provider
if OpenRouteService is unavailable. Nominatim's usage policy requires an
identifying User-Agent and no more than one request per second, both honoured
here.
"""

from __future__ import annotations

import threading
import time

import httpx

from . import geometry
from .routing import GeocodingError, RoutingError
from .types import GeoPoint, RouteLeg

OSRM_BASE = "https://router.project-osrm.org"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
USER_AGENT = "spotter-eld-trip-planner/1.0 (HOS assessment app)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Nominatim allows at most 1 request/second.
_NOMINATIM_MIN_INTERVAL = 1.05

_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def abbreviate_state(name: str) -> str:
    return _STATE_ABBREV.get(name, name)


class _Throttle:
    """Serialises calls and keeps them at least ``interval`` apart."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = time.monotonic() - self._last
            if gap < self.interval:
                time.sleep(self.interval - gap)
            self._last = time.monotonic()


_nominatim_throttle = _Throttle(_NOMINATIM_MIN_INTERVAL)


class OsrmProvider:
    name = "osrm"

    def __init__(self) -> None:
        self._reverse_cache: dict[tuple[float, float], str] = {}

    # -- geocoding (Nominatim) -----------------------------------------

    def _nominatim(self, path: str, params: dict) -> list | dict:
        _nominatim_throttle.wait()
        try:
            response = httpx.get(
                f"{NOMINATIM_BASE}/{path}",
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise RoutingError(f"Nominatim request failed: {exc}") from exc

    @staticmethod
    def _format_place(item: dict) -> str:
        address = item.get("address", {})
        town = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("suburb")
            or address.get("county")
            or ""
        )
        state = abbreviate_state(address.get("state", ""))
        if town and state:
            return f"{town}, {state}"
        return town or state or item.get("display_name", "").split(",")[0]

    def autocomplete(self, query: str, limit: int = 5) -> list[GeoPoint]:
        if not query.strip():
            return []
        results = self._nominatim(
            "search",
            {
                "q": query,
                "format": "jsonv2",
                "limit": limit,
                "countrycodes": "us",
                "addressdetails": 1,
            },
        )
        return [
            GeoPoint(
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                label=item.get("display_name", ""),
            )
            for item in results
        ]

    def geocode(self, query: str) -> GeoPoint:
        matches = self.autocomplete(query, limit=1)
        if not matches:
            raise GeocodingError(f"Could not find a location matching {query!r}")
        return matches[0]

    def reverse(self, lat: float, lon: float) -> str:
        key = (round(lat, 3), round(lon, 3))
        if key in self._reverse_cache:
            return self._reverse_cache[key]

        try:
            item = self._nominatim(
                "reverse",
                {
                    "lat": lat,
                    "lon": lon,
                    "format": "jsonv2",
                    "zoom": 10,
                    "addressdetails": 1,
                },
            )
            place = self._format_place(item) if isinstance(item, dict) else ""
        except RoutingError:
            place = ""

        place = place or f"{lat:.3f}, {lon:.3f}"
        self._reverse_cache[key] = place
        return place

    def reverse_many(self, points: list[tuple[float, float]]) -> list[str]:
        """Sequential by necessity: Nominatim permits only 1 request/second."""
        return [self.reverse(lat, lon) for lat, lon in points]

    # -- routing (OSRM) ------------------------------------------------

    def route(self, start: GeoPoint, end: GeoPoint) -> RouteLeg:
        coords = f"{start.lon},{start.lat};{end.lon},{end.lat}"
        try:
            response = httpx.get(
                f"{OSRM_BASE}/route/v1/driving/{coords}",
                params={"overview": "full", "geometries": "geojson", "steps": "true"},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise RoutingError(f"OSRM request failed: {exc}") from exc

        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RoutingError(f"OSRM could not route: {payload.get('message', payload.get('code'))}")

        return _leg_from_osrm(payload["routes"][0])


def _leg_from_osrm(route: dict) -> RouteLeg:
    """Rebuild the polyline from step geometries so step boundaries are exact."""
    coords: list[tuple[float, float]] = []
    steps: list[tuple[int, int, float, float]] = []

    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            points = [(lat, lon) for lon, lat in step["geometry"]["coordinates"]]
            if not points:
                continue
            if coords and points[0] == coords[-1]:
                points = points[1:]  # drop the vertex shared with the previous step
            if not points:
                continue
            start_index = max(0, len(coords) - 1)
            coords.extend(points)
            steps.append((start_index, len(coords) - 1, step["distance"], step["duration"]))

    if len(coords) < 2:
        # Degenerate route (identical endpoints): synthesise a two-point leg.
        geom = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]] or [(0.0, 0.0)]
        coords = geom * 2 if len(geom) == 1 else geom
        steps = [(0, len(coords) - 1, route.get("distance", 0.0), route.get("duration", 0.0))]

    return geometry.build_leg(coords, steps)
