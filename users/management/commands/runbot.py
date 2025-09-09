import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from asgiref.sync import sync_to_async
from django.db import transaction, models, IntegrityError

from django.utils import timezone
from django.core.management.base import BaseCommand
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    PicklePersistence,
)

from users.models import User
from trips.models import Vehicle, Trip, Booking, Rating
from support.models import SupportTicket

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
FIND_TRIP_BTN = "Найти поездку 🔍"
MY_BOOKINGS_BTN = "Мои бронирования 🗒️"
CREATE_TRIP_BTN = "Создать поездку ➕"
MY_TRIPS_BTN = "Мои поездки 🚕"
MY_PROFILE_BTN = "Мой профиль 👤"
SUPPORT_BTN = "Поддержка 💬"
CHANGE_ROLE_BTN = "Смена роли ✏️"
BACK_TO_MENU_BTN = "⬅️ Назад в главное меню"
CONFIRM_YES_BTN = "Да, сменить"
CONFIRM_NO_BTN = "Нет, отмена"
TRIP_HISTORY_BTN = "История поездок 📜"  # Новая кнопка

# --- Система локализации ---
TRANSLATIONS = {
    'ru': {
        'select_language': "Пожалуйста, выберите ваш язык:",
        'share_phone': "Спасибо! Теперь, пожалуйста, поделитесь вашим номером телефона.",
        'select_role': "Отлично! Кем вы будете в нашем сервисе?",
        'driver_pending': "Спасибо! Ваша заявка на роль водителя принята и отправлена на проверку. Мы сообщим вам, когда она будет одобрена.",
        'registration_complete': "Поздравляем! 🎉 Регистрация успешно завершена!",
        'profile_menu': "👤 Ваш профиль:\n\n<b>Имя:</b> {name}\n<b>Телефон:</b> {phone}\n<b>Роль:</b> {role}\n<b>Рейтинг:</b> {rating}",
        'change_role_confirm': "Вы уверены, что хотите сменить вашу роль с <b>{current}</b> на <b>{new}</b>?",
        'role_changed': "Ваша роль успешно изменена!",
        'role_change_cancelled': "Смена роли отменена.",
        'no_vehicles': "У вас еще нет добавленных автомобилей. Давайте сначала добавим ваш транспорт.\n\nВведите марку автомобиля (например, Kia):",
        'select_vehicle': "Выберите автомобиль для поездки:",
        'vehicle_selected': "Автомобиль выбран. Теперь начнем создание поездки.",
        'enter_departure': "Откуда вы отправляетесь? (например, Краснодар)",
        'enter_destination': "Куда вы поедете? (например, Москва)",
        'enter_time': "Когда? Введите дату и время отправления в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 15.09.2025 18:00)",
        'enter_seats': "Сколько свободных мест для пассажиров? (введите число)",
        'enter_price': "Укажите цену за одно место в рублях (введите число):",
        'trip_created': "✅ Поездка успешно создана!\n\n<b>Маршрут:</b> {departure} → {destination}\n<b>Время:</b> {time}\n<b>Авто:</b> {vehicle}\n<b>Мест:</b> {seats}\n<b>Цена:</b> {price} руб./место",
        'invalid_time_past': "Нельзя создавать поездки в прошлом. Пожалуйста, введите будущую дату и время.",
        'invalid_format_time': "Неверный формат. Пожалуйста, введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ",
        'invalid_seats': "Пожалуйста, введите целое положительное число от 1 до 7.",
        'invalid_price': "Пожалуйста, введите положительное число не менее 50.",
        'vehicle_added': "Автомобиль {brand} {model} ({plate}) успешно добавлен!\n\nТеперь давайте создадим поездку.\nОткуда вы отправляетесь? (например, Краснодар)",
        'find_trip_start': "Начинаем поиск поездки. Откуда вы хотите поехать? (например, Москва)",
        'find_trip_destination': "Куда вы хотите поехать? (например, Санкт-Петербург)",
        'find_trip_date': "На какую дату ищем? Введите в формате ДД.ММ.ГГГГ (например, 25.12.2025)",
        'searching_trips': "Ищу поездки из г. {departure} в г. {destination} на {date}...",
        'no_trips_found': "К сожалению, на эту дату поездок не найдено. Попробуйте поискать на другую дату.",
        'trips_found': "Вот что удалось найти:",
        'trip_info': "<b>Водитель:</b> {driver} ({rating})\n<b>Маршрут:</b> {dep} → {dest}\n<b>Время:</b> {time}\n<b>Авто:</b> {vehicle}\n<b>Свободных мест:</b> {seats}\n<b>Цена:</b> {price} руб.",
        'invalid_date_format': "Неверный формат. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ",
        'book_trip_unavailable': "Извините, эта поездка уже недоступна, завершена или все места заняты.",
        'select_seats_for_booking': "Вы выбрали поездку {dep} - {dest}.\n\nСколько мест вы хотите забронировать? (Свободно: {seats})",
        'invalid_seats_booking': "Пожалуйста, введите целое положительное число.",
        'booking_error': "Ошибка бронирования: {error}",
        'booking_success': "✅ Поздравляем! Вы успешно забронировали {seats} мест(а)!\nОбщая стоимость: {cost} руб.",
        'driver_notification': "🔔 Новое бронирование!\n\nПассажир: {passenger} ({phone})\nЗабронировал(а) мест: {seats}\nПоездка: {trip}",
        'no_trips': "У вас пока нет созданных поездок.",
        'my_trips': "Ваши активные поездки:",
        'no_active_trips': "У вас нет активных поездок для управления.",
        'trip_active_info': "<b>📍 Активна</b>\n<b>Маршрут:</b> {dep} → {dest}\n<b>Время:</b> {time}\n<b>Свободных мест:</b> {seats}\n<b>Цена:</b> {price} руб./место",
        'trip_completed': "Поездка {trip} завершена.",
        'trip_cancelled': "Поездка {trip} отменена.",
        'trip_not_found': "Не удалось найти поездку.",
        'no_bookings': "У вас пока нет активных бронирований.",
        'my_bookings': "Ваши активные бронирования:",
        'booking_info': "<b>Маршрут:</b> {dep} → {dest}\n<b>Время:</b> {time}\n<b>Водитель:</b> {driver}, тел: {phone}\n<b>Авто:</b> {vehicle}\n<b>Забронировано мест:</b> {seats}\n<b>Общая стоимость:</b> {cost} руб.",
        'no_history': "У вас нет поездок в истории.",
        'trip_history': "История ваших поездок:",
        'history_completed': "✅ Завершена",
        'history_cancelled': "❌ Отменена",
        'history_trip_info': "<b>{status}</b>\n<b>Маршрут:</b> {dep} → {dest}\n<b>Время:</b> {time}\n<b>Авто:</b> {vehicle}\n<b>Мест:</b> {seats}\n<b>Цена:</b> {price} руб./место",
        'history_booking_info': "<b>{status}</b>\n<b>Маршрут:</b> {dep} → {dest}\n<b>Время:</b> {time}\n<b>Водитель:</b> {driver}, тел: {phone}\n<b>Авто:</b> {vehicle}\n<b>Забронировано мест:</b> {seats}\n<b>Общая стоимость:</b> {cost} руб.",
        'select_field_to_edit': "Что вы хотите изменить?",
        'enter_new_value': "Пожалуйста, введите {prompt}:",
        'invalid_value': "Неверный формат. Пожалуйста, попробуйте еще раз.",
        'past_date_error': "Нельзя установить дату в прошлом. Попробуйте еще раз.",
        'edit_success': "✅ Данные поездки успешно обновлены!",
        'edit_error': "Ошибка: данные для редактирования не найдены.",
        'support_start': "Опишите вашу проблему или вопрос одним сообщением. Мы сохраним ваше обращение, и администратор свяжется с вами.",
        'support_message_too_long': "Ваше сообщение слишком длинное (максимум 1000 символов). Пожалуйста, сократите его.",
        'support_submitted': "Спасибо! Ваше обращение принято. Администратор скоро его рассмотрит.",
        'rate_driver': "Поездка с водителем {driver} завершена. Пожалуйста, оцените его:",
        'rate_passenger': "Пожалуйста, оцените поездку с пассажиром {passenger}:",
        'rating_thanks': "Спасибо! Вы поставили оценку {score} ⭐ пользователю {user}.",
        'already_rated': "Вы уже оценили этого пользователя за эту поездку.",
        'chat_started': "Вы вошли в чат с {role} {name}.\nВсе, что вы напишете, будет переслано. Чтобы выйти, отправьте /cancel.",
        'chat_error': "Ошибка: бронирование не найдено.",
        'not_participant': "Ошибка: вы не участник этого бронирования.",
        'chat_not_initialized': "Ошибка: чат не инициализирован.",
        'message_too_long': "Сообщение слишком длинное (максимум 1000 символов). Пожалуйста, сократите его.",
        'message_sent': "Сообщение отправлено!",
        'chat_cancelled': "Чат завершен.",
        'action_cancelled': "Действие отменено.",
        'unverified_driver': "Ваш аккаунт водителя еще не прошел проверку. Пожалуйста, дождитесь одобрения от администрации.",
        'critical_error_vehicle': "Критическая ошибка: автомобиль не найден по ID. Пожалуйста, попробуйте создать поездку заново.",
        'conflict_error': "Этот автомобиль уже используется в другой активной поездке в указанное время.",
        'invalid_language': "Пожалуйста, выберите язык с помощью кнопок.",
        'welcome_back': "С возвращением, {name}!",
        'passenger_menu': "Меню пассажира:",
        'driver_menu': "Меню водителя:",
    },
    'uz': {
        # Здесь добавить переводы на узбекский, для примера оставим заглушки
        'select_language': "Iltimos, tilingizni tanlang:",
        # ... и так далее для всех ключей
    },
    'tj': {
        # Здесь добавить переводы на таджикский
        'select_language': "Лутфан, забонро интихоб кунед:",
        # ... и так далее
    }
}

