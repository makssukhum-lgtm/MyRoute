from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

class Vehicle(models.Model):
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vehicles',
        verbose_name='Водитель'
    )
    brand = models.CharField('Марка', max_length=50)
    model = models.CharField('Модель', max_length=50)
    license_plate = models.CharField('Гос. номер', max_length=20, unique=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    def __str__(self):
        return f"{self.brand} {self.model} ({self.license_plate})"

    class Meta:
        verbose_name = 'Автомобиль'
        verbose_name_plural = 'Автомобили'

class Trip(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Активна'
        COMPLETED = 'COMPLETED', 'Завершена'
        CANCELED = 'CANCELED', 'Отменена'

    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trips_as_driver',
        verbose_name='Водитель'
    )
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='trips', verbose_name='Автомобиль')
    departure_location = models.CharField('Место отправления', max_length=100)
    destination_location = models.CharField('Место назначения', max_length=100)
    departure_time = models.DateTimeField('Время отправления')
    available_seats = models.PositiveSmallIntegerField('Свободные места')
    price = models.DecimalField('Цена за место', max_digits=8, decimal_places=2)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    status = models.CharField(
        'Статус поездки',
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    def __str__(self):
        return f"{self.departure_location} - {self.destination_location} ({self.departure_time.strftime('%d.%m.%Y')})"

    class Meta:
        verbose_name = 'Поездка'
        verbose_name_plural = 'Поездки'
        ordering = ['-departure_time']

class Booking(models.Model):
    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings_as_passenger',
        verbose_name='Пассажир'
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='bookings', verbose_name='Поездка')
    seats_booked = models.PositiveSmallIntegerField('Забронировано мест')
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    def __str__(self):
        return f"Бронь на {self.trip} от {self.passenger}"

    class Meta:
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'

class Rating(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='ratings', verbose_name='Поездка')
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_ratings',
        verbose_name='Кто оценил'
    )
    rated_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_ratings',
        verbose_name='Кого оценили'
    )
    score = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField('Комментарий', blank=True, null=True)
    created_at = models.DateTimeField('Дата оценки', auto_now_add=True)

    def __str__(self):
        return f"Оценка {self.score} от {self.rater.name} для {self.rated_user.name}"

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'
        unique_together = ('trip', 'rater', 'rated_user')
