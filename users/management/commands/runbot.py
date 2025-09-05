import os
import logging
from dotenv import load_dotenv
from asgiref.sync import sync_to_async

from django.core.management.base import BaseCommand
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Подключаем нашу модель User из Django
from users.models import User

# Настраиваем логирование для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Определяем "состояния" нашего диалога
SELECTING_LANGUAGE, REQUESTING_PHONE, SELECTING_ROLE = range(3)

# --- Функции для СИНХРОННОЙ работы с базой данных ---
# Эти функции остаются без изменений. Они работают в обычном, синхронном режиме.

def get_user(telegram_id):
    """Получает пользователя из БД."""
    try:
        return User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None

def create_user(telegram_id, name):
    """Создает нового пользователя в БД."""
    return User.objects.create(telegram_id=telegram_id, name=name)

def update_user_language(user, language_code):
    """Обновляет язык пользователя."""
    user.language = language_code
    user.save()

def update_user_phone(user, phone_number):
    """Обновляет номер телефона пользователя."""
    user.phone_number = phone_number
    user.save()

def update_user_role(user, role):
    """Обновляет роль пользователя."""
    user.role = role
    user.save()

# --- Создаем АСИНХРОННЫЕ "обертки" для наших синхронных функций ---
# Это "переводчики", которые позволяют безопасно вызывать код Django из асинхронного бота
get_user_async = sync_to_async(get_user, thread_sensitive=True)
create_user_async = sync_to_async(create_user, thread_sensitive=True)
update_user_language_async = sync_to_async(update_user_language, thread_sensitive=True)
update_user_phone_async = sync_to_async(update_user_phone, thread_sensitive=True)
update_user_role_async = sync_to_async(update_user_role, thread_sensitive=True)


# --- Функции-обработчики для диалога (теперь используют async-обертки) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог регистрации при команде /start."""
    telegram_user = update.effective_user
    
    # ИСПОЛЬЗУЕМ АСИНХРОННУЮ ВЕРСИЮ
    user = await get_user_async(telegram_user.id)

    if user:
        # Если пользователь уже есть, приветствуем его и завершаем диалог
        await update.message.reply_text(f"С возвращением, {user.name}! Вы уже зарегистрированы.")
        return ConversationHandler.END
    else:
        # Если пользователя нет, начинаем регистрацию
        # ИСПОЛЬЗУЕМ АСИНХРОННУЮ ВЕРСИЮ
        await create_user_async(telegram_user.id, telegram_user.full_name)
        
        # Предлагаем выбрать язык
        keyboard = [
            [KeyboardButton("Русский 🇷🇺"), KeyboardButton("O'zbekcha 🇺🇿"), KeyboardButton("Тоҷикӣ 🇹🇯")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Пожалуйста, выберите ваш язык:", reply_markup=reply_markup)
        
        return SELECTING_LANGUAGE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор языка и запрашивает номер телефона."""
    language_map = {
        "Русский 🇷🇺": "ru",
        "O'zbekcha 🇺🇿": "uz",
        "Тоҷикӣ 🇹🇯": "tj",
    }
    selected_language = update.message.text
    language_code = language_map.get(selected_language)

    if not language_code:
        await update.message.reply_text("Пожалуйста, выберите язык с помощью кнопок.")
        return SELECTING_LANGUAGE

    user = await get_user_async(update.effective_user.id)
    await update_user_language_async(user, language_code)
    
    keyboard = [[KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Спасибо! Теперь, пожалуйста, поделитесь вашим номером телефона.",
        reply_markup=reply_markup
    )
    return REQUESTING_PHONE

async def request_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает номер телефона и предлагает выбрать роль."""
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Пожалуйста, используйте кнопку для отправки номера.")
        return REQUESTING_PHONE

    phone_number = contact.phone_number
    user = await get_user_async(update.effective_user.id)
    await update_user_phone_async(user, phone_number)

    keyboard = [[KeyboardButton("Я Пассажир 🧍"), KeyboardButton("Я Водитель 🚕")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text("Отлично! Кем вы будете в нашем сервисе?", reply_markup=reply_markup)
    return SELECTING_ROLE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимает роль и завершает регистрацию."""
    role_map = {
        "Я Пассажир 🧍": User.Role.PASSENGER,
        "Я Водитель 🚕": User.Role.DRIVER,
    }
    selected_role_text = update.message.text
    role = role_map.get(selected_role_text)

    if not role:
        await update.message.reply_text("Пожалуйста, выберите роль с помощью кнопок.")
        return SELECTING_ROLE
        
    user = await get_user_async(update.effective_user.id)
    await update_user_role_async(user, role)

    await update.message.reply_text(
        "Поздравляем! 🎉 Регистрация успешно завершена! \n\n"
        "Теперь вы можете пользоваться всеми функциями бота.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Здесь можно будет добавить логику для перехода в главное меню
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет и завершает диалог."""
    await update.message.reply_text(
        "Регистрация отменена.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


class Command(BaseCommand):
    """Django-команда для запуска телеграм-бота."""
    help = 'Запускает телеграм-бота'

    def handle(self, *args, **options):
        """Основная логика команды."""
        self.stdout.write("Запуск телеграм-бота...")
        load_dotenv()
        bot_token = os.getenv("BOT_TOKEN")

        if not bot_token:
            self.stderr.write(self.style.ERROR("Токен бота не найден."))
            return

        application = Application.builder().token(bot_token).build()

        # Создаем обработчик диалога
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                SELECTING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_language)],
                REQUESTING_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, request_phone_number)],
                SELECTING_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(conv_handler)
        
        self.stdout.write(self.style.SUCCESS("Бот успешно запущен! Нажмите Ctrl+C для остановки."))
        application.run_polling()

