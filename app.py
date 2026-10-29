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
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"

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
    "pregame": 60 * 10,
    "espn": 60 * 15,
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
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

TEAM_NAME_TO_ABBREV = {
    "anaheim ducks": "ANA", "ducks": "ANA", "ana": "ANA",
    "boston bruins": "BOS", "bruins": "BOS", "bos": "BOS",
    "buffalo sabres": "BUF", "sabres": "BUF", "buf": "BUF",
    "calgary flames": "CGY", "flames": "CGY", "cgy": "CGY", "cal": "CGY",
    "carolina hurricanes": "CAR", "hurricanes": "CAR", "car": "CAR",
    "chicago blackhawks": "CHI", "blackhawks": "CHI", "chi": "CHI",
    "colorado avalanche": "COL", "avalanche": "COL", "col": "COL",
    "columbus blue jackets": "CBJ", "blue jackets": "CBJ", "cbj": "CBJ", "clb": "CBJ",
    "dallas stars": "DAL", "stars": "DAL", "dal": "DAL",
    "detroit red wings": "DET", "red wings": "DET", "det": "DET",
    "edmonton oilers": "EDM", "oilers": "EDM", "edm": "EDM",
    "florida panthers": "FLA", "panthers": "FLA", "fla": "FLA",
    "los angeles kings": "LAK", "kings": "LAK", "lak": "LAK", "la": "LAK",
    "minnesota wild": "MIN", "wild": "MIN", "min": "MIN",
    "montreal canadiens": "MTL", "canadiens": "MTL", "mtl": "MTL", "mon": "MTL", "montréal canadiens": "MTL",
    "nashville predators": "NSH", "predators": "NSH", "nsh": "NSH", "nas": "NSH",
    "new jersey devils": "NJD", "devils": "NJD", "njd": "NJD", "nj": "NJD",
    "new york islanders": "NYI", "islanders": "NYI", "nyi": "NYI",
    "new york rangers": "NYR", "rangers": "NYR", "nyr": "NYR",
    "ottawa senators": "OTT", "senators": "OTT", "ott": "OTT",
    "philadelphia flyers": "PHI", "flyers": "PHI", "phi": "PHI",
    "pittsburgh penguins": "PIT", "penguins": "PIT", "pit": "PIT",
    "san jose sharks": "SJS", "sharks": "SJS", "sjs": "SJS", "sj": "SJS",
    "seattle kraken": "SEA", "kraken": "SEA", "sea": "SEA",
    "st. louis blues": "STL", "st louis blues": "STL", "blues": "STL", "stl": "STL",
    "tampa bay lightning": "TBL", "lightning": "TBL", "tbl": "TBL", "tb": "TBL",
    "toronto maple leafs": "TOR", "maple leafs": "TOR", "tor": "TOR",
    "utah hockey club": "UTA", "utah": "UTA", "uta": "UTA", "utah mammoth": "UTA",
    "vancouver canucks": "VAN", "canucks": "VAN", "van": "VAN",
    "vegas golden knights": "VGK", "golden knights": "VGK", "vgk": "VGK",
    "washington capitals": "WSH", "capitals": "WSH", "wsh": "WSH", "was": "WSH",
    "winnipeg jets": "WPG", "jets": "WPG", "wpg": "WPG", "win": "WPG",
}

TEAM_ABBREV_ALIASES = {
    "TB": "TBL",
    "NJ": "NJD",
    "SJ": "SJS",
    "LA": "LAK",
    "WAS": "WSH",
    "MON": "MTL",
    "MTL": "MTL",
    "CLB": "CBJ",
    "NAS": "NSH",
    "WIN": "WPG",
    "CAL": "CGY",
}


