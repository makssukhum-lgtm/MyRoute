# support/models.py

from django.db import models
from users.models import User

class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        CLOSED = 'CLOSED', 'Закрыт'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    message = models.TextField(verbose_name="Текст обращения") # <-- Наше недостающее поле
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Статус"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    def __str__(self):
        return f"Тикет #{self.id} от {self.user.name}"

    class Meta:
        verbose_name = "Обращение в поддержку"
        verbose_name_plural = "Обращения в поддержку"
        ordering = ['-created_at']

class ChatMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Сообщение от {self.author.name} в тикете #{self.ticket.id}"

    class Meta:
        ordering = ['timestamp']
