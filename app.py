import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


NHL_BASE = "https://api-web.nhle.com/v1"
NHL_STATS_BASE = "https://api.nhle.com/stats/rest/en"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = "https://nhl-miniapp-1.onrender.com"
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
    "matchup": 60 * 30,
    "player_search": 60 * 10,
    "team_schedule": 60 * 10,
}

_cache: dict[str, tuple[float, Any]] = {}

app = FastAPI(title="NHL Mini App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


async def fetch_with_cache(
    cache_key: str,
    url: str,
    ttl: int,
) -> Any:
    now = time.time()
    cached = _cache.get(cache_key)

    if cached and now - cached[0] < ttl:
        return cached[1]

    async with httpx.AsyncClient(
        timeout=12,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(
                url,
                headers=DEFAULT_HEADERS,
            )

            if response.status_code == 200:
                data = response.json()
                _cache[cache_key] = (now, data)
                return data

            if cache_key in _cache:
                return _cache[cache_key][1]

            return {
                "error": f"NHL API status {response.status_code}"
            }

        except Exception as error:
            if cache_key in _cache:
                return _cache[cache_key][1]

            return {
                "error": str(error)
            }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/schedule")
async def schedule(date: str):
    schedule_url = f"{NHL_BASE}/schedule/{date}"
    standings_url = f"{NHL_BASE}/standings/now"

    schedule_data, standings_data = await asyncio.gather(
        fetch_with_cache(
            f"schedule:{date}",
            schedule_url,
            CACHE_TTL["schedule"],
        ),
        fetch_with_cache(
            "standings",
            standings_url,
            CACHE_TTL["standings"],
        ),
    )

    if not isinstance(schedule_data, dict):
        return schedule_data

    standings_rows = (
        standings_data.get("standings", [])
        if isinstance(standings_data, dict)
        else []
    )

    standings_map = {}

    for row in standings_rows:
        if not isinstance(row, dict):
            continue

        abbreviation = row.get("teamAbbrev")

        if isinstance(abbreviation, dict):
            abbreviation = abbreviation.get("default")

        if not abbreviation:
            continue

        standings_map[str(abbreviation).upper()] = {
            "wins": row.get("wins", 0),
            "losses": row.get("losses", 0),
            "otLosses": row.get("otLosses", 0),
            "points": row.get("points", 0),
        }

    game_week = schedule_data.get("gameWeek", [])

    if not isinstance(game_week, list):
        return schedule_data

    for day in game_week:
        if not isinstance(day, dict):
            continue

        games = day.get("games", [])

        if not isinstance(games, list):
            continue

        for game in games:
            if not isinstance(game, dict):
                continue

            for side in ("awayTeam", "homeTeam"):
                team = game.get(side) or {}

                if not isinstance(team, dict):
                    continue

                abbreviation = (
                    team.get("abbrev")
                    or team.get("teamAbbrev")
                )

                if isinstance(abbreviation, dict):
                    abbreviation = abbreviation.get("default")

                if not abbreviation:
                    continue

                record = standings_map.get(
                    str(abbreviation).upper()
                )

                if record:
                    team["currentRecord"] = record

    return schedule_data


@app.get("/api/standings")
async def standings():
    return await fetch_with_cache(
        "standings",
        f"{NHL_BASE}/standings/now",
        CACHE_TTL["standings"],
    )


@app.get("/api/standings-by-date/{date}")
async def standings_by_date(date: str):
    return await fetch_with_cache(
        f"standings:{date}",
        f"{NHL_BASE}/standings/{date}",
        CACHE_TTL["standings"],
    )


@app.get("/api/seasons-list")
async def seasons_list():
    return await fetch_with_cache(
        "seasons-list",
        f"{NHL_BASE}/standings-season",
        CACHE_TTL["standings"],
    )


@app.get("/api/playoff-bracket/{year}")
async def playoff_bracket(year: str):
    return await fetch_with_cache(
        f"bracket:{year}",
        f"{NHL_BASE}/playoff-bracket/{year}",
        CACHE_TTL["standings"],
    )


ALLOWED_CATEGORIES = {
    "points",
    "goals",
    "assists",
    "plusMinus",
}


@app.get("/api/leaders/{category}")
async def leaders(
    category: str,
    limit: int = 25,
    season: str | None = None,
):
    if category not in ALLOWED_CATEGORIES:
        category = "points"

    limit = max(1, min(limit, 50))

    if season:
        url = (
            f"{NHL_BASE}/skater-stats-leaders/"
            f"{season}/2"
            f"?categories={category}"
            f"&limit={limit}"
        )
        cache_key = f"leaders:{category}:{limit}:{season}"
    else:
        url = (
            f"{NHL_BASE}/skater-stats-leaders/"
            f"current?categories={category}"
            f"&limit={limit}"
        )
        cache_key = f"leaders:{category}:{limit}"

    return await fetch_with_cache(
        cache_key,
        url,
        CACHE_TTL["leaders"],
    )


@app.get("/api/goalie-leaders")
async def goalie_leaders(
    limit: int = 100,
    season: str | None = None,
):
    limit = max(1, min(limit, 100))

    now = time.localtime()
    current_start_year = (
        now.tm_year
        if now.tm_mon >= 9
        else now.tm_year - 1
    )

    current_season = (
        f"{current_start_year}"
        f"{current_start_year + 1}"
    )

    target_season = season or current_season

    async def load_season(season_id: str):
        params = {
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": (
                f"seasonId={season_id} "
                "and gameTypeId=2"
            ),
            "start": 0,
            "limit": limit,
            "sort": (
                '[{"property":"gamesPlayed",'
                '"direction":"DESC"}]'
            ),
        }

        url = (
            f"{NHL_STATS_BASE}/goalie/summary?"
            f"{httpx.QueryParams(params)}"
        )

        data = await fetch_with_cache(
            f"goalie-summary:{season_id}:{limit}",
            url,
            CACHE_TTL["leaders"],
        )

        if not isinstance(data, dict):
            return [], {"error": "Некорректный ответ NHL API"}

        if data.get("error"):
            return [], {"error": data["error"]}

        rows = data.get("data", [])

        if not isinstance(rows, list):
            rows = []

        return rows, None

    rows, api_error = await load_season(target_season)
    stats_season = target_season

    if not rows and target_season == current_season:
        previous_start_year = current_start_year - 1
        previous_season = (
            f"{previous_start_year}"
            f"{previous_start_year + 1}"
        )

        rows, previous_error = await load_season(
            previous_season
        )

        if rows:
            stats_season = previous_season
            api_error = None
        elif previous_error:
            api_error = previous_error

    if not rows and api_error:
        return {
            "season": stats_season,
            "requestedSeason": target_season,
            "fallback": stats_season != target_season,
            "goalies": [],
            "error": api_error.get(
                "error",
                "Ошибка NHL Stats API",
            ),
        }

    goalies = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        first_name = row.get("firstName", "")
        last_name = row.get("lastName", "")

        if isinstance(first_name, dict):
            first_name = first_name.get("default", "")

        if isinstance(last_name, dict):
            last_name = last_name.get("default", "")

        player_id = row.get("playerId")

        full_name = (
            row.get("goalieFullName")
            or row.get("playerName")
            or ""
        )

        if isinstance(full_name, dict):
            full_name = full_name.get("default", "")

        if not full_name:
            full_name = f"{first_name} {last_name}".strip()

        team_abbrev = (
            row.get("teamAbbrevs")
            or row.get("teamAbbrev")
            or ""
        )

        if isinstance(team_abbrev, list):
            team_abbrev = ", ".join(
                str(value)
                for value in team_abbrev
            )

        goalies.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": team_abbrev,
            "gamesPlayed": row.get("gamesPlayed"),
            "gamesStarted": row.get("gamesStarted"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "otLosses": row.get("otLosses"),
            "savePctg": row.get(
                "savePctg",
                row.get("savePct"),
            ),
            "gaa": row.get(
                "goalsAgainstAverage",
                row.get("gaa"),
            ),
            "shutouts": row.get("shutouts"),
            "saves": row.get("saves"),
            "shotsAgainst": row.get("shotsAgainst"),
        })

    return {
        "season": stats_season,
        "requestedSeason": target_season,
        "fallback": stats_season != target_season,
        "goalies": goalies,
    }


