"""
NHL Mini App — единый сервер.

В этом файле объединено всё:
1. API с кэшем для данных NHL (защита от лишних запросов к NHL API)
2. Раздача интерфейса Mini App (static/index.html)
3. Telegram-бот: принимает сообщения через webhook и отправляет
   кнопку для открытия Mini App

Настройки берутся из переменных окружения (их задаёшь на хостинге,
без правки кода):
- BOT_TOKEN     — токен бота от @BotFather
- WEBAPP_URL    — публичный адрес этого сервера (Render даёт его
                  автоматически в переменной RENDER_EXTERNAL_URL)
"""

import os
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

NHL_BASE = "https://api-web.nhle.com/v1"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBAPP_URL", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Сколько секунд хранить данные в кэше для каждого типа запроса
CACHE_TTL = {
    "schedule": 60 * 30,   # расписание — 30 минут
    "standings": 60 * 60,  # таблица — 1 час
    "score": 30,           # live-счёт — 30 секунд
}

# Простой кэш в памяти: {key: (timestamp, data)}
_cache: dict[str, tuple[float, dict]] = {}

app = FastAPI(title="NHL Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def fetch_with_cache(cache_key: str, url: str, ttl: int) -> dict:
    """Возвращает данные из кэша, либо запрашивает NHL API и кладёт в кэш."""
    now = time.time()
    cached = _cache.get(cache_key)

    if cached and (now - cached[0]) < ttl:
        return cached[1]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    _cache[cache_key] = (now, data)
    return data


# ---------- API для Mini App ----------

@app.get("/api/schedule")
async def schedule(date: str):
    """Расписание/результаты на дату в формате YYYY-MM-DD."""
    url = f"{NHL_BASE}/schedule/{date}"
    return await fetch_with_cache(f"schedule:{date}", url, CACHE_TTL["schedule"])


@app.get("/api/standings")
async def standings():
    """Текущая турнирная таблица."""
    url = f"{NHL_BASE}/standings/now"
    return await fetch_with_cache("standings", url, CACHE_TTL["standings"])


# Разрешённые категории статистики, чтобы не пробрасывать произвольные значения в NHL API
ALLOWED_CATEGORIES = {"points", "goals", "assists", "plusMinus"}


@app.get("/api/leaders/{category}")
async def leaders(category: str):
    """Топ-10 игроков по выбранной категории статистики."""
    if category not in ALLOWED_CATEGORIES:
        category = "points"
    url = f"{NHL_BASE}/skater-stats-leaders/current?categories={category}&limit=10"
    return await fetch_with_cache(f"leaders:{category}", url, CACHE_TTL["standings"])


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    """Live-счёт конкретного матча."""
    url = f"{NHL_BASE}/gamecenter/{game_id}/landing"
    return await fetch_with_cache(f"score:{game_id}", url, CACHE_TTL["score"])


# ---------- Telegram-бот (webhook) ----------

@app.post("/webhook")
async def telegram_webhook(update: dict):
    """Telegram присылает сюда сообщения пользователей."""
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":
        keyboard = {
            "inline_keyboard": [[
                {"text": "🏒 Открыть NHL Live", "web_app": {"url": WEBAPP_URL}}
            ]]
        }
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": (
                    "Привет! Здесь можно посмотреть расписание матчей NHL, "
                    "live-результаты и турнирную таблицу."
                ),
                "reply_markup": keyboard,
            })

    return {"ok": True}


# ---------- Раздача интерфейса Mini App ----------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
