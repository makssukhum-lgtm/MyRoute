# support/admin.py

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import SupportTicket, ChatMessage

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'created_at', 'open_chat_link')
    list_filter = ('status', 'created_at')
    search_fields = ('user__name', 'user__telegram_id', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('user', 'message', 'created_at', 'updated_at')

    def open_chat_link(self, obj):
        """
        Создает ссылку на страницу чата, которая открывается в той же вкладке.
        Атрибут target="_blank" был удален.
        """
        url = reverse('ticket_detail', args=[obj.id])
        return format_html('<a href="{}">Перейти в чат</a>', url)

    open_chat_link.short_description = 'Чат с пользователем'

# Регистрируем модель сообщений, чтобы видеть ее в админке (для отладки)
@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'author', 'timestamp')
    list_filter = ('timestamp', 'author')
    search_fields = ('message', 'author__name')
