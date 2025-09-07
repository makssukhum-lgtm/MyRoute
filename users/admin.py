import os
import httpx
from django.contrib import admin, messages
from .models import User

# Новая функция для отправки уведомлений
def send_telegram_notification(chat_id, text):
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("Токен бота не найден для отправки уведомления.")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    
    try:
        response = httpx.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")
        return False

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'role', 'verification_status', 'average_rating')
    list_filter = ('role', 'verification_status', 'language')
    search_fields = ('name', 'phone_number', 'telegram_id')
    list_editable = ('verification_status',)
    actions = ['approve_selected', 'reject_selected']
    
    fieldsets = (
        ('Основная информация', {'fields': ('name', 'phone_number', 'telegram_id')}),
        ('Статус и Роль', {'fields': ('role', 'verification_status')}),
        ('Рейтинг', {'fields': ('average_rating', 'rating_count')}),
        ('Техническая информация', {'fields': ('username', 'password', 'date_joined', 'last_login'), 'classes': ('collapse',)}),
    )
    readonly_fields = ('date_joined', 'last_login', 'average_rating', 'rating_count')


    @admin.action(description='Одобрить выбранных пользователей (станут водителями)')
    def approve_selected(self, request, queryset):
        updated_count = queryset.update(verification_status=User.VerificationStatus.VERIFIED)
        
        # Отправляем уведомление каждому одобренному пользователю
        for user in queryset:
            if user.telegram_id:
                message = "✅ Ваш аккаунт водителя был одобрен! Теперь вы можете создавать поездки в боте."
                send_telegram_notification(user.telegram_id, message)
                
        self.message_user(
            request,
            f"{updated_count} пользователей были успешно верифицированы.",
            messages.SUCCESS,
        )

    @admin.action(description='Отклонить выбранных пользователей')
    def reject_selected(self, request, queryset):
        updated_count = queryset.update(verification_status=User.VerificationStatus.REJECTED)
        
        for user in queryset:
            if user.telegram_id:
                message = "❌ К сожалению, ваш аккаунт водителя был отклонен. Свяжитесь с поддержкой для уточнений."
                send_telegram_notification(user.telegram_id, message)

        self.message_user(
            request,
            f"{updated_count} пользователей были отклонены.",
            messages.WARNING,
        )
