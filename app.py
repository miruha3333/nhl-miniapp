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
    "utah hockey club": "UTA", "utah": "UTA", "uta": "UTA",
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
async def skater_leaders_ext(season: str | None = None):
    now = time.localtime()
    current_start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    current_season = f"{current_start_year}{current_start_year + 1}"
    target_season = season or current_season

    summary_params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 100,
        "sort": '[{"property":"points","direction":"DESC"}]',
    }

    realtime_params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 100,
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

        time_on_ice = row.get("timeOnIcePerGame", row.get("timeOnIce", 0))
        toi_str = "0:00"
        if isinstance(time_on_ice, (int, float)):
            mins = int(time_on_ice // 60)
            secs = int(time_on_ice % 60)
            toi_str = f"{mins}:{secs:02d}"
        elif isinstance(time_on_ice, str):
            toi_str = time_on_ice

        skaters.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": team_abbr,
            "headshot": f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png",
            "gamesPlayed": row.get("gamesPlayed", 0),
            "goals": row.get("goals", 0),
            "assists": row.get("assists", 0),
            "points": row.get("points", 0),
            "plusMinus": row.get("plusMinus", 0),
            "penaltyMinutes": row.get("penaltyMinutes", row.get("pim", 0)),
            "shots": row.get("shots", row.get("sog", 0)),
            "hits": rt.get("hits", row.get("hits", 0)),
            "blockedShots": rt.get("blockedShots", row.get("blockedShots", row.get("blocks", 0))),
            "toiPerGame": toi_str,
        })

    return {
        "season": target_season,
        "skaters": skaters,
    }


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
        result.append({
            "id": g.get("playerId") or g.get("id"),
            "name": name,
            "gamesPlayed": g.get("gamesPlayed", 0),
            "gamesStarted": g.get("gamesStarted", 0),
            "wins": g.get("wins", 0),
            "losses": g.get("losses", 0),
            "otLosses": g.get("otLosses", 0),
            "savePctg": g.get("savePctg", g.get("savePercentage")),
            "gaa": g.get("goalsAgainstAverage", g.get("gaa")),
            "shutouts": g.get("shutouts", 0),
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

    rail_data, landing_data, standings_data, injuries_data = await asyncio.gather(
        rail_task,
        landing_task,
        standings_task,
        injuries_task,
        return_exceptions=True,
    )

    rail_data = rail_data if isinstance(rail_data, dict) else {}
    landing_data = landing_data if isinstance(landing_data, dict) else {}
    standings_data = standings_data if isinstance(standings_data, dict) else {}
    injuries_data = injuries_data if isinstance(injuries_data, dict) else {}

    away_team_obj = landing_data.get("awayTeam") or {}
    home_team_obj = landing_data.get("homeTeam") or {}

    away_abbr = normalize_team_abbr(
        away
        or away_team_obj.get("abbrev")
        or away_team_obj.get("teamAbbrev")
    )
    home_abbr = normalize_team_abbr(
        home
        or home_team_obj.get("abbrev")
        or home_team_obj.get("teamAbbrev")
    )

    game_date = date or landing_data.get("gameDate") or ""
    espn_events = await fetch_espn_scoreboard(game_date)
    probable_goalies = extract_probable_goalies(espn_events, away_abbr, home_abbr)

    roster_tasks = []
    if away_abbr:
        roster_tasks.append(roster_stats(away_abbr))
    else:
        roster_tasks.append(asyncio.sleep(0, result={}))

    if home_abbr:
        roster_tasks.append(roster_stats(home_abbr))
    else:
        roster_tasks.append(asyncio.sleep(0, result={}))

    away_roster, home_roster = await asyncio.gather(*roster_tasks)
    away_roster = away_roster if isinstance(away_roster, dict) else {}
    home_roster = home_roster if isinstance(home_roster, dict) else {}

    standings_rows = standings_data.get("standings", []) if isinstance(standings_data, dict) else []
    standings_map = {}
    for row in standings_rows:
        if isinstance(row, dict):
            abbr = normalize_team_abbr(row.get("teamAbbrev"))
            if abbr:
                standings_map[abbr] = row

    away_st = standings_map.get(away_abbr, {})
    home_st = standings_map.get(home_abbr, {})

    pregame_stats = []
    rail_pre = rail_data.get("preGameStats") or rail_data.get("teamGameStats") or []

    if isinstance(rail_pre, list) and rail_pre:
        pregame_stats = rail_pre
    else:
        def make_comp(cat, label, away_val, home_val, higher_is_better=True):
            return {
                "category": cat,
                "label": label,
                "awayValue": away_val,
                "homeValue": home_val,
                "higherIsBetter": higher_is_better,
            }

        away_gp = away_st.get("gamesPlayed") or 1
        home_gp = home_st.get("gamesPlayed") or 1

        away_gf_pg = round((away_st.get("goalFor", 0) / away_gp), 2) if away_gp else 0
        home_gf_pg = round((home_st.get("goalFor", 0) / home_gp), 2) if home_gp else 0

        away_ga_pg = round((away_st.get("goalAgainst", 0) / away_gp), 2) if away_gp else 0
        home_ga_pg = round((home_st.get("goalAgainst", 0) / home_gp), 2) if home_gp else 0

        pregame_stats = [
            make_comp("powerPlayPctg", "Большинство (%PP)", away_st.get("powerPlayPctg"), home_st.get("powerPlayPctg"), True),
            make_comp("penaltyKillPctg", "Меньшинство (%PK)", away_st.get("penaltyKillPctg"), home_st.get("penaltyKillPctg"), True),
            make_comp("goalsForPerGame", "Заброшено за игру (GF/G)", away_gf_pg, home_gf_pg, True),
            make_comp("goalsAgainstPerGame", "Пропущено за игру (GA/G)", away_ga_pg, home_ga_pg, False),
        ]

    away_streak_code = away_st.get("streakCode") or ""
    away_streak_count = away_st.get("streakCount") or 0
    home_streak_code = home_st.get("streakCode") or ""
    home_streak_count = home_st.get("streakCount") or 0

    rail_streaks = rail_data.get("streaks") or {}
    if isinstance(rail_streaks, dict):
        if "awayTeam" in rail_streaks:
            away_streak_code = rail_streaks["awayTeam"].get("type") or away_streak_code
            away_streak_count = rail_streaks["awayTeam"].get("count") or away_streak_count
        if "homeTeam" in rail_streaks:
            home_streak_code = rail_streaks["homeTeam"].get("type") or home_streak_code
            home_streak_count = rail_streaks["homeTeam"].get("count") or home_streak_count

    season_series = rail_data.get("seasonSeries") or landing_data.get("seasonSeries") or []
    if isinstance(season_series, dict):
        season_series = season_series.get("games") or [season_series]

    away_skaters = away_roster.get("regular", {}).get("skaters", [])
    home_skaters = home_roster.get("regular", {}).get("skaters", [])
    away_goalies = away_roster.get("regular", {}).get("goalies", [])
    home_goalies = home_roster.get("regular", {}).get("goalies", [])

    return {
        "gameId": game_id,
        "gameDate": game_date,
        "startTimeUTC": landing_data.get("startTimeUTC"),
        "awayTeam": {
            "abbrev": away_abbr,
            "name": away_team_obj.get("name") or away_team_obj.get("placeName", {}).get("default") or away_abbr,
            "logo": away_team_obj.get("logo") or f"https://assets.nhle.com/mugs/nhl/default-team/{away_abbr}.png",
            "record": {
                "wins": away_st.get("wins", 0),
                "losses": away_st.get("losses", 0),
                "otLosses": away_st.get("otLosses", 0),
                "points": away_st.get("points", 0),
                "gamesPlayed": away_st.get("gamesPlayed", 0),
            },
            "homeRecord": f"{away_st.get('homeWins', 0)}-{away_st.get('homeLosses', 0)}-{away_st.get('homeOtLosses', 0)}",
            "roadRecord": f"{away_st.get('roadWins', 0)}-{away_st.get('roadLosses', 0)}-{away_st.get('roadOtLosses', 0)}",
            "l10Record": f"{away_st.get('l10Wins', 0)}-{away_st.get('l10Losses', 0)}-{away_st.get('l10OtLosses', 0)}",
            "streak": f"{away_streak_code}{away_streak_count}" if away_streak_code else "—",
            "streakCode": away_streak_code,
            "streakCount": away_streak_count,
        },
        "homeTeam": {
            "abbrev": home_abbr,
            "name": home_team_obj.get("name") or home_team_obj.get("placeName", {}).get("default") or home_abbr,
            "logo": home_team_obj.get("logo") or f"https://assets.nhle.com/mugs/nhl/default-team/{home_abbr}.png",
            "record": {
                "wins": home_st.get("wins", 0),
                "losses": home_st.get("losses", 0),
                "otLosses": home_st.get("otLosses", 0),
                "points": home_st.get("points", 0),
                "gamesPlayed": home_st.get("gamesPlayed", 0),
            },
            "homeRecord": f"{home_st.get('homeWins', 0)}-{home_st.get('homeLosses', 0)}-{home_st.get('homeOtLosses', 0)}",
            "roadRecord": f"{home_st.get('roadWins', 0)}-{home_st.get('roadLosses', 0)}-{home_st.get('roadOtLosses', 0)}",
            "l10Record": f"{home_st.get('l10Wins', 0)}-{home_st.get('l10Losses', 0)}-{home_st.get('l10OtLosses', 0)}",
            "streak": f"{home_streak_code}{home_streak_count}" if home_streak_code else "—",
            "streakCode": home_streak_code,
            "streakCount": home_streak_count,
        },
        "preGameStats": pregame_stats,
        "probableGoalies": probable_goalies,
        "injuries": {
            "away": injuries_data.get(away_abbr, []),
            "home": injuries_data.get(home_abbr, []),
        },
        "topScorers": {
            "away": extract_top_scorers(away_skaters, limit=3),
            "home": extract_top_scorers(home_skaters, limit=3),
        },
        "clubGoalies": {
            "away": extract_club_goalies(away_goalies),
            "home": extract_club_goalies(home_goalies),
        },
        "seasonSeries": season_series,
    }


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
                [{"text": "🏒 ОТКРЫТЬ NHL", "web_app": {"url": WEBAPP_URL}}],
                [
                    {"text": "📅 Матчи", "web_app": {"url": f"{WEBAPP_URL}?section=schedule"}},
                    {"text": "📊 Таблица", "web_app": {"url": f"{WEBAPP_URL}?section=standings"}},
                ],
                [
                    {"text": "🏆 Лидеры", "web_app": {"url": f"{WEBAPP_URL}?section=leaders"}},
                    {"text": "🥅 Вратари", "web_app": {"url": f"{WEBAPP_URL}?section=goalies"}},
                ],
            ],
        }

        async with httpx.AsyncClient(timeout=12) as client:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "Добро пожаловать в NHL Live! Выберите раздел:",
                    "reply_markup": keyboard,
                },
            )

    return {"ok": True}


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ROOT_INDEX = BASE_DIR / "index.html"
STATIC_INDEX = STATIC_DIR / "index.html"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    if STATIC_INDEX.is_file():
        return FileResponse(str(STATIC_INDEX), media_type="text/html")
    if ROOT_INDEX.is_file():
        return FileResponse(str(ROOT_INDEX), media_type="text/html")
    return {"detail": "index.html not found"}
