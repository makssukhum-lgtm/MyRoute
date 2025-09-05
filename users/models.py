from django.db import models

class User(models.Model):
    """
    Модель пользователя Телеграм-бота.
    """
    class Role(models.TextChoices):
        PASSENGER = 'passenger', 'Пассажир'
        DRIVER = 'driver', 'Водитель'

    class VerificationStatus(models.TextChoices):
        NOT_VERIFIED = 'not_verified', 'Не проверен'
        PENDING = 'pending', 'На проверке'
        APPROVED = 'approved', 'Одобрен'
        REJECTED = 'rejected', 'Отклонен'

    telegram_id = models.BigIntegerField(unique=True, verbose_name='ID пользователя в Телеграм')
    name = models.CharField(max_length=255, verbose_name='Имя пользователя')
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name='Номер телефона')
    language = models.CharField(max_length=2, blank=True, null=True, verbose_name='Язык')
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        blank=True,
        null=True,
        verbose_name='Роль'
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NOT_VERIFIED,
        verbose_name='Статус верификации'
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