def normalize_team_abbr(raw: Any) -> str:
    if not raw:
        return ""
    if isinstance(raw, dict):
        raw = raw.get("default") or raw.get("abbrev") or raw.get("triCode") or raw.get("rawTricode") or ""
    val_str = str(raw).strip()
    upper = val_str.upper()
    if upper in TEAM_ABBREV_ALIASES:
        return TEAM_ABBREV_ALIASES[upper]
    if upper in TEAM_NAME_TO_ABBREV.values():
        return upper
    clean_key = val_str.lower().replace("é", "e")
    return TEAM_NAME_TO_ABBREV.get(clean_key, TEAM_NAME_TO_ABBREV.get(val_str.lower(), upper))


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
        timeout=14,
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
                "error": f"API status {response.status_code}"
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

        abbreviation = normalize_team_abbr(row.get("teamAbbrev"))
        if not abbreviation:
            continue

        standings_map[abbreviation] = {
            "wins": row.get("wins", 0),
            "losses": row.get("losses", 0),
            "otLosses": row.get("otLosses", 0),
            "points": row.get("points", 0),
        }

    game_week = schedule_data.get("gameWeek", [])
    if isinstance(game_week, list):
        for day in game_week:
            if not isinstance(day, dict):
                continue

            for game in day.get("games", []):
                if not isinstance(game, dict):
                    continue

                for side in ("awayTeam", "homeTeam"):
                    team = game.get(side) or {}
                    if not isinstance(team, dict):
                        continue

                    abbrev = normalize_team_abbr(team.get("abbrev") or team.get("teamAbbrev"))
                    if abbrev and abbrev in standings_map:
                        team["currentRecord"] = standings_map[abbrev]

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


@app.get("/api/team-special-teams")
async def team_special_teams(season: str | None = None):
    now = time.localtime()
    current_start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    current_season = f"{current_start_year}{current_start_year + 1}"
    target_season = season or current_season

    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 50,
        "sort": '[{"property":"powerPlayPct","direction":"DESC"}]',
    }

    url = f"{NHL_STATS_BASE}/team/summary?{httpx.QueryParams(params)}"
    data = await fetch_with_cache(f"team-special-teams:{target_season}", url, CACHE_TTL["standings"])

    rows = data.get("data", []) if isinstance(data, dict) else []

    teams = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_abbr = row.get("teamAbbrev") or row.get("teamAbbrevs") or row.get("rawTricode") or row.get("triCode")
        full_name = row.get("teamFullName") or row.get("fullName") or ""
        team_abbr = normalize_team_abbr(raw_abbr) or normalize_team_abbr(full_name)

        if not team_abbr:
            continue

        teams.append({
            "teamAbbrev": team_abbr,
            "teamName": full_name,
            "powerPlayPctg": row.get("powerPlayPct"),
            "penaltyKillPctg": row.get("penaltyKillPct"),
        })

    return {
        "season": target_season,
        "teams": teams,
    }


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