@app.get("/api/matchup/{game_id}")
async def matchup(game_id: str):
    """
    Возвращает личные встречи команд из landing NHL API.

    NHL может использовать один из двух форматов:
    - matchup
    - seasonSeries
    """

    url = f"{NHL_BASE}/gamecenter/{game_id}/landing"

    data = await fetch_with_cache(
        f"matchup:{game_id}",
        url,
        CACHE_TTL["matchup"],
    )

    if not isinstance(data, dict):
        return {
            "available": False,
            "gameId": game_id,
            "matchup": None,
            "seasonSeries": None,
        }

    if data.get("error"):
        return {
            "available": False,
            "gameId": game_id,
            "matchup": None,
            "seasonSeries": None,
            "error": data["error"],
        }

    matchup_data = data.get("matchup")
    season_series = data.get("seasonSeries")

    if matchup_data is None:
        summary = data.get("summary")

        if isinstance(summary, dict):
            matchup_data = summary.get("matchup")
            season_series = (
                season_series
                or summary.get("seasonSeries")
            )

    return {
        "available": bool(
            matchup_data is not None
            or season_series is not None
        ),
        "gameId": game_id,
        "matchup": matchup_data,
        "seasonSeries": season_series,
    }


@app.get("/api/game-video/{game_id}")
async def game_video(game_id: str):
    landing_url = (
        f"{NHL_BASE}/gamecenter/"
        f"{game_id}/landing"
    )

    landing = await fetch_with_cache(
        f"game-video-landing:{game_id}",
        landing_url,
        CACHE_TTL["score"],
    )

    if not isinstance(landing, dict) or landing.get("error"):
        return {
            "available": False,
            "error": (
                landing.get("error")
                if isinstance(landing, dict)
                else "NHL API error"
            ),
        }

    videos = []

    def add_video(kind: str, value: Any, title: str):
        if value is None or value == "":
            return

        if isinstance(value, dict):
            value = (
                value.get("url")
                or value.get("shareUrl")
                or value.get("videoUrl")
                or value.get("href")
            )

        if not isinstance(value, str):
            return

        value = value.strip()

        if value.startswith("/video/"):
            value = "https://www.nhl.com" + value
        elif value.startswith("http://"):
            value = "https://" + value[7:]
        elif not value.startswith("https://"):
            return

        videos.append({
            "kind": kind,
            "title": title,
            "url": value,
        })

    add_video(
        "recap",
        landing.get("threeMinRecap"),
        "3-Minute Recap",
    )

    add_video(
        "condensed",
        landing.get("condensedGame"),
        "Condensed Game",
    )

    summary = landing.get("summary") or {}

    if isinstance(summary, dict):
        add_video(
            "recap",
            summary.get("threeMinRecap"),
            "3-Minute Recap",
        )

        add_video(
            "condensed",
            summary.get("condensedGame"),
            "Condensed Game",
        )

    game_date = landing.get("gameDate")

    if isinstance(game_date, str) and game_date:
        score_url = f"{NHL_BASE}/score/{game_date}"

        score_data = await fetch_with_cache(
            f"score-date-for-video:{game_date}",
            score_url,
            CACHE_TTL["score"],
        )

        games = (
            score_data.get("games", [])
            if isinstance(score_data, dict)
            else []
        )

        for game in games:
            if str(game.get("id")) != str(game_id):
                continue

            add_video(
                "recap",
                game.get("threeMinRecap"),
                "3-Minute Recap",
            )

            add_video(
                "condensed",
                game.get("condensedGame"),
                "Condensed Game",
            )

            break

    unique = []
    seen = set()

    for video in videos:
        if video["url"] not in seen:
            seen.add(video["url"])
            unique.append(video)

    game_center = (
        landing.get("gameCenterLink")
        or f"https://www.nhl.com/gamecenter/{game_id}"
    )

    if (
        isinstance(game_center, str)
        and game_center.startswith("/")
    ):
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
    query = q.strip()

    if len(query) < 2:
        return []

    url = "https://search.d3.nhle.com/api/v1/search/player"
    cache_key = f"player-search:{query.lower()}"

    cached = _cache.get(cache_key)
    now = time.time()

    if cached and now - cached[0] < CACHE_TTL["player_search"]:
        return cached[1]

    async with httpx.AsyncClient(
        timeout=12,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(
                url,
                params={
                    "culture": "en-us",
                    "limit": 10,
                    "q": query,
                    "active": "true",
                },
                headers=DEFAULT_HEADERS,
            )

            if response.status_code == 200:
                data = response.json()
                _cache[cache_key] = (now, data)
                return data

            return {
                "error": (
                    f"NHL search status "
                    f"{response.status_code}"
                ),
            }

        except Exception as error:
            return {"error": str(error)}


@app.get("/api/team-schedule/{team}")
async def team_schedule(
    team: str,
    season: str | None = None,
):
    team_upper = team.upper()
    season_key = season or "now"

    url = (
        f"{NHL_BASE}/club-schedule-season/"
        f"{team_upper}/{season_key}"
    )

    return await fetch_with_cache(
        f"team-schedule:{team_upper}:{season_key}",
        url,
        CACHE_TTL["team_schedule"],
    )


@app.get("/api/player/{player_id}")
async def player(player_id: str):
    url = f"{NHL_BASE}/player/{player_id}/landing"

    return await fetch_with_cache(
        f"player:{player_id}",
        url,
        CACHE_TTL["player"],
    )


@app.get("/api/goalie/{player_id}")
async def goalie_player(
    player_id: str,
    season: str | None = None,
):
    now = time.localtime()

    current_start_year = (
        now.tm_year
        if now.tm_mon >= 9
        else now.tm_year - 1
    )

    current_season = (
        f"{current_start_year}"
        f"{current_start_year + 1}"
    )

    target_season = season or current_season

    async def load(season_id: str):
        params = {
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": (
                f"seasonId={season_id} "
                f"and gameTypeId=2 "
                f"and playerId={player_id}"
            ),
            "limit": 5,
        }

        url = (
            f"{NHL_STATS_BASE}/goalie/summary?"
            f"{httpx.QueryParams(params)}"
        )

        data = await fetch_with_cache(
            f"goalie-player:{player_id}:{season_id}",
            url,
            CACHE_TTL["player"],
        )

        rows = (
            data.get("data", [])
            if isinstance(data, dict)
            else []
        )

        return (
            rows[0]
            if isinstance(rows, list) and rows
            else None
        )

    row = await load(target_season)
    stats_season = target_season

    if row is None and target_season == current_season:
        previous_start_year = current_start_year - 1
        previous_season = (
            f"{previous_start_year}"
            f"{previous_start_year + 1}"
        )

        row = await load(previous_season)
        stats_season = previous_season

    if not isinstance(row, dict):
        return {
            "season": stats_season,
            "requestedSeason": target_season,
            "fallback": stats_season != target_season,
            "found": False,
        }

    return {
        "season": stats_season,
        "requestedSeason": target_season,
        "fallback": stats_season != target_season,
        "found": True,
        "stats": row,
    }


