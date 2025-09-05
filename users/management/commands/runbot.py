import os
import asyncio
from dotenv import load_dotenv

from django.core.management.base import BaseCommand
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# Определяем асинхронную функцию для команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение в ответ на команду /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я бот MyRoute. Добро пожаловать!",
    )

class Command(BaseCommand):
    """
    Django-команда для запуска телеграм-бота.
    Запускает бота в режиме polling (постоянный опрос).
    """
    help = 'Запускает телеграм-бота'

    def handle(self, *args, **options):
        """Основная логика команды."""
        self.stdout.write("Запуск телеграм-бота...")

        # Загружаем переменные окружения из файла .env
        load_dotenv()
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            self.stderr.write(self.style.ERROR("Токен бота не найден. Убедитесь, что файл .env существует и содержит BOT_TOKEN."))
            return

        # Создаем экземпляр бота
        application = Application.builder().token(bot_token).build()

        # Добавляем обработчик для команды /start
        application.add_handler(CommandHandler("start", start))

        # Запускаем бота
        self.stdout.write(self.style.SUCCESS("Бот успешно запущен! Нажмите Ctrl+C для остановки."))
        application.run_polling()
