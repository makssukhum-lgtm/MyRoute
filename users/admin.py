from django.contrib import admin, messages
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Настройки отображения пользователей в админ-панели.
    """
    list_display = ('name', 'telegram_id', 'phone_number', 'role', 'verification_status')
    list_filter = ('role', 'language', 'verification_status')
    search_fields = ('name', 'telegram_id', 'phone_number')
    list_editable = ('verification_status',)
    actions = ['approve_drivers', 'reject_drivers']
    list_per_page = 20

    @admin.action(description='Одобрить выбранных водителей')
    def approve_drivers(self, request, queryset):
        # Одобряем только тех, у кого есть роль водителя, чтобы избежать ошибок
        updated = queryset.filter(role=User.Role.DRIVER).update(verification_status=User.VerificationStatus.APPROVED)
        if updated > 0:
            self.message_user(request, f'{updated} водителей были успешно одобрены.', messages.SUCCESS)
        else:
            self.message_user(request, 'Не было выбрано ни одного пользователя с ролью "Водитель".', messages.WARNING)


    @admin.action(description='Отклонить выбранных водителей')
    def reject_drivers(self, request, queryset):
        updated = queryset.filter(role=User.Role.DRIVER).update(verification_status=User.VerificationStatus.REJECTED)
        if updated > 0:
            self.message_user(request, f'{updated} водителей были отклонены.', messages.WARNING)
        else:
            self.message_user(request, 'Не было выбрано ни одного пользователя с ролью "Водитель".', messages.WARNING)