@app.get("/api/roster-stats/{team}")
async def roster_stats(
    team: str,
    season: str | None = None,
):
    team_upper = team.upper()

    try:
        if season:
            target_season = season
        else:
            now_url = f"{NHL_BASE}/club-stats/{team_upper}/now"

            base_data = await fetch_with_cache(
                f"roster-now:{team_upper}",
                now_url,
                CACHE_TTL["roster"],
            )

            if "error" in base_data:
                return base_data

            target_season = base_data.get(
                "season",
                20252026,
            )

        regular_url = (
            f"{NHL_BASE}/club-stats/"
            f"{team_upper}/{target_season}/2"
        )

        playoff_url = (
            f"{NHL_BASE}/club-stats/"
            f"{team_upper}/{target_season}/3"
        )

        regular_data = await fetch_with_cache(
            f"club-stats:{team_upper}:{target_season}:2",
            regular_url,
            CACHE_TTL["roster"],
        )

        playoff_data = await fetch_with_cache(
            f"club-stats:{team_upper}:{target_season}:3",
            playoff_url,
            CACHE_TTL["roster"],
        )

        return {
            "team": team_upper,
            "season": target_season,
            "regular": {
                "skaters": regular_data.get("skaters", []),
                "goalies": regular_data.get("goalies", []),
            },
            "playoff": {
                "skaters": playoff_data.get("skaters", []),
                "goalies": playoff_data.get("goalies", []),
            },
        }

    except Exception as error:
        return {"error": str(error)}


