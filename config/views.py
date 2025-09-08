# config/views.py

from django.shortcuts import render

def index_view(request):
    """
    Эта функция отвечает за отображение главной страницы.
    """
    return render(request, 'index.html')
