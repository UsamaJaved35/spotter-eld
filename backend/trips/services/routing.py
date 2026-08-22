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


def get_provider() -> RoutingProvider:
    """The configured primary provider: OpenRouteService if keyed, else OSRM."""
    from .ors import OpenRouteServiceProvider
    from .osrm import OsrmProvider

    if getattr(settings, "ORS_API_KEY", ""):
        return OpenRouteServiceProvider(settings.ORS_API_KEY)
    return OsrmProvider()


def get_fallback_provider() -> RoutingProvider:
    from .osrm import OsrmProvider

    return OsrmProvider()


class FallbackProvider:
    """Tries the primary provider, then the keyless one.

    A hosted demo should degrade rather than fail: if the OpenRouteService quota
    is exhausted mid-assessment, routing quietly continues on OSRM.
    """

    name = "fallback"

    def __init__(self, primary: RoutingProvider, secondary: RoutingProvider):
        self.primary = primary
        self.secondary = secondary

    @property
    def active(self) -> str:
        return self._used or self.primary.name

    def __post_init__(self):  # pragma: no cover - dataclass parity
        pass

    _used: str | None = None

    def _attempt(self, method: str, *args, **kwargs):
        try:
            result = getattr(self.primary, method)(*args, **kwargs)
            self._used = self.primary.name
            return result
        except RoutingError as exc:
            if self.primary is self.secondary:
                raise
            logger.warning(
                "%s.%s failed (%s); falling back to %s",
                self.primary.name,
                method,
                exc,
                self.secondary.name,
            )
            result = getattr(self.secondary, method)(*args, **kwargs)
            self._used = self.secondary.name
            return result

    def geocode(self, query: str) -> GeoPoint:
        return self._attempt("geocode", query)

    def autocomplete(self, query: str, limit: int = 5) -> list[GeoPoint]:
        return self._attempt("autocomplete", query, limit)

    def reverse(self, lat: float, lon: float) -> str:
        return self._attempt("reverse", lat, lon)

    def reverse_many(self, points: list[tuple[float, float]]) -> list[str]:
        return self._attempt("reverse_many", points)

    def route(self, start: GeoPoint, end: GeoPoint) -> RouteLeg:
        return self._attempt("route", start, end)


def get_routing_service() -> FallbackProvider:
    primary = get_provider()
    secondary = get_fallback_provider()
    if primary.name == secondary.name:
        secondary = primary
    return FallbackProvider(primary, secondary)
