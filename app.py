"""
NHL Mini App — единый сервер.

В этом файле объединено всё:
1. API с кэшем для данных NHL (защита от лишних запросов к NHL API)
2. Раздача интерфейса Mini App (static/index.html)
3. Telegram-бот: принимает сообщения через webhook и отправляет
   кнопку для открытия Mini App
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
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}\"

# Кэш в памяти (дополнительно страхует от лимитов NHL API)
CACHE_TTL = {
    "schedule": 60 * 15,   # 15 минут
    "standings": 60 * 30,  # 30 минут
    "score": 15,           # 15 секунд (для live)
    "roster": 60 * 60,     # 1 час
    "leaders": 60 * 30,    # 30 минут
    "player": 60 * 60,     # 1 час
    "boxscore": 30         # 30 секунд
}

cache_data = {}

async def fetch_with_cache(cache_key: str, url: str, ttl: int):
    now = time.time()
    if cache_key in cache_data:
        entry = cache_data[cache_key]
        if now - entry["timestamp"] < ttl:
            return entry["data"]
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                cache_data[cache_key] = {"timestamp": now, "data": data}
                return data
            else:
                # Если NHL API временно сбоит, но есть старый кэш — отдаем его
                if cache_key in cache_data:
                    return cache_data[cache_key]["data"]
                return {"error": f"NHL API returned status {res.status_code}"}
        except Exception as e:
            if cache_key in cache_data:
                return cache_data[cache_key]["data"]
            return {"error": str(e)}

app = FastAPI(title="NHL Live API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/schedule")
async def schedule(date: str):
    """Расписание матчей на выбранную дату (YYYY-MM-DD)"""
    url = f"{NHL_BASE}/schedule/{date}"
    return await fetch_with_cache(f"schedule:{date}", url, CACHE_TTL["schedule"])

@app.get("/api/standings")
async def standings():
    """Текущая турнирная таблица регулярного чемпионата"""
    url = f"{NHL_BASE}/standings/now"
    return await fetch_with_cache("standings_now", url, CACHE_TTL["standings"])

@app.get("/api/leaders/{category}")
async def leaders(category: str, limit: int = 25):
    """Лидеры лиги по категориям (points, goals, assists, plusMinus)"""
    url = f"{NHL_BASE}/skater-stats-leaders/current?category={category}&limit={limit}"
    return await fetch_with_cache(f"leaders:{category}:{limit}", url, CACHE_TTL["leaders"])

@app.get("/api/roster-stats/{team}")
async def roster_stats(team: str):
    """Состав команды и полная статистика игроков текущего клуба"""
    url = f"{NHL_BASE}/roster/{team}/current"
    return await fetch_with_cache(f"roster:{team}", url, CACHE_TTL["roster"])

@app.get("/api/player/{player_id}")
async def player_profile(player_id: str):
    """Профиль игрока, био и вся история его карьеры по сезонам"""
    url = f"{NHL_BASE}/player/{player_id}/landing"
    return await fetch_with_cache(f"player:{player_id}", url, CACHE_TTL["player"])

@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    """Подробный боксскор матча (статистика вратарей, броски, игровое время)"""
    url = f"{NHL_BASE}/gamecenter/{game_id}/boxscore"
    return await fetch_with_cache(f"boxscore:{game_id}", url, CACHE_TTL["boxscore"])

@app.get("/api/score/{game_id}")
async def score(game_id: str):
    """Сводка матча (голы по периодам, авторы, ассистенты, штрафы)"""
    url = f"{NHL_BASE}/gamecenter/{game_id}/landing"
    return await fetch_with_cache(f"score:{game_id}", url, CACHE_TTL["score"])


# ---------- Telegram-бот (webhook) ----------

@app.post("/webhook")
async def telegram_webhook(update: dict):
    """Прием сообщений от Telegram юзеров"""
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":
        keyboard = {
            "inline_keyboard": [[\n                {"text": "🏒 Открыть NHL Live", "web_app": {"url": WEBAPP_URL}}\n            ]]
        }
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": (
                    "Привет! Добро пожаловать в NHL Live.\n"
                    "Здесь можно посмотреть live-результаты матчей, "
                    "турнирные таблицы, статистику клубов и карточки игроков."
                ),
                "reply_markup": keyboard,
            })

    return {"ok": True}


# ---------- Раздача интерфейса Mini App ----------

# Если папка static существует, монтируем её для раздачи index.html
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "NHL API работает. Файл static/index.html не найден."}
