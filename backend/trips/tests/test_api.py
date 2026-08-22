"""API tests. Routing is stubbed so these never touch the network."""

from __future__ import annotations

import json

import pytest

from trips.services.types import GeoPoint
from trips.tests.factories import straight_leg

pytestmark = pytest.mark.django_db


class FakeProvider:
    """Deterministic stand-in for a routing provider."""

    name = "fake"

    PLACES = {
        "dallas, texas": GeoPoint(32.7767, -96.7970, "Dallas, TX"),
        "oklahoma city, oklahoma": GeoPoint(35.4676, -97.5164, "Oklahoma City, OK"),
        "chicago, illinois": GeoPoint(41.8781, -87.6298, "Chicago, IL"),
    }

    def geocode(self, query):
        from trips.services.routing import GeocodingError

        try:
            return self.PLACES[query.strip().lower()]
        except KeyError:
            raise GeocodingError(f"Could not find a location matching {query!r}")

    def autocomplete(self, query, limit=5):
        return list(self.PLACES.values())[:limit]

    def reverse(self, lat, lon):
        return "Testville, TX"

    def reverse_many(self, points):
        return ["Testville, TX"] * len(points)

    def route(self, start, end):
        return straight_leg(500)


@pytest.fixture(autouse=True)
def stub_routing(monkeypatch):
    from trips.services import routing

    provider = FakeProvider()
    monkeypatch.setattr(routing, "get_provider", lambda: provider)
    monkeypatch.setattr(routing, "get_fallback_provider", lambda: provider)
    return provider


def post_trip(client, **overrides):
    payload = {
        "current_location": "Dallas, Texas",
        "pickup_location": "Oklahoma City, Oklahoma",
        "dropoff_location": "Chicago, Illinois",
        "cycle_used_hours": 20,
        "start_at": "2026-03-02T06:00:00",
        **overrides,
    }
    return client.post("/api/trips/", data=json.dumps(payload), content_type="application/json")


def test_create_trip_returns_a_complete_plan(client):
    response = post_trip(client)
    assert response.status_code == 201

    body = response.json()
    assert body["summary"]["total_miles"] == pytest.approx(1000, abs=1)
    assert body["daily_logs"], "expected at least one log sheet"
    assert body["route"]["legs"][0]["coords"]
    assert body["assumptions"]


def test_every_returned_log_sheet_totals_twenty_four_hours(client):
    body = post_trip(client).json()

    for log in body["daily_logs"]:
        assert sum(log["totals"].values()) == pytest.approx(24.0, abs=0.01), log["date"]


def test_trip_is_retrievable_by_its_shareable_id(client):
    created = post_trip(client).json()

    response = client.get(f"/api/trips/{created['id']}/")
    assert response.status_code == 200
    assert response.json()["summary"] == created["summary"]


def test_unknown_place_is_a_400_not_a_500(client):
    response = post_trip(client, current_location="Nowhere At All")
    assert response.status_code == 400
    assert "Nowhere At All" in response.json()["detail"]


def test_cycle_hours_beyond_the_limit_are_rejected(client):
    response = post_trip(client, cycle_used_hours=85)
    assert response.status_code == 400
    assert "cycle_used_hours" in response.json()


def test_pickup_and_dropoff_must_differ(client):
    response = post_trip(client, dropoff_location="Oklahoma City, Oklahoma")
    assert response.status_code == 400
    assert "dropoff_location" in response.json()


def test_health_endpoint(client):
    assert client.get("/api/health/").json() == {"status": "ok"}