def get_text(user, key, **kwargs):
    lang = user.language if user and user.language in TRANSLATIONS else 'ru'
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['ru'][key])
    return text.format(**kwargs) if kwargs else text

# --- Состояния ---
(
    MAIN_MENU,
    PROFILE_MENU,
    CONFIRMING_ROLE_CHANGE,
    SELECTING_LANGUAGE,
    REQUESTING_PHONE,
    SELECTING_ROLE,
    CREATE_TRIP_ENTERING_DEPARTURE,
    CREATE_TRIP_ENTERING_DESTINATION,
    CREATE_TRIP_ENTERING_TIME,
    CREATE_TRIP_ENTERING_SEATS,
    CREATE_TRIP_ENTERING_PRICE,
    ADD_VEHICLE_ENTERING_BRAND,
    ADD_VEHICLE_ENTERING_MODEL,
    ADD_VEHICLE_ENTERING_PLATE,
    SELECTING_VEHICLE,
    FIND_TRIP_ENTERING_DEPARTURE,
    FIND_TRIP_ENTERING_DESTINATION,
    FIND_TRIP_ENTERING_DATE,
    BOOK_TRIP_ENTERING_SEATS,
    SUPPORT_ENTERING_MESSAGE,
    RATING_TRIP,
    EDIT_TRIP_SELECT_FIELD,
    EDIT_TRIP_ENTERING_VALUE,
    IN_CHAT,
    TRIP_HISTORY,  # Новое состояние
) = range(25)

# --- Функции для работы с БД (users) ---
def get_user(telegram_id):
    try:
        return User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None

def create_user(telegram_id, name):
    return User.objects.create(telegram_id=telegram_id, name=name, username=f'user_{telegram_id}')

def update_user_language(user, language_code):
    user.language = language_code
    user.save()

def update_user_phone(user, phone_number):
    user.phone_number = phone_number
    user.save()

def update_user_role(user, role):
    user.role = role
    if role == User.Role.DRIVER:
        user.verification_status = User.VerificationStatus.PENDING
    user.save()

# --- Функции для работы с БД (trips & ratings) ---
def get_vehicles_for_driver(driver):
    return list(driver.vehicles.all())

def add_vehicle(driver, brand, model, license_plate):
    return Vehicle.objects.create(
        driver=driver, brand=brand, model=model, license_plate=license_plate
    )

def get_vehicle_by_id(vehicle_id):
    try:
        return Vehicle.objects.get(id=vehicle_id)
    except Vehicle.DoesNotExist:
        return None

def create_trip(driver, vehicle, departure, destination, time, seats, price):
    aware_time = timezone.make_aware(time, timezone.get_current_timezone())
    # Проверка на конфликт расписания
    conflicting_trips = Trip.objects.filter(
        vehicle=vehicle,
        status=Trip.Status.ACTIVE,
        departure_time__range=(aware_time - timezone.timedelta(hours=2), aware_time + timezone.timedelta(hours=2))
    )
    if conflicting_trips.exists():
        raise ValueError("conflict_error")
    
    return Trip.objects.create(
        driver=driver, vehicle=vehicle, departure_location=departure, destination_location=destination,
        departure_time=aware_time, available_seats=seats, price=price
    )

