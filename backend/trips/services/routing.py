"""Routing/geocoding provider abstraction.

Two implementations sit behind one interface so the planner never knows which is
in use:

* :mod:`ors` -- OpenRouteService. Needs a free API key. Offers address
  autocomplete and a heavy-goods-vehicle routing profile.
* :mod:`osrm` -- OSRM's public demo server plus Nominatim. Keyless, so the app
  works with no signup at all, and serves as the fallback if OpenRouteService is
  unreachable or over quota.
"""

from __future__ import annotations

import logging
from typing import Protocol

from django.conf import settings

from .types import GeoPoint, RouteLeg

logger = logging.getLogger(__name__)


class RoutingError(RuntimeError):
    """Raised when a provider cannot satisfy a request."""


class GeocodingError(RoutingError):
    """Raised when a place name cannot be resolved to coordinates."""


class RoutingProvider(Protocol):
    name: str

    def geocode(self, query: str) -> GeoPoint: ...

    def autocomplete(self, query: str, limit: int = 5) -> list[GeoPoint]: ...

    def reverse(self, lat: float, lon: float) -> str: ...

    def reverse_many(self, points: list[tuple[float, float]]) -> list[str]: ...

    def route(self, start: GeoPoint, end: GeoPoint) -> RouteLeg: ...


def _providers() -> tuple[list, list]:
    """Return ``(geocoders, routers)``, each in preference order.

    Geocoding and routing are resolved separately because the best provider
    differs by role:

    * **Geocoding** prefers OpenRouteService. It resolves rural coordinates to a
      real town ("Steelville, MO" where Nominatim gives "Crawford County, MO"),
      which matters because 395.8 wants a city and state at every duty change,
      and it has no one-request-per-second ceiling, so a trip's stop names
      resolve concurrently instead of taking a second each.

    * **Routing** prefers OSRM. ORS's driving-hgv profile is heavily
      conservative: on Dallas -> Oklahoma City it returns 211.7 mi in 5.96 h,
      a 35.5 mph average, against OSRM's 55.1 mph and ORS's own driving-car at
      60.5 mph. Around 55 mph is the realistic planning figure for a
      property-carrying CMV, and since every hours-of-service clock is driven by
      elapsed driving time, a 40% slow bias would inflate the rest count and the
      number of log sheets.
    """
    from .ors import OpenRouteServiceProvider
    from .osrm import OsrmProvider

    osrm = OsrmProvider()
    if getattr(settings, "ORS_API_KEY", ""):
        ors = OpenRouteServiceProvider(settings.ORS_API_KEY)
        return [ors, osrm], [osrm, ors]
    return [osrm], [osrm]


class RoutingService:
    """Fronts the providers, falling through the preference order on failure.

    A hosted demo should degrade rather than break: if the OpenRouteService
    quota runs out mid-assessment, geocoding quietly continues on Nominatim.
    """

    def __init__(self, geocoders: list, routers: list):
        self.geocoders = geocoders
        self.routers = routers
        self.used_geocoder: str | None = None
        self.used_router: str | None = None

    @property
    def active(self) -> str:
        return self.used_router or self.routers[0].name

    @property
    def geocoder_name(self) -> str:
        return self.used_geocoder or self.geocoders[0].name

    def _try(self, providers: list, method: str, *args):
        last: Exception | None = None
        for provider in providers:
            try:
                result = getattr(provider, method)(*args)
            except RoutingError as exc:
                last = exc
                logger.warning("%s.%s failed: %s", provider.name, method, exc)
                continue
            return provider.name, result
        raise last or RoutingError(f"No provider could handle {method}")

    # -- geocoding -----------------------------------------------------

    def geocode(self, query: str) -> GeoPoint:
        name, result = self._try(self.geocoders, "geocode", query)
        self.used_geocoder = name
        return result

    def autocomplete(self, query: str, limit: int = 5) -> list[GeoPoint]:
        name, result = self._try(self.geocoders, "autocomplete", query, limit)
        self.used_geocoder = name
        return result

    def reverse(self, lat: float, lon: float) -> str:
        name, result = self._try(self.geocoders, "reverse", lat, lon)
        self.used_geocoder = name
        return result

    def reverse_many(self, points: list[tuple[float, float]]) -> list[str]:
        name, result = self._try(self.geocoders, "reverse_many", points)
        self.used_geocoder = name
        return result

    # -- routing -------------------------------------------------------

    def route(self, start: GeoPoint, end: GeoPoint) -> RouteLeg:
        name, result = self._try(self.routers, "route", start, end)
        self.used_router = name
        return result


def get_routing_service() -> RoutingService:
    geocoders, routers = _providers()
    return RoutingService(geocoders, routers)
