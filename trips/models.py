from django.db import models
from users.models import User # Импортируем нашу модель пользователя

class Vehicle(models.Model):
    """Модель для хранения информации о транспортном средстве водителя."""
    # Связываем транспорт с конкретным пользователем (водителем)
    # on_delete=models.CASCADE означает, что если водитель удалится, его транспорт тоже удалится
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vehicles')
    
    brand = models.CharField("Марка", max_length=50)
    model = models.CharField("Модель", max_length=50)
    license_plate = models.CharField("Гос. номер", max_length=20, unique=True) # Номер должен быть уникальным

    def __str__(self):
        return f"{self.brand} {self.model} ({self.license_plate})"

class Trip(models.Model):
    """Модель для хранения информации о поездке."""
    # Связываем поездку с водителем и его конкретным транспортом
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips_as_driver')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='trips')
    
    departure_location = models.CharField("Место отправления", max_length=255)
    destination_location = models.CharField("Место назначения", max_length=255)
    departure_time = models.DateTimeField("Время отправления")
    available_seats = models.PositiveSmallIntegerField("Количество свободных мест")
    price = models.DecimalField("Цена за место", max_digits=10, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Поездка из {self.departure_location} в {self.destination_location} в {self.departure_time}"
