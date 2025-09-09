import asyncio
import traceback
from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Bot, error

class Command(BaseCommand):
    help = 'Тестово отправляет прямое сообщение пользователю в Telegram из окружения Django.'

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int, help='ID пользователя в Telegram для отправки сообщения')
        parser.add_argument('message', type=str, help='Текст сообщения для отправки в кавычках')

    async def main_logic(self, telegram_id, message):
        self.stdout.write("\n--- НАЧАЛО ТЕСТА ПРЯМОЙ ОТПРАВКИ ---")
        
        bot_token = settings.BOT_TOKEN
        if not bot_token:
            self.stderr.write(self.style.ERROR("!!! ПРОВАЛ: BOT_TOKEN не найден в настройках Django!"))
            self.stderr.write("Убедитесь, что .env загружается в manage.py и asgi.py.")
            return

        self.stdout.write(f"Использую токен, который заканчивается на: ...{bot_token[-6:]}")
        
        try:
            self.stdout.write(f"Пытаюсь отправить сообщение '{message}' пользователю с ID: {telegram_id}...")
            bot = Bot(token=bot_token)
            await bot.send_message(
                chat_id=telegram_id,
                text=f"Это прямое тестовое сообщение от вашего сайта:\n\n{message}"
            )
            self.stdout.write(self.style.SUCCESS("--- УСПЕХ! Команда отправки выполнена. Проверьте ваш Telegram. ---"))

        except error.TelegramError as e:
            self.stderr.write(self.style.ERROR(f"!!! ПРОВАЛ: ОШИБКА TELEGRAM API: {e} !!!"))
            self.stderr.write("Проверьте правильность токена и ID пользователя.")
        except Exception:
            self.stderr.write(self.style.ERROR("!!! ПРОВАЛ: Произошла непредвиденная ошибка !!!"))
            traceback.print_exc()

        self.stdout.write("--- КОНЕЦ ТЕСТА ---\n")

    def handle(self, *args, **options):
        telegram_id = options['telegram_id']
        message = options['message']
        asyncio.run(self.main_logic(telegram_id, message))
