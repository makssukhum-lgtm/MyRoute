from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404
from .models import SupportTicket

@login_required
def ticket_detail_view(request, ticket_id):
    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        raise Http404("Тикет не найден")

    context = { 'ticket': ticket }
    return render(request, 'support/templates/support/ticket_detail.html', context)