def find_trips(departure, destination, search_date):
    return list(Trip.objects.filter(
        departure_location__icontains=departure, destination_location__icontains=destination,
        departure_time__date=search_date, departure_time__gte=timezone.now(), status=Trip.Status.ACTIVE
    ).select_related('driver', 'vehicle'))

def get_trip_by_id(trip_id):
    try:
        return Trip.objects.select_related('driver', 'vehicle').prefetch_related('bookings__passenger').get(id=trip_id)
    except Trip.DoesNotExist:
        return None
        
def get_booking_by_id(booking_id):
    try:
        return Booking.objects.select_related('passenger', 'trip__driver').get(id=booking_id)
    except Booking.DoesNotExist:
        return None

@transaction.atomic
def create_booking(passenger, trip, seats_to_book):
    trip_for_update = Trip.objects.select_for_update().get(id=trip.id)
    if trip_for_update.status != Trip.Status.ACTIVE:
        return None, "booking_unavailable"
    if trip_for_update.available_seats >= seats_to_book:
        trip_for_update.available_seats -= seats_to_book
        trip_for_update.save()
        booking = Booking.objects.create(passenger=passenger, trip=trip_for_update, seats_booked=seats_to_book)
        return booking, None
    else:
        error_message = f"Недостаточно мест. Осталось только {trip_for_update.available_seats}."
        return None, error_message

def get_trips_for_driver(driver):
    return list(driver.trips_as_driver.select_related('vehicle').prefetch_related('bookings__passenger').order_by('-departure_time'))

def get_bookings_for_passenger(passenger, active_only=True):
    query = passenger.bookings_as_passenger.select_related('trip__driver', 'trip__vehicle').order_by('-trip__departure_time')
    if active_only:
        query = query.filter(trip__status=Trip.Status.ACTIVE)
    return list(query)

def update_trip_status(trip_id, new_status):
    try:
        trip = Trip.objects.get(id=trip_id)
        trip.status = new_status
        trip.save()
        return trip
    except Trip.DoesNotExist:
        return None

@transaction.atomic
def add_rating_and_update_user(rater, rated_user, trip, score):
    try:
        Rating.objects.create(rater=rater, rated_user=rated_user, trip=trip, score=score)
    except IntegrityError:
        logger.warning(f"Attempt to add duplicate rating by {rater.id} for {rated_user.id} on trip {trip.id}")
        raise
    user_to_update = User.objects.select_for_update().get(id=rated_user.id)
    all_ratings = user_to_update.received_ratings.all()
    new_rating_count = all_ratings.count()
    new_average = all_ratings.aggregate(models.Avg('score'))['score__avg']
    user_to_update.rating_count = new_rating_count
    user_to_update.average_rating = new_average
    user_to_update.save()

def create_support_ticket(user, message):
    return SupportTicket.objects.create(user=user, message=message)
    
def update_trip_field(trip_id, field, value):
    trip = Trip.objects.get(id=trip_id)
    if field == 'departure_time':
        value = timezone.make_aware(value, timezone.get_current_timezone())
    setattr(trip, field, value)
    trip.save()
    return trip

# --- Асинхронные "обертки" ---
get_user_async = sync_to_async(get_user, thread_sensitive=True)
create_user_async = sync_to_async(create_user, thread_sensitive=True)
update_user_language_async = sync_to_async(update_user_language, thread_sensitive=True)
update_user_phone_async = sync_to_async(update_user_phone, thread_sensitive=True)
update_user_role_async = sync_to_async(update_user_role, thread_sensitive=True)
get_vehicles_for_driver_async = sync_to_async(get_vehicles_for_driver, thread_sensitive=True)
add_vehicle_async = sync_to_async(add_vehicle, thread_sensitive=True)
get_vehicle_by_id_async = sync_to_async(get_vehicle_by_id, thread_sensitive=True)
create_trip_async = sync_to_async(create_trip, thread_sensitive=True)
find_trips_async = sync_to_async(find_trips, thread_sensitive=True)
get_trip_by_id_async = sync_to_async(get_trip_by_id, thread_sensitive=True)
create_booking_async = sync_to_async(create_booking, thread_sensitive=True)
get_trips_for_driver_async = sync_to_async(get_trips_for_driver, thread_sensitive=True)
get_bookings_for_passenger_async = sync_to_async(get_bookings_for_passenger, thread_sensitive=True)
create_support_ticket_async = sync_to_async(create_support_ticket, thread_sensitive=True)
update_trip_status_async = sync_to_async(update_trip_status, thread_sensitive=True)
add_rating_and_update_user_async = sync_to_async(add_rating_and_update_user, thread_sensitive=True)
update_trip_field_async = sync_to_async(update_trip_field, thread_sensitive=True)
get_booking_by_id_async = sync_to_async(get_booking_by_id, thread_sensitive=True)

# --- Основные обработчики ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    if not user or not user.role:
        return await start_registration(update, context)

    menu_text = get_text(user, 'passenger_menu' if user.role == User.Role.PASSENGER else 'driver_menu')
    if user.role == User.Role.PASSENGER:
        keyboard = [[FIND_TRIP_BTN], [MY_BOOKINGS_BTN, TRIP_HISTORY_BTN], [MY_PROFILE_BTN], [SUPPORT_BTN]]
    elif user.role == User.Role.DRIVER:
        keyboard = [[CREATE_TRIP_BTN], [MY_TRIPS_BTN, TRIP_HISTORY_BTN], [MY_PROFILE_BTN], [SUPPORT_BTN]]
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu_text, reply_markup=reply_markup)
    return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_user = update.effective_user
    user = await get_user_async(telegram_user.id)
    if user and user.role:
        welcome_text = get_text(user, 'welcome_back', name=telegram_user.first_name)
        await update.message.reply_text(welcome_text)
        return await show_main_menu(update, context)
    else:
        return await start_registration(update, context)

