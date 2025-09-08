# support/consumers.py

import json
from django.conf import settings
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from telegram import Bot, error
from .models import SupportTicket, ChatMessage

# Инициализируем бота ОДИН РАЗ, используя токен из настроек
telegram_bot = Bot(token=settings.BOT_TOKEN)

class SupportConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.ticket_id = self.scope['url_route']['kwargs']['ticket_id']
        self.room_group_name = f'support_{self.ticket_id}'
        self.user = self.scope['user']

        # Проверяем, что к чату подключается аутентифицированный сотрудник
        if not self.user.is_authenticated or not self.user.is_staff:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        
        chat_message = await self.save_message(message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': self.user.name,
                'timestamp': chat_message.timestamp.strftime("%d.%m.%Y %H:%M"),
            }
        )
        await self.send_message_to_telegram(chat_message)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'username': event['username'],
            'timestamp': event['timestamp'],
        }))

    @sync_to_async
    def save_message(self, message):
        ticket = SupportTicket.objects.select_related('user').get(id=self.ticket_id)
        return ChatMessage.objects.create(
            ticket=ticket,
            author=self.user,
            message=message
        )
            
    async def send_message_to_telegram(self, chat_message):
        user_telegram_id = chat_message.ticket.user.telegram_id
        text = f"💬 **Ответ от поддержки:**\n\n{chat_message.message}"
        try:
            await telegram_bot.send_message(chat_id=user_telegram_id, text=text, parse_mode='Markdown')
        except error.TelegramError as e:
            print(f"!!! ОШИБКА: Не удалось отправить сообщение в Telegram пользователю {user_telegram_id}: {e}")