@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    return await fetch_with_cache(
        f"boxscore:{game_id}",
        f"{NHL_BASE}/gamecenter/{game_id}/boxscore",
        CACHE_TTL["boxscore"],
    )


@app.get("/api/right-rail/{game_id}")
async def right_rail(game_id: str):
    return await fetch_with_cache(
        f"rightrail:{game_id}",
        f"{NHL_BASE}/gamecenter/{game_id}/right-rail",
        CACHE_TTL["rightrail"],
    )


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    return await fetch_with_cache(
        f"score:{game_id}",
        f"{NHL_BASE}/gamecenter/{game_id}/landing",
        CACHE_TTL["score"],
    )


@app.post("/webhook")
async def telegram_webhook(update: dict):
    message = update.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🏒 ОТКРЫТЬ NHL",
                        "web_app": {
                            "url": WEBAPP_URL,
                        },
                    },
                ],
                [
                    {
                        "text": "📅 Матчи",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=schedule"
                            ),
                        },
                    },
                    {
                        "text": "📊 Таблица",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=standings"
                            ),
                        },
                    },
                ],
                [
                    {
                        "text": "🏆 Лидеры",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=leaders"
                            ),
                        },
                    },
                    {
                        "text": "🥅 Вратари",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=goalies"
                            ),
                        },
                    },
                ],
                [
                    {
                        "text": "👤 Игроки",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=players"
                            ),
                        },
                    },
                    {
                        "text": "🎥 Обзоры",
                        "web_app": {
                            "url": (
                                f"{WEBAPP_URL}"
                                "?section=videos"
                            ),
                        },
                    },
                ],
            ],
        }

        async with httpx.AsyncClient(timeout=12) as client:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "Привет! Добро пожаловать "
                        "в обновленный NHL Live.\n\n"
                        "Выбирай нужный раздел:"
                    ),
                    "reply_markup": keyboard,
                },
            )

    return {"ok": True}


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ROOT_INDEX = BASE_DIR / "index.html"
STATIC_INDEX = STATIC_DIR / "index.html"

if STATIC_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )


@app.get("/")
async def index():
    if STATIC_INDEX.is_file():
        return FileResponse(
            str(STATIC_INDEX),
            media_type="text/html",
        )

    if ROOT_INDEX.is_file():
        return FileResponse(
            str(ROOT_INDEX),
            media_type="text/html",
        )

    return {
        "detail": "index.html not found",
    }
