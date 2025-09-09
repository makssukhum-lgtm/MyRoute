import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
import httpx

from users.models import User
from .models import SupportTicket, TicketMessage

# --- Вспомогательные функции для работы с БД ---
@database_sync_to_async
def get_ticket_and_user(ticket_id, admin_user):
    """
    Находит обращение в БД и проверяет, что пользователь - администратор.
    """
    try:
        ticket = SupportTicket.objects.select_related('user').get(id=ticket_id)
        if not admin_user.is_staff:
            return None, None
        return ticket, ticket.user
    except SupportTicket.DoesNotExist:
        return None, None

@database_sync_to_async
def save_message(ticket, sender, message_text):
    """
    Сохраняет новое сообщение в базу данных.
    """
    return TicketMessage.objects.create(
        ticket=ticket,
        sender=sender,
        text=message_text
    )

@database_sync_to_async
def get_ticket_history(ticket):
    """
    Загружает историю сообщений для данного обращения.
    """
    return list(ticket.messages.select_related('sender').order_by('timestamp'))

# --- Функция для отправки сообщения пользователю в Telegram ---
def send_telegram_message(chat_id, text):
    """
    Отправляет сообщение пользователю в Telegram.
    (Эта функция дублируется из admin.py для использования здесь)
    """
    bot_token = settings.BOT_TOKEN
    if not bot_token:
        print("Ошибка: Токен бота не найден в настройках Django.")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    try:
        # Используем синхронный запрос, так как consumer работает в асинхронном потоке
        with httpx.Client() as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Получаем ID обращения из URL
        self.ticket_id = self.scope['url_route']['kwargs']['ticket_id']
        self.room_group_name = f'chat_{self.ticket_id}'
        self.user = self.scope['user']

        # Проверяем, что пользователь авторизован и является администратором
        if not self.user.is_authenticated or not self.user.is_staff:
            await self.close()
            return

        # Присоединяемся к "комнате" чата
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Загружаем и отправляем историю сообщений
        history = await get_ticket_history(await get_ticket_and_user(self.ticket_id, self.user))
        for msg in history:
            sender_name = "Вы (Админ)" if msg.sender == self.user else msg.sender.name
            await self.send(text_data=json.dumps({
                'message': msg.text,
                'sender': sender_name
            }))


    async def disconnect(self, close_code):
        # Отключаемся от "комнаты"
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Принимаем сообщение от WebSocket (от администратора с сайта)
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        
        ticket, target_user = await get_ticket_and_user(self.ticket_id, self.user)
        if not ticket:
            return

        # Сохраняем сообщение в БД
        await save_message(ticket, self.user, message)

        # Отправляем сообщение пользователю в Telegram
        send_telegram_message(target_user.telegram_id, message)
        
        # Отправляем сообщение в "комнату" (чтобы оно отобразилось у самого администратора)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': 'Вы (Админ)'
            }
        )

    # Принимаем сообщение от "комнаты" (от бота)
    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']

        # Отправляем сообщение в WebSocket (в браузер администратору)
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender
        }))

