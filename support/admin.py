import os
import httpx
from django.contrib import admin, messages
from django.utils import timezone
from .models import SupportTicket

# Функция для отправки сообщения через Telegram API
def send_telegram_message(chat_id, text):
    """
    Отправляет сообщение пользователю в Telegram.
    """
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("Ошибка: Токен бота не найден в .env")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = httpx.post(url, json=payload)
        response.raise_for_status() # Проверяем, что запрос успешный
        return True
    except httpx.HTTPStatusError as e:
        print(f"Ошибка отправки сообщения: {e.response.json()}")
        return False
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return False

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """
    Настройки отображения обращений в поддержку.
    """
    list_display = ('user', 'status', 'created_at', 'responded_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__name', 'user__telegram_id', 'message')
    readonly_fields = ('user', 'message', 'created_at', 'responded_at')
    
    fieldsets = (
        ('Информация об обращении', {
            'fields': ('user', 'message', 'created_at', 'status')
        }),
        ('Ответ администратора', {
            'fields': ('response', 'responded_at')
        }),
    )

    def has_add_permission(self, request):
        # Отключаем возможность создавать обращения из админки
        return False

    def save_model(self, request, obj, form, change):
        """
        Переопределяем метод сохранения, чтобы добавить логику отправки ответа.
        """
        # Проверяем, был ли добавлен новый ответ и объект уже существует (мы не на странице создания)
        if change and 'response' in form.changed_data and obj.response:
            user_chat_id = obj.user.telegram_id
            response_text = (
                f"<b>Ответ на ваше обращение:</b>\n\n"
                f"<i>«{obj.message[:100]}...»</i>\n\n"
                f"<b>Ответ:</b> {obj.response}"
            )
            
            success = send_telegram_message(user_chat_id, response_text)
            
            if success:
                obj.status = SupportTicket.Status.CLOSED
                obj.responded_at = timezone.now()
                self.message_user(request, "Ответ успешно отправлен пользователю.", messages.SUCCESS)
            else:
                self.message_user(request, "Ошибка! Не удалось отправить ответ пользователю в Telegram.", messages.ERROR)

        super().save_model(request, obj, form, change)

