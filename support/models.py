from django.db import models
from users.models import User

class SupportTicket(models.Model):
    """
    Модель для хранения обращений в службу поддержки.
    """
    class Status(models.TextChoices):
        OPEN = 'open', 'Открыт'
        CLOSED = 'closed', 'Закрыт'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets', verbose_name='Пользователь')
    message = models.TextField(verbose_name='Сообщение')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name='Статус'
    )
    response = models.TextField(blank=True, null=True, verbose_name='Ответ администратора')
    responded_at = models.DateTimeField(blank=True, null=True, verbose_name='Дата ответа')

    def __str__(self):
        return f"Обращение от {self.user.name} ({self.created_at.strftime('%d.%m.%Y')})"

    class Meta:
        verbose_name = 'Обращение в поддержку'
        verbose_name_plural = 'Обращения в поддержку'
        ordering = ['-created_at']

