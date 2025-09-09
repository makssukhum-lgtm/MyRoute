from django.urls import path
from . import views

urlpatterns = [
    path('ticket/<int:ticket_id>/', views.ticket_detail_view, name='ticket_detail'),
]
