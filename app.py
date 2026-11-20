import asyncio
import json as py_json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles


NHL_BASE = "https://api-web.nhle.com/v1"
NHL_STATS_BASE = "https://api.nhle.com/stats/rest/en"
NHL_SEARCH_BASE = "https://search.d3.nhle.com/api/v1"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://nhl-miniapp-1.onrender.com").rstrip("/")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CACHE_TTL = {
    "schedule": 60,
    "standings": 600,
    "leaders": 1800,
    "score": 15,
    "pbp": 20,
    "roster": 3600,
    "player": 3600,
    "boxscore": 20,
    "rightrail": 20,
    "matchup": 1800,
    "player_search": 600,
    "team_schedule": 600,
    "pregame": 300,
    "espn": 900,
    "video": 1800,
    "transactions": 900,
    "advanced": 1800,
    "edge": 3600,
    "news": 600,
}

MAX_CACHE_ENTRIES = 1200
_cache: dict[str, tuple[float, float, Any]] = {}
_votes_store: dict[str, dict[str, int]] = {}
_http_client: httpx.AsyncClient | None = None

NEWS_FILE = Path(__file__).resolve().parent / "news.json"


def load_saved_news() -> list[dict]:
    if NEWS_FILE.is_file():
        try:
            with open(NEWS_FILE, "r", encoding="utf-8") as f:
                return py_json.load(f)
        except Exception:
            return []
    return []


def save_news_to_disk(news_list: list[dict]):
    try:
        with open(NEWS_FILE, "w", encoding="utf-8") as f:
            py_json.dump(news_list[:30], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_news_store: list[dict] = load_saved_news()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=14,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=15),
    )
    try:
        yield
    finally:
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None


app = FastAPI(title="NHL Mini App", lifespan=lifespan)

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
    ),
    "Accept": "application/json",
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

TEAM_ID_FALLBACK = {
    "NJD": 1, "NYI": 2, "NYR": 3, "PHI": 4, "PIT": 5, "BOS": 6, "BUF": 7, "MTL": 8,
    "OTT": 9, "TOR": 10, "CAR": 12, "FLA": 13, "TBL": 14, "WSH": 15, "CHI": 16, "DET": 17,
    "NSH": 18, "STL": 19, "CGY": 20, "COL": 21, "EDM": 22, "VAN": 23, "ANA": 24, "DAL": 25,
    "LAK": 26, "SJS": 28, "CBJ": 29, "MIN": 30, "WPG": 52, "VGK": 54, "SEA": 55, "UTA": 59,
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


def normalize_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("default") or "")
    return str(value or "")


def _prune_cache(now: float):
    expired = [k for k, (ts, ttl, _) in _cache.items() if now - ts >= ttl]
    for k in expired:
        _cache.pop(k, None)
    if len(_cache) >= MAX_CACHE_ENTRIES:
        oldest = sorted(_cache.items(), key=lambda item: item[1][0])[: len(_cache) - MAX_CACHE_ENTRIES + 100]
        for k, _ in oldest:
            _cache.pop(k, None)


def get_client() -> httpx.AsyncClient:
    if _http_client is not None:
        return _http_client
    return httpx.AsyncClient(timeout=14, follow_redirects=True)


async def fetch_with_cache(
    cache_key: str,
    url: str,
    ttl: int,
    params: dict[str, Any] | None = None,
    should_cache: Callable[[Any], bool] | None = None,
) -> Any:
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < cached[1]:
        return cached[2]

    client = get_client()
    close_after = _http_client is None
    try:
        response = await client.get(url, params=params, headers=DEFAULT_HEADERS)
        if response.status_code == 200:
            data = response.json()
            if should_cache is None or should_cache(data):
                _prune_cache(now)
                _cache[cache_key] = (now, ttl, data)
            return data
        if cache_key in _cache:
            return _cache[cache_key][2]
        return {"error": f"API status {response.status_code}"}
    except Exception as error:
        if cache_key in _cache:
            return _cache[cache_key][2]
        return {"error": str(error)}
    finally:
        if close_after:
            await client.aclose()


def current_season_id() -> str:
    now = time.localtime()
    start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    return f"{start_year}{start_year + 1}"


def to_pct(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    return round(n * 100 if n <= 1.5 else n, 1)


def parse_iso_ts(date_str: str) -> float:
    if not date_str:
        return 0.0
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


@app.get("/health")
async def health():
    return {"status": "ok"}


# 1. Расписание с рекордами и индикаторами плей-офф
@app.get("/api/schedule")
async def schedule(date: str):
    schedule_url = f"{NHL_BASE}/schedule/{date}"
    standings_url = f"{NHL_BASE}/standings/now"

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sched_ttl = 3600 if date < today_str else CACHE_TTL["schedule"]

    schedule_data, standings_data = await asyncio.gather(
        fetch_with_cache(f"schedule:{date}", schedule_url, sched_ttl),
        fetch_with_cache("standings", standings_url, CACHE_TTL["standings"]),
    )

    if not isinstance(schedule_data, dict):
        return schedule_data

    standings_rows = standings_data.get("standings", []) if isinstance(standings_data, dict) else []
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
            "clinchIndicator": row.get("clinchIndicator"),
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


# 2. Турнирная таблица
@app.get("/api/standings")
async def standings():
    return await fetch_with_cache("standings", f"{NHL_BASE}/standings/now", CACHE_TTL["standings"])


@app.get("/api/standings-by-date/{date}")
async def standings_by_date(date: str):
    if not date or date in ("undefined", "null") or len(date) < 8:
        return await standings()
    data = await fetch_with_cache(f"standings:{date}", f"{NHL_BASE}/standings/{date}", CACHE_TTL["standings"])
    if isinstance(data, dict) and data.get("error"):
        return await standings()
    return data


# 3. Спецбригады, вбрасывания и бросковая активность
@app.get("/api/team-special-teams")
async def team_special_teams(season: str | None = None):
    target_season = season or current_season_id()
    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": 50,
        "sort": '[{"property":"points","direction":"DESC"}]',
    }

    url = f"{NHL_STATS_BASE}/team/summary?{httpx.QueryParams(params)}"
    data = await fetch_with_cache(f"team-special-teams:v40:{target_season}", url, CACHE_TTL["standings"])
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
            "teamId": row.get("teamId"),
            "teamAbbrev": team_abbr,
            "teamName": full_name,
            "powerPlayPctg": to_pct(row.get("powerPlayPct") or row.get("powerPlayPercentage")),
            "penaltyKillPctg": to_pct(row.get("penaltyKillPct") or row.get("penaltyKillPercentage")),
            "faceoffWinPct": to_pct(row.get("faceoffWinPct") or row.get("faceoffWinningPct")),
            "shotsForPerGame": round(float(row["shotsForPerGame"]), 1) if row.get("shotsForPerGame") is not None else None,
            "shotsAgainstPerGame": round(float(row["shotsAgainstPerGame"]), 1) if row.get("shotsAgainstPerGame") is not None else None,
        })

    return {"season": target_season, "teams": teams}


# 4. Лидеры полевых игроков
@app.get("/api/skater-leaders-ext")
@app.get("/api/leaders/{category}")
async def skater_leaders_ext(
    category: str = "points",
    season: str | None = None,
    limit: int = 50,
    subgroup: str | None = None,
):
    target_season = season or current_season_id()
    safe_limit = max(1, min(limit, 100))

    sort_prop = "points"
    endpoint = "summary"

    if category == "goals":
        sort_prop = "goals"
    elif category == "assists":
        sort_prop = "assists"
    elif category == "plusMinus":
        sort_prop = "plusMinus"
    elif category in ("shots", "sog"):
        sort_prop = "shots"
    elif category in ("gameWinningGoals", "gwg"):
        sort_prop = "gameWinningGoals"
    elif category in ("penaltyMinutes", "pim"):
        sort_prop = "penaltyMinutes"
    elif category in ("toiPerGame", "atoi"):
        sort_prop = "timeOnIcePerGame"
    elif category in ("hits", "hit"):
        sort_prop = "hits"
        endpoint = "realtime"
    elif category in ("blockedShots", "blk"):
        sort_prop = "blockedShots"
        endpoint = "realtime"

    cayenne = f"gameTypeId=2 and seasonId={target_season}"
    if subgroup == "defensemen":
        cayenne += ' and positionCode="D"'
    elif subgroup == "rookies":
        cayenne += " and isRookie=1"

    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": cayenne,
        "start": 0,
        "limit": safe_limit,
        "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]',
    }

    url = f"{NHL_STATS_BASE}/skater/{endpoint}?{httpx.QueryParams(params)}"
    cache_key = f"skaters-v40:{target_season}:{category}:{safe_limit}:{subgroup or 'all'}"
    data = await fetch_with_cache(
        cache_key,
        url,
        CACHE_TTL["leaders"],
        should_cache=lambda d: isinstance(d, dict) and bool(d.get("data")),
    )
    rows = data.get("data", []) if isinstance(data, dict) else []

    skaters = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        player_id = row.get("playerId")
        first_name = normalize_name(row.get("firstName"))
        last_name = normalize_name(row.get("lastName"))
        full_name = normalize_name(row.get("skaterFullName") or row.get("playerName")) or f"{first_name} {last_name}".strip()
        team_abbr = normalize_team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev") or "")

        games_played = row.get("gamesPlayed", 0)
        total_toi_sec = row.get("timeOnIce", 0)
        toi_pg_sec = row.get("timeOnIcePerGame", (total_toi_sec / games_played if games_played else 0))

        toi_str = "0:00"
        if isinstance(toi_pg_sec, (int, float)):
            mins = int(toi_pg_sec // 60)
            secs = round(toi_pg_sec % 60)
            if secs == 60:
                mins += 1
                secs = 0
            toi_str = f"{mins}:{secs:02d}"

        goals = row.get("goals", 0)
        assists = row.get("assists", 0)
        points = row.get("points", goals + assists)
        plus_minus = row.get("plusMinus", 0)
        shots = row.get("shots", row.get("sog", 0))
        hits = row.get("hits", 0)
        blocks = row.get("blockedShots", row.get("blocks", 0))
        gwg = row.get("gameWinningGoals", row.get("gwg", 0))
        pim = row.get("penaltyMinutes", row.get("pim", 0))

        val_to_show = points
        if category == "goals":
            val_to_show = goals
        elif category == "assists":
            val_to_show = assists
        elif category == "plusMinus":
            val_to_show = plus_minus
        elif category in ("shots", "sog"):
            val_to_show = shots
        elif category in ("hits", "hit"):
            val_to_show = hits
        elif category in ("blockedShots", "blk"):
            val_to_show = blocks
        elif category in ("gameWinningGoals", "gwg"):
            val_to_show = gwg
        elif category in ("penaltyMinutes", "pim"):
            val_to_show = pim
        elif category in ("toiPerGame", "atoi"):
            val_to_show = toi_str

        skaters.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "positionCode": row.get("positionCode", ""),
            "teamAbbrev": team_abbr,
            "headshot": f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png",
            "gamesPlayed": games_played,
            "goals": goals,
            "assists": assists,
            "points": points,
            "plusMinus": plus_minus,
            "penaltyMinutes": pim,
            "shots": shots,
            "hits": hits,
            "blockedShots": blocks,
            "gameWinningGoals": gwg,
            "toiPerGame": toi_str,
            "value": val_to_show,
        })

    return {
        "season": target_season,
        "category": category,
        category: skaters,
        "skaters": skaters,
    }


# 5. Лидеры вратарей (без выдуманных формул)
@app.get("/api/goalie-leaders")
async def goalie_leaders(limit: int = 100, season: str | None = None):
    limit = max(1, min(limit, 100))
    target_season = season or current_season_id()

    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"seasonId={target_season} and gameTypeId=2",
        "start": 0,
        "limit": limit,
        "sort": '[{"property":"gamesPlayed","direction":"DESC"}]',
    }

    url = f"{NHL_STATS_BASE}/goalie/summary?{httpx.QueryParams(params)}"
    data = await fetch_with_cache(
        f"goalies:v40:{target_season}:{limit}",
        url,
        CACHE_TTL["leaders"],
        should_cache=lambda d: isinstance(d, dict) and bool(d.get("data")),
    )
    rows = data.get("data", []) if isinstance(data, dict) else []

    goalies = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        first_name = normalize_name(row.get("firstName"))
        last_name = normalize_name(row.get("lastName"))
        player_id = row.get("playerId")
        full_name = normalize_name(row.get("goalieFullName") or row.get("playerName")) or f"{first_name} {last_name}".strip()
        team_abbr = normalize_team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev") or "")

        time_on_ice = row.get("timeOnIce", 0)
        time_in_min = round(time_on_ice / 60) if isinstance(time_on_ice, (int, float)) else 0
        games_started = row.get("gamesStarted", row.get("gamesPlayed", 0))
        sv_pct = float(row.get("savePctg") or row.get("savePct") or 0.0)

        goalies.append({
            "id": player_id,
            "playerId": player_id,
            "name": full_name,
            "firstName": first_name,
            "lastName": last_name,
            "teamAbbrev": team_abbr,
            "headshot": f"https://assets.nhle.com/mugs/nhl/latest/{player_id}.png",
            "gamesPlayed": row.get("gamesPlayed", 0),
            "gamesStarted": games_started,
            "wins": row.get("wins", 0),
            "losses": row.get("losses", 0),
            "otLosses": row.get("otLosses", 0),
            "savePctg": sv_pct,
            "gaa": float(row.get("goalsAgainstAverage") or row.get("gaa") or 0.0),
            "shutouts": row.get("shutouts", 0),
            "saves": row.get("saves", 0),
            "shotsAgainst": row.get("shotsAgainst", row.get("shots", 0)),
            "timeOnIce": time_in_min,
        })

    return {"season": target_season, "goalies": goalies}


