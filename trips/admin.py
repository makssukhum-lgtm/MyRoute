from django.contrib import admin, messages
from .models import Vehicle, Trip, Booking

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'driver')
    search_fields = ('brand', 'model', 'license_plate', 'driver__name')
    list_filter = ('brand',)

class BookingInline(admin.TabularInline):
    model = Booking
    extra = 0
    readonly_fields = ('passenger', 'seats_booked', 'created_at')
    # Убираем возможность добавлять/изменять/удалять бронирования напрямую из поездки
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'driver', 'status', 'departure_time', 'available_seats')
    list_filter = ('status', 'departure_time', 'departure_location', 'destination_location')
    search_fields = ('departure_location', 'destination_location', 'driver__name', 'vehicle__license_plate')
    readonly_fields = ('created_at',)
    inlines = [BookingInline]
    actions = ['mark_as_completed', 'mark_as_canceled']

    @admin.action(description='Отметить выбранные поездки как "Завершенные"')
    def mark_as_completed(self, request, queryset):
        updated_count = queryset.update(status=Trip.Status.COMPLETED)
        self.message_user(
            request,
            f"{updated_count} поездок были успешно отмечены как завершенные.",
            messages.SUCCESS,
        )

    @admin.action(description='Отметить выбранные поездки как "Отмененные"')
    def mark_as_canceled(self, request, queryset):
        updated_count = queryset.update(status=Trip.Status.CANCELED)
        self.message_user(
            request,
            f"{updated_count} поездок были успешно отмечены как отмененные.",
            messages.SUCCESS,
        )

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'trip', 'passenger', 'seats_booked', 'created_at')
    search_fields = ('trip__departure_location', 'passenger__name')
