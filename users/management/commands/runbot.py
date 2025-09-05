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

# --- Константы для кнопок меню (чтобы избежать опечаток) ---
# Пассажир
FIND_TRIP_BTN = "Найти поездку 🔍"
MY_BOOKINGS_BTN = "Мои бронирования 🗒️"
# Водитель
CREATE_TRIP_BTN = "Создать поездку ➕"
MY_TRIPS_BTN = "Мои поездки 🚕"
# Общие
MY_PROFILE_BTN = "Мой профиль 👤"


# --- НОВАЯ СТРУКТУРА СОСТОЯНИЙ ---
# Теперь у нас есть состояние для главного меню и для регистрации
MAIN_MENU, SELECTING_LANGUAGE, REQUESTING_PHONE, SELECTING_ROLE = range(4)

# --- Функции для работы с БД (без изменений) ---
def get_user(telegram_id):
    try:
        return User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None

def create_user(telegram_id, name):
    return User.objects.create(telegram_id=telegram_id, name=name)

def update_user_language(user, language_code):
    user.language = language_code
    user.save()

def update_user_phone(user, phone_number):
    user.phone_number = phone_number
    user.save()

def update_user_role(user, role):
    user.role = role
    user.save()

# --- Асинхронные "обертки" для работы с БД (без изменений) ---
get_user_async = sync_to_async(get_user, thread_sensitive=True)
create_user_async = sync_to_async(create_user, thread_sensitive=True)
update_user_language_async = sync_to_async(update_user_language, thread_sensitive=True)
update_user_phone_async = sync_to_async(update_user_phone, thread_sensitive=True)
update_user_role_async = sync_to_async(update_user_role, thread_sensitive=True)


# --- Функции-обработчики ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Определяет роль пользователя, показывает меню и переходит в состояние MAIN_MENU."""
    user = await get_user_async(update.effective_user.id)
    
    if not user:
        await update.message.reply_text("Похоже, вы не зарегистрированы. Давайте это исправим!")
        return await start_registration(update, context)

    if user.role == User.Role.PASSENGER:
        keyboard = [
            [KeyboardButton(FIND_TRIP_BTN)],
            [KeyboardButton(MY_BOOKINGS_BTN), KeyboardButton(MY_PROFILE_BTN)],
        ]
        menu_text = "Меню пассажира:"
    elif user.role == User.Role.DRIVER:
        keyboard = [
            [KeyboardButton(CREATE_TRIP_BTN)],
            [KeyboardButton(MY_TRIPS_BTN), KeyboardButton(MY_PROFILE_BTN)],
        ]
        menu_text = "Меню водителя:"
    else:
        await update.message.reply_text("Ваша роль не определена. Начнем регистрацию.")
        return await start_registration(update, context)

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu_text, reply_markup=reply_markup)
    return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Главная точка входа. Проверяет регистрацию и перенаправляет."""
    telegram_user = update.effective_user
    user = await get_user_async(telegram_user.id)

    if user and user.role:
        return await show_main_menu(update, context)
    else:
        return await start_registration(update, context)

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает именно процесс регистрации."""
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    user = await get_user_async(user_id)
    if not user:
        await create_user_async(user_id, user_name)
    
    keyboard = [[KeyboardButton("Русский 🇷🇺"), KeyboardButton("O'zbekcha 🇺🇿"), KeyboardButton("Тоҷикӣ 🇹🇯")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Пожалуйста, выберите ваш язык:", reply_markup=reply_markup)
    return SELECTING_LANGUAGE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Код без изменений)
    language_map = {
        "Русский 🇷🇺": "ru", "O'zbekcha 🇺🇿": "uz", "Тоҷикӣ 🇹🇯": "tj",
    }
    language_code = language_map.get(update.message.text)
    if not language_code:
        await update.message.reply_text("Пожалуйста, выберите язык с помощью кнопок.")
        return SELECTING_LANGUAGE

    user = await get_user_async(update.effective_user.id)
    await update_user_language_async(user, language_code)
    
    keyboard = [[KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Спасибо! Теперь, пожалуйста, поделитесь вашим номером телефона.", reply_markup=reply_markup)
    return REQUESTING_PHONE

async def request_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Код без изменений, кроме одной проверки)
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Пожалуйста, используйте кнопку для отправки номера.")
        return REQUESTING_PHONE

    user = await get_user_async(update.effective_user.id)
    await update_user_phone_async(user, contact.phone_number)

    keyboard = [[KeyboardButton("Я Пассажир 🧍"), KeyboardButton("Я Водитель 🚕")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Отлично! Кем вы будете в нашем сервисе?", reply_markup=reply_markup)
    return SELECTING_ROLE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Код без изменений, кроме возвращаемого значения)
    role_map = {
        "Я Пассажир 🧍": User.Role.PASSENGER, "Я Водитель 🚕": User.Role.DRIVER,
    }
    role = role_map.get(update.message.text)
    if not role:
        await update.message.reply_text("Пожалуйста, выберите роль с помощью кнопок.")
        return SELECTING_ROLE
        
    user = await get_user_async(update.effective_user.id)
    await update_user_role_async(user, role)

    await update.message.reply_text(
        "Поздравляем! 🎉 Регистрация успешно завершена!", reply_markup=ReplyKeyboardRemove()
    )
    return await show_main_menu(update, context)

async def placeholder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Временный обработчик для кнопок, остается в том же состоянии."""
    await update.message.reply_text(f"Вы нажали '{update.message.text}'. Эта функция находится в разработке.")
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог и показывает главное меню, если пользователь зарегистрирован."""
    user = await get_user_async(update.effective_user.id)
    if user and user.role:
        await update.message.reply_text("Действие отменено.")
        return await show_main_menu(update, context)
    else:
        await update.message.reply_text("Регистрация отменена.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


class Command(BaseCommand):
    help = 'Запускает телеграм-бота'

    def handle(self, *args, **options):
        self.stdout.write("Запуск телеграм-бота...")
        load_dotenv()
        bot_token = os.getenv("BOT_TOKEN")

        if not bot_token:
            self.stderr.write(self.style.ERROR("Токен бота не найден."))
            return

        application = Application.builder().token(bot_token).build()

        # --- НОВЫЙ ЕДИНЫЙ ОБРАБОТЧИК ДИАЛОГА ---
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                # Состояния регистрации
                SELECTING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_language)],
                REQUESTING_PHONE: [MessageHandler(filters.CONTACT, request_phone_number)],
                SELECTING_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
                
                # Новое состояние для главного меню
                MAIN_MENU: [
                    MessageHandler(filters.Regex(f"^{FIND_TRIP_BTN}$"), placeholder_handler),
                    MessageHandler(filters.Regex(f"^{MY_BOOKINGS_BTN}$"), placeholder_handler),
                    MessageHandler(filters.Regex(f"^{CREATE_TRIP_BTN}$"), placeholder_handler),
                    MessageHandler(filters.Regex(f"^{MY_TRIPS_BTN}$"), placeholder_handler),
                    MessageHandler(filters.Regex(f"^{MY_PROFILE_BTN}$"), placeholder_handler),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(conv_handler)
        
        self.stdout.write(self.style.SUCCESS("Бот успешно запущен! Нажмите Ctrl+C для остановки."))
        application.run_polling()


