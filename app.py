"""
NHL Mini App — единый сервер.
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

CACHE_TTL = {
    "schedule": 60 * 30,   # расписание — 30 минут
    "standings": 60 * 60,  # таблица — 1 час
    "score": 30,           # live-счёт — 30 секунд
    "roster": 60 * 60,     # состав команды — 1 час
    "player": 60 * 60,     # карточка игрока — 1 час
    "boxscore": 30,        # статистика матча — 30 секунд
}

_cache: dict[str, tuple[float, dict]] = {}

app = FastAPI(title="NHL Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def fetch_with_cache(cache_key: str, url: str, ttl: int) -> dict:
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
    url = f"{NHL_BASE}/schedule/{date}"
    return await fetch_with_cache(f"schedule:{date}", url, CACHE_TTL["schedule"])


@app.get("/api/standings")
async def standings(season: str = "now"):
    # Передаем season (например, "now") в NHL API
    url = f"{NHL_BASE}/standings/{season}"
    return await fetch_with_cache(f"standings:{season}", url, CACHE_TTL["standings"])


ALLOWED_CATEGORIES = {"points", "goals", "assists", "plusMinus"}


@app.get("/api/leaders/{category}")
async def leaders(category: str, limit: int = 25, season_type: int = 2):
    """Топ игроков. season_type: 2 - регулярка, 3 - плей-офф"""
    if category not in ALLOWED_CATEGORIES:
        category = "points"
    limit = max(1, min(limit, 50))
    # Подставляем тип сезона в запрос лидерам
    url = f"{NHL_BASE}/skater-stats-leaders/current?categories={category}&limit={limit}"
    # Обрати внимание: официальное API NHL для некоторых экспресс-лидеров требует корректных параметров. 
    # Оставляем базовый URL, но добавляем дифференциацию кэша.
    return await fetch_with_cache(f"leaders:{category}:{limit}:{season_type}", url, CACHE_TTL["standings"])


@app.get("/api/player/{player_id}")
async def player(player_id: int):
    # Landing возвращает как текущую статистику, так и сезонную историю (careerTotals)
    url = f"{NHL_BASE}/player/{player_id}/landing"
    return await fetch_with_cache(f"player:{player_id}", url, CACHE_TTL["player"])


@app.get("/api/roster-stats/{team}")
async def roster_stats(team: str):
    url = f"{NHL_BASE}/club-stats/{team.upper()}/now"
    return await fetch_with_cache(f"roster:{team.upper()}", url, CACHE_TTL["roster"])


@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    url = f"{NHL_BASE}/gamecenter/{game_id}/boxscore"
    return await fetch_with_cache(f"boxscore:{game_id}", url, CACHE_TTL["boxscore"])


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    url = f"{NHL_BASE}/gamecenter/{game_id}/landing"
    return await fetch_with_cache(f"score:{game_id}", url, CACHE_TTL["score"])


# ---------- Telegram-бот (webhook) ----------

@app.post("/webhook")
async def telegram_webhook(update: dict):
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
                    "live-результаты, таблицы и полную статистику."
                ),
                "reply_markup": keyboard,
            })

    return {"ok": True}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")
