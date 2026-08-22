"""OpenRouteService provider.

Preferred when ``ORS_API_KEY`` is configured: it gives address autocomplete, a
heavy-goods-vehicle routing profile, and geocoding without Nominatim's
one-request-per-second ceiling.

Free tier is roughly 2,000-2,500 requests/day with a hard 6,000 km cap per
routing request, which is why the planner routes each leg separately rather
than sending all three points at once.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from . import geometry
from .routing import GeocodingError, RoutingError
from .types import GeoPoint, RouteLeg

BASE = "https://api.openrouteservice.org"
PROFILE = "driving-hgv"  # property-carrying CMV
TIMEOUT = httpx.Timeout(25.0, connect=10.0)
MAX_REVERSE_WORKERS = 8


class OpenRouteServiceProvider:
    name = "openrouteservice"

    def __init__(self, api_key: str):
        if not api_key:
            raise RoutingError("OpenRouteService API key is not configured")
        self.api_key = api_key
        self._reverse_cache: dict[tuple[float, float], str] = {}

    # -- transport -----------------------------------------------------

    def _get(self, path: str, params: dict) -> dict:
        try:
            response = httpx.get(
                f"{BASE}/{path}",
                params={**params, "api_key": self.api_key},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise RoutingError(f"OpenRouteService request failed: {exc}") from exc

    def _post(self, path: str, body: dict) -> dict:
        try:
            response = httpx.post(
                f"{BASE}/{path}",
                json=body,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/geo+json",
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise RoutingError(f"OpenRouteService request failed: {exc}") from exc

    # -- geocoding (Pelias) --------------------------------------------

    @staticmethod
    def _to_point(feature: dict) -> GeoPoint:
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        return GeoPoint(lat=lat, lon=lon, label=props.get("label", ""))

    @staticmethod
    def _city_state(feature: dict) -> str:
        props = feature.get("properties", {})
        town = (
            props.get("locality")
            or props.get("localadmin")
            or props.get("county")
            or props.get("region")
            or ""
        )
        state = props.get("region_a") or props.get("region") or ""
        if town and state and town != state:
            return f"{town}, {state}"
        return town or state or props.get("label", "")

    def autocomplete(self, query: str, limit: int = 5) -> list[GeoPoint]:
        if not query.strip():
            return []
        payload = self._get(
            "geocode/autocomplete",
            {"text": query, "boundary.country": "US", "size": limit},
        )
        return [self._to_point(f) for f in payload.get("features", [])]

    def geocode(self, query: str) -> GeoPoint:
        payload = self._get(
            "geocode/search", {"text": query, "boundary.country": "US", "size": 1}
        )
        features = payload.get("features", [])
        if not features:
            raise GeocodingError(f"Could not find a location matching {query!r}")
        return self._to_point(features[0])

    def reverse(self, lat: float, lon: float) -> str:
        key = (round(lat, 3), round(lon, 3))
        if key in self._reverse_cache:
            return self._reverse_cache[key]

        try:
            payload = self._get(
                "geocode/reverse",
                {"point.lat": lat, "point.lon": lon, "size": 1, "layers": "locality,county"},
            )
            features = payload.get("features", [])
            place = self._city_state(features[0]) if features else ""
        except RoutingError:
            place = ""

        place = place or f"{lat:.3f}, {lon:.3f}"
        self._reverse_cache[key] = place
        return place

    def reverse_many(self, points: list[tuple[float, float]]) -> list[str]:
        """Concurrent, unlike Nominatim -- ORS has no per-second cap."""
        if not points:
            return []
        workers = min(MAX_REVERSE_WORKERS, len(points))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda p: self.reverse(*p), points))

    # -- routing -------------------------------------------------------

    def route(self, start: GeoPoint, end: GeoPoint) -> RouteLeg:
        payload = self._post(
            f"v2/directions/{PROFILE}/geojson",
            {
                "coordinates": [[start.lon, start.lat], [end.lon, end.lat]],
                "instructions": True,
                "units": "m",
            },
        )
        features = payload.get("features", [])
        if not features:
            raise RoutingError("OpenRouteService returned no route")
        return _leg_from_ors(features[0])


def _leg_from_ors(feature: dict) -> RouteLeg:
    coords = [(lat, lon) for lon, lat in feature["geometry"]["coordinates"]]
    steps: list[tuple[int, int, float, float]] = []

    for segment in feature.get("properties", {}).get("segments", []):
        for step in segment.get("steps", []):
            way_points = step.get("way_points") or [0, 0]
            steps.append(
                (way_points[0], way_points[-1], step.get("distance", 0.0), step.get("duration", 0.0))
            )

    if not steps:
        summary = feature.get("properties", {}).get("summary", {})
        steps = [(0, len(coords) - 1, summary.get("distance", 0.0), summary.get("duration", 0.0))]

    return geometry.build_leg(coords, steps)
