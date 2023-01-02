from django.shortcuts import render
import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from weatherdash import settings

DEFAULT_WEATHER = {
    "city": "No data",
    "temperature": 99,
    "hi": 99,
    "lo": 99,
    "unit": "C",
    "description": "No data.",
    "icon": "01d",
    "timezone_offset": 0,
}

_FORECAST_ONE_DAY = {
    "day": "ERROR",
    "city": "No data",
    "hi": 99,
    "lo": 99,
    "unit": "C",
    "morning_description": "No data.",
    "noon_description": "No data",
    "evening_description": "No data",
    "morning_icon": "01d",
    "noon_icon": "01d",
    "evening_icon": "01d",
}

DEFAULT_FORECAST = {f"day{x}": _FORECAST_ONE_DAY for x in range(5)}


def _get_clock_and_date(tz_offset=None):
    current_dt = pd.to_datetime("now")
    if tz_offset is not None:
        current_dt += pd.Timedelta(tz_offset, "seconds")
    clock = current_dt.strftime("%H:%M")
    date = current_dt.strftime("%A, %b %d")
    current_time = {"clock": clock, "date": date, "current_dt": current_dt}
    return current_time


def _get_weather_response(
    city_name=settings.CITY,
    state_code=settings.STATE_CODE,
    country_code=settings.COUNTRY_CODE,
    unit=settings.UNIT,
):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name},{state_code},{country_code}&units={unit}&appid={settings.OPEN_WEATHER_MAP_API_KEY}"
    session = requests.Session()
    session.mount("http://", HTTPAdapter(max_retries=999999))
    weather_response = session.get(url).json()
    return weather_response


def _get_forecast_response(
    city_name=settings.CITY,
    state_code=settings.STATE_CODE,
    country_code=settings.COUNTRY_CODE,
    unit=settings.UNIT,
):
    forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city_name},{state_code},{country_code}&units={unit}&appid={settings.OPEN_WEATHER_MAP_API_KEY}"
    session = requests.Session()
    session.mount("http://", HTTPAdapter(max_retries=999999))
    forecast_response = session.get(forecast_url).json()
    return forecast_response


def _process_forecast_response(forecast_response):
    all_forecasts = []
    timezone_offset = forecast_response["city"]["timezone"]
    for forecast in forecast_response["list"]:
        dt = pd.to_datetime(forecast["dt_txt"]) + pd.Timedelta(
            timezone_offset, unit="seconds"
        )
        df = pd.DataFrame(
            {
                "DATETIME": [dt],
                "DAY": [dt.strftime("%a").upper()],
                "LOCAL_MIN_TEMP": [forecast["main"]["temp_min"]],
                "LOCAL_MAX_TEMP": [forecast["main"]["temp_max"]],
                "CONDITION": [forecast["weather"][0]["main"]],
                "ICON": [forecast["weather"][0]["icon"]],
            }
        )
        all_forecasts.append(df)
    df = pd.concat(all_forecasts, ignore_index=True)

    df["DATE"] = df["DATETIME"].dt.strftime("%Y-%m-%d")
    df["LO"] = (
        df.groupby("DATE")["LOCAL_MIN_TEMP"].transform("min").round(0).astype(int)
    )
    df["HI"] = (
        df.groupby("DATE")["LOCAL_MAX_TEMP"].transform("max").round(0).astype(int)
    )
    df["HOUR"] = df["DATETIME"].dt.strftime("%H").astype(int)
    df["PERIOD"] = None
    df.loc[df["HOUR"] < 12, "PERIOD"] = "MORNING"
    df.loc[(df["HOUR"] >= 12) & (df["HOUR"] < 18), "PERIOD"] = "NOON"
    df.loc[df["HOUR"] >= 18, "PERIOD"] = "EVENING"

    # {icon ID (without d/n tag): priority}
    priority_icon_map = {
        "11": 1,  # Thunderstorm
        "10": 2,  # Rain
        "09": 3,  # Drizzle
        "13": 4,  # Snow
        "04": 5,  # Clouds
        "03": 6,  # Clouds
        "02": 7,  # Clouds
        "50": 8,  # Atmosphere
        "01": 9,  # Clear
    }

    df["PRIORITY"] = df["ICON"].apply(lambda x: x[:2]).map(priority_icon_map)
    df["HIGHEST_PRIORITY"] = df.groupby(["DAY", "PERIOD"])["PRIORITY"].transform("min")
    df = df[df["PRIORITY"] == df["HIGHEST_PRIORITY"]].copy()
    df["ICON"] = df["ICON"].apply(lambda x: x[:-1])
    df.loc[df["PERIOD"].isin(["MORNING", "NOON"]), "ICON"] += "d"
    df.loc[df["PERIOD"] == "EVENING", "ICON"] += "n"
    df = df[
        ["DATE", "DAY", "HI", "LO", "PERIOD", "CONDITION", "ICON"]
    ].drop_duplicates()

    df = (
        df.set_index(["DATE", "DAY", "HI", "LO", "PERIOD"])
        .unstack("PERIOD")
        .reset_index()
    )
    df.columns = [t[1] + "_" + t[0] if t[1] else t[0] for t in df]

    col_order = [
        "DATE",
        "DAY",
        "HI",
        "LO",
        "MORNING_CONDITION",
        "NOON_CONDITION",
        "EVENING_CONDITION",
        "MORNING_ICON",
        "NOON_ICON",
        "EVENING_ICON",
    ]
    df = df[col_order]
    df = df.fillna(axis="columns", method="ffill")
    return df