@app.get("/api/skater-leaders-ext")
async def skater_leaders_ext(
    season: str | None = None,
    category: str = "points",
    limit: int = 50,
):
    now = time.localtime()
    current_start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    current_season = f"{current_start_year}{current_start_year + 1}"
    target_season = season or current_season
    safe_limit = max(1, min(limit, 100))

    summary_params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 150,
        "sort": '[{"property":"points","direction":"DESC"}]',
    }

    realtime_params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 150,
        "sort": '[{"property":"hits","direction":"DESC"}]',
    }

    url_summary = f"{NHL_STATS_BASE}/skater/summary?{httpx.QueryParams(summary_params)}"
    url_realtime = f"{NHL_STATS_BASE}/skater/realtime?{httpx.QueryParams(realtime_params)}"

    summary_data, realtime_data = await asyncio.gather(
        fetch_with_cache(f"skater-summary:{target_season}", url_summary, CACHE_TTL["leaders"]),
        fetch_with_cache(f"skater-realtime:{target_season}", url_realtime, CACHE_TTL["leaders"]),
    )

    rows_summary = summary_data.get("data", []) if isinstance(summary_data, dict) else []
    rows_realtime = realtime_data.get("data", []) if isinstance(realtime_data, dict) else []

    realtime_map = {r.get("playerId"): r for r in rows_realtime if isinstance(r, dict) and r.get("playerId")}

    skaters = []
    for row in rows_summary:
        if not isinstance(row, dict):
            continue

        player_id = row.get("playerId")
        first_name = row.get("firstName", "")
        last_name = row.get("lastName", "")
        if isinstance(first_name, dict):
            first_name = first_name.get("default", "")
        if isinstance(last_name, dict):
            last_name = last_name.get("default", "")

        full_name = row.get("skaterFullName") or row.get("playerName") or f"{first_name} {last_name}".strip()
        team_abbr = normalize_team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev") or "")

        rt = realtime_map.get(player_id, {})

        games_played = row.get("gamesPlayed", 0)
        total_toi_sec = row.get("timeOnIce", 0)
        toi_pg_sec = row.get("timeOnIcePerGame", (total_toi_sec / games_played if games_played else 0))

        toi_str = "0:00"
        if isinstance(toi_pg_sec, (int, float)):
            mins = int(toi_pg_sec // 60)
            secs = int(toi_pg_sec % 60)
            toi_str = f"{mins}:{secs:02d}"
        elif isinstance(toi_pg_sec, str):
            toi_str = toi_pg_sec

        toi_minutes = round(total_toi_sec / 60) if isinstance(total_toi_sec, (int, float)) else 0

        goals = row.get("goals", 0)
        assists = row.get("assists", 0)
        points = row.get("points", 0)
        plus_minus = row.get("plusMinus", 0)
        shots = row.get("shots", row.get("sog", 0))
        hits = rt.get("hits", row.get("hits", 0))
        blocks = rt.get("blockedShots", row.get("blockedShots", row.get("blocks", 0)))

        skaters.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": team_abbr,
            "headshot": f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png",
            "gamesPlayed": games_played,
            "goals": goals,
            "assists": assists,
            "points": points,
            "plusMinus": plus_minus,
            "penaltyMinutes": row.get("penaltyMinutes", row.get("pim", 0)),
            "shots": shots,
            "hits": hits,
            "blockedShots": blocks,
            "timeOnIce": toi_minutes,
            "timeOnIceSeconds": total_toi_sec,
            "toiPerGame": toi_str,
            "toiPerGameSeconds": toi_pg_sec,
        })

    # Сортировка по запрашиваемой категории
    if category == "goals":
        skaters.sort(key=lambda x: x.get("goals", 0), reverse=True)
    elif category == "assists":
        skaters.sort(key=lambda x: x.get("assists", 0), reverse=True)
    elif category == "plusMinus":
        skaters.sort(key=lambda x: x.get("plusMinus", 0), reverse=True)
    elif category in ("shots", "sog"):
        skaters.sort(key=lambda x: x.get("shots", 0), reverse=True)
    elif category in ("hits", "hit"):
        skaters.sort(key=lambda x: x.get("hits", 0), reverse=True)
    elif category in ("blockedShots", "blk"):
        skaters.sort(key=lambda x: x.get("blockedShots", 0), reverse=True)
    elif category in ("timeOnIce", "toi"):
        skaters.sort(key=lambda x: x.get("timeOnIceSeconds", 0), reverse=True)
    elif category in ("toiPerGame", "atoi"):
        skaters.sort(key=lambda x: x.get("toiPerGameSeconds", 0), reverse=True)
    else:
        skaters.sort(key=lambda x: x.get("points", 0), reverse=True)

    result_slice = skaters[:safe_limit]

    # Проставляем value для удобного отображения в интерфейсе
    for p in result_slice:
        if category == "goals":
            p["value"] = p["goals"]
        elif category == "assists":
            p["value"] = p["assists"]
        elif category == "plusMinus":
            p["value"] = p["plusMinus"]
        elif category in ("shots", "sog"):
            p["value"] = p["shots"]
        elif category in ("hits", "hit"):
            p["value"] = p["hits"]
        elif category in ("blockedShots", "blk"):
            p["value"] = p["blockedShots"]
        elif category in ("timeOnIce", "toi"):
            p["value"] = p["timeOnIce"]
        elif category in ("toiPerGame", "atoi"):
            p["value"] = p["toiPerGame"]
        else:
            p["value"] = p["points"]

    return {
        "season": target_season,
        "category": category,
        category: result_slice,
        "skaters": result_slice,
    }


EXTENDED_SKATER_CATEGORIES = {
    "shots", "sog", "hits", "hit", "blockedShots", "blk", "timeOnIce", "toi", "toiPerGame", "atoi"
}