# --- Регистрация ---
async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    user = await get_user_async(user_id)
    if not user:
        await create_user_async(user_id, user_name)
    user = await get_user_async(user_id)  # Refresh user
    # Автоматическое определение языка, если не выбран
    if not user.language:
        lang_code = update.effective_user.language_code
        if lang_code in ['ru', 'uz', 'tg']:  # tg for Tajik
            await update_user_language_async(user, lang_code)
    
    keyboard = [[KeyboardButton("Русский 🇷🇺"), KeyboardButton("O'zbekcha 🇺🇿"), KeyboardButton("Тоҷикӣ 🇹🇯")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    lang_text = get_text(user, 'select_language')
    await update.message.reply_text(lang_text, reply_markup=reply_markup)
    return SELECTING_LANGUAGE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language_map = {"Русский 🇷🇺": "ru", "O'zbekcha 🇺🇿": "uz", "Тоҷикӣ 🇹🇯": "tj"}
    language_code = language_map.get(update.message.text)
    if not language_code:
        user = await get_user_async(update.effective_user.id)
        lang_text = get_text(user, 'invalid_language')
        await update.message.reply_text(lang_text)
        return SELECTING_LANGUAGE
    user = await get_user_async(update.effective_user.id)
    await update_user_language_async(user, language_code)
    keyboard = [[KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    phone_text = get_text(user, 'share_phone')
    await update.message.reply_text(phone_text, reply_markup=reply_markup)
    return REQUESTING_PHONE

async def request_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    if not contact:
        user = await get_user_async(update.effective_user.id)
        phone_text = get_text(user, 'share_phone')
        await update.message.reply_text(phone_text)
        return REQUESTING_PHONE
    user = await get_user_async(update.effective_user.id)
    await update_user_phone_async(user, contact.phone_number)
    keyboard = [[KeyboardButton("Я Пассажир 🧍"), KeyboardButton("Я Водитель 🚕")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    role_text = get_text(user, 'select_role')
    await update.message.reply_text(role_text, reply_markup=reply_markup)
    return SELECTING_ROLE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role_map = {"Я Пассажир 🧍": User.Role.PASSENGER, "Я Водитель 🚕": User.Role.DRIVER}
    role = role_map.get(update.message.text)
    if not role:
        user = await get_user_async(update.effective_user.id)
        role_text = get_text(user, 'select_role')
        await update.message.reply_text(role_text)
        return SELECTING_ROLE
    user = await get_user_async(update.effective_user.id)
    await update_user_role_async(user, role)
    
    if role == User.Role.DRIVER:
        pending_text = get_text(user, 'driver_pending')
        await update.message.reply_text(pending_text, reply_markup=ReplyKeyboardRemove())
    else:
        complete_text = get_text(user, 'registration_complete')
        await update.message.reply_text(complete_text, reply_markup=ReplyKeyboardRemove())
        
    return await show_main_menu(update, context)

# --- Профиль ---
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    role_text = user.get_role_display()
    rating_text = f"{user.average_rating:.1f} ⭐ ({user.rating_count} оценок)"
    profile_text = get_text(user, 'profile_menu', name=user.name, phone=user.phone_number, role=role_text, rating=rating_text)
    keyboard = [[CHANGE_ROLE_BTN], [BACK_TO_MENU_BTN]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(profile_text, parse_mode='HTML', reply_markup=reply_markup)
    return PROFILE_MENU

async def change_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    current_role_text = user.get_role_display()
    new_role_text = "Водитель" if user.role == User.Role.PASSENGER else "Пассажир"
    confirm_text = get_text(user, 'change_role_confirm', current=current_role_text, new=new_role_text)
    keyboard = [[CONFIRM_YES_BTN, CONFIRM_NO_BTN]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(confirm_text, parse_mode='HTML', reply_markup=reply_markup)
    return CONFIRMING_ROLE_CHANGE

async def confirm_role_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text
    if answer == CONFIRM_NO_BTN:
        user = await get_user_async(update.effective_user.id)
        cancel_text = get_text(user, 'role_change_cancelled')
        await update.message.reply_text(cancel_text)
        return await my_profile(update, context)
    user = await get_user_async(update.effective_user.id)
    new_role = User.Role.DRIVER if user.role == User.Role.PASSENGER else User.Role.PASSENGER
    await update_user_role_async(user, new_role)
    changed_text = get_text(user, 'role_changed')
    await update.message.reply_text(changed_text)
    return await show_main_menu(update, context)

# --- Создание поездки ---
async def create_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    
    if user.verification_status != User.VerificationStatus.VERIFIED:
        unverified_text = get_text(user, 'unverified_driver')
        await update.message.reply_text(unverified_text)
        return MAIN_MENU

    vehicles = await get_vehicles_for_driver_async(user)
    if not vehicles:
        no_vehicles_text = get_text(user, 'no_vehicles')
        await update.message.reply_text(
            no_vehicles_text,
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_VEHICLE_ENTERING_BRAND

    keyboard = [[InlineKeyboardButton(str(v), callback_data=f"select_vehicle_{v.id}")] for v in vehicles]
    reply_markup = InlineKeyboardMarkup(keyboard)
    select_vehicle_text = get_text(user, 'select_vehicle')
    await update.message.reply_text(select_vehicle_text, reply_markup=reply_markup)
    return SELECTING_VEHICLE

async def trip_select_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    vehicle_id = int(query.data.split("_")[-1])
    context.user_data['selected_vehicle_id'] = vehicle_id
    
    user = await get_user_async(update.effective_user.id)
    selected_text = get_text(user, 'vehicle_selected')
    await query.edit_message_text(text=selected_text)
    departure_text = get_text(user, 'enter_departure')
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=departure_text,
        reply_markup=ReplyKeyboardRemove()
    )
    return CREATE_TRIP_ENTERING_DEPARTURE

async def add_vehicle_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vehicle_brand'] = update.message.text
    user = await get_user_async(update.effective_user.id)
    model_prompt = "Отлично! Теперь введите модель (например, Rio):"  # Можно локализовать
    await update.message.reply_text(model_prompt)
    return ADD_VEHICLE_ENTERING_MODEL

async def add_vehicle_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vehicle_model'] = update.message.text
    plate_prompt = "Теперь введите гос. номер автомобиля (например, А123БВ 777):"
    await update.message.reply_text(plate_prompt)
    return ADD_VEHICLE_ENTERING_PLATE

async def add_vehicle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    brand = context.user_data.get('vehicle_brand')
    model = context.user_data.get('vehicle_model')
    plate = update.message.text
    
    new_vehicle = await add_vehicle_async(user, brand, model, plate)
    context.user_data['selected_vehicle_id'] = new_vehicle.id
    
    added_text = get_text(user, 'vehicle_added', brand=brand, model=model, plate=plate)
    departure_text = get_text(user, 'enter_departure')
    await update.message.reply_text(
        f"{added_text}\n\n{departure_text}"
    )
    return CREATE_TRIP_ENTERING_DEPARTURE

async def trip_enter_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['trip_departure'] = update.message.text
    user = await get_user_async(update.effective_user.id)
    destination_text = get_text(user, 'enter_destination')
    await update.message.reply_text(destination_text)
    return CREATE_TRIP_ENTERING_DESTINATION

async def trip_enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['trip_destination'] = update.message.text
    user = await get_user_async(update.effective_user.id)
    time_text = get_text(user, 'enter_time')
    await update.message.reply_text(time_text)
    return CREATE_TRIP_ENTERING_TIME

async def trip_enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    try:
        time_obj = datetime.strptime(update.message.text, '%d.%m.%Y %H:%M')
        if time_obj < datetime.now():
             past_text = get_text(user, 'invalid_time_past')
             await update.message.reply_text(past_text)
             return CREATE_TRIP_ENTERING_TIME
        context.user_data['trip_time'] = update.message.text
    except ValueError:
        format_text = get_text(user, 'invalid_format_time')
        await update.message.reply_text(format_text)
        return CREATE_TRIP_ENTERING_TIME
        
    seats_text = get_text(user, 'enter_seats')
    await update.message.reply_text(seats_text)
    return CREATE_TRIP_ENTERING_SEATS

async def trip_enter_seats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    try:
        seats = int(update.message.text)
        if seats <= 0 or seats > 7:
            raise ValueError
        context.user_data['trip_seats'] = seats
    except ValueError:
        invalid_seats_text = get_text(user, 'invalid_seats')
        await update.message.reply_text(invalid_seats_text)
        return CREATE_TRIP_ENTERING_SEATS
        
    price_text = get_text(user, 'enter_price')
    await update.message.reply_text(price_text)
    return CREATE_TRIP_ENTERING_PRICE

async def trip_enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    try:
        price = float(update.message.text)
        if price < 50:
            raise ValueError
        context.user_data['trip_price'] = price
    except ValueError:
        invalid_price_text = get_text(user, 'invalid_price')
        await update.message.reply_text(invalid_price_text)
        return CREATE_TRIP_ENTERING_PRICE
        
    vehicle_id = context.user_data.get('selected_vehicle_id')
    vehicle = await get_vehicle_by_id_async(vehicle_id)
    
    if not vehicle:
        critical_text = get_text(user, 'critical_error_vehicle')
        await update.message.reply_text(critical_text)
        return await show_main_menu(update, context)

    departure = context.user_data.get('trip_departure')
    destination = context.user_data.get('trip_destination')
    time_str = context.user_data.get('trip_time')
    time_obj = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
    seats = context.user_data.get('trip_seats')
    price = context.user_data.get('trip_price')
    
    try:
        await create_trip_async(user, vehicle, departure, destination, time_obj, seats, price)
        created_text = get_text(user, 'trip_created', departure=departure, destination=destination, time=time_str, vehicle=vehicle, seats=seats, price=price)
        await update.message.reply_text(created_text, parse_mode='HTML')
    except ValueError as e:
        conflict_text = get_text(user, 'conflict_error')
        await update.message.reply_text(conflict_text)
    
    return await show_main_menu(update, context)

# --- Поиск поездки ---
async def find_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    start_text = get_text(user, 'find_trip_start')
    await update.message.reply_text(
        start_text,
        reply_markup=ReplyKeyboardRemove()
    )
    return FIND_TRIP_ENTERING_DEPARTURE

async def find_trip_enter_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['find_departure'] = update.message.text
    user = await get_user_async(update.effective_user.id)
    dest_text = get_text(user, 'find_trip_destination')
    await update.message.reply_text(dest_text)
    return FIND_TRIP_ENTERING_DESTINATION

async def find_trip_enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['find_destination'] = update.message.text
    user = await get_user_async(update.effective_user.id)
    date_text = get_text(user, 'find_trip_date')
    await update.message.reply_text(date_text)
    return FIND_TRIP_ENTERING_DATE

async def find_trip_enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    try:
        search_date_obj = datetime.strptime(update.message.text, '%d.%m.%Y').date()
    except ValueError:
        invalid_date_text = get_text(user, 'invalid_date_format')
        await update.message.reply_text(invalid_date_text)
        return FIND_TRIP_ENTERING_DATE

    departure = context.user_data.get('find_departure')
    destination = context.user_data.get('find_destination')

    searching_text = get_text(user, 'searching_trips', departure=departure, destination=destination, date=update.message.text)
    await update.message.reply_text(searching_text)

    trips = await find_trips_async(departure, destination, search_date_obj)

    if not trips:
        no_trips_text = get_text(user, 'no_trips_found')
        await update.message.reply_text(no_trips_text)
        return await show_main_menu(update, context)

    found_text = get_text(user, 'trips_found')
    await update.message.reply_text(found_text)
    for trip in trips:
        driver = trip.driver
        rating_text = f"{driver.average_rating:.1f} ⭐ ({driver.rating_count} оценок)"
        dep = trip.departure_location
        dest = trip.destination_location
        time_str = trip.departure_time.strftime('%d.%m.%Y в %H:%M')
        info_text = get_text(user, 'trip_info', driver=driver.name, rating=rating_text, dep=dep, dest=dest, time=time_str, vehicle=trip.vehicle, seats=trip.available_seats, price=trip.price)
        keyboard = [[InlineKeyboardButton("✅ Забронировать", callback_data=f"book_trip_{trip.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(info_text, parse_mode='HTML', reply_markup=reply_markup)
    
    return MAIN_MENU

# --- Бронирование поездки ---
async def book_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    trip_id = int(query.data.split("_")[-1])
    trip = await get_trip_by_id_async(trip_id)

    if not trip or trip.status != Trip.Status.ACTIVE or trip.available_seats == 0:
        user = await get_user_async(update.effective_user.id)
        unavailable_text = get_text(user, 'book_trip_unavailable')
        await query.edit_message_text(unavailable_text)
        return MAIN_MENU
    
    context.user_data['booking_trip_id'] = trip_id
    
    user = await get_user_async(update.effective_user.id)
    seats_text = get_text(user, 'select_seats_for_booking', dep=trip.departure_location, dest=trip.destination_location, seats=trip.available_seats)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=seats_text,
    )
    return BOOK_TRIP_ENTERING_SEATS

async def book_trip_enter_seats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    try:
        seats_to_book = int(update.message.text)
        if seats_to_book <= 0: raise ValueError
    except ValueError:
        invalid_booking_text = get_text(user, 'invalid_seats_booking')
        await update.message.reply_text(invalid_booking_text)
        return BOOK_TRIP_ENTERING_SEATS
        
    trip_id = context.user_data.get('booking_trip_id')
    trip = await get_trip_by_id_async(trip_id)
    passenger = user
    
    if not trip or not passenger:
        error_text = "Произошла ошибка, не удалось найти поездку или ваш профиль."
        await update.message.reply_text(error_text)
        return await show_main_menu(update, context)

    booking, error = await create_booking_async(passenger, trip, seats_to_book)

    if error:
        if error == "booking_unavailable":
            unavailable_text = get_text(user, 'book_trip_unavailable')
            await update.message.reply_text(unavailable_text)
        else:
            error_text = get_text(user, 'booking_error', error=error)
            await update.message.reply_text(error_text)
    else:
        # Уведомляем водителя
        driver_message = get_text(None, 'driver_notification', passenger=passenger.name, phone=passenger.phone_number, seats=seats_to_book, trip=trip)  # Use ru for admin
        driver_keyboard = [[InlineKeyboardButton("💬 Связаться с пассажиром", callback_data=f"contact_user_{booking.id}")]]
        await context.bot.send_message(
            chat_id=trip.driver.telegram_id, 
            text=driver_message, 
            reply_markup=InlineKeyboardMarkup(driver_keyboard)
        )

        # Отвечаем пассажиру
        total_cost = seats_to_book * trip.price
        success_text = get_text(user, 'booking_success', seats=seats_to_book, cost=total_cost)
        passenger_keyboard = [[InlineKeyboardButton("💬 Связаться с водителем", callback_data=f"contact_user_{booking.id}")]]
        await update.message.reply_text(
            success_text, 
            reply_markup=InlineKeyboardMarkup(passenger_keyboard)
        )

    context.user_data.pop('booking_trip_id', None)
    return await show_main_menu(update, context)

# --- "Мои поездки" ---
async def my_trips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    driver = await get_user_async(update.effective_user.id)
    trips = await get_trips_for_driver_async(driver)
    
    if not trips:
        no_trips_text = get_text(driver, 'no_trips')
        await update.message.reply_text(no_trips_text)
        return MAIN_MENU
        
    my_trips_text = get_text(driver, 'my_trips')
    await update.message.reply_text(my_trips_text)
    active_trips_found = False
    for trip in trips:
        if trip.status == Trip.Status.ACTIVE:
            active_trips_found = True
            dep = trip.departure_location
            dest = trip.destination_location
            time_str = trip.departure_time.strftime('%d.%m.%Y в %H:%M')
            info_text = get_text(driver, 'trip_active_info', dep=dep, dest=dest, time=time_str, seats=trip.available_seats, price=trip.price)
            
            keyboard = [[
                InlineKeyboardButton("✅ Завершить", callback_data=f"complete_trip_{trip.id}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_trip_{trip.id}"),
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_trip_{trip.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(info_text, parse_mode='HTML', reply_markup=reply_markup)
    
    if not active_trips_found:
        no_active_text = get_text(driver, 'no_active_trips')
        await update.message.reply_text(no_active_text)
        
    return MAIN_MENU

# --- "Мои бронирования" ---
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    passenger = await get_user_async(update.effective_user.id)
    bookings = await get_bookings_for_passenger_async(passenger, active_only=True)

    if not bookings:
        no_bookings_text = get_text(passenger, 'no_bookings')
        await update.message.reply_text(no_bookings_text)
        return MAIN_MENU

    my_bookings_text = get_text(passenger, 'my_bookings')
    await update.message.reply_text(my_bookings_text)
    for booking in bookings:
        trip = booking.trip
        total_cost = booking.seats_booked * trip.price
        dep = trip.departure_location
        dest = trip.destination_location
        time_str = trip.departure_time.strftime('%d.%m.%Y в %H:%M')
        info_text = get_text(passenger, 'booking_info', dep=dep, dest=dest, time=time_str, driver=trip.driver.name, phone=trip.driver.phone_number, vehicle=trip.vehicle, seats=booking.seats_booked, cost=total_cost)
        await update.message.reply_text(info_text, parse_mode='HTML')

    return MAIN_MENU

# --- "История поездок" ---
async def trip_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    
    if user.role == User.Role.DRIVER:
        trips = await get_trips_for_driver_async(user)
        if not trips:
            no_history_text = get_text(user, 'no_history')
            await update.message.reply_text(no_history_text)
            return MAIN_MENU
        
        history_text = get_text(user, 'trip_history')
        await update.message.reply_text(history_text)
        for trip in trips:
            if trip.status in [Trip.Status.COMPLETED, Trip.Status.CANCELED]:
                status_text = get_text(user, 'history_completed' if trip.status == Trip.Status.COMPLETED else 'history_cancelled')
                dep = trip.departure_location
                dest = trip.destination_location
                time_str = trip.departure_time.strftime('%d.%m.%Y в %H:%M')
                info_text = get_text(user, 'history_trip_info', status=status_text, dep=dep, dest=dest, time=time_str, vehicle=trip.vehicle, seats=trip.available_seats, price=trip.price)
                await update.message.reply_text(info_text, parse_mode='HTML')
    
    elif user.role == User.Role.PASSENGER:
        bookings = await get_bookings_for_passenger_async(user, active_only=False)
        if not bookings:
            no_history_text = get_text(user, 'no_history')
            await update.message.reply_text(no_history_text)
            return MAIN_MENU
        
        history_text = get_text(user, 'trip_history')
        await update.message.reply_text(history_text)
        for booking in bookings:
            trip = booking.trip
            if trip.status in [Trip.Status.COMPLETED, Trip.Status.CANCELED]:
                status_text = get_text(user, 'history_completed' if trip.status == Trip.Status.COMPLETED else 'history_cancelled')
                total_cost = booking.seats_booked * trip.price
                dep = trip.departure_location
                dest = trip.destination_location
                time_str = trip.departure_time.strftime('%d.%m.%Y в %H:%M')
                info_text = get_text(user, 'history_booking_info', status=status_text, dep=dep, dest=dest, time=time_str, driver=trip.driver.name, phone=trip.driver.phone_number, vehicle=trip.vehicle, seats=booking.seats_booked, cost=total_cost)
                await update.message.reply_text(info_text, parse_mode='HTML')

    return MAIN_MENU

# --- Управление поездкой ---
async def edit_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])
    context.user_data['editing_trip_id'] = trip_id

    user = await get_user_async(update.effective_user.id)
    select_field_text = get_text(user, 'select_field_to_edit')

    keyboard = [
        [InlineKeyboardButton("Время отправления", callback_data="edit_field_departure_time")],
        [InlineKeyboardButton("Количество мест", callback_data="edit_field_available_seats")],
        [InlineKeyboardButton("Цену", callback_data="edit_field_price")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(select_field_text, reply_markup=reply_markup)
    return EDIT_TRIP_SELECT_FIELD

async def edit_trip_select_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if not callback_data.startswith("edit_field_"):
        await query.edit_message_text("Ошибка: неверный формат callback_data.")
        return await show_main_menu(update, context)
    
    field_to_edit = callback_data[len("edit_field_"):]
    valid_fields = ["departure_time", "available_seats", "price"]
    if field_to_edit not in valid_fields:
        await query.edit_message_text(f"Ошибка: неизвестное поле '{field_to_edit}'.")
        return await show_main_menu(update, context)
    
    context.user_data['editing_field'] = field_to_edit
    
    user = await get_user_async(update.effective_user.id)
    field_map = {
        "departure_time": "новое время отправления в формате ДД.ММ.ГГГГ ЧЧ:ММ",
        "available_seats": "новое количество свободных мест",
        "price": "новую цену за место",
    }
    prompt_text = get_text(user, 'enter_new_value', prompt=field_map[field_to_edit])
    
    await query.edit_message_text(prompt_text)
    return EDIT_TRIP_ENTERING_VALUE

async def edit_trip_enter_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trip_id = context.user_data.get('editing_trip_id')
    field = context.user_data.get('editing_field')
    new_value_str = update.message.text
    user = await get_user_async(update.effective_user.id)
    
    if not trip_id or not field:
        error_text = get_text(user, 'edit_error')
        await update.message.reply_text(error_text)
        context.user_data.pop('editing_trip_id', None)
        context.user_data.pop('editing_field', None)
        return await show_main_menu(update, context)
    
    try:
        if field == 'departure_time':
            new_value = datetime.strptime(new_value_str, '%d.%m.%Y %H:%M')
            if new_value < datetime.now():
                past_error_text = get_text(user, 'past_date_error')
                await update.message.reply_text(past_error_text)
                return EDIT_TRIP_ENTERING_VALUE
        elif field == 'available_seats':
            new_value = int(new_value_str)
            if new_value < 0: raise ValueError
        elif field == 'price':
            new_value = float(new_value_str)
            if new_value < 0: raise ValueError
        else:
            await update.message.reply_text(f"Неизвестное поле для редактирования: '{field}'.")
            context.user_data.pop('editing_trip_id', None)
            context.user_data.pop('editing_field', None)
            return await show_main_menu(update, context)
    except ValueError:
        invalid_value_text = get_text(user, 'invalid_value')
        await update.message.reply_text(invalid_value_text)
        return EDIT_TRIP_ENTERING_VALUE

    await update_trip_field_async(trip_id, field, new_value)
    success_text = get_text(user, 'edit_success')
    await update.message.reply_text(success_text)
    
    context.user_data.pop('editing_trip_id', None)
    context.user_data.pop('editing_field', None)
    
    return await show_main_menu(update, context)

async def complete_trip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])
    
    trip = await get_trip_by_id_async(trip_id)
    if not trip:
        not_found_text = get_text(None, 'trip_not_found')  # ru
        await query.edit_message_text(text=not_found_text)
        return MAIN_MENU

    await update_trip_status_async(trip.id, Trip.Status.COMPLETED)
    completed_text = get_text(None, 'trip_completed', trip=trip)  # ru
    await query.edit_message_text(text=completed_text)
    
    await start_rating_process(context.bot, trip)
        
    return MAIN_MENU

async def cancel_trip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])

    trip = await update_trip_status_async(trip_id, Trip.Status.CANCELED)

    if trip:
        cancelled_text = get_text(None, 'trip_cancelled', trip=trip)  # ru
        await query.edit_message_text(text=cancelled_text)
    else:
        not_found_text = get_text(None, 'trip_not_found')  # ru
        await query.edit_message_text(text=not_found_text)

    return MAIN_MENU

# --- Система поддержки ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    start_text = get_text(user, 'support_start')
    await update.message.reply_text(
        start_text,
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"User {update.effective_user.id} entered support_start")
    return SUPPORT_ENTERING_MESSAGE

async def support_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    message_text = update.message.text
    
    if len(message_text) > 1000:
        too_long_text = get_text(user, 'support_message_too_long')
        await update.message.reply_text(too_long_text)
        return SUPPORT_ENTERING_MESSAGE
        
    logger.info(f"User {user.telegram_id} submitted support ticket: {message_text}")
    await create_support_ticket_async(user, message_text)
    
    submitted_text = get_text(user, 'support_submitted')
    await update.message.reply_text(
        submitted_text
    )
    return await show_main_menu(update, context)

# --- Система рейтинга ---
async def start_rating_process(bot, trip):
    driver = await get_user_async(trip.driver.telegram_id)
    bookings = await sync_to_async(list)(trip.bookings.select_related('passenger').all())
    
    if not bookings: return

    passengers = [booking.passenger for booking in bookings]

    if passengers:
        for passenger in passengers:
            rating_exists = await sync_to_async(Rating.objects.filter(trip=trip, rater=driver, rated_user=passenger).exists)()
            if not rating_exists:
                keyboard = [[InlineKeyboardButton(f"{i} ⭐", callback_data=f"rate_{trip.id}_{driver.id}_{passenger.id}_{i}") for i in range(1, 6)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                rate_text = get_text(driver, 'rate_passenger', passenger=passenger.name)
                await bot.send_message(
                    chat_id=driver.telegram_id,
                    text=rate_text,
                    reply_markup=reply_markup
                )

    for passenger in passengers:
        rating_exists = await sync_to_async(Rating.objects.filter(trip=trip, rater=passenger, rated_user=driver).exists)()
        if not rating_exists:
            keyboard = [[InlineKeyboardButton(f"{i} ⭐", callback_data=f"rate_{trip.id}_{passenger.id}_{driver.id}_{i}") for i in range(1, 6)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            rate_text = get_text(passenger, 'rate_driver', driver=driver.name)
            await bot.send_message(
                chat_id=passenger.telegram_id,
                text=rate_text,
                reply_markup=reply_markup
            )

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    trip_id = int(parts[1])
    rater_id = int(parts[2])
    rated_user_id = int(parts[3])
    score = int(parts[4])

    trip = await sync_to_async(Trip.objects.get)(id=trip_id)
    rater = await sync_to_async(User.objects.get)(id=rater_id)
    rated_user = await sync_to_async(User.objects.get)(id=rated_user_id)

    try:
        await add_rating_and_update_user_async(rater, rated_user, trip, score)
        thanks_text = get_text(rater, 'rating_thanks', score=score, user=rated_user.name)
        await query.edit_message_text(text=thanks_text)
    except IntegrityError:
        already_text = get_text(rater, 'already_rated')
        await query.edit_message_text(text=already_text)

# --- Анонимный чат ---
async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    booking_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id
    
    booking = await get_booking_by_id_async(booking_id)
    if not booking:
        chat_error_text = get_text(None, 'chat_error')  # ru
        await query.edit_message_text(chat_error_text)
        return MAIN_MENU

    if user_id == booking.passenger.telegram_id:
        chat_partner = booking.trip.driver
        partner_role = "водителем"
    elif user_id == booking.trip.driver.telegram_id:
        chat_partner = booking.passenger
        partner_role = "пассажиром"
    else:
        not_participant_text = get_text(None, 'not_participant')  # ru
        await query.edit_message_text(not_participant_text)
        return MAIN_MENU
    
    context.user_data['chat_partner_id'] = chat_partner.telegram_id
    
    started_text = get_text(None, 'chat_started', role=partner_role, name=chat_partner.name)  # ru
    await query.edit_message_text(
        started_text
    )
    return IN_CHAT

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_partner_id = context.user_data.get('chat_partner_id')
    if not chat_partner_id:
        not_initialized_text = get_text(None, 'chat_not_initialized')  # ru
        await update.message.reply_text(not_initialized_text)
        return await show_main_menu(update, context)
    
    message_text = update.message.text
    if len(message_text) > 1000:
        too_long_text = get_text(None, 'message_too_long')  # ru
        await update.message.reply_text(too_long_text)
        return IN_CHAT
    
    user = await get_user_async(update.effective_user.id)
    
    sent_text = get_text(user, 'message_sent')
    await context.bot.send_message(
        chat_id=chat_partner_id,
        text=f"Сообщение от {user.name}:\n{message_text}"
    )
    await update.message.reply_text(sent_text)
    return IN_CHAT

async def cancel_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('chat_partner_id', None)
    cancelled_text = get_text(None, 'chat_cancelled')  # ru
    await update.message.reply_text(cancelled_text)
    return await show_main_menu(update, context)

# --- Вспомогательные обработчики ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('chat_partner_id', None)
    cancelled_text = get_text(None, 'action_cancelled')  # ru
    await update.message.reply_text(cancelled_text)
    return await show_main_menu(update, context)

# --- ГЛАВНЫЙ КЛАСС ЗАПУСКА ---
class Command(BaseCommand):
    help = 'Запускает телеграм-бота'

    def handle(self, *args, **options):
        self.stdout.write("Запуск телеграм-бота...")
        load_dotenv()
        bot_token = os.getenv("BOT_TOKEN")

        if not bot_token:
            self.stderr.write(self.style.ERROR("Токен бота не найден."))
            return
        
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder().token(bot_token).persistence(persistence).build()

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                SELECTING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_language)],
                REQUESTING_PHONE: [MessageHandler(filters.CONTACT, request_phone_number)],
                SELECTING_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
                
                MAIN_MENU: [
                    MessageHandler(filters.Regex(f"^{MY_PROFILE_BTN}$"), my_profile),
                    MessageHandler(filters.Regex(f"^{CREATE_TRIP_BTN}$"), create_trip_start),
                    MessageHandler(filters.Regex(f"^{FIND_TRIP_BTN}$"), find_trip_start),
                    MessageHandler(filters.Regex(f"^{MY_BOOKINGS_BTN}$"), my_bookings),
                    MessageHandler(filters.Regex(f"^{MY_TRIPS_BTN}$"), my_trips),
                    MessageHandler(filters.Regex(f"^{SUPPORT_BTN}$"), support_start),
                    MessageHandler(filters.Regex(f"^{TRIP_HISTORY_BTN}$"), trip_history),
                    CallbackQueryHandler(book_trip_start, pattern="^book_trip_"),
                    CallbackQueryHandler(complete_trip, pattern="^complete_trip_"),
                    CallbackQueryHandler(cancel_trip, pattern="^cancel_trip_"),
                    CallbackQueryHandler(edit_trip_start, pattern="^edit_trip_"),
                    CallbackQueryHandler(start_chat, pattern="^contact_user_"),
                ],

                PROFILE_MENU: [
                    MessageHandler(filters.Regex(f"^{CHANGE_ROLE_BTN}$"), change_role),
                    MessageHandler(filters.Regex(f"^{BACK_TO_MENU_BTN}$"), show_main_menu),
                ],

                CONFIRMING_ROLE_CHANGE: [MessageHandler(filters.Regex(f"^({CONFIRM_YES_BTN}|{CONFIRM_NO_BTN})$"), confirm_role_change)],
                
                SELECTING_VEHICLE: [CallbackQueryHandler(trip_select_vehicle, pattern="^select_vehicle_")],

                ADD_VEHICLE_ENTERING_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vehicle_brand)],
                ADD_VEHICLE_ENTERING_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vehicle_model)],
                ADD_VEHICLE_ENTERING_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vehicle_plate)],

                CREATE_TRIP_ENTERING_DEPARTURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_enter_departure)],
                CREATE_TRIP_ENTERING_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_enter_destination)],
                CREATE_TRIP_ENTERING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_enter_time)],
                CREATE_TRIP_ENTERING_SEATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_enter_seats)],
                CREATE_TRIP_ENTERING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trip_enter_price)],

                FIND_TRIP_ENTERING_DEPARTURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_trip_enter_departure)],
                FIND_TRIP_ENTERING_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_trip_enter_destination)],
                FIND_TRIP_ENTERING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_trip_enter_date)],
                
                BOOK_TRIP_ENTERING_SEATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_trip_enter_seats)],

                SUPPORT_ENTERING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_enter_message)],

                EDIT_TRIP_SELECT_FIELD: [CallbackQueryHandler(edit_trip_select_field, pattern="^edit_field_")],
                EDIT_TRIP_ENTERING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_trip_enter_value)],

                IN_CHAT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, forward_message),
                    CommandHandler("cancel", cancel_chat),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            persistent=True,
            name="main_conversation"
        )
        
        application.add_handler(conv_handler)
        
        # Отдельный обработчик для рейтинга
        application.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))
        
        self.stdout.write(self.style.SUCCESS("Бот успешно запущен! Нажмите Ctrl+C для остановки."))
        application.run_polling()