# Create your views here.
def index(request):
    city_name = settings.CITY
    state_code = settings.STATE_CODE
    unit = settings.UNIT

    # do not allow failure
    try:
        weather_response = _get_weather_response(
            city_name=city_name, state_code=state_code, unit=unit
        )

        if int(weather_response["cod"]) == 200:
            weather = {
                "city": city_name,
                "temperature": int(weather_response["main"]["temp"]),
                "hi": int(weather_response["main"]["temp_max"]),
                "lo": int(weather_response["main"]["temp_min"]),
                "unit": "C" if unit == "metric" else "F",
                "description": weather_response["weather"][0]["description"],
                "icon": weather_response["weather"][0]["icon"],
                "timezone_offset": weather_response["timezone"],
            }
        else:
            weather = DEFAULT_WEATHER

        current_time = _get_clock_and_date(tz_offset=weather["timezone_offset"])

        forecast_response = _get_forecast_response(
            city_name=city_name, state_code=state_code, unit=unit
        )

        if int(forecast_response["cod"]) == 200:
            df = _process_forecast_response(forecast_response)
            # IF TODAY IS MISSING when the data rolls, just append current weather
            # to the front of the forecast df.
            today = current_time["current_dt"].strftime("%a").upper()
            if df["DAY"].tolist()[0] != today:
                df_today = pd.DataFrame(
                    columns=df.columns,
                    data=[
                        [
                            current_time["current_dt"],
                            today,
                            weather["hi"],
                            weather["lo"],
                            "NONE",
                            "NONE",
                            "NONE",
                            None,
                            None,
                            weather["icon"],
                        ]
                    ],
                )
                df = pd.concat([df_today, df], ignore_index=True)

            weather_forecast = {}

            for index, row in df.iterrows():
                weather_forecast["day" + str(index)] = {
                    "day": row["DAY"],
                    "city": city_name,
                    "hi": row["HI"],
                    "lo": row["LO"],
                    "unit": "C" if unit == "metric" else "F",
                    "morning_description": row["MORNING_CONDITION"],
                    "noon_description": row["NOON_CONDITION"],
                    "evening_description": row["EVENING_CONDITION"],
                    "morning_icon": row["MORNING_ICON"],
                    "noon_icon": row["NOON_ICON"],
                    "evening_icon": row["EVENING_ICON"],
                }
        else:
            weather_forecast = DEFAULT_FORECAST

    except Exception as e:
        current_time = _get_clock_and_date()
        weather = DEFAULT_WEATHER
        weather_forecast = DEFAULT_FORECAST

    finally:
        context = {
            "weather": weather,
            "time": current_time,
            "forecast": weather_forecast,
        }

    return render(request, "weatherapp/index.html", context)
