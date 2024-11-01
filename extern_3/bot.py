# Код для тг-бота, получающего координаты начальной и конечной точки и выводящий температуру в них в следующие несколько дней

from api import API_KEY, API_TOKEN
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import requests
from datetime import datetime
import logging

# Инициализация бота и логирования
BASE_URL = "http://dataservice.accuweather.com"
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Класс состояний для последовательного ввода данных
class WeatherForm(StatesGroup):
    start_location = State()
    end_location = State()
    forecast_days = State()

# Создаем клавиатуры для выбора локации
location_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("Отправить моё местоположение", request_location=True)
)

# Функции для получения данных о погоде и местоположении
def get_location_key(lat, lon):
    url = f"{BASE_URL}/locations/v1/cities/geoposition/search?apikey={API_KEY}&q={lat}%2C{lon}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('Key')
    except Exception as e:
        logging.error(f"Ошибка при получении location_key: {e}")
        return None

def get_weather_data(location_key):
    url = f"{BASE_URL}/forecasts/v1/daily/5day/{location_key}?apikey={API_KEY}&language=ru-ru&details=true&metric=true"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get('DailyForecasts')
    except Exception as e:
        logging.error(f"Ошибка при получении данных о погоде: {e}")
        return None

# Обработчики команд /start и /help
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я погодный бот. Используйте /weather, чтобы получить прогноз погоды по заданному маршруту.")

@dp.message_handler(commands=['help'])
async def send_help(message: types.Message):
    await message.reply("Список команд:\n"
                        "/start - Начать работу с ботом\n"
                        "/weather - Прогноз погоды на маршруте\n"
                        "Вы также можете отправить своё местоположение.")

# Команда /weather для начала получения прогноза погоды на маршруте
@dp.message_handler(commands=['weather'])
async def weather_command(message: types.Message):
    await message.reply("Выберите начальную точку маршрута или отправьте свои координаты вручную:", reply_markup=location_keyboard)
    await WeatherForm.start_location.set()

# Обработчик для начальной точки маршрута
@dp.message_handler(content_types=['location'], state=WeatherForm.start_location)
async def process_start_location_geo(message: types.Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    await state.update_data(start_location=(lat, lon))
    await message.reply("Теперь выберите конечную точку маршрута или отправьте свои координаты вручную:", reply_markup=location_keyboard)
    await WeatherForm.next()

@dp.message_handler(state=WeatherForm.start_location)
async def process_start_location_text(message: types.Message, state: FSMContext):
    start_location = message.text.split(',')
    if len(start_location) == 2:
        try:
            await state.update_data(start_location=(float(start_location[0]), float(start_location[1])))
            await message.reply("Теперь выберите конечную точку маршрута или отправьте свои координаты вручную:", reply_markup=location_keyboard)
            await WeatherForm.next()
        except ValueError:
            await message.reply("Координаты должны быть числовыми. Попробуйте ещё раз.")
    else:
        await message.reply("Пожалуйста, введите координаты в формате 'широта, долгота'.")

# Обработчик для конечной точки маршрута
@dp.message_handler(content_types=['location'], state=WeatherForm.end_location)
async def process_end_location_geo(message: types.Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    await state.update_data(end_location=(lat, lon))
    # Переход к выбору количества дней прогноза
    await choose_forecast_days(message, state)

@dp.message_handler(state=WeatherForm.end_location)
async def process_end_location_text(message: types.Message, state: FSMContext):
    end_location = message.text.split(',')
    if len(end_location) == 2:
        try:
            await state.update_data(end_location=(float(end_location[0]), float(end_location[1])))
            # Переход к выбору количества дней прогноза
            await choose_forecast_days(message, state)
        except ValueError:
            await message.reply("Координаты должны быть числовыми. Попробуйте ещё раз.")
    else:
        await message.reply("Пожалуйста, введите координаты в формате 'широта, долгота'.")

# Функция для выбора количества дней прогноза с использованием встроенной клавиатуры
async def choose_forecast_days(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("2 дня", callback_data='forecast_2'),
        InlineKeyboardButton("5 дней", callback_data='forecast_5')
    )
    await message.reply("Выберите количество дней прогноза:", reply_markup=keyboard)
    await WeatherForm.forecast_days.set()

# Обработчик для выбора количества дней прогноза и вывода данных о погоде
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('forecast_'), state=WeatherForm.forecast_days)
async def process_forecast_days(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    forecast_days = int(callback_query.data.split('_')[1])
    user_data = await state.get_data()

    start_location = user_data['start_location']
    end_location = user_data['end_location']

    start_key = get_location_key(*start_location)
    end_key = get_location_key(*end_location)

    if not start_key or not end_key:
        await bot.send_message(callback_query.from_user.id, "Ошибка получения данных. Проверьте координаты.")
    else:
        weather_data_start = get_weather_data(start_key)
        weather_data_end = get_weather_data(end_key)

        if not weather_data_start or not weather_data_end:
            await bot.send_message(callback_query.from_user.id, "Ошибка получения прогноза погоды.")
        else:
            response = f"Прогноз на {forecast_days} дней:\n"
            for i in range(forecast_days):
                date = datetime.strptime(weather_data_start[i]['Date'][:10], '%Y-%m-%d').strftime('%d-%m-%Y')
                temp_start = weather_data_start[i]['Temperature']['Maximum']['Value']
                temp_end = weather_data_end[i]['Temperature']['Maximum']['Value']
                response += f"{date}: Начальная точка {temp_start}°C, Конечная точка {temp_end}°C\n"
            await bot.send_message(callback_query.from_user.id, response)
    await state.finish()

# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)