@app.get("/api/leaders/{category}")
async def leaders(
    category: str,
    limit: int = 25,
    season: str | None = None,
):
    if category in EXTENDED_SKATER_CATEGORIES:
        return await skater_leaders_ext(season=season, category=category, limit=limit)

    allowed = {"points", "goals", "assists", "plusMinus"}
    cat = category if category in allowed else "points"
    limit = max(1, min(limit, 50))

    if season:
        url = (
            f"{NHL_BASE}/skater-stats-leaders/"
            f"{season}/2"
            f"?categories={cat}"
            f"&limit={limit}"
        )
        cache_key = f"leaders:{cat}:{limit}:{season}"
    else:
        url = (
            f"{NHL_BASE}/skater-stats-leaders/"
            f"current?categories={cat}"
            f"&limit={limit}"
        )
        cache_key = f"leaders:{cat}:{limit}"

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

    current_season = f"{current_start_year}{current_start_year + 1}"
    target_season = season or current_season

    async def load_season(season_id: str):
        params = {
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": f"seasonId={season_id} and gameTypeId=2",
            "start": 0,
            "limit": limit,
            "sort": '[{"property":"gamesPlayed","direction":"DESC"}]',
        }

        url = f"{NHL_STATS_BASE}/goalie/summary?{httpx.QueryParams(params)}"

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
        return (rows if isinstance(rows, list) else []), None

    rows, api_error = await load_season(target_season)
    stats_season = target_season

    if not rows and target_season == current_season:
        previous_start_year = current_start_year - 1
        previous_season = f"{previous_start_year}{previous_start_year + 1}"
        rows, previous_error = await load_season(previous_season)
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
            "error": api_error.get("error", "Ошибка NHL Stats API"),
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
        full_name = row.get("goalieFullName") or row.get("playerName") or ""
        if isinstance(full_name, dict):
            full_name = full_name.get("default", "")
        if not full_name:
            full_name = f"{first_name} {last_name}".strip()

        team_abbrev = row.get("teamAbbrevs") or row.get("teamAbbrev") or ""
        if isinstance(team_abbrev, list):
            team_abbrev = ", ".join(str(value) for value in team_abbrev)
        team_abbrev = normalize_team_abbr(team_abbrev)

        # Перевод в минуты
        time_on_ice = row.get("timeOnIce", 0)
        time_in_min = round(time_on_ice / 60) if isinstance(time_on_ice, (int, float)) else 0

        goalies.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": team_abbrev,
            "headshot": f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png",
            "gamesPlayed": row.get("gamesPlayed", 0),
            "gamesStarted": row.get("gamesStarted", 0),
            "wins": row.get("wins", 0),
            "losses": row.get("losses", 0),
            "otLosses": row.get("otLosses", 0),
            "savePctg": row.get("savePctg", row.get("savePct", 0)),
            "gaa": row.get("goalsAgainstAverage", row.get("gaa", 0)),
            "shutouts": row.get("shutouts", 0),
            "saves": row.get("saves", 0),
            "shotsAgainst": row.get("shotsAgainst", row.get("shots", 0)),
            "timeOnIce": time_in_min,
        })

    return {
        "season": stats_season,
        "requestedSeason": target_season,
        "fallback": stats_season != target_season,
        "goalies": goalies,
    }


@app.get("/api/matchup/{game_id}")
async def matchup(game_id: str):
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
            season_series = season_series or summary.get("seasonSeries")

    return {
        "available": bool(matchup_data is not None or season_series is not None),
        "gameId": game_id,
        "matchup": matchup_data,
        "seasonSeries": season_series,
    }


@app.get("/api/team-schedule/{team}")
async def team_schedule(
    team: str,
    season: str | None = None,
):
    team_upper = normalize_team_abbr(team)
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
    return await fetch_with_cache(
        f"player:{player_id}",
        url,
        CACHE_TTL["player"],
    )


