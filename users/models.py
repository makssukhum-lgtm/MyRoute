from django.db import models

class User(models.Model):
    """
    Модель, представляющая пользователя телеграм-бота.
    """
    class Role(models.TextChoices):
        PASSENGER = 'passenger', 'Пассажир'
        DRIVER = 'driver', 'Водитель'

    class Language(models.TextChoices):
        RU = 'ru', 'Русский'
        UZ = 'uz', 'Узбекский'
        TJ = 'tj', 'Таджикский'

    telegram_id = models.BigIntegerField(
        unique=True,
        verbose_name='ID пользователя в Telegram'
    )
    name = models.CharField(
        max_length=255,
        verbose_name='Имя пользователя'
    )
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Номер телефона'
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.PASSENGER,
        verbose_name='Роль'
    )
    language = models.CharField(
        max_length=2,
        choices=Language.choices,
        default=Language.RU,
        verbose_name='Язык интерфейса'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата регистрации'
    )

    def __str__(self):
        return f'{self.name} ({self.telegram_id})'

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

