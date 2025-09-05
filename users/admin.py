from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Настройки отображения пользователей в админ-панели.
    """
    list_display = ('name', 'telegram_id', 'phone_number', 'role', 'language')
    list_filter = ('role', 'language')
    search_fields = ('name', 'telegram_id', 'phone_number')
    list_per_page = 20
