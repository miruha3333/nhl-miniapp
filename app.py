"""
NHL Mini App — единый сервер.
Обновленная версия с поддержкой разделения статистики на Регулярный сезон и Плей-офф.
"""

import os
import time
import asyncio
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
    url = f"{NHL_BASE}/schedule/{date}"
    return await fetch_with_cache(f"schedule:{date}", url, CACHE_TTL["schedule"])


@app.get("/api/standings")
async def standings():
    url = f"{NHL_BASE}/standings/now"
    return await fetch_with_cache("standings", url, CACHE_TTL["standings"])


@app.get("/api/standings-by-date/{date}")
async def standings_by_date(date: str):
    """Турнирная таблица на конкретную дату."""
    url = f"{NHL_BASE}/standings/{date}"
    return await fetch_with_cache(f"standings:{date}", url, CACHE_TTL["standings"])


@app.get("/api/seasons-list")
async def seasons_list():
    """Список всех сезонов в истории НХЛ с точной датой окончания регулярного
    сезона (standingsEnd). Это устраняет угадывание дат — для каждого сезона
    NHL API сам говорит, когда закончилась регулярка."""
    url = f"{NHL_BASE}/standings-season"
    return await fetch_with_cache("seasons-list", url, CACHE_TTL["standings"])


@app.get("/api/playoff-bracket/{year}")
async def playoff_bracket(year: str):
    """Сетка плей-офф за указанный год (год начала сезона, например 2024
    для плей-офф сезона 2023-24)."""
    url = f"{NHL_BASE}/playoff-bracket/{year}"
    return await fetch_with_cache(f"bracket:{year}", url, CACHE_TTL["standings"])


ALLOWED_CATEGORIES = {"points", "goals", "assists", "plusMinus"}

@app.get("/api/leaders/{category}")
async def leaders(category: str, limit: int = 25, season: str | None = None):
    """Лидеры лиги по категории статистики. Если season не указан — берутся
    текущие лидеры (skater-stats-leaders/current). Если указан (формат
    YYYYYYYY) — лидеры именно этого сезона за регулярный чемпионат (gameType=2),
    иначе вкладка 'Игроки' всегда показывала текущий сезон независимо от
    выбора в таблице."""
    if category not in ALLOWED_CATEGORIES:
        category = "points"
    limit = max(1, min(limit, 50))

    if season:
        url = f"{NHL_BASE}/skater-stats-leaders/{season}/2?categories={category}&limit={limit}"
        cache_key = f"leaders:{category}:{limit}:{season}"
    else:
        url = f"{NHL_BASE}/skater-stats-leaders/current?categories={category}&limit={limit}"
        cache_key = f"leaders:{category}:{limit}"

    return await fetch_with_cache(cache_key, url, CACHE_TTL["leaders"])


