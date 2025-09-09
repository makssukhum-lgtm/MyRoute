import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from asgiref.sync import sync_to_async

from django.db import transaction, models
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
    Rating.objects.create(rater=rater, rated_user=rated_user, trip=trip, score=score)
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

    if user.role == User.Role.PASSENGER:
        keyboard = [[FIND_TRIP_BTN], [MY_BOOKINGS_BTN, TRIP_HISTORY_BTN], [MY_PROFILE_BTN], [SUPPORT_BTN]]
        menu_text = "Меню пассажира:"
    elif user.role == User.Role.DRIVER:
        keyboard = [[CREATE_TRIP_BTN], [MY_TRIPS_BTN, TRIP_HISTORY_BTN], [MY_PROFILE_BTN], [SUPPORT_BTN]]
        menu_text = "Меню водителя:"
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu_text, reply_markup=reply_markup)
    return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telegram_user = update.effective_user
    user = await get_user_async(telegram_user.id)
    if user and user.role:
        await update.message.reply_text(f"С возвращением, {telegram_user.first_name}!")
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
    keyboard = [[KeyboardButton("Русский 🇷🇺"), KeyboardButton("O'zbekcha 🇺🇿"), KeyboardButton("Тоҷикӣ 🇹🇯")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Пожалуйста, выберите ваш язык:", reply_markup=reply_markup)
    return SELECTING_LANGUAGE

async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language_map = {"Русский 🇷🇺": "ru", "O'zbekcha 🇺🇿": "uz", "Тоҷикӣ 🇹🇯": "tj"}
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
    role_map = {"Я Пассажир 🧍": User.Role.PASSENGER, "Я Водитель 🚕": User.Role.DRIVER}
    role = role_map.get(update.message.text)
    if not role:
        await update.message.reply_text("Пожалуйста, выберите роль с помощью кнопок.")
        return SELECTING_ROLE
    user = await get_user_async(update.effective_user.id)
    await update_user_role_async(user, role)
    
    if role == User.Role.DRIVER:
        await update.message.reply_text("Спасибо! Ваша заявка на роль водителя принята и отправлена на проверку. Мы сообщим вам, когда она будет одобрена.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Поздравляем! 🎉 Регистрация успешно завершена!", reply_markup=ReplyKeyboardRemove())
        
    return await show_main_menu(update, context)

# --- Профиль ---
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    role_text = user.get_role_display()
    rating_text = f"{user.average_rating:.1f} ⭐ ({user.rating_count} оценок)"
    profile_text = (f"👤 Ваш профиль:\n\n<b>Имя:</b> {user.name}\n<b>Телефон:</b> {user.phone_number}\n<b>Роль:</b> {role_text}\n<b>Рейтинг:</b> {rating_text}")
    keyboard = [[CHANGE_ROLE_BTN], [BACK_TO_MENU_BTN]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(profile_text, parse_mode='HTML', reply_markup=reply_markup)
    return PROFILE_MENU

async def change_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    current_role_text = user.get_role_display()
    new_role_text = "Водитель" if user.role == User.Role.PASSENGER else "Пассажир"
    confirmation_text = (f"Вы уверены, что хотите сменить вашу роль с <b>{current_role_text}</b> на <b>{new_role_text}</b>?")
    keyboard = [[CONFIRM_YES_BTN, CONFIRM_NO_BTN]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(confirmation_text, parse_mode='HTML', reply_markup=reply_markup)
    return CONFIRMING_ROLE_CHANGE

async def confirm_role_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text
    if answer == CONFIRM_NO_BTN:
        await update.message.reply_text("Смена роли отменена.")
        return await my_profile(update, context)
    user = await get_user_async(update.effective_user.id)
    new_role = User.Role.DRIVER if user.role == User.Role.PASSENGER else User.Role.PASSENGER
    await update_user_role_async(user, new_role)
    await update.message.reply_text("Ваша роль успешно изменена!")
    return await show_main_menu(update, context)

# --- Создание поездки ---
async def create_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    
    if user.verification_status != User.VerificationStatus.VERIFIED:
        await update.message.reply_text("Ваш аккаунт водителя еще не прошел проверку. Пожалуйста, дождитесь одобрения от администрации.")
        return MAIN_MENU

    vehicles = await get_vehicles_for_driver_async(user)
    if not vehicles:
        await update.message.reply_text(
            "У вас еще нет добавленных автомобилей. Давайте сначала добавим ваш транспорт.\n\n"
            "Введите марку автомобиля (например, Kia):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_VEHICLE_ENTERING_BRAND

    keyboard = [[InlineKeyboardButton(str(v), callback_data=f"select_vehicle_{v.id}")] for v in vehicles]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите автомобиль для поездки:", reply_markup=reply_markup)
    return SELECTING_VEHICLE

async def trip_select_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    vehicle_id = int(query.data.split("_")[-1])
    context.user_data['selected_vehicle_id'] = vehicle_id
    
    await query.edit_message_text(text=f"Автомобиль выбран. Теперь начнем создание поездки.")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Откуда вы отправляетесь? (например, Краснодар)",
        reply_markup=ReplyKeyboardRemove()
    )
    return CREATE_TRIP_ENTERING_DEPARTURE

async def add_vehicle_brand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vehicle_brand'] = update.message.text
    await update.message.reply_text("Отлично! Теперь введите модель (например, Rio):")
    return ADD_VEHICLE_ENTERING_MODEL

async def add_vehicle_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['vehicle_model'] = update.message.text
    await update.message.reply_text("Теперь введите гос. номер автомобиля (например, А123БВ 777):")
    return ADD_VEHICLE_ENTERING_PLATE

async def add_vehicle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    brand = context.user_data.get('vehicle_brand')
    model = context.user_data.get('vehicle_model')
    plate = update.message.text
    
    new_vehicle = await add_vehicle_async(user, brand, model, plate)
    context.user_data['selected_vehicle_id'] = new_vehicle.id
    
    await update.message.reply_text(
        f"Автомобиль {brand} {model} ({plate}) успешно добавлен!\n\n"
        "Теперь давайте создадим поездку.\n"
        "Откуда вы отправляетесь? (например, Краснодар)"
    )
    return CREATE_TRIP_ENTERING_DEPARTURE

async def trip_enter_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['trip_departure'] = update.message.text
    await update.message.reply_text("Куда вы поедете? (например, Москва)")
    return CREATE_TRIP_ENTERING_DESTINATION

async def trip_enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['trip_destination'] = update.message.text
    await update.message.reply_text("Когда? Введите дату и время отправления в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 15.09.2025 18:00)")
    return CREATE_TRIP_ENTERING_TIME

async def trip_enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        time_obj = datetime.strptime(update.message.text, '%d.%m.%Y %H:%M')
        if time_obj < datetime.now():
             await update.message.reply_text("Нельзя создавать поездки в прошлом. Пожалуйста, введите будущую дату и время.")
             return CREATE_TRIP_ENTERING_TIME
        context.user_data['trip_time'] = update.message.text
    except ValueError:
        await update.message.reply_text("Неверный формат. Пожалуйста, введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ")
        return CREATE_TRIP_ENTERING_TIME
        
    await update.message.reply_text("Сколько свободных мест для пассажиров? (введите число)")
    return CREATE_TRIP_ENTERING_SEATS

async def trip_enter_seats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        seats = int(update.message.text)
        if seats <= 0: raise ValueError
        context.user_data['trip_seats'] = seats
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите целое положительное число.")
        return CREATE_TRIP_ENTERING_SEATS
        
    await update.message.reply_text("Укажите цену за одно место в рублях (введите число):")
    return CREATE_TRIP_ENTERING_PRICE

async def trip_enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text)
        if price < 0: raise ValueError
        context.user_data['trip_price'] = price
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите положительное число.")
        return CREATE_TRIP_ENTERING_PRICE
        
    user = await get_user_async(update.effective_user.id)
    vehicle_id = context.user_data.get('selected_vehicle_id')
    vehicle = await get_vehicle_by_id_async(vehicle_id)
    
    if not vehicle:
        await update.message.reply_text("Критическая ошибка: автомобиль не найден по ID. Пожалуйста, попробуйте создать поездку заново.")
        return await show_main_menu(update, context)

    departure = context.user_data.get('trip_departure')
    destination = context.user_data.get('trip_destination')
    time_str = context.user_data.get('trip_time')
    time_obj = datetime.strptime(time_str, '%d.%m.%Y %H:%M')
    seats = context.user_data.get('trip_seats')
    price = context.user_data.get('trip_price')
    
    await create_trip_async(user, vehicle, departure, destination, time_obj, seats, price)
    
    summary_text = (
        f"✅ Поездка успешно создана!\n\n"
        f"<b>Маршрут:</b> {departure} → {destination}\n"
        f"<b>Время:</b> {time_str}\n"
        f"<b>Авто:</b> {vehicle}\n"
        f"<b>Мест:</b> {seats}\n"
        f"<b>Цена:</b> {price} руб./место"
    )
    
    await update.message.reply_text(summary_text, parse_mode='HTML')
    return await show_main_menu(update, context)

# --- Поиск поездки ---
async def find_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Начинаем поиск поездки. Откуда вы хотите поехать? (например, Москва)",
        reply_markup=ReplyKeyboardRemove()
    )
    return FIND_TRIP_ENTERING_DEPARTURE

async def find_trip_enter_departure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['find_departure'] = update.message.text
    await update.message.reply_text("Куда вы хотите поехать? (например, Санкт-Петербург)")
    return FIND_TRIP_ENTERING_DESTINATION

async def find_trip_enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['find_destination'] = update.message.text
    await update.message.reply_text("На какую дату ищем? Введите в формате ДД.ММ.ГГГГ (например, 25.12.2025)")
    return FIND_TRIP_ENTERING_DATE

async def find_trip_enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        search_date_obj = datetime.strptime(update.message.text, '%d.%m.%Y').date()
    except ValueError:
        await update.message.reply_text("Неверный формат. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ")
        return FIND_TRIP_ENTERING_DATE

    departure = context.user_data.get('find_departure')
    destination = context.user_data.get('find_destination')

    await update.message.reply_text(f"Ищу поездки из г. {departure} в г. {destination} на {update.message.text}...")

    trips = await find_trips_async(departure, destination, search_date_obj)

    if not trips:
        await update.message.reply_text("К сожалению, на эту дату поездок не найдено. Попробуйте поискать на другую дату.")
        return await show_main_menu(update, context)

    await update.message.reply_text("Вот что удалось найти:")
    for trip in trips:
        driver = trip.driver
        rating_text = f"{driver.average_rating:.1f} ⭐ ({driver.rating_count} оценок)"
        trip_info = (
            f"<b>Водитель:</b> {driver.name} ({rating_text})\n"
            f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
            f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
            f"<b>Авто:</b> {trip.vehicle}\n"
            f"<b>Свободных мест:</b> {trip.available_seats}\n"
            f"<b>Цена:</b> {trip.price} руб."
        )
        keyboard = [[InlineKeyboardButton("✅ Забронировать", callback_data=f"book_trip_{trip.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(trip_info, parse_mode='HTML', reply_markup=reply_markup)
    
    return MAIN_MENU

# --- Бронирование поездки ---
async def book_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    trip_id = int(query.data.split("_")[-1])
    trip = await get_trip_by_id_async(trip_id)

    if not trip or trip.available_seats == 0:
        await query.edit_message_text("Извините, эта поездка уже недоступна или все места заняты.")
        return MAIN_MENU
    
    context.user_data['booking_trip_id'] = trip_id
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Вы выбрали поездку {trip.departure_location} - {trip.destination_location}.\n\n"
             f"Сколько мест вы хотите забронировать? (Свободно: {trip.available_seats})",
    )
    return BOOK_TRIP_ENTERING_SEATS

async def book_trip_enter_seats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        seats_to_book = int(update.message.text)
        if seats_to_book <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите целое положительное число.")
        return BOOK_TRIP_ENTERING_SEATS
        
    trip_id = context.user_data.get('booking_trip_id')
    trip = await get_trip_by_id_async(trip_id)
    passenger = await get_user_async(update.effective_user.id)
    
    if not trip or not passenger:
        await update.message.reply_text("Произошла ошибка, не удалось найти поездку или ваш профиль.")
        return await show_main_menu(update, context)

    booking, error = await create_booking_async(passenger, trip, seats_to_book)

    if error:
        await update.message.reply_text(f"Ошибка бронирования: {error}")
    else:
        # Уведомляем водителя
        driver_message = (
            f"🔔 Новое бронирование!\n\n"
            f"Пассажир: {passenger.name} ({passenger.phone_number})\n"
            f"Забронировал(а) мест: {seats_to_book}\n"
            f"Поездка: {trip}"
        )
        driver_keyboard = [[InlineKeyboardButton("💬 Связаться с пассажиром", callback_data=f"contact_user_{booking.id}")]]
        await context.bot.send_message(
            chat_id=trip.driver.telegram_id, 
            text=driver_message, 
            reply_markup=InlineKeyboardMarkup(driver_keyboard)
        )

        # Отвечаем пассажиру
        total_cost = seats_to_book * trip.price
        passenger_message = (
            f"✅ Поздравляем! Вы успешно забронировали {seats_to_book} мест(а)!\n"
            f"Общая стоимость: {total_cost} руб."
        )
        passenger_keyboard = [[InlineKeyboardButton("💬 Связаться с водителем", callback_data=f"contact_user_{booking.id}")]]
        await update.message.reply_text(
            passenger_message, 
            reply_markup=InlineKeyboardMarkup(passenger_keyboard)
        )

    context.user_data.pop('booking_trip_id', None)
    return await show_main_menu(update, context)

# --- "Мои поездки" ---
async def my_trips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    driver = await get_user_async(update.effective_user.id)
    trips = await get_trips_for_driver_async(driver)
    
    if not trips:
        await update.message.reply_text("У вас пока нет созданных поездок.")
        return MAIN_MENU
        
    await update.message.reply_text("Ваши активные поездки:")
    active_trips_found = False
    for trip in trips:
        if trip.status == Trip.Status.ACTIVE:
            active_trips_found = True
            trip_info = (
                f"<b>📍 Активна</b>\n"
                f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
                f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
                f"<b>Свободных мест:</b> {trip.available_seats}\n"
                f"<b>Цена:</b> {trip.price} руб./место"
            )
            
            keyboard = [[
                InlineKeyboardButton("✅ Завершить", callback_data=f"complete_trip_{trip.id}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_trip_{trip.id}"),
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_trip_{trip.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(trip_info, parse_mode='HTML', reply_markup=reply_markup)
    
    if not active_trips_found:
        await update.message.reply_text("У вас нет активных поездок для управления.")
        
    return MAIN_MENU

# --- "Мои бронирования" ---
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    passenger = await get_user_async(update.effective_user.id)
    bookings = await get_bookings_for_passenger_async(passenger, active_only=True)

    if not bookings:
        await update.message.reply_text("У вас пока нет активных бронирований.")
        return MAIN_MENU

    await update.message.reply_text("Ваши активные бронирования:")
    for booking in bookings:
        trip = booking.trip
        total_cost = booking.seats_booked * trip.price
        booking_info = (
            f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
            f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
            f"<b>Водитель:</b> {trip.driver.name}, тел: {trip.driver.phone_number}\n"
            f"<b>Авто:</b> {trip.vehicle}\n"
            f"<b>Забронировано мест:</b> {booking.seats_booked}\n"
            f"<b>Общая стоимость:</b> {total_cost} руб."
        )
        await update.message.reply_text(booking_info, parse_mode='HTML')

    return MAIN_MENU

# --- "История поездок" ---
async def trip_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    
    if user.role == User.Role.DRIVER:
        trips = await get_trips_for_driver_async(user)
        if not trips:
            await update.message.reply_text("У вас нет поездок в истории.")
            return MAIN_MENU
        
        await update.message.reply_text("История ваших поездок:")
        for trip in trips:
            if trip.status in [Trip.Status.COMPLETED, Trip.Status.CANCELED]:
                status_text = "✅ Завершена" if trip.status == Trip.Status.COMPLETED else "❌ Отменена"
                trip_info = (
                    f"<b>{status_text}</b>\n"
                    f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
                    f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
                    f"<b>Авто:</b> {trip.vehicle}\n"
                    f"<b>Мест:</b> {trip.available_seats}\n"
                    f"<b>Цена:</b> {trip.price} руб./место"
                )
                await update.message.reply_text(trip_info, parse_mode='HTML')
    
    elif user.role == User.Role.PASSENGER:
        bookings = await get_bookings_for_passenger_async(user, active_only=False)
        if not bookings:
            await update.message.reply_text("У вас нет поездок в истории.")
            return MAIN_MENU
        
        await update.message.reply_text("История ваших поездок:")
        for booking in bookings:
            trip = booking.trip
            if trip.status in [Trip.Status.COMPLETED, Trip.Status.CANCELED]:
                status_text = "✅ Завершена" if trip.status == Trip.Status.COMPLETED else "❌ Отменена"
                total_cost = booking.seats_booked * trip.price
                booking_info = (
                    f"<b>{status_text}</b>\n"
                    f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
                    f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
                    f"<b>Водитель:</b> {trip.driver.name}, тел: {trip.driver.phone_number}\n"
                    f"<b>Авто:</b> {trip.vehicle}\n"
                    f"<b>Забронировано мест:</b> {booking.seats_booked}\n"
                    f"<b>Общая стоимость:</b> {total_cost} руб."
                )
                await update.message.reply_text(booking_info, parse_mode='HTML')

    return MAIN_MENU

# --- Управление поездкой ---
async def edit_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])
    context.user_data['editing_trip_id'] = trip_id

    keyboard = [
        [InlineKeyboardButton("Время отправления", callback_data="edit_field_departure_time")],
        [InlineKeyboardButton("Количество мест", callback_data="edit_field_available_seats")],
        [InlineKeyboardButton("Цену", callback_data="edit_field_price")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Что вы хотите изменить?", reply_markup=reply_markup)
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
    
    field_map = {
        "departure_time": "новое время отправления в формате ДД.ММ.ГГГГ ЧЧ:ММ",
        "available_seats": "новое количество свободных мест",
        "price": "новую цену за место",
    }
    prompt_text = f"Пожалуйста, введите {field_map[field_to_edit]}:"
    
    await query.edit_message_text(prompt_text)
    return EDIT_TRIP_ENTERING_VALUE

async def edit_trip_enter_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trip_id = context.user_data.get('editing_trip_id')
    field = context.user_data.get('editing_field')
    new_value_str = update.message.text
    
    if not trip_id or not field:
        await update.message.reply_text("Ошибка: данные для редактирования не найдены.")
        context.user_data.pop('editing_trip_id', None)
        context.user_data.pop('editing_field', None)
        return await show_main_menu(update, context)
    
    try:
        if field == 'departure_time':
            new_value = datetime.strptime(new_value_str, '%d.%m.%Y %H:%M')
            if new_value < datetime.now():
                await update.message.reply_text("Нельзя установить дату в прошлом. Попробуйте еще раз.")
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
        await update.message.reply_text("Неверный формат. Пожалуйста, попробуйте еще раз.")
        return EDIT_TRIP_ENTERING_VALUE

    await update_trip_field_async(trip_id, field, new_value)
    await update.message.reply_text("✅ Данные поездки успешно обновлены!")
    
    context.user_data.pop('editing_trip_id', None)
    context.user_data.pop('editing_field', None)
    
    return await show_main_menu(update, context)

async def complete_trip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])
    
    trip = await get_trip_by_id_async(trip_id)
    if not trip:
        await query.edit_message_text(text="Не удалось найти поездку.")
        return MAIN_MENU

    await update_trip_status_async(trip.id, Trip.Status.COMPLETED)
    await query.edit_message_text(text=f"Поездка {trip} завершена.")
    
    await start_rating_process(context.bot, trip)
        
    return MAIN_MENU

async def cancel_trip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data.split("_")[-1])

    trip = await update_trip_status_async(trip_id, Trip.Status.CANCELED)

    if trip:
        await query.edit_message_text(text=f"Поездка {trip} отменена.")
    else:
        await query.edit_message_text(text="Не удалось найти поездку.")

    return MAIN_MENU

# --- Система поддержки ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Опишите вашу проблему или вопрос одним сообщением. "
        "Мы сохраним ваше обращение, и администратор свяжется с вами.",
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"User {update.effective_user.id} entered support_start")
    return SUPPORT_ENTERING_MESSAGE

async def support_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    message_text = update.message.text
    logger.info(f"User {user.telegram_id} submitted support ticket: {message_text}")
    
    await create_support_ticket_async(user, message_text)
    
    await update.message.reply_text(
        "Спасибо! Ваше обращение принято. Администратор скоро его рассмотрит."
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
                await bot.send_message(
                    chat_id=driver.telegram_id,
                    text=f"Пожалуйста, оцените поездку с пассажиром {passenger.name}:",
                    reply_markup=reply_markup
                )

    for passenger in passengers:
        rating_exists = await sync_to_async(Rating.objects.filter(trip=trip, rater=passenger, rated_user=driver).exists)()
        if not rating_exists:
            keyboard = [[InlineKeyboardButton(f"{i} ⭐", callback_data=f"rate_{trip.id}_{passenger.id}_{driver.id}_{i}") for i in range(1, 6)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await bot.send_message(
                chat_id=passenger.telegram_id,
                text=f"Поездка с водителем {driver.name} завершена. Пожалуйста, оцените его:",
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

    await add_rating_and_update_user_async(rater, rated_user, trip, score)

    await query.edit_message_text(text=f"Спасибо! Вы поставили оценку {score} ⭐ пользователю {rated_user.name}.")

# --- Анонимный чат ---
async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    booking_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id
    
    booking = await get_booking_by_id_async(booking_id)
    if not booking:
        await query.edit_message_text("Ошибка: бронирование не найдено.")
        return MAIN_MENU

    if user_id == booking.passenger.telegram_id:
        chat_partner = booking.trip.driver
        partner_role = "водителем"
    elif user_id == booking.trip.driver.telegram_id:
        chat_partner = booking.passenger
        partner_role = "пассажиром"
    else:
        await query.edit_message_text("Ошибка: вы не участник этого бронирования.")
        return MAIN_MENU
    
    context.user_data['chat_partner_id'] = chat_partner.telegram_id
    
    await query.edit_message_text(
        f"Вы вошли в чат с {partner_role} {chat_partner.name}.\n"
        "Все, что вы напишете, будет переслано. Чтобы выйти, отправьте /cancel."
    )
    return IN_CHAT

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_partner_id = context.user_data.get('chat_partner_id')
    if not chat_partner_id:
        await update.message.reply_text("Ошибка: чат не инициализирован.")
        return await show_main_menu(update, context)
    
    message_text = update.message.text
    user = await get_user_async(update.effective_user.id)
    
    await context.bot.send_message(
        chat_id=chat_partner_id,
        text=f"Сообщение от {user.name}:\n{message_text}"
    )
    await update.message.reply_text("Сообщение отправлено!")
    return IN_CHAT

async def cancel_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('chat_partner_id', None)
    await update.message.reply_text("Чат завершен.")
    return await show_main_menu(update, context)

# --- Вспомогательные обработчики ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('chat_partner_id', None)
    await update.message.reply_text("Действие отменено.")
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
