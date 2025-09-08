# support/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Этот маршрут будет открывать страницу чата по адресу /support/ID/,
    # например /support/12/
    path('<int:ticket_id>/', views.ticket_detail_view, name='ticket_detail'),
]
