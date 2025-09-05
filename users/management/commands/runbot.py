import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from asgiref.sync import sync_to_async

from django.db import transaction
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
from trips.models import Vehicle, Trip, Booking
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
CHANGE_ROLE_BTN = "Сменить роль ✏️"
BACK_TO_MENU_BTN = "⬅️ Назад в главное меню"
CONFIRM_YES_BTN = "Да, сменить"
CONFIRM_NO_BTN = "Нет, отмена"

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
) = range(20)

# --- Функции для работы с БД (users) ---
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

# --- Функции для работы с БД (trips) ---
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
    return Trip.objects.create(
        driver=driver,
        vehicle=vehicle,
        departure_location=departure,
        destination_location=destination,
        departure_time=time,
        available_seats=seats,
        price=price
    )

def find_trips(departure, destination, search_date):
    return list(Trip.objects.filter(
        departure_location__icontains=departure,
        destination_location__icontains=destination,
        departure_time__date=search_date,
        departure_time__gte=datetime.now()
    ).select_related('driver', 'vehicle'))

def get_trip_by_id(trip_id):
    try:
        return Trip.objects.select_related('driver', 'vehicle').get(id=trip_id)
    except Trip.DoesNotExist:
        return None

@transaction.atomic
def create_booking(passenger, trip, seats_to_book):
    trip_for_update = Trip.objects.select_for_update().get(id=trip.id)
    if trip_for_update.available_seats >= seats_to_book:
        trip_for_update.available_seats -= seats_to_book
        trip_for_update.save()
        booking = Booking.objects.create(
            passenger=passenger,
            trip=trip_for_update,
            seats_booked=seats_to_book
        )
        return booking, None
    else:
        error_message = f"Недостаточно мест. Осталось только {trip_for_update.available_seats}."
        return None, error_message

def get_trips_for_driver(driver):
    return list(driver.trips_as_driver.prefetch_related('bookings__passenger').order_by('-departure_time'))

def get_bookings_for_passenger(passenger):
    return list(passenger.bookings_as_passenger.select_related('trip__driver', 'trip__vehicle').order_by('-trip__departure_time'))

# --- Функции для работы с БД (support) ---
def create_support_ticket(user, message):
    return SupportTicket.objects.create(user=user, message=message)


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


# --- Основные обработчики (start, меню) ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    if not user or not user.role:
        return await start_registration(update, context)

    if user.role == User.Role.PASSENGER:
        keyboard = [[FIND_TRIP_BTN], [MY_BOOKINGS_BTN, MY_PROFILE_BTN], [SUPPORT_BTN]]
        menu_text = "Меню пассажира:"
    elif user.role == User.Role.DRIVER:
        keyboard = [[CREATE_TRIP_BTN], [MY_TRIPS_BTN, MY_PROFILE_BTN], [SUPPORT_BTN]]
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
    await update.message.reply_text("Поздравляем! 🎉 Регистрация успешно завершена!", reply_markup=ReplyKeyboardRemove())
    return await show_main_menu(update, context)

