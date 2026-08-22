from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("geocode/", views.geocode_suggestions, name="geocode"),
    path("trips/", views.create_trip, name="trip-create"),
    path("trips/<uuid:pk>/", views.TripDetail.as_view(), name="trip-detail"),
]
