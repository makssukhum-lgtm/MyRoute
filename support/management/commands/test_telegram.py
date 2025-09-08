# support/management/commands/test_telegram.py

import asyncio
import traceback
from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Bot

# --- ВАЖНО: Вставьте сюда ID вашего личного Telegram аккаунта ---
# Вы можете узнать его, написав боту @userinfobot
TEST_TELEGRAM_ID = 997878534 # ЗАМЕНИТЕ ЭТОТ ID НА СВОЙ

class Command(BaseCommand):
    help = 'Отправляет тестовое сообщение в Telegram для отладки.'

    async def main_logic(self):
        self.stdout.write("--- НАЧАЛО ТЕСТА ОТПРАВКИ ---")

        bot_token = settings.BOT_TOKEN
        if not bot_token:
            self.stderr.write(self.style.ERROR("ОШИБКА: BOT_TOKEN не найден в настройках Django!"))
            self.stderr.write("Убедитесь, что он есть в .env и в config/settings.py.")
            return

        self.stdout.write(f"Использую токен, который заканчивается на: ...{bot_token[-6:]}")

        try:
            self.stdout.write(f"Пытаюсь отправить сообщение пользователю с ID: {TEST_TELEGRAM_ID}...")
            bot = Bot(token=bot_token)
            await bot.send_message(
                chat_id=TEST_TELEGRAM_ID,
                text="Это тестовое сообщение от вашего сайта Django. Если вы его получили, все работает!"
            )
            self.stdout.write(self.style.SUCCESS("УСПЕХ! Сообщение успешно отправлено. Проверьте ваш Telegram."))

        except Exception as e:
            self.stderr.write(self.style.ERROR("!!! КРИТИЧЕСКАЯ ОШИБКА ПРИ ОТПРАВКЕ !!!"))
            # Выводим полный текст ошибки, чтобы точно понять причину
            traceback.print_exc()

        self.stdout.write("--- КОНЕЦ ТЕСТА ---")


    def handle(self, *args, **options):
        asyncio.run(self.main_logic())