# --- Профиль ---
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    role_text = user.get_role_display()
    profile_text = (f"👤 Ваш профиль:\n\n<b>Имя:</b> {user.name}\n<b>Телефон:</b> {user.phone_number}\n<b>Роль:</b> {role_text}")
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
    vehicles = await get_vehicles_for_driver_async(user)
    
    if not vehicles:
        await update.message.reply_text(
            "У вас еще нет добавленных автомобилей. Давайте сначала добавим ваш транспорт.\n\n"
            "Введите марку автомобиля (например, Kia):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_VEHICLE_ENTERING_BRAND

    keyboard = [
        [InlineKeyboardButton(str(v), callback_data=f"select_vehicle_{v.id}")]
        for v in vehicles
    ]
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
        text="Откуда вы отправляетесь? (например, Казань)",
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
        "Откуда вы отправляетесь? (например, Казань)"
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
        trip_info = (
            f"<b>Водитель:</b> {trip.driver.name}\n"
            f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
            f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
            f"<b>Авто:</b> {trip.vehicle}\n"
            f"<b>Свободных мест:</b> {trip.available_seats}\n"
            f"<b>Цена:</b> {trip.price} руб."
        )
        keyboard = [[InlineKeyboardButton("✅ Забронировать", callback_data=f"book_trip_{trip.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(trip_info, parse_mode='HTML', reply_markup=reply_markup)
    
    return await show_main_menu(update, context)

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
        await update.message.reply_text(
            f"✅ Поздравляем! Вы успешно забронировали {seats_to_book} мест(а)!\n\n"
            f"С водителем можно будет связаться позже (эта функция в разработке)."
        )

    context.user_data.pop('booking_trip_id', None)
    return await show_main_menu(update, context)

# --- "Мои поездки" и "Мои бронирования" ---
async def my_trips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    driver = await get_user_async(update.effective_user.id)
    trips = await get_trips_for_driver_async(driver)
    
    if not trips:
        await update.message.reply_text("У вас пока нет созданных поездок.")
        return MAIN_MENU
        
    await update.message.reply_text("Ваши созданные поездки:")
    for trip in trips:
        trip_info = (
            f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
            f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
            f"<b>Авто:</b> {trip.vehicle}\n"
            f"<b>Свободных мест:</b> {trip.available_seats}"
        )
        
        passengers_info = []
        for booking in trip.bookings.all():
            passengers_info.append(
                f" - {booking.passenger.name}, тел: {booking.passenger.phone_number} (мест: {booking.seats_booked})"
            )
        
        if passengers_info:
            trip_info += "\n\n<b>Забронировавшие пассажиры:</b>\n" + "\n".join(passengers_info)
        else:
            trip_info += "\n\n<i>Пассажиров пока нет.</i>"
            
        await update.message.reply_text(trip_info, parse_mode='HTML')
        
    return MAIN_MENU

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    passenger = await get_user_async(update.effective_user.id)
    bookings = await get_bookings_for_passenger_async(passenger)

    if not bookings:
        await update.message.reply_text("У вас пока нет активных бронирований.")
        return MAIN_MENU

    await update.message.reply_text("Ваши бронирования:")
    for booking in bookings:
        trip = booking.trip
        booking_info = (
            f"<b>Маршрут:</b> {trip.departure_location} → {trip.destination_location}\n"
            f"<b>Время:</b> {trip.departure_time.strftime('%d.%m.%Y в %H:%M')}\n"
            f"<b>Водитель:</b> {trip.driver.name}, тел: {trip.driver.phone_number}\n"
            f"<b>Авто:</b> {trip.vehicle}\n"
            f"<b>Вы забронировали:</b> {booking.seats_booked} мест(а)"
        )
        await update.message.reply_text(booking_info, parse_mode='HTML')

    return MAIN_MENU

# --- Система поддержки ---
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Опишите вашу проблему или вопрос одним сообщением. "
        "Мы сохраним ваше обращение, и администратор свяжется с вами.",
        reply_markup=ReplyKeyboardRemove()
    )
    return SUPPORT_ENTERING_MESSAGE

async def support_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = await get_user_async(update.effective_user.id)
    message_text = update.message.text
    
    await create_support_ticket_async(user, message_text)
    
    await update.message.reply_text(
        "Спасибо! Ваше обращение принято. Администратор скоро его рассмотрит."
    )
    return await show_main_menu(update, context)

# --- Вспомогательные обработчики ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
                    CallbackQueryHandler(book_trip_start, pattern="^book_trip_"),
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
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            persistent=True,
            name="main_conversation"
        )

        application.add_handler(conv_handler)
        
        self.stdout.write(self.style.SUCCESS("Бот успешно запущен! Нажмите Ctrl+C для остановки."))
        application.run_polling()

