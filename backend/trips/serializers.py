"""Request validation and response shaping for the trips API."""

from __future__ import annotations

from datetime import datetime

from rest_framework import serializers

from .models import Trip
from .services.hos import DEFAULT_RULES


class TripCreateSerializer(serializers.ModelSerializer):
    """The four inputs from the brief, plus optional log-header details."""

    current_location = serializers.CharField(max_length=255, trim_whitespace=True)
    pickup_location = serializers.CharField(max_length=255, trim_whitespace=True)
    dropoff_location = serializers.CharField(max_length=255, trim_whitespace=True)
    cycle_used_hours = serializers.FloatField(
        min_value=0,
        max_value=DEFAULT_RULES.cycle_limit_hours,
        help_text="Hours already used against the 70-hour/8-day cycle.",
    )
    start_at = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = Trip
        fields = [
            "current_location",
            "pickup_location",
            "dropoff_location",
            "cycle_used_hours",
            "start_at",
            "driver_name",
            "carrier_name",
            "main_office",
            "truck_number",
            "shipping_doc",
        ]

    def validate(self, attrs):
        if attrs["pickup_location"].strip().lower() == attrs["dropoff_location"].strip().lower():
            raise serializers.ValidationError(
                {"dropoff_location": "Dropoff must differ from pickup."}
            )
        return attrs


class TripSerializer(serializers.ModelSerializer):
    """A stored trip plus its computed plan."""

    class Meta:
        model = Trip
        fields = ["id", "created_at", "provider", "plan"]
        read_only_fields = fields

    def to_representation(self, instance: Trip) -> dict:
        data = super().to_representation(instance)
        plan = data.pop("plan") or {}
        return {"id": data["id"], "created_at": data["created_at"], **plan}
