from django.db import models
from users.models import User

class SupportTicket(models.Model):
    """
    Модель для хранения обращений в службу поддержки.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='support_tickets',
        verbose_name='Пользователь'
    )
    message = models.TextField(verbose_name='Текст обращения')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    is_resolved = models.BooleanField(default=False, verbose_name='Обращение решено')

    def __str__(self):
        return f'Обращение от {self.user.name} ({self.created_at.strftime("%d.%m.%Y %H:%M")})'

    class Meta:
        verbose_name = 'Обращение в поддержку'
        verbose_name_plural = 'Обращения в поддержку'
        ordering = ['-created_at']

