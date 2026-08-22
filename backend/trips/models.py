"""Persistence for planned trips.

The computed plan is stored alongside the inputs so a shared ``/trip/<id>`` link
reloads instantly without spending another routing-provider request.
"""

from __future__ import annotations

import uuid

from django.db import models


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- inputs from the form ---
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    cycle_used_hours = models.FloatField(default=0)
    start_at = models.DateTimeField()

    # --- optional record-of-duty-status header fields (395.8) ---
    driver_name = models.CharField(max_length=120, blank=True)
    carrier_name = models.CharField(max_length=160, blank=True)
    main_office = models.CharField(max_length=200, blank=True)
    truck_number = models.CharField(max_length=80, blank=True)
    shipping_doc = models.CharField(max_length=120, blank=True)

    # --- computed plan ---
    plan = models.JSONField(default=dict)
    provider = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pickup_location} -> {self.dropoff_location} ({self.id})"
