"""API endpoints for planning, retrieving and geocoding trips."""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from .models import Trip
from .serializers import TripCreateSerializer, TripSerializer
from .services.planner import TripRequest, build_trip, round_to_quarter_hour
from .services.routing import GeocodingError, RoutingError, get_routing_service

logger = logging.getLogger(__name__)


@api_view(["POST"])
def create_trip(request):
    """Plan a trip: geocode, route, simulate hours of service, draw the logs."""
    serializer = TripCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    start_at = data.get("start_at") or datetime.now()
    if timezone.is_aware(start_at):
        start_at = timezone.make_naive(start_at, timezone.get_default_timezone())

    trip_request = TripRequest(
        current_location=data["current_location"],
        pickup_location=data["pickup_location"],
        dropoff_location=data["dropoff_location"],
        cycle_used_hours=data["cycle_used_hours"],
        start_at=round_to_quarter_hour(start_at),
        driver_name=data.get("driver_name", ""),
        carrier_name=data.get("carrier_name", ""),
        main_office=data.get("main_office", ""),
        truck_number=data.get("truck_number", ""),
        shipping_doc=data.get("shipping_doc", ""),
    )

    try:
        plan = build_trip(trip_request)
    except GeocodingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except RoutingError as exc:
        logger.exception("Routing failed")
        return Response(
            {"detail": f"Could not plan this route right now. {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    trip = Trip.objects.create(
        **{field: getattr(trip_request, field) for field in (
            "current_location", "pickup_location", "dropoff_location",
            "cycle_used_hours", "start_at", "driver_name", "carrier_name",
            "main_office", "truck_number", "shipping_doc",
        )},
        plan=plan,
        provider=plan["route"]["provider"],
    )

    return Response(TripSerializer(trip).data, status=status.HTTP_201_CREATED)


class TripDetail(RetrieveAPIView):
    """Rehydrate a saved trip for its shareable link."""

    queryset = Trip.objects.all()
    serializer_class = TripSerializer


@api_view(["GET"])
def geocode_suggestions(request):
    """Address autocomplete, proxied so the API key never reaches the browser."""
    query = request.query_params.get("q", "").strip()
    if len(query) < 3:
        return Response({"results": []})

    try:
        matches = get_routing_service().autocomplete(query, limit=5)
    except RoutingError as exc:
        logger.warning("Autocomplete failed: %s", exc)
        return Response({"results": []})

    return Response(
        {"results": [{"lat": m.lat, "lon": m.lon, "label": m.label} for m in matches]}
    )


@api_view(["GET"])
def health(request):
    """Liveness probe, also used to warm a cold serverless function.

    ``?deep=1`` additionally reports whether each provider is reachable from
    *this* environment, which is the only practical way to tell a missing
    deployment variable apart from a provider outage. Never reveals the key --
    only whether one is configured and how long it is.
    """
    if request.query_params.get("deep") not in {"1", "true", "yes"}:
        return Response({"status": "ok"})

    from django.conf import settings

    key = getattr(settings, "ORS_API_KEY", "")
    report = {
        "status": "ok",
        "ors_key_configured": bool(key),
        "ors_key_length": len(key),
        "providers": {},
    }

    service = get_routing_service()
    report["geocoders"] = [g.name for g in service.geocoders]
    report["routers"] = [r.name for r in service.routers]

    for provider in {p.name: p for p in service.geocoders}.values():
        checks = {}
        for label, call in (
            ("geocode", lambda p=provider: p.geocode("Dallas, Texas").label),
            ("reverse", lambda p=provider: p.reverse(32.7767, -96.7970)),
        ):
            try:
                checks[label] = {"ok": True, "result": call()}
            except Exception as exc:  # noqa: BLE001 - a probe reports, never raises
                checks[label] = {"ok": False, "error": str(exc)[:300]}
        report["providers"][provider.name] = checks

    return Response(report)
