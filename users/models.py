from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission

class User(AbstractUser):
    class Role(models.TextChoices):
        PASSENGER = 'PASSENGER', 'Пассажир'
        DRIVER = 'DRIVER', 'Водитель'

    class VerificationStatus(models.TextChoices):
        NOT_VERIFIED = 'NOT_VERIFIED', 'Не проверен'
        PENDING = 'PENDING', 'На проверке'
        VERIFIED = 'VERIFIED', 'Проверен'
        REJECTED = 'REJECTED', 'Отклонен'

    # Убираем стандартные поля, которые нам не нужны
    first_name = None
    last_name = None

    # Наши кастомные поля
    telegram_id = models.BigIntegerField('ID пользователя в Telegram', unique=True, null=True, blank=True)
    name = models.CharField('Имя пользователя', max_length=255)
    phone_number = models.CharField('Номер телефона', max_length=20, null=True, blank=True)
    language = models.CharField('Язык', max_length=2, null=True, blank=True)
    role = models.CharField('Роль', max_length=10, choices=Role.choices, null=True, blank=True)
    verification_status = models.CharField(
        'Статус верификации',
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NOT_VERIFIED
    )
    # НОВЫЕ ПОЛЯ ДЛЯ РЕЙТИНГА
    average_rating = models.FloatField('Средний рейтинг', default=0.0)
    rating_count = models.PositiveIntegerField('Количество оценок', default=0)

    # Поля для решения конфликтов с auth.User
    groups = models.ManyToManyField(
        Group,
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="custom_user_groups",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="custom_user_permissions",
        related_query_name="user",
    )

    def __str__(self):
        return self.name or f"User {self.telegram_id}"
