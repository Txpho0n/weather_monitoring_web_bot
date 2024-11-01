# Код сайта, по заданным координатам выводящий карту с маршрутом и графики погодных условий

from dash import Dash, dcc, html, Input, Output
import dash_leaflet as dl
import plotly.graph_objs as go
import requests
from datetime import datetime, timedelta
from api import API_KEY

BASE_URL = "http://dataservice.accuweather.com"

# Функции для получения данных о погоде и ключей местоположений

def get_location_key(lat, lon):
    weather_url = f"{BASE_URL}/locations/v1/cities/geoposition/search?apikey={API_KEY}&q={lat}%2C{lon}"
    try:
        response = requests.get(weather_url)
        response.raise_for_status()
        loc_data = response.json()
        return loc_data['Key']
    except Exception as e:
        print("Ошибка при получении location_key:", e)
        return None

def get_weather_data(location_key):
    """Получение прогноза погоды на 5 дней по location_key"""
    weather_url = f"{BASE_URL}/forecasts/v1/daily/5day/{location_key}?apikey={API_KEY}&language=en-us&details=true&metric=true"
    try:
        response = requests.get(weather_url)
        response.raise_for_status()
        return response.json().get('DailyForecasts')
    except Exception as e:
        print("Ошибка при получении данных о погоде:", e)
        return None

# Инициализация Dash-приложения
app = Dash(__name__)

# Интерфейс Dash
app.layout = html.Div([
    html.H1("Прогноз погоды на маршруте"),

    # Ввод начальной и конечной точки с интервалом прогноза
    html.Div([
        html.Label("Координаты начальной точки:"),
        dcc.Input(id='start_lat', type='number', placeholder="Широта", debounce=True),
        dcc.Input(id='start_lon', type='number', placeholder="Долгота", debounce=True),

        html.Label("Координаты конечной точки:"),
        dcc.Input(id='end_lat', type='number', placeholder="Широта", debounce=True),
        dcc.Input(id='end_lon', type='number', placeholder="Долгота", debounce=True),

        html.Label("Количество дней прогноза:"),
        dcc.Dropdown(id='forecast_days', options=[
            {'label': '2 дня', 'value': 2},
            {'label': '5 дней', 'value': 5}
        ], value=5),
    ], style={'display': 'flex', 'gap': '20px'}),

    # Карта маршрута
    dl.Map(id="map", center=(33, 33), zoom=5, children=[
        dl.TileLayer(),
        dl.LayerGroup(id="route_layer"),
    ], style={'width': '100%', 'height': '500px', 'margin': "auto", "display": "block"}),

    # Элементы для выбора данных и построения графиков
    html.Div([
        dcc.Tabs(id='weather_tabs', children=[
            dcc.Tab(label='Температура', value='temperature'),
            dcc.Tab(label='Скорость ветра', value='wind_speed'),
            dcc.Tab(label='Вероятность осадков', value='precipitation')
        ]),
        dcc.Graph(id='weather_graph')
    ])
])

# Обработчики данных для обновления графиков и карты
@app.callback(
    [Output('weather_graph', 'figure'),
     Output('map', 'center'),
     Output('route_layer', 'children')],
    [Input('start_lat', 'value'),
     Input('start_lon', 'value'),
     Input('end_lat', 'value'),
     Input('end_lon', 'value'),
     Input('forecast_days', 'value'),
     Input('weather_tabs', 'value')]
)
def update_visuals(start_lat, start_lon, end_lat, end_lon, forecast_days, weather_param):
    if not all([start_lat, start_lon, end_lat, end_lon]):
        return go.Figure(), (33, 33), []  # Пустые значения, если координаты не указаны

    # Получаем location_key и данные о погоде для обеих точек
    location_key_start = get_location_key(start_lat, start_lon)
    location_key_end = get_location_key(end_lat, end_lon)

    if not location_key_start or not location_key_end:
        return go.Figure(), (33, 33), []

    weather_data_start = get_weather_data(location_key_start)
    weather_data_end = get_weather_data(location_key_end)

    if not weather_data_start or not weather_data_end:
        return go.Figure(), (33, 33), []

    # Ограничиваем данные числом выбранных дней прогноза
    weather_data_start = weather_data_start[:forecast_days]
    weather_data_end = weather_data_end[:forecast_days]

    # Преобразуем даты и создаем ось для графика
    dates = [datetime.strptime(forecast['Date'][:10], '%Y-%m-%d').strftime('%d-%m-%Y') for forecast in weather_data_start]

    # Выбираем нужные данные в зависимости от параметра
    if weather_param == 'temperature':
        y_start = [forecast['Temperature']['Maximum']['Value'] for forecast in weather_data_start]
        y_end = [forecast['Temperature']['Maximum']['Value'] for forecast in weather_data_end]
        y_label = "Температура (°C)"
    elif weather_param == 'wind_speed':
        y_start = [forecast['Day']['Wind']['Speed']['Value'] for forecast in weather_data_start]
        y_end = [forecast['Day']['Wind']['Speed']['Value'] for forecast in weather_data_end]
        y_label = "Скорость ветра (км/ч)"
    else:  # precipitation
        y_start = [forecast['Day']['PrecipitationProbability'] for forecast in weather_data_start]
        y_end = [forecast['Day']['PrecipitationProbability'] for forecast in weather_data_end]
        y_label = "Вероятность осадков (%)"

    # Создание графика
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=y_start, mode='lines+markers', name='Начальная точка'))
    fig.add_trace(go.Scatter(x=dates, y=y_end, mode='lines+markers', name='Конечная точка'))

    fig.update_layout(
        title=f"Прогноз погоды ({weather_param.capitalize()}) на {forecast_days} дней",
        xaxis_title="Дата",
        yaxis_title=y_label,
        hovermode="x unified",
        legend_title="Точка маршрута"
    )

    # Отображение на карте
    route_layer = [
        dl.Marker(position=(start_lat, start_lon), children=dl.Tooltip("Начальная точка")),
        dl.Marker(position=(end_lat, end_lon), children=dl.Tooltip("Конечная точка")),
        dl.Polyline(positions=[(start_lat, start_lon), (end_lat, end_lon)], color="blue")
    ]

    return fig, [(start_lat + end_lat) / 2, (start_lon + end_lon) / 2], route_layer

# Запуск сервера
if __name__ == '__main__':
    app.run_server(debug=True)