# 6. Продвинутая статистика команд (реальные метрики без заглушек)
@app.get("/api/advanced-team-stats")
async def advanced_team_stats(season: str | None = None):
    target_season = season or current_season_id()
    cay = f"gameTypeId=2 and seasonId={target_season}"
    sum_url = f"{NHL_STATS_BASE}/team/summary?{httpx.QueryParams({'isAggregate': 'false', 'isGame': 'false', 'limit': 50, 'cayenneExp': cay})}"
    pct_url = f"{NHL_STATS_BASE}/team/percentages?{httpx.QueryParams({'isAggregate': 'false', 'isGame': 'false', 'limit': 50, 'cayenneExp': cay})}"
    rt_url = f"{NHL_STATS_BASE}/team/realtime?{httpx.QueryParams({'isAggregate': 'false', 'isGame': 'false', 'limit': 50, 'cayenneExp': cay})}"

    sum_data, pct_data, rt_data = await asyncio.gather(
        fetch_with_cache(f"adv-sum:v40:{target_season}", sum_url, CACHE_TTL["advanced"]),
        fetch_with_cache(f"adv-pct:v40:{target_season}", pct_url, CACHE_TTL["advanced"]),
        fetch_with_cache(f"adv-rt:v40:{target_season}", rt_url, CACHE_TTL["advanced"]),
    )

    sum_rows = sum_data.get("data", []) if isinstance(sum_data, dict) else []
    pct_rows = pct_data.get("data", []) if isinstance(pct_data, dict) else []
    rt_rows = rt_data.get("data", []) if isinstance(rt_data, dict) else []

    pct_map = {normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev")): r for r in pct_rows if isinstance(r, dict)}
    rt_map = {normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev")): r for r in rt_rows if isinstance(r, dict)}

    teams = []
    for r in sum_rows:
        if not isinstance(r, dict):
            continue
        ab = normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev") or "")
        if not ab:
            continue
        p = pct_map.get(ab, {})
        rt = rt_map.get(ab, {})

        sat_val = p.get("satPct") or p.get("satPct5v5") or p.get("satPercentage") or r.get("satPct")
        usat_val = p.get("usatPct") or p.get("usatPct5v5") or p.get("usatPercentage") or r.get("usatPct")

        pdo_val = p.get("pdo") or p.get("shootingPlusSavePct5v5")
        if pdo_val is None and p.get("shootingPct5v5") is not None and p.get("savePct5v5") is not None:
            sh = float(p["shootingPct5v5"])
            sv = float(p["savePct5v5"])
            if sh <= 1:
                sh *= 100
            if sv <= 1:
                sv *= 100
            pdo_val = round(sh + sv, 1)
        elif pdo_val is not None:
            n = float(pdo_val)
            pdo_val = round(n * 100 if n <= 2 else n, 1)

        oz_val = p.get("zoneStartPct") or p.get("offensiveZoneStartPct") or p.get("offensiveZoneStartPct5v5")

        teams.append({
            "teamId": r.get("teamId"),
            "teamAbbrev": ab,
            "teamName": r.get("teamFullName") or ab,
            "satPct": to_pct(sat_val),
            "usatPct": to_pct(usat_val),
            "pdo": pdo_val,
            "ozsp": to_pct(oz_val),
            "powerPlayPctg": to_pct(r.get("powerPlayPct")),
            "penaltyKillPctg": to_pct(r.get("penaltyKillPct")),
            "faceoffWinPct": to_pct(r.get("faceoffWinPct") or r.get("faceoffWinningPct")),
            "shotsForPerGame": round(float(r["shotsForPerGame"]), 1) if r.get("shotsForPerGame") is not None else None,
            "shotsAgainstPerGame": round(float(r["shotsAgainstPerGame"]), 1) if r.get("shotsAgainstPerGame") is not None else None,
            "hits": rt.get("hits"),
            "blockedShots": rt.get("blockedShots"),
            "giveaways": rt.get("giveaways"),
            "takeaways": rt.get("takeaways"),
        })

    return {"season": target_season, "teams": teams}


# 7. Голосование Pick'em
@app.api_route("/api/vote/{game_id}", methods=["GET", "POST"])
async def vote(game_id: str, request: Request):
    store_key = f"pickem_{game_id}"
    if store_key not in _votes_store:
        _votes_store[store_key] = {"away": 0, "tie": 0, "home": 0}

    current = _votes_store[store_key]

    if request.method == "POST":
        try:
            body = await request.json()
            pick = body.get("pick")
            if pick in current:
                current[pick] += 1
                _votes_store[store_key] = current
        except Exception:
            pass

    total_raw = sum(current.values())
    total = total_raw or 1
    away_pct = round((current["away"] / total) * 100) if total_raw else 0
    tie_pct = round((current["tie"] / total) * 100) if total_raw else 0
    home_pct = max(0, 100 - away_pct - tie_pct) if total_raw else 0

    return JSONResponse({
        "gameId": game_id,
        "votes": current,
        "total": total_raw,
        "awayPct": away_pct,
        "tiePct": tie_pct,
        "homePct": home_pct,
    })


# 8. Автоматический поиск видеообзора на YouTube (исправлен URL)
@app.get("/api/game-youtube-recap")
async def game_youtube_recap(away: str, home: str, date: str = ""):
    query = f"NHL {away} vs {home} {date} game highlights".strip()
    cache_key = f"yt:recap:{away}:{home}:{date}"
    now = time.time()
    cached = _cache.get(cache_key)

    if cached and now - cached[0] < cached[1]:
        return cached[2]

    client = get_client()
    close_after = _http_client is None
    try:
        resp = await client.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+111; SOCS=CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg",
            },
        )
        if resp.status_code == 200:
            html = resp.text
            match = re.search(r'"videoRenderer"\s*:\s*\{[^}]*?"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
            if not match:
                match = re.search(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)

            video_id = match.group(1) if match else None
            result = {
                "videoId": video_id,
                "embedUrl": f"https://www.youtube.com/embed/{video_id}?playsinline=1&rel=0" if video_id else None,
            }
            if video_id:
                _prune_cache(now)
                _cache[cache_key] = (now, CACHE_TTL["video"], result)
            return result
    except Exception:
        pass
    finally:
        if close_after:
            await client.aclose()

    return {"videoId": None, "embedUrl": None}


# 9. Трансферы и переходы от ESPN (исправлен диапазон дат и сортировка)
@app.get("/api/transactions")
async def transactions():
    now_dt = datetime.now(timezone.utc)
    from_str = (now_dt - timedelta(days=35)).strftime("%Y%m%d")
    to_str = (now_dt + timedelta(days=2)).strftime("%Y%m%d")

    async def _load():
        data = await fetch_with_cache(
            "espn:transactions:raw:v40",
            f"{ESPN_BASE}/transactions?dates={from_str}-{to_str}&limit=100",
            CACHE_TTL["transactions"],
            should_cache=lambda d: isinstance(d, dict) and bool(d.get("transactions")),
        )
        if not isinstance(data, dict) or not data.get("transactions"):
            data = await fetch_with_cache(
                "espn:transactions:fallback:v40",
                f"{ESPN_BASE}/transactions?limit=100",
                CACHE_TTL["transactions"],
                should_cache=lambda d: isinstance(d, dict) and bool(d.get("transactions")),
            )
        return data

    data = await _load()
    if not isinstance(data, dict):
        return {"transactions": []}

    raw_tx = data.get("transactions", [])
    if not isinstance(raw_tx, list):
        return {"transactions": []}

    sorted_tx = sorted(
        [t for t in raw_tx if isinstance(t, dict)],
        key=lambda t: parse_iso_ts(str(t.get("date") or "")),
        reverse=True,
    )

    result = []
    for t in sorted_tx[:80]:
        team_obj = t.get("team") or {}
        team_name = team_obj.get("abbreviation") or team_obj.get("displayName") or team_obj.get("name") or ""
        result.append({
            "date": t.get("date", ""),
            "description": t.get("description") or t.get("text") or "",
            "team": normalize_team_abbr(team_name),
        })

    return {"transactions": result}


# 10. Новости Telegram-канала (унифицированный формат с fallback на t.me/s)
@app.get("/api/news")
async def get_news():
    if _news_store:
        formatted = []
        for item in _news_store:
            photo_id = item.get("photo_id", "")
            img = item.get("image") or (f"/api/news/photo/{photo_id}" if photo_id else "")
            formatted.append({
                "id": item.get("id"),
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "image": img,
                "date": item.get("date", ""),
            })
        return {"news": formatted}

    channel = os.environ.get("TELEGRAM_CHANNEL", "xokkey9")
    now = time.time()
    cached = _cache.get(f"tg_news_{channel}")
    if cached and now - cached[0] < cached[1]:
        return cached[2]

    client = get_client()
    close_after = _http_client is None
    try:
        resp = await client.get(
            f"https://t.me/s/{channel}",
            headers={"User-Agent": DEFAULT_HEADERS["User-Agent"], "Accept-Language": "ru,en;q=0.9"},
        )
        if resp.status_code != 200:
            return {"news": []}
        html = resp.text
        blocks = html.split('<div class="tgme_widget_message_wrap')
        posts = []
        for block in blocks[1:]:
            link_m = re.search(r'href="(https://t\.me/[^/]+/\d+)"', block)
            if not link_m:
                continue
            post_link = link_m.group(1)
            msg_id = post_link.rsplit("/", 1)[-1]
            bg_m = re.search(r"background-image:\s*url\('([^']+)'\)", block)
            img_url = bg_m.group(1) if bg_m else ""
            text_m = re.search(r'<div class="tgme_widget_message_text[^>]*>([\s\S]*?)</div>', block)
            text = ""
            if text_m:
                cleaned = re.sub(r"<br\s*/?>", "\n", text_m.group(1), flags=re.IGNORECASE)
                cleaned = re.sub(r"<[^>]+>", "", cleaned)
                text = unescape(cleaned).strip()
            if not text and not img_url:
                continue
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            title = lines[0] if lines else "Новость канала"
            if len(title) > 130:
                title = title[:127] + "..."
            date_str = "Свежая новость"
            time_m = re.search(r'<time datetime="([^"]+)"', block)
            if time_m:
                ts = parse_iso_ts(time_m.group(1))
                if ts:
                    msk = datetime.fromtimestamp(ts + 3 * 3600, tz=timezone.utc)
                    date_str = msk.strftime("%d.%m %H:%M")
            posts.append({"id": msg_id, "title": title, "link": post_link, "image": img_url, "date": date_str})

        res = {"news": list(reversed(posts))[:20]}
        if res["news"]:
            _prune_cache(now)
            _cache[f"tg_news_{channel}"] = (now, CACHE_TTL["news"], res)
        return res
    except Exception:
        return {"news": []}
    finally:
        if close_after:
            await client.aclose()


@app.get("/api/news/photo/{file_id}")
async def get_news_photo(file_id: str):
    if not BOT_TOKEN or not file_id:
        return JSONResponse({"error": "No token or file_id"}, status_code=404)
    client = get_client()
    close_after = _http_client is None
    try:
        file_info_resp = await client.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
        if file_info_resp.status_code != 200:
            return JSONResponse({"error": "Failed to get file info"}, status_code=404)

        file_path = file_info_resp.json().get("result", {}).get("file_path")
        if not file_path:
            return JSONResponse({"error": "File path not found"}, status_code=404)

        img_resp = await client.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}")
        return Response(
            content=img_resp.content,
            media_type=img_resp.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if close_after:
            await client.aclose()


# Базовые NHL эндпоинты
@app.get("/api/seasons-list")
async def seasons_list():
    return await fetch_with_cache("seasons-list", f"{NHL_BASE}/standings-season", CACHE_TTL["standings"])


@app.get("/api/playoff-bracket/{year}")
async def playoff_bracket(year: str):
    return await fetch_with_cache(f"bracket:{year}", f"{NHL_BASE}/playoff-bracket/{year}", CACHE_TTL["standings"])


@app.get("/api/draft/{year}")
@app.get("/api/draft/{year}/{draft_round}")
async def draft_picks(year: str, draft_round: str | None = None, round: str = "all"):
    target_round = draft_round or round or "all"
    url = f"{NHL_BASE}/draft/picks/{year}/{target_round}"
    return await fetch_with_cache(f"draft:{year}:{target_round}", url, 21600)


@app.get("/api/matchup/{game_id}")
async def matchup(game_id: str):
    return await fetch_with_cache(f"matchup:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/landing", CACHE_TTL["matchup"])


@app.get("/api/team-schedule/{team}")
async def team_schedule(team: str, season: str | None = None):
    team_upper = normalize_team_abbr(team)
    season_key = season or "now"
    return await fetch_with_cache(f"team-schedule:{team_upper}:{season_key}", f"{NHL_BASE}/club-schedule-season/{team_upper}/{season_key}", CACHE_TTL["team_schedule"])


@app.get("/api/player/{player_id}")
async def player(player_id: str):
    return await fetch_with_cache(f"player:{player_id}", f"{NHL_BASE}/player/{player_id}/landing", CACHE_TTL["player"])


@app.get("/api/player-gamelog/{player_id}")
async def player_gamelog(player_id: str, season: str | None = None, gameType: str = "2"):
    if season:
        url = f"{NHL_BASE}/player/{player_id}/game-log/{season}/{gameType}"
        key = f"pglog:{player_id}:{season}:{gameType}"
    else:
        url = f"{NHL_BASE}/player/{player_id}/game-log/now"
        key = f"pglog:{player_id}:now:{gameType}"
    return await fetch_with_cache(key, url, CACHE_TTL["team_schedule"])


@app.get("/api/player-search")
async def player_search(q: str = "", limit: int = 20):
    query = q.strip()
    if len(query) < 2:
        return {"results": []}
    safe_limit = max(1, min(limit, 40))
    data = await fetch_with_cache(
        f"psearch:{query.lower()}:{safe_limit}",
        f"{NHL_SEARCH_BASE}/search/player",
        CACHE_TTL["player_search"],
        params={"culture": "en-us", "limit": safe_limit, "q": query},
    )
    if isinstance(data, list):
        return {"results": data}
    return {"results": []}


async def _resolve_team_id(abbrev: str) -> int | None:
    norm = normalize_team_abbr(abbrev)
    season = current_season_id()
    url = f"{NHL_STATS_BASE}/team/summary?{httpx.QueryParams({'isAggregate': 'false', 'isGame': 'false', 'limit': 50, 'cayenneExp': f'gameTypeId=2 and seasonId={season}'})}"
    data = await fetch_with_cache(f"team-id-raw:{season}", url, 21600)
    rows = data.get("data", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ab = normalize_team_abbr(row.get("teamFullName") or row.get("teamAbbrev") or "")
        if ab == norm and row.get("teamId"):
            return int(row["teamId"])
    return TEAM_ID_FALLBACK.get(norm)


@app.get("/api/edge/skater/{player_id}")
async def edge_skater(player_id: str, season: str | None = None, gameType: str = "2"):
    if season:
        url = f"{NHL_BASE}/edge/skater-detail/{player_id}/{season}/{gameType}"
        key = f"edge:skater:{player_id}:{season}:{gameType}"
    else:
        url = f"{NHL_BASE}/edge/skater-detail/{player_id}/now"
        key = f"edge:skater:{player_id}:now"
    return await fetch_with_cache(key, url, CACHE_TTL["edge"])


@app.get("/api/edge/goalie/{player_id}")
async def edge_goalie(player_id: str, season: str | None = None, gameType: str = "2"):
    if season:
        url = f"{NHL_BASE}/edge/goalie-detail/{player_id}/{season}/{gameType}"
        key = f"edge:goalie:{player_id}:{season}:{gameType}"
    else:
        url = f"{NHL_BASE}/edge/goalie-detail/{player_id}/now"
        key = f"edge:goalie:{player_id}:now"
    return await fetch_with_cache(key, url, CACHE_TTL["edge"])


@app.get("/api/edge/team/{team}")
async def edge_team(team: str, season: str | None = None, gameType: str = "2"):
    team_id = await _resolve_team_id(team)
    if not team_id:
        return JSONResponse({"error": "Team not found"}, status_code=404)
    if season:
        url = f"{NHL_BASE}/edge/team-detail/{team_id}/{season}/{gameType}"
        key = f"edge:team:{team_id}:{season}:{gameType}"
    else:
        url = f"{NHL_BASE}/edge/team-detail/{team_id}/now"
        key = f"edge:team:{team_id}:now"
    return await fetch_with_cache(key, url, CACHE_TTL["edge"])


@app.get("/api/roster-stats/{team}")
async def roster_stats(team: str, season: str | None = None, gameType: str = "2"):
    team_upper = normalize_team_abbr(team)
    target_season = season or "now"
    if target_season == "now" and gameType == "2":
        target_url = f"{NHL_BASE}/club-stats/{team_upper}/now"
        cache_key = f"club-stats:{team_upper}:now"
    else:
        target_url = f"{NHL_BASE}/club-stats/{team_upper}/{target_season}/{gameType}"
        cache_key = f"club-stats:{team_upper}:{target_season}:{gameType}"
    data = await fetch_with_cache(cache_key, target_url, CACHE_TTL["roster"])
    if isinstance(data, dict) and "error" in data:
        return {"skaters": [], "goalies": [], "season": target_season, "gameType": gameType}
    return data


@app.get("/api/pbp/{game_id}")
async def play_by_play(game_id: str):
    data = await fetch_with_cache(f"pbp:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/play-by-play", CACHE_TTL["pbp"])
    if isinstance(data, dict) and data.get("gameState") in ("OFF", "FINAL"):
        _cache[f"pbp:{game_id}"] = (time.time(), 3600, data)
    return data


@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    data = await fetch_with_cache(f"boxscore:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/boxscore", CACHE_TTL["boxscore"])
    if isinstance(data, dict) and data.get("gameState") in ("OFF", "FINAL"):
        _cache[f"boxscore:{game_id}"] = (time.time(), 3600, data)
    return data


@app.get("/api/right-rail/{game_id}")
async def right_rail(game_id: str):
    return await fetch_with_cache(f"rightrail:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/right-rail", CACHE_TTL["rightrail"])


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    data = await fetch_with_cache(f"score:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/landing", CACHE_TTL["score"])
    if isinstance(data, dict) and data.get("gameState") in ("OFF", "FINAL"):
        _cache[f"score:{game_id}"] = (time.time(), 3600, data)
    return data


async def get_espn_probable_goalies(date_str: str, away_abbr: str, home_abbr: str):
    clean_date = date_str.replace("-", "") if date_str else ""
    url = f"{ESPN_BASE}/scoreboard?dates={clean_date}" if clean_date else f"{ESPN_BASE}/scoreboard"
    data = await fetch_with_cache(f"espn:probables:{clean_date}", url, 300)
    events = data.get("events", []) if isinstance(data, dict) else []
    res = {"away": None, "home": None}

    if not isinstance(events, list):
        return res

    for ev in events:
        comps = ev.get("competitions", [])
        for comp in comps:
            competitors = comp.get("competitors", [])
            matched = {}
            for c in competitors:
                raw_team = c.get("team", {}).get("abbreviation") or c.get("team", {}).get("displayName") or ""
                matched[normalize_team_abbr(raw_team)] = c

            if away_abbr in matched and home_abbr in matched:
                for side, side_abbr in [("away", away_abbr), ("home", home_abbr)]:
                    c = matched[side_abbr]
                    probables = c.get("probables") or c.get("probableStartingGoalie") or []
                    if not isinstance(probables, list):
                        probables = [probables] if probables else []
                    if probables:
                        item = probables[0]
                        athlete = item.get("athlete", {}) if isinstance(item, dict) else {}
                        status_obj = item.get("status", {}) if isinstance(item, dict) else {}
                        status_str = status_obj.get("name", "") if isinstance(status_obj, dict) else str(status_obj or "")
                        confirmed = status_str.lower() == "confirmed" or item.get("confirmed") is True
                        hs = athlete.get("headshot", "")
                        if isinstance(hs, dict):
                            hs = hs.get("href", "")

                        res[side] = {
                            "name": athlete.get("displayName") or athlete.get("name") or "Не объявлен",
                            "jersey": athlete.get("jersey", ""),
                            "confirmed": confirmed,
                            "status": "Подтвержден" if confirmed else ("Вероятен" if status_str else "Ожидается"),
                            "headshot": hs,
                        }
                return res
    return res


@app.get("/api/injuries")
async def get_injuries():
    url = f"{ESPN_BASE}/injuries"
    data = await fetch_with_cache(
        "espn:injuries:v40",
        url,
        CACHE_TTL["espn"],
        should_cache=lambda d: isinstance(d, dict) and bool(d.get("injuries")),
    )
    if not isinstance(data, dict):
        return {}

    teams_data = data.get("injuries", [])
    result = {}
    if not isinstance(teams_data, list):
        return {}

    for item in teams_data:
        if not isinstance(item, dict):
            continue
        team_abbr = normalize_team_abbr(item.get("displayName") or item.get("name") or item.get("abbreviation") or "")
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
                or inj.get("longComment")
                or ""
            )
            status = inj.get("status") or "Injured"
            headshot = athlete.get("headshot", {}).get("href", "") if isinstance(athlete.get("headshot"), dict) else (athlete.get("headshot") or "")

            team_injuries.append({
                "id": athlete.get("id"),
                "name": athlete.get("displayName") or athlete.get("name") or "Игрок",
                "position": pos_code,
                "status": status,
                "details": detail_desc,
                "date": inj.get("date", ""),
                "headshot": headshot,
            })
        if team_abbr and team_injuries:
            result[team_abbr] = team_injuries

    return result


@app.get("/api/scoreboard-espn")
async def get_scoreboard_espn(date: str | None = None):
    params = f"?dates={date.replace('-', '')}" if date else ""
    url = f"{ESPN_BASE}/scoreboard{params}"
    cache_key = f"espn:scoreboard:{date or 'today'}"
    data = await fetch_with_cache(cache_key, url, CACHE_TTL["espn"])
    if not isinstance(data, dict):
        return []
    return data.get("events", []) if isinstance(data.get("events"), list) else []


def _extract_top_scorers(skaters: list[dict], limit: int = 3) -> list[dict]:
    valid = [s for s in skaters if isinstance(s, dict)]
    valid.sort(key=lambda s: (s.get("points", 0), s.get("goals", 0)), reverse=True)
    out = []
    for s in valid[:limit]:
        first = normalize_name(s.get("firstName"))
        last = normalize_name(s.get("lastName"))
        name = f"{first} {last}".strip() or s.get("name") or "Игрок"
        p_id = s.get("playerId") or s.get("id")
        out.append({
            "id": p_id,
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
            "headshot": s.get("headshot") or (f"https://assets.nhle.com/mugs/nhl/latest/{p_id}.png" if p_id else ""),
        })
    return out


def _extract_club_goalies(goalies: list[dict]) -> list[dict]:
    valid = [g for g in goalies if isinstance(g, dict)]
    valid.sort(key=lambda g: g.get("gamesPlayed", 0), reverse=True)
    out = []
    for g in valid:
        first = normalize_name(g.get("firstName"))
        last = normalize_name(g.get("lastName"))
        name = f"{first} {last}".strip() or g.get("name") or "Вратарь"
        p_id = g.get("playerId") or g.get("id")
        toi_raw = g.get("timeOnIce", g.get("toi", 0))
        if isinstance(toi_raw, (int, float)):
            toi_mins = round(toi_raw / 60) if toi_raw > 3000 else round(toi_raw)
        else:
            toi_mins = 0
        sa = g.get("shotsAgainst")
        ga = g.get("goalsAgainst")
        saves = g.get("saves")
        if saves is None and sa is not None and ga is not None:
            saves = sa - ga
        out.append({
            "id": p_id,
            "name": name,
            "firstName": first,
            "lastName": last,
            "gamesPlayed": g.get("gamesPlayed", 0),
            "gamesStarted": g.get("gamesStarted", 0),
            "wins": g.get("wins", 0),
            "losses": g.get("losses", 0),
            "otLosses": g.get("otLosses", 0),
            "savePctg": g.get("savePctg") if g.get("savePctg") is not None else g.get("savePercentage"),
            "gaa": g.get("goalsAgainstAverage") if g.get("goalsAgainstAverage") is not None else g.get("gaa"),
            "shutouts": g.get("shutouts", 0),
            "saves": saves or 0,
            "shotsAgainst": sa or 0,
            "timeOnIce": toi_mins,
            "headshot": g.get("headshot") or (f"https://assets.nhle.com/mugs/nhl/latest/{p_id}.png" if p_id else ""),
        })
    return out


# Предматчевый аналитический центр (полностью синхронизирован с Cloudflare Worker)
@app.get("/api/pregame/{game_id}")
async def pregame(
    game_id: str,
    date: str | None = None,
    away: str | None = None,
    home: str | None = None,
):
    current_season = current_season_id()

    rail_data, landing_data, standings_data, injuries_data, summary_data = await asyncio.gather(
        fetch_with_cache(f"rightrail:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/right-rail", CACHE_TTL["rightrail"]),
        fetch_with_cache(f"landing:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/landing", CACHE_TTL["score"]),
        fetch_with_cache("standings", f"{NHL_BASE}/standings/now", CACHE_TTL["standings"]),
        get_injuries(),
        fetch_with_cache(
            f"team-summary:{current_season}",
            f"{NHL_STATS_BASE}/team/summary?isAggregate=false&isGame=false&cayenneExp=gameTypeId=2%20and%20seasonId={current_season}",
            CACHE_TTL["standings"],
        ),
        return_exceptions=True,
    )

    rail_data = rail_data if isinstance(rail_data, dict) else {}
    landing_data = landing_data if isinstance(landing_data, dict) else {}
    standings_data = standings_data if isinstance(standings_data, dict) else {}
    injuries_data = injuries_data if isinstance(injuries_data, dict) else {}
    summary_data = summary_data if isinstance(summary_data, dict) else {}

    away_team_obj = landing_data.get("awayTeam") or {}
    home_team_obj = landing_data.get("homeTeam") or {}

    away_abbr = normalize_team_abbr(away or away_team_obj.get("abbrev") or away_team_obj.get("teamAbbrev"))
    home_abbr = normalize_team_abbr(home or home_team_obj.get("abbrev") or home_team_obj.get("teamAbbrev"))

    game_date = date or landing_data.get("gameDate") or ""

    probables, away_roster, home_roster = await asyncio.gather(
        get_espn_probable_goalies(game_date, away_abbr, home_abbr),
        roster_stats(away_abbr) if away_abbr else asyncio.sleep(0, result={}),
        roster_stats(home_abbr) if home_abbr else asyncio.sleep(0, result={}),
    )

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

    summary_rows = summary_data.get("data", []) if isinstance(summary_data, dict) else []
    summary_map = {}
    for r in summary_rows:
        if isinstance(r, dict):
            ab = normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev") or "")
            if ab:
                summary_map[ab] = {
                    "pp": r.get("powerPlayPct"),
                    "pk": r.get("penaltyKillPct"),
                    "sfPg": round(float(r["shotsForPerGame"]), 1) if r.get("shotsForPerGame") is not None else None,
                    "saPg": round(float(r["shotsAgainstPerGame"]), 1) if r.get("shotsAgainstPerGame") is not None else None,
                }

    away_spec = summary_map.get(away_abbr, {})
    home_spec = summary_map.get(home_abbr, {})

    away_gp = away_st.get("gamesPlayed") or 1
    home_gp = home_st.get("gamesPlayed") or 1

    away_gf_pg = round((away_st.get("goalFor", 0) / away_gp), 2) if away_gp else 0
    home_gf_pg = round((home_st.get("goalFor", 0) / home_gp), 2) if home_gp else 0
    away_ga_pg = round((away_st.get("goalAgainst", 0) / away_gp), 2) if away_gp else 0
    home_ga_pg = round((home_st.get("goalAgainst", 0) / home_gp), 2) if home_gp else 0

    def make_comp(cat, label, away_val, home_val, higher_is_better=True):
        return {
            "category": cat,
            "label": label,
            "awayValue": away_val,
            "homeValue": home_val,
            "higherIsBetter": higher_is_better,
        }

    pregame_stats = [
        make_comp("powerPlayPctg", "Большинство (%PP)", away_spec.get("pp") if away_spec.get("pp") is not None else away_st.get("powerPlayPctg"), home_spec.get("pp") if home_spec.get("pp") is not None else home_st.get("powerPlayPctg"), True),
        make_comp("penaltyKillPctg", "Меньшинство (%PK)", away_spec.get("pk") if away_spec.get("pk") is not None else away_st.get("penaltyKillPctg"), home_spec.get("pk") if home_spec.get("pk") is not None else home_st.get("penaltyKillPctg"), True),
        make_comp("goalsForPerGame", "Заброшено за игру (GF/G)", away_gf_pg, home_gf_pg, True),
        make_comp("goalsAgainstPerGame", "Пропущено за игру (GA/G)", away_ga_pg, home_ga_pg, False),
        make_comp("shotsForPerGame", "Броски по воротам соперника (SF/G)", away_spec.get("sfPg"), home_spec.get("sfPg"), True),
        make_comp("shotsAgainstPerGame", "Броски соперника по своим воротам (SA/G)", away_spec.get("saPg"), home_spec.get("saPg"), False),
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

    return {
        "gameId": game_id,
        "gameDate": game_date,
        "startTimeUTC": landing_data.get("startTimeUTC"),
        "awayTeam": {
            "abbrev": away_abbr,
            "name": away_team_obj.get("name") or away_team_obj.get("placeName", {}).get("default") or away_abbr,
            "logo": away_team_obj.get("logo") or f"https://assets.nhle.com/logos/nhl/svg/{away_abbr}_light.svg",
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
            "logo": home_team_obj.get("logo") or f"https://assets.nhle.com/logos/nhl/svg/{home_abbr}_light.svg",
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
        "probableGoalies": probables,
        "injuries": {
            "away": injuries_data.get(away_abbr, []),
            "home": injuries_data.get(home_abbr, []),
        },
        "topScorers": {
            "away": _extract_top_scorers(away_roster.get("skaters", []), 3),
            "home": _extract_top_scorers(home_roster.get("skaters", []), 3),
        },
        "clubGoalies": {
            "away": _extract_club_goalies(away_roster.get("goalies", [])),
            "home": _extract_club_goalies(home_roster.get("goalies", [])),
        },
        "seasonSeries": season_series,
    }


# Telegram Webhook (с проверкой secret_token если задан)
@app.api_route("/webhook", methods=["GET", "POST"])
async def telegram_webhook(request: Request):
    if request.method == "GET":
        return {"status": "ok", "message": "Webhook is active and listening!"}

    if WEBHOOK_SECRET:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != WEBHOOK_SECRET:
            return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=403)

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    channel_post = update.get("channel_post")
    if channel_post:
        chat = channel_post.get("chat", {})
        channel_username = chat.get("username", "")
        message_id = channel_post.get("message_id")

        raw_text = channel_post.get("text") or channel_post.get("caption") or ""
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

        title = lines[0][:117] + "..." if lines and len(lines[0]) > 120 else (lines[0] if lines else "⚡ Публикация в канале")
        post_link = f"https://t.me/{channel_username}/{message_id}" if channel_username else f"https://t.me/c/{str(chat.get('id', '')).replace('-100', '')}/{message_id}"

        photo_id = ""
        photos = channel_post.get("photo", [])
        if isinstance(photos, list) and photos:
            photo_id = photos[-1].get("file_id", "")

        post_ts = channel_post.get("date", time.time())
        date_str = time.strftime("%d.%m в %H:%M", time.gmtime(post_ts + 3 * 3600))

        news_item = {
            "id": message_id,
            "title": title,
            "link": post_link,
            "photo_id": photo_id,
            "date": date_str,
            "timestamp": post_ts,
        }

        global _news_store
        _news_store = [n for n in _news_store if n.get("id") != message_id]
        _news_store.insert(0, news_item)
        _news_store = _news_store[:30]
        save_news_to_disk(_news_store)
        return {"ok": True}

    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/start") or text in ("/matches", "/standings", "/leaders", "/news", "/donate", "/help"):
        donate_url = "https://t.me/tribute/app?startapp=dTl8"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📅 Матчи", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=matches"}},
                    {"text": "📊 Таблица", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=standings"}},
                ],
                [
                    {"text": "🏆 Лидеры", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=leaders"}},
                    {"text": "🎯 Драфт", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=draft"}},
                ],
                [
                    {"text": "🔄 Трансферы", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=transactions"}},
                    {"text": "📢 Новости", "web_app": {"url": f"{WEBAPP_URL}/?v=2&section=news"}},
                ],
                [
                    {"text": "☕ Поддержать проект", "url": donate_url},
                ],
            ],
        }

        if BOT_TOKEN:
            client = get_client()
            close_after = _http_client is None
            try:
                resp = await client.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": (
                            "🏒 <b>NHL LIVE</b>\n\n"
                            "Всё главное об NHL — в одном приложении прямо в Telegram:\n\n"
                            "📅 <b>Матчи</b> — счёт live, голы, карта бросков и видеообзоры\n"
                            "📊 <b>Таблица</b> — общая, по дивизионам и продвинутая статистика\n"
                            "🏆 <b>Лидеры</b> — гонка бомбардиров, вратарей и поиск игроков\n"
                            "🎯 <b>Драфт</b> — вся история ярмарок талантов с 1963 года\n"
                            "🔄 <b>Трансферы</b> — свежие переходы и травмы лиги\n"
                            "📢 <b>Новости</b> — свежие инсайды нашего канала\n\n"
                            "Выбери нужный раздел кнопками ниже:"
                        ),
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                )
                print(f"[TG SEND RESULT] Код: {resp.status_code}, Ответ: {resp.text}")
            except Exception as e:
                print(f"[TG SEND ERROR] Ошибка: {e}")
            finally:
                if close_after:
                    await client.aclose()

    return {"ok": True}


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ROOT_INDEX = BASE_DIR / "index.html"
STATIC_INDEX = STATIC_DIR / "index.html"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if ROOT_INDEX.is_file():
        return FileResponse(str(ROOT_INDEX), media_type="text/html", headers=no_cache_headers)
    if STATIC_INDEX.is_file():
        return FileResponse(str(STATIC_INDEX), media_type="text/html", headers=no_cache_headers)
    return {"detail": "index.html not found"}