@app.get("/api/goalie-leaders")
async def goalie_leaders(limit: int = 50, season: str | None = None):
    """Полная таблица вратарей из NHL Stats REST API.

    В отличие от нескольких отдельных leaderboard-запросов здесь получаем
    одну строку на вратаря с И/В/П/ПБО/%ОБ/ГКИ/SO, поэтому фронтенд может
    нормально сортировать всю таблицу.
    """
    limit = max(1, min(limit, 100))

    if season:
        target_season = season
    else:
        now = time.localtime()
        start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
        target_season = f"{start_year}{start_year + 1}"

    url = (
        "https://api.nhle.com/stats/rest/en/goalie/summary"
        f"?isAggregate=true&cayenneExp=seasonId={target_season}%20and%20gameTypeId=2"
        f"&limit={limit}"
    )
    cache_key = f"goalie-summary:{target_season}:{limit}"
    data = await fetch_with_cache(cache_key, url, CACHE_TTL["leaders"])

    if not isinstance(data, dict):
        return {"season": target_season, "goalies": []}

    raw_rows = data.get("data", [])
    if not isinstance(raw_rows, list):
        raw_rows = []

    goalies = []
    for row in raw_rows:
        first_name = row.get("firstName", "")
        last_name = row.get("lastName", "")
        if isinstance(first_name, dict):
            first_name = first_name.get("default", "")
        if isinstance(last_name, dict):
            last_name = last_name.get("default", "")

        goalies.append({
            "id": row.get("playerId"),
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": row.get("teamAbbrevs") or row.get("teamAbbrev") or "",
            "gamesPlayed": row.get("gamesPlayed"),
            "gamesStarted": row.get("gamesStarted"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "otLosses": row.get("otLosses"),
            "savePctg": row.get("savePctg"),
            "gaa": row.get("goalsAgainstAverage", row.get("gaa")),
            "shutouts": row.get("shutouts"),
            "saves": row.get("saves"),
            "shotsAgainst": row.get("shotsAgainst"),
        })

    return {"season": target_season, "goalies": goalies}


@app.get("/api/game-video/{game_id}")
async def game_video(game_id: str):
    """Возвращает официальные ссылки на видео обзора из NHL API.

    В разных версиях NHL API видеоданные встречаются в двух местах:
    1) в scoreboard/schedule как относительный путь /video/...
    2) в landing.summary.gameVideo как ID ролика.

    Поэтому сначала смотрим landing, затем scoreboard за дату матча.
    Это позволяет не зависеть от одной конкретной формы ответа API.
    """
    landing_url = f"{NHL_BASE}/gamecenter/{game_id}/landing"
    landing = await fetch_with_cache(
        f"game-video-landing:{game_id}", landing_url, CACHE_TTL["score"]
    )

    if not isinstance(landing, dict) or landing.get("error"):
        return {
            "available": False,
            "error": landing.get("error") if isinstance(landing, dict) else "NHL API error",
        }

    videos = []

    def add_video(kind: str, value, title: str):
        if value is None or value == "":
            return
        if isinstance(value, dict):
            value = value.get("url") or value.get("shareUrl") or value.get("videoUrl") or value.get("href")
        if not isinstance(value, str):
            # В landing.summary.gameVideo NHL иногда отдаёт числовой video ID.
            # Без надёжного публичного metadata URL не выдумываем прямой mp4.
            return
        value = value.strip()
        if not value:
            return
        if value.startswith("/video/"):
            value = "https://www.nhl.com" + value
        elif value.startswith("http://"):
            value = "https://" + value[7:]
        elif not value.startswith("https://"):
            return
        videos.append({"kind": kind, "title": title, "url": value})

    # Некоторые ответы landing содержат готовые URL/пути.
    add_video("recap", landing.get("threeMinRecap"), "3-Minute Recap")
    add_video("condensed", landing.get("condensedGame"), "Condensed Game")

    summary = landing.get("summary") or {}
    if isinstance(summary, dict):
        add_video("recap", summary.get("threeMinRecap"), "3-Minute Recap")
        add_video("condensed", summary.get("condensedGame"), "Condensed Game")

    # Надёжный источник: scoreboard за дату матча.
    game_date = landing.get("gameDate")
    if isinstance(game_date, str) and game_date:
        score_url = f"{NHL_BASE}/score/{game_date}"
        score_data = await fetch_with_cache(
            f"score-date-for-video:{game_date}", score_url, CACHE_TTL["score"]
        )
        for game in (score_data.get("games", []) if isinstance(score_data, dict) else []):
            if str(game.get("id")) != str(game_id):
                continue
            add_video("recap", game.get("threeMinRecap"), "3-Minute Recap")
            add_video("condensed", game.get("condensedGame"), "Condensed Game")
            break

    # Убираем дубли.
    unique = []
    seen = set()
    for video in videos:
        key = video["url"]
        if key not in seen:
            seen.add(key)
            unique.append(video)

    game_center = landing.get("gameCenterLink") or f"https://www.nhl.com/gamecenter/{game_id}"
    if isinstance(game_center, str) and game_center.startswith("/"):
        game_center = "https://www.nhl.com" + game_center

    return {
        "available": bool(unique),
        "videos": unique,
        "gameCenterLink": game_center,
        "gameState": landing.get("gameState"),
        "gameDate": game_date,
    }


@app.get("/api/search/player")
async def search_player(q: str):
    """Поиск игрока по имени через поисковый сервис NHL."""
    query = q.strip()
    if len(query) < 2:
        return []

    url = "https://search.d3.nhle.com/api/v1/search/player"
    cache_key = f"player-search:{query.lower()}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    cached = _cache.get(cache_key)
    now = time.time()
    if cached and (now - cached[0]) < CACHE_TTL["player_search"]:
        return cached[1]

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            resp = await client.get(
                url,
                params={"culture": "en-us", "limit": 10, "q": query, "active": "true"},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                _cache[cache_key] = (now, data)
                return data
            return {"error": f"NHL search status {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}


@app.get("/api/team-schedule/{team}")
async def team_schedule(team: str, season: str | None = None):
    """Полный календарь команды за текущий или выбранный сезон."""
    team_upper = team.upper()
    season_key = season or "now"
    url = f"{NHL_BASE}/club-schedule-season/{team_upper}/{season_key}"
    return await fetch_with_cache(
        f"team-schedule:{team_upper}:{season_key}",
        url,
        CACHE_TTL["team_schedule"],
    )


@app.get("/api/player/{player_id}")
async def player(player_id: str):
    url = f"{NHL_BASE}/player/{player_id}/landing"
    return await fetch_with_cache(f"player:{player_id}", url, CACHE_TTL["player"])


@app.get("/api/roster-stats/{team}")
async def roster_stats(team: str, season: str | None = None):
    """
    Состав и статистика команды за регулярку (gameType=2) и плей-офф (gameType=3).
    Если season не указан — берётся текущий сезон (club-stats/.../now).
    Если season указан (формат YYYYYYYY, например 20232024) — берётся состав
    и статистика именно этого сезона, что важно для исторических данных:
    без этого параметра при выборе старого сезона в таблице состав команды
    всегда показывал бы текущих игроков.
    """
    team_upper = team.upper()

    try:
        if season:
            target_season = season
        else:
            now_url = f"{NHL_BASE}/club-stats/{team_upper}/now"
            base_data = await fetch_with_cache(f"roster_now:{team_upper}", now_url, CACHE_TTL["roster"])
            if "error" in base_data:
                return base_data
            target_season = base_data.get("season", 20252026)

        reg_url = f"{NHL_BASE}/club-stats/{team_upper}/{target_season}/2"
        po_url = f"{NHL_BASE}/club-stats/{team_upper}/{target_season}/3"

        regular_data = await fetch_with_cache(f"club_stats:{team_upper}:{target_season}:2", reg_url, CACHE_TTL["roster"])
        playoff_data = await fetch_with_cache(f"club_stats:{team_upper}:{target_season}:3", po_url, CACHE_TTL["roster"])

        return {
            "team": team_upper,
            "season": target_season,
            "regular": {
                "skaters": regular_data.get("skaters", []),
                "goalies": regular_data.get("goalies", [])
            },
            "playoff": {
                "skaters": playoff_data.get("skaters", []),
                "goalies": playoff_data.get("goalies", [])
            }
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    url = f"{NHL_BASE}/gamecenter/{game_id}/boxscore"
    return await fetch_with_cache(f"boxscore:{game_id}", url, CACHE_TTL["boxscore"])


@app.get("/api/right-rail/{game_id}")
async def right_rail(game_id: str):
    """Командная статистика матча: броски, хиты, вбрасывания, силовые приёмы,
    штраф, потери/отборы шайбы — общие показатели и разбивка по периодам."""
    url = f"{NHL_BASE}/gamecenter/{game_id}/right-rail"
    return await fetch_with_cache(f"rightrail:{game_id}", url, CACHE_TTL["rightrail"])


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    url = f"{NHL_BASE}/gamecenter/{game_id}/landing"
    return await fetch_with_cache(f"score:{game_id}", url, CACHE_TTL["score"])


# ---------- Telegram-бот ----------

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
                    "Привет! Добро пожаловать в обновленный NHL Live. "
                    "Смотри результаты матчей, таблицы и расширенную статистику клубов."
                ),
                "reply_markup": keyboard,
            })

    return {"ok": True}


# ---------- Раздача интерфейса ----------

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "NHL API работает успешно. Файл static/index.html не найден."}
