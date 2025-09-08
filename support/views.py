# support/views.py

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from .models import SupportTicket

@staff_member_required
def ticket_detail_view(request, ticket_id):
    """
    Отображает страницу чата для конкретного тикета.
    Доступно только для персонала (администраторов).
    """
    try:
        ticket = SupportTicket.objects.prefetch_related('messages', 'messages__author').get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        from django.http import Http404
        raise Http404("Тикет не найден")

    # Передаем контекст, который нужен для базового шаблона админки
    context = {
        'ticket': ticket,
        'chat_messages': ticket.messages.all(),
        'title': f'Чат по обращению #{ticket.id}',
        'has_permission': True, # Говорим, что у админа есть права на просмотр
    }
    return render(request, 'support/ticket_detail.html', context)
