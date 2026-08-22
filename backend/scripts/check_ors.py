"""Hands-on diagnostic for the OpenRouteService integration.

Run it to see exactly what the app asks OpenRouteService for, what comes back,
and the measurement behind the decision to route with OSRM instead.

    cd backend
    .venv/bin/python scripts/check_ors.py

Never prints your API key.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("LOG_LEVEL", "ERROR")

import django  # noqa: E402

django.setup()

import httpx  # noqa: E402
from django.conf import settings  # noqa: E402

from trips.services.osrm import OsrmProvider  # noqa: E402
from trips.services.ors import OpenRouteServiceProvider  # noqa: E402
from trips.services.routing import RoutingError, get_routing_service  # noqa: E402
from trips.services.types import GeoPoint  # noqa: E402

BOLD, DIM, GREEN, RED, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m",
)

# Dallas and Oklahoma City: ~210 miles of interstate, a clean speed benchmark.
DALLAS = GeoPoint(32.736212, -96.784359, "Dallas, TX")
OKC = GeoPoint(35.393761, -97.602513, "Oklahoma City, OK")

# A point on I-44 in rural Missouri, well away from any large city. This is
# where the two geocoders disagree most.
RURAL_MO = (37.98, -91.35)


def header(n: int, title: str, why: str) -> None:
    print(f"\n{BOLD}[{n}] {title}{RESET}\n{DIM}    {why}{RESET}\n")


def main() -> int:
    print(f"{BOLD}OpenRouteService check{RESET}")

    key = settings.ORS_API_KEY
    if not key:
        print(f"\n  {YELLOW}No ORS_API_KEY found.{RESET}")
        print("  Put one in backend/.env as ORS_API_KEY=... and re-run.")
        print("  (The app still works without it, on OSRM + Nominatim.)")
        return 1
    print(f"  key: {GREEN}configured{RESET}, {len(key)} chars, ends ...{key[-4:]}")

    ors = OpenRouteServiceProvider(key)
    osrm = OsrmProvider()

    # ---------------------------------------------------------------
    header(1, "Forward geocoding", "Turns what you type into coordinates.")
    for query in ("Dallas, Texas", "Oklahoma City, Oklahoma"):
        point = ors.geocode(query)
        print(f"    {query:<26} -> {point.lat:9.5f}, {point.lon:10.5f}  {point.label}")

    # ---------------------------------------------------------------
    header(2, "Autocomplete", "Powers the dropdown under each location box.")
    for fragment in ("Dall", "Chicag"):
        labels = [p.label for p in ors.autocomplete(fragment, 3)]
        print(f"    {fragment!r:<10} -> {labels}")

    # ---------------------------------------------------------------
    header(
        3,
        "Reverse geocoding",
        "49 CFR 395.8 wants a city and state in Remarks at every duty change.",
    )
    corridors = [
        (37.98, -91.35, "I-44, Missouri"),
        (32.05, -101.30, "I-20, west Texas"),
        (34.77, -114.50, "I-40, Arizona"),
        (41.13, -100.77, "I-80, Nebraska"),
    ]
    print(f"    {'corridor':<20} {'OpenRouteService':<24} {'Nominatim':<24}")
    disagreements = 0
    for lat, lon, label in corridors:
        a, b = ors.reverse(lat, lon), osrm.reverse(lat, lon)
        if a != b:
            disagreements += 1
        mark = f"  {YELLOW}differ{RESET}" if a != b else ""
        print(f"    {label:<20} {a:<24} {b:<24}{mark}")

    print(
        f"\n    {DIM}Name quality is close to a wash -- they agreed on "
        f"{len(corridors) - disagreements} of {len(corridors)} here, and both fall back to a"
    )
    print(f"    county where no town exists. That is honest: ORS is not clearly better at naming.{RESET}")

    points = [c[:2] for c in corridors] + [(39.1, -94.6), (38.6, -90.2)]
    t0 = time.time()
    ors.reverse_many(points)
    ors_secs = time.time() - t0
    print(f"\n    {BOLD}The real difference is throughput:{RESET}")
    print(f"      {len(points)} lookups, concurrent (ORS):      {GREEN}{ors_secs:5.2f}s{RESET}")
    print(f"      {len(points)} lookups, throttled (Nominatim): {YELLOW}~{len(points) * 1.05:5.2f}s{RESET}"
          f"  {DIM}(policy caps it at 1/second){RESET}")
    print(f"\n    {DIM}A long trip has 15-20 stops to name. That is the difference between a")
    print(f"    5-second response and a 25-second one. Nominatim's usage policy also asks")
    print(f"    you not to point autocomplete traffic at it, which ORS has no issue with.{RESET}")

    # ---------------------------------------------------------------
    header(
        4,
        "Routing speed  <- the reason we do NOT route with ORS",
        "Dallas to Oklahoma City, ~210 miles, almost all interstate.",
    )
    rows = []
    for label, fn in (
        ("ORS driving-hgv", lambda: _ors_route(key, "driving-hgv")),
        ("ORS driving-car", lambda: _ors_route(key, "driving-car")),
        ("OSRM driving", lambda: (osrm.route(DALLAS, OKC).total_miles,
                                  osrm.route(DALLAS, OKC).total_time_s / 3600)),
    ):
        try:
            miles, hours = fn()
            rows.append((label, miles, hours, miles / hours))
        except Exception as exc:  # noqa: BLE001
            print(f"    {label:<18} failed: {exc}")

    print(f"    {'profile':<18} {'miles':>7} {'hours':>7} {'avg mph':>9}")
    for label, miles, hours, mph in rows:
        flag = ""
        if mph < 45:
            flag = f"  {RED}<- unrealistically slow{RESET}"
        elif 50 <= mph <= 58:
            flag = f"  {GREEN}<- realistic for a truck{RESET}"
        print(f"    {label:<18} {miles:7.1f} {hours:7.2f} {mph:9.1f}{flag}")

    print(f"\n    {DIM}Every hours-of-service clock is driven by elapsed time, so a slow")
    print(f"    routing profile would invent extra rest stops and extra log sheets.{RESET}")

    # ---------------------------------------------------------------
    header(5, "What the app actually does with all this", "Roles resolve separately.")
    service = get_routing_service()
    print(f"    geocoding, in preference order: {[g.name for g in service.geocoders]}")
    print(f"    routing,   in preference order: {[r.name for r in service.routers]}")
    print(f"\n    {DIM}Each falls through to the next if one fails, so a spent quota")
    print(f"    degrades the app instead of breaking it.{RESET}")

    print(f"\n{GREEN}{BOLD}All checks completed.{RESET}\n")
    return 0


def _ors_route(key: str, profile: str) -> tuple[float, float]:
    """Call ORS directly so the profile can be varied for the comparison."""
    response = httpx.post(
        f"https://api.openrouteservice.org/v2/directions/{profile}/geojson",
        json={
            "coordinates": [[DALLAS.lon, DALLAS.lat], [OKC.lon, OKC.lat]],
            # Without this ORS rejects its own geocoder's city centroids:
            # "Could not find routable point within a radius of 350.0 metres".
            "radiuses": [-1, -1],
        },
        headers={"Authorization": key, "Content-Type": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    summary = response.json()["features"][0]["properties"]["summary"]
    return summary["distance"] / 1609.344, summary["duration"] / 3600


if __name__ == "__main__":
    raise SystemExit(main())