@app.get("/api/roster-stats/{team}")
async def roster_stats(
    team: str,
    season: str | None = None,
):
    team_upper = normalize_team_abbr(team)

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

            target_season = base_data.get("season", 20252026)

        regular_url = f"{NHL_BASE}/club-stats/{team_upper}/{target_season}/2"
        playoff_url = f"{NHL_BASE}/club-stats/{team_upper}/{target_season}/3"

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
                "skaters": regular_data.get("skaters", []) if isinstance(regular_data, dict) else [],
                "goalies": regular_data.get("goalies", []) if isinstance(regular_data, dict) else [],
            },
            "playoff": {
                "skaters": playoff_data.get("skaters", []) if isinstance(playoff_data, dict) else [],
                "goalies": playoff_data.get("goalies", []) if isinstance(playoff_data, dict) else [],
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


async def fetch_espn_injuries() -> dict[str, list[dict]]:
    url = f"{ESPN_BASE}/injuries"
    data = await fetch_with_cache("espn:injuries", url, CACHE_TTL["espn"])

    if not isinstance(data, dict):
        return {}

    teams_data = data.get("injuries", [])
    result: dict[str, list[dict]] = {}

    if not isinstance(teams_data, list):
        return {}

    for item in teams_data:
        if not isinstance(item, dict):
            continue

        raw_name = (
            item.get("displayName")
            or item.get("name")
            or item.get("abbreviation")
            or ""
        )
        team_abbr = normalize_team_abbr(raw_name)
        injuries_list = item.get("injuries", [])

        if not isinstance(injuries_list, list):
            continue

        team_injuries = []
        for inj in injuries_list:
            if not isinstance(inj, dict):
                continue

            athlete = inj.get("athlete", {}) or {}
            pos = athlete.get("position", {})
            pos_code = pos.get("abbreviation") if isinstance(pos, dict) else str(pos or "")

            details = inj.get("details", {})
            detail_desc = (
                details.get("type")
                or details.get("detail")
                or inj.get("type")
                or inj.get("shortComment")
                or ""
            )

            status = inj.get("status") or "Injured"
            headshot = ""
            hs = athlete.get("headshot")
            if isinstance(hs, dict):
                headshot = hs.get("href", "")
            elif isinstance(hs, str):
                headshot = hs

            team_injuries.append({
                "id": athlete.get("id"),
                "name": athlete.get("displayName") or athlete.get("name") or "Игрок",
                "position": pos_code,
                "status": status,
                "details": detail_desc,
                "headshot": headshot,
            })

        if team_abbr and team_injuries:
            result[team_abbr] = team_injuries

    return result


async def fetch_espn_scoreboard(date_str: str | None = None) -> list[dict]:
    params = ""
    if date_str:
        clean = date_str.replace("-", "")
        params = f"?dates={clean}"

    url = f"{ESPN_BASE}/scoreboard{params}"
    cache_key = f"espn:scoreboard:{date_str or 'today'}"
    data = await fetch_with_cache(cache_key, url, CACHE_TTL["espn"])

    if not isinstance(data, dict):
        return []
    return data.get("events", []) if isinstance(data.get("events"), list) else []


def extract_probable_goalies(
    events: list[dict],
    away_abbr: str,
    home_abbr: str,
) -> dict[str, dict | None]:
    away_norm = normalize_team_abbr(away_abbr)
    home_norm = normalize_team_abbr(home_abbr)
    res: dict[str, dict | None] = {"away": None, "home": None}

    for event in events:
        if not isinstance(event, dict):
            continue

        competitions = event.get("competitions", [])
        if not isinstance(competitions, list):
            continue

        for comp in competitions:
            if not isinstance(comp, dict):
                continue

            competitors = comp.get("competitors", [])
            if not isinstance(competitors, list):
                continue

            matched_teams: dict[str, dict] = {}
            for c in competitors:
                if not isinstance(c, dict):
                    continue
                team_obj = c.get("team", {})
                raw_abbr = team_obj.get("abbreviation") or team_obj.get("displayName") or ""
                norm = normalize_team_abbr(raw_abbr)
                matched_teams[norm] = c

            if away_norm in matched_teams and home_norm in matched_teams:
                for side, norm_code in [("away", away_norm), ("home", home_norm)]:
                    c = matched_teams[norm_code]
                    probables = c.get("probables") or c.get("probableStartingGoalie") or []
                    if isinstance(probables, dict):
                        probables = [probables]

                    if isinstance(probables, list) and probables:
                        item = probables[0]
                        if isinstance(item, dict):
                            athlete = item.get("athlete", {}) or {}
                            if not athlete and "displayName" in item:
                                athlete = item

                            status = item.get("status", {})
                            status_str = (
                                status.get("name")
                                if isinstance(status, dict)
                                else str(status or "")
                            )

                            confirmed = (
                                status_str.lower() == "confirmed"
                                or item.get("confirmed") is True
                            )

                            hs = athlete.get("headshot")
                            headshot = hs.get("href") if isinstance(hs, dict) else (hs or "")

                            res[side] = {
                                "name": athlete.get("displayName") or athlete.get("name") or "Не объявлен",
                                "jersey": athlete.get("jersey") or "",
                                "confirmed": confirmed,
                                "status": "Подтвержден" if confirmed else ("Вероятен" if status_str else "Ожидается"),
                                "statusRaw": status_str,
                                "headshot": headshot,
                            }
                return res

    return res


def extract_top_scorers(skaters: list[dict], limit: int = 3) -> list[dict]:
    valid = [s for s in skaters if isinstance(s, dict)]
    sorted_skaters = sorted(
        valid,
        key=lambda x: (
            int(x.get("points") or 0),
            int(x.get("goals") or 0),
            int(x.get("assists") or 0),
        ),
        reverse=True,
    )

    result = []
    for s in sorted_skaters[:limit]:
        first = s.get("firstName", "")
        last = s.get("lastName", "")
        if isinstance(first, dict):
            first = first.get("default", "")
        if isinstance(last, dict):
            last = last.get("default", "")

        name = f"{first} {last}".strip() or s.get("name") or "Игрок"
        result.append({
            "id": s.get("playerId") or s.get("id"),
            "name": name,
            "firstName": first,
            "lastName": last,
            "position": s.get("positionCode") or s.get("position") or "",
            "gamesPlayed": s.get("gamesPlayed", 0),
            "goals": s.get("goals", 0),
            "assists": s.get("assists", 0),
            "points": s.get("points", 0),
            "plusMinus": s.get("plusMinus", 0),
            "penaltyMinutes": s.get("penaltyMinutes", s.get("pim", 0)),
            "headshot": s.get("headshot", ""),
        })

    return result


def extract_club_goalies(goalies: list[dict]) -> list[dict]:
    valid = [g for g in goalies if isinstance(g, dict)]
    sorted_goalies = sorted(
        valid,
        key=lambda x: int(x.get("gamesPlayed") or 0),
        reverse=True,
    )

    result = []
    for g in sorted_goalies:
        first = g.get("firstName", "")
        last = g.get("lastName", "")
        if isinstance(first, dict):
            first = first.get("default", "")
        if isinstance(last, dict):
            last = last.get("default", "")

        name = f"{first} {last}".strip() or g.get("name") or "Вратарь"

        # Приводим timeOnIce к целым минутам
        time_on_ice = g.get("timeOnIce", 0)
        toi_mins = 0
        if isinstance(time_on_ice, (int, float)):
            toi_mins = round(time_on_ice / 60) if time_on_ice > 3000 else round(time_on_ice)
        elif isinstance(time_on_ice, str):
            try:
                val_num = float(time_on_ice)
                toi_mins = round(val_num / 60) if val_num > 3000 else round(val_num)
            except ValueError:
                toi_mins = 0

        shots = g.get("shotsAgainst", 0)
        ga = g.get("goalsAgainst", 0)
        saves = g.get("saves", (shots - ga if shots and ga is not None else 0))

        result.append({
            "id": g.get("playerId") or g.get("id"),
            "name": name,
            "firstName": first,
            "lastName": last,
            "gamesPlayed": g.get("gamesPlayed", 0),
            "gamesStarted": g.get("gamesStarted", 0),
            "wins": g.get("wins", 0),
            "losses": g.get("losses", 0),
            "otLosses": g.get("otLosses", 0),
            "savePctg": g.get("savePctg", g.get("savePercentage")),
            "gaa": g.get("goalsAgainstAverage", g.get("gaa")),
            "shutouts": g.get("shutouts", 0),
            "saves": saves,
            "shotsAgainst": shots,
            "timeOnIce": toi_mins,
            "headshot": g.get("headshot", ""),
        })

    return result


@app.get("/api/injuries")
async def get_injuries():
    return await fetch_espn_injuries()


@app.get("/api/scoreboard-espn")
async def get_scoreboard_espn(date: str | None = None):
    return await fetch_espn_scoreboard(date)


@app.get("/api/pregame/{game_id}")
async def pregame(
    game_id: str,
    date: str | None = None,
    away: str | None = None,
    home: str | None = None,
):
    now = time.localtime()
    current_start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    current_season_id = f"{current_start_year}{current_start_year + 1}"

    rail_task = fetch_with_cache(
        f"rightrail:{game_id}",
        f"{NHL_BASE}/gamecenter/{game_id}/right-rail",
        CACHE_TTL["rightrail"],
    )
    landing_task = fetch_with_cache(
        f"landing:{game_id}",
        f"{NHL_BASE}/gamecenter/{game_id}/landing",
        CACHE_TTL["score"],
    )
    standings_task = fetch_with_cache(
        "standings",
        f"{NHL_BASE}/standings/now",
        CACHE_TTL["standings"],
    )
    injuries_task = fetch_espn_injuries()

    team_summa
