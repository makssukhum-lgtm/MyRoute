from django.contrib import admin
from .models import Vehicle, Trip, Booking

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    """
    Настройки отображения транспорта.
    """
    list_display = ('__str__', 'driver')
    search_fields = ('brand', 'model', 'license_plate', 'driver__name')

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    """
    Настройки отображения поездок.
    """
    list_display = (
        'departure_location',
        'destination_location',
        'departure_time',
        'driver',
        'vehicle',
        'available_seats'
    )
    list_filter = ('departure_location', 'destination_location')
    search_fields = ('departure_location', 'destination_location', 'driver__name')
    date_hierarchy = 'departure_time'

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """
    Настройки отображения бронирований.
    """
    list_display = ('passenger', 'trip', 'seats_booked', 'created_at')
    search_fields = ('passenger__name', 'trip__driver__name')
