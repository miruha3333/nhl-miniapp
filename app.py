"""
NHL Mini App — единый сервер.
Обновленная версия с поддержкой разделения статистики на Регулярный сезон и Плей-офф.
"""

import os
import time
import asyncio
from pathlib import Path
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
    "schedule": 60 * 15,
    "standings": 60 * 30,
    "leaders": 60 * 30,
    "score": 15,
    "roster": 60 * 45,
    "player": 60 * 45,
    "boxscore": 20,
    "rightrail": 20,
    "player_search": 60 * 10,
    "team_schedule": 60 * 10,
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

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                _cache[cache_key] = (now, data)
                return data
            else:
                if cache_key in _cache:
                    return _cache[cache_key][1]
                return {"error": f"NHL API status {resp.status_code}"}
        except Exception as e:
            if cache_key in _cache:
                return _cache[cache_key][1]
            return {"error": str(e)}


# ---------- Служебный endpoint ----------

@app.get("/health")
async def health():
    """Простой ответ для проверки доступности сервиса."""
    return {"status": "ok"}


# ---------- API для Mini App ----------

@app.get("/api/schedule")
async def schedule(date: str):
    """Расписание дня + текущие показатели обеих команд.

    В превью матча фронтенду нужны В/П/ПБО/О. Эти показатели берём
    из текущей таблицы NHL, а не из календаря, чтобы они всегда отражали
    актуальное положение клуба. Таблица кэшируется отдельно, поэтому
    добавление этих данных не создаёт новый запрос к NHL на каждый матч.

