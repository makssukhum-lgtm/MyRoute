# config/urls.py

from django.contrib import admin
from django.urls import path, include
from .views import index_view  # <-- ДОБАВЬТЕ ЭТУ СТРОКУ

urlpatterns = [
    path('', index_view, name='index'),  # <-- И ДОБАВЬТЕ ЭТУ СТРОКУ
    path('admin/', admin.site.urls),
    path('support/', include('support.urls')),
    # ... здесь могут быть другие ваши пути
]
