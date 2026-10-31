import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    "pbp": 15,
    "roster": 60 * 45,
    "player": 60 * 45,
    "boxscore": 20,
    "rightrail": 20,
    "matchup": 60 * 30,
    "player_search": 60 * 10,
    "team_schedule": 60 * 10,
    "pregame": 60 * 10,
    "espn": 60 * 15,
    "video": 60 * 30,
    "transactions": 60 * 30,
    "advanced": 60 * 30,
}

_cache: dict[str, tuple[float, Any]] = {}
_votes_store: dict[str, dict[str, int]] = {}

# =======================================================
# === НАЧАЛО: ХРАНИЛИЩЕ НОВОСТЕЙ TELEGRAM ===============
# =======================================================
import json as py_json

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
# =======================================================
# === КОНЕЦ: ХРАНИЛИЩЕ НОВОСТЕЙ TELEGRAM ================
# =======================================================

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


async def fetch_with_cache(cache_key: str, url: str, ttl: int) -> Any:
    now = time.time()
    cached = _cache.get(cache_key)

    if cached and now - cached[0] < ttl:
        return cached[1]

    async with httpx.AsyncClient(timeout=14, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=DEFAULT_HEADERS)
            if response.status_code == 200:
                data = response.json()
                _cache[cache_key] = (now, data)
                return data
            if cache_key in _cache:
                return _cache[cache_key][1]
            return {"error": f"API status {response.status_code}"}
        except Exception as error:
            if cache_key in _cache:
                return _cache[cache_key][1]
            return {"error": str(error)}


def current_season_id() -> str:
    now = time.localtime()
    start_year = now.tm_year if now.tm_mon >= 9 else now.tm_year - 1
    return f"{start_year}{start_year + 1}"


@app.get("/health")
async def health():
    return {"status": "ok"}


# 1. Расписание с рекордами и индикаторами плей-офф
@app.get("/api/schedule")
async def schedule(date: str):
    schedule_url = f"{NHL_BASE}/schedule/{date}"
    standings_url = f"{NHL_BASE}/standings/now"

    schedule_data, standings_data = await asyncio.gather(
        fetch_with_cache(f"schedule:{date}", schedule_url, CACHE_TTL["schedule"]),
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
            "clinchIndicator": row.get("clinchIndicator"),  # 'x', 'y', 'p'
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
    return await fetch_with_cache(f"standings:{date}", f"{NHL_BASE}/standings/{date}", CACHE_TTL["standings"])


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
    data = await fetch_with_cache(f"team-special-teams:v30:{target_season}", url, CACHE_TTL["standings"])
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

        fo_raw = row.get("faceoffWinPct") or row.get("faceoffWinningPct")
        fo_val = round(fo_raw * 100 if fo_raw and fo_raw <= 1 else fo_raw, 1) if fo_raw is not None else None
        sf_val = round(float(row["shotsForPerGame"]), 1) if row.get("shotsForPerGame") is not None else None
        sa_val = round(float(row["shotsAgainstPerGame"]), 1) if row.get("shotsAgainstPerGame") is not None else None

        pp_raw = row.get("powerPlayPct")
        pk_raw = row.get("penaltyKillPct")

        teams.append({
            "teamAbbrev": team_abbr,
            "teamName": full_name,
            "powerPlayPctg": round(pp_raw * 100 if pp_raw and pp_raw <= 1 else pp_raw, 1) if pp_raw is not None else None,
            "penaltyKillPctg": round(pk_raw * 100 if pk_raw and pk_raw <= 1 else pk_raw, 1) if pk_raw is not None else None,
            "faceoffWinPct": fo_val,
            "shotsForPerGame": sf_val,
            "shotsAgainstPerGame": sa_val,
        })

    return {"season": target_season, "teams": teams}


# 4. Лидеры полевых игроков (прямая сортировка: GWG, PIM, HIT, BLK, SOG, ATOI)
@app.get("/api/skater-leaders-ext")
@app.get("/api/leaders/{category}")
async def skater_leaders_ext(
    category: str = "points",
    season: str | None = None,
    limit: int = 50,
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

    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"gameTypeId=2 and seasonId={target_season}",
        "start": 0,
        "limit": safe_limit,
        "sort": f'[{{"property":"{sort_prop}","direction":"DESC"}}]',
    }

    url = f"{NHL_STATS_BASE}/skater/{endpoint}?{httpx.QueryParams(params)}"
    data = await fetch_with_cache(f"skaters-exact-v30:{target_season}:{category}:{safe_limit}", url, CACHE_TTL["leaders"])
    rows = data.get("data", []) if isinstance(data, dict) else []

    skaters = []
    for row in rows:
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

        games_played = row.get("gamesPlayed", 0)
        total_toi_sec = row.get("timeOnIce", 0)
        toi_pg_sec = row.get("timeOnIcePerGame", (total_toi_sec / games_played if games_played else 0))

        toi_str = "0:00"
        if isinstance(toi_pg_sec, (int, float)):
            mins = int(toi_pg_sec // 60)
            secs = int(toi_pg_sec % 60)
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


# 5. Лидеры вратарей (QS, SV, SA, W, L, SV%, GAA, SO)
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
    data = await fetch_with_cache(f"goalie-summary:v30:{target_season}:{limit}", url, CACHE_TTL["leaders"])
    rows = data.get("data", []) if isinstance(data, dict) else []

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
        full_name = row.get("goalieFullName") or row.get("playerName") or f"{first_name} {last_name}".strip()
        team_abbr = normalize_team_abbr(row.get("teamAbbrevs") or row.get("teamAbbrev") or "")

        time_on_ice = row.get("timeOnIce", 0)
        time_in_min = round(time_on_ice / 60) if isinstance(time_on_ice, (int, float)) else 0

        games_started = row.get("gamesStarted", row.get("gamesPlayed", 0))
        sv_pct = float(row.get("savePctg") or row.get("savePct") or 0.0)
        qs = round(games_started * (0.72 if sv_pct >= 0.910 else max(0.2, (sv_pct - 0.85) / 0.09)))

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
            "gaa": row.get("goalsAgainstAverage", row.get("gaa", 0)),
            "shutouts": row.get("shutouts", 0),
            "saves": row.get("saves", 0),
            "shotsAgainst": row.get("shotsAgainst", row.get("shots", 0)),
            "qualityStarts": qs,
            "timeOnIce": time_in_min,
        })

    return {"season": target_season, "goalies": goalies}


# 6. Продвинутая статистика команд (SAT/Corsi%, USAT/Fenwick%, PDO, Zone Starts)
@app.get("/api/advanced-team-stats")
async def advanced_team_stats(season: str | None = None):
    target_season = season or current_season_id()
    sum_url = f"{NHL_STATS_BASE}/team/summary?isAggregate=false&isGame=false&cayenneExp=gameTypeId=2%20and%20seasonId={target_season}"
    pct_url = f"{NHL_STATS_BASE}/team/percentages?isAggregate=false&isGame=false&cayenneExp=gameTypeId=2%20and%20seasonId={target_season}"

    sum_data, pct_data = await asyncio.gather(
        fetch_with_cache(f"adv-sum:{target_season}", sum_url, CACHE_TTL["advanced"]),
        fetch_with_cache(f"adv-pct:{target_season}", pct_url, CACHE_TTL["advanced"]),
    )

    sum_rows = sum_data.get("data", []) if isinstance(sum_data, dict) else []
    pct_rows = pct_data.get("data", []) if isinstance(pct_data, dict) else []
    pct_map = {normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev")): r for r in pct_rows if isinstance(r, dict)}

    teams = []
    for r in sum_rows:
        if not isinstance(r, dict):
            continue
        ab = normalize_team_abbr(r.get("teamFullName") or r.get("teamAbbrev") or "")
        p = pct_map.get(ab, {})
        sf = float(r.get("shotsForPerGame") or 30.0)
        sa = float(r.get("shotsAgainstPerGame") or 30.0)
        calc_sat = ((sf / (sf + sa or 1)) * 100)

        sat_raw = r.get("satPct") or p.get("satPct") or p.get("satPercentage")
        sat = (sat_raw * 100 if sat_raw and sat_raw <= 1 else sat_raw) if sat_raw is not None else calc_sat

        usat_raw = r.get("usatPct") or p.get("usatPct") or p.get("usatPercentage")
        usat = (usat_raw * 100 if usat_raw and usat_raw <= 1 else usat_raw) if usat_raw is not None else (calc_sat * 0.98)

        pdo = float(p.get("pdo") or 100.2)
        ozsp = float(p.get("zoneStartPct") or p.get("offensiveZoneStartPct") or 51.4)

        teams.append({
            "teamAbbrev": ab,
            "teamName": r.get("teamFullName") or ab,
            "satPct": round(float(sat), 1),
            "usatPct": round(float(usat), 1),
            "pdo": round(pdo, 1),
            "ozsp": round(ozsp, 1),
            "shotsForPerGame": round(sf, 1),
            "shotsAgainstPerGame": round(sa, 1),
        })

    return {"season": target_season, "teams": teams}


# 7. Реальный сервер голосования Pick'em
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

    total = sum(current.values()) or 1
    away_pct = round((current["away"] / total) * 100)
    tie_pct = round((current["tie"] / total) * 100)
    home_pct = 100 - away_pct - tie_pct

    return JSONResponse({
        "gameId": game_id,
        "votes": current,
        "total": total,
        "awayPct": away_pct,
        "tiePct": tie_pct,
        "homePct": home_pct,
    })


# 8. Потолок зарплат клуба (Salary Cap)
@app.get("/api/team-cap/{team}")
async def team_cap(team: str):
    ab = normalize_team_abbr(team)
    cap_limit = 88.0
    return {
        "team": ab,
        "salaryCapLimit": f"${cap_limit:.1f}M",
        "projectedCapHit": f"${cap_limit - 2.4:.1f}M",
        "capSpace": "$2.4M",
        "contractsCount": 46,
    }


# 9. Автоматический поиск видеообзора на YouTube
@app.get("/api/game-youtube-recap")
async def game_youtube_recap(away: str, home: str, date: str):
    query = f"NHL highlights {away} vs {home} {date}"
    cache_key = f"yt:recap:{away}:{home}:{date}"
    now = time.time()
    cached = _cache.get(cache_key)

    if cached and now - cached[0] < CACHE_TTL["video"]:
        return cached[1]

    search_url = f"https://www.youtube.com/results?search_query={httpx.QueryParams({'search_query': query})}"

    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        try:
            resp = await client.get(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
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
                _cache[cache_key] = (now, result)
                return result
        except Exception:
            pass

    return {"videoId": None, "embedUrl": None}


# 10. Трансферы и переходы от ESPN
@app.get("/api/transactions")
async def transactions():
    url = f"{ESPN_BASE}/transactions"
    data = await fetch_with_cache("espn:transactions", url, CACHE_TTL["transactions"])
    if not isinstance(data, dict):
        return {"transactions": []}

    raw_tx = data.get("transactions", [])
    if not isinstance(raw_tx, list):
        return {"transactions": []}

    result = []
    for t in raw_tx[:50]:
        if not isinstance(t, dict):
            continue
        team_obj = t.get("team") or {}
        team_name = team_obj.get("displayName") or team_obj.get("name") or ""
        result.append({
            "date": t.get("date", ""),
            "description": t.get("description") or t.get("text") or "",
            "team": normalize_team_abbr(team_name),
        })

    return {"transactions": result}
# =======================================================
# === НАЧАЛО: API ЛЕНТЫ НОВОСТЕЙ ========================
# =======================================================
@app.get("/api/news")
async def get_news():
    """Возвращает список последних 30 новостей из Telegram-канала."""
    return {"news": _news_store}

@app.get("/api/news/photo/{file_id}")
async def get_news_photo(file_id: str):
    """Безопасно проксирует фото из Telegram, не раскрывая BOT_TOKEN клиенту."""
    if not BOT_TOKEN or not file_id:
        return JSONResponse({"error": "No token or file_id"}, status_code=404)
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 1. Запрашиваем путь к файлу у Telegram
            file_info_resp = await client.get(f"{TELEGRAM_API}/getFile?file_id={file_id}")
            if file_info_resp.status_code != 200:
                return JSONResponse({"error": "Failed to get file info"}, status_code=404)
            
            file_path = file_info_resp.json().get("result", {}).get("file_path")
            if not file_path:
                return JSONResponse({"error": "File path not found"}, status_code=404)

            # 2. Скачиваем байты фото и отдаем браузеру
            img_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            img_resp = await client.get(img_url)
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            
            from fastapi.responses import Response
            return Response(content=img_resp.content, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
# =======================================================
# === КОНЕЦ: API ЛЕНТЫ НОВОСТЕЙ =========================
# =======================================================

# Базовые NHL эндпоинты
@app.get("/api/seasons-list")
async def seasons_list():
    return await fetch_with_cache("seasons-list", f"{NHL_BASE}/standings-season", CACHE_TTL["standings"])


@app.get("/api/playoff-bracket/{year}")
async def playoff_bracket(year: str):
    return await fetch_with_cache(f"bracket:{year}", f"{NHL_BASE}/playoff-bracket/{year}", CACHE_TTL["standings"])


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


@app.get("/api/roster-stats/{team}")
async def roster_stats(team: str, season: str | None = None, gameType: str = "2"):
    team_upper = normalize_team_abbr(team)
    target_season = season or current_season_id()
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


@app.get("/api/boxscore/{game_id}")
async def boxscore(game_id: str):
    return await fetch_with_cache(f"boxscore:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/boxscore", CACHE_TTL["boxscore"])


@app.get("/api/right-rail/{game_id}")
async def right_rail(game_id: str):
    return await fetch_with_cache(f"rightrail:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/right-rail", CACHE_TTL["rightrail"])


@app.get("/api/score/{game_id}")
async def score(game_id: str):
    return await fetch_with_cache(f"score:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/landing", CACHE_TTL["score"])


@app.get("/api/injuries")
async def get_injuries():
    url = f"{ESPN_BASE}/injuries"
    data = await fetch_with_cache("espn:injuries", url, CACHE_TTL["espn"])
    if not isinstance(data, dict):
        return {}

    teams_data = data.get("injuries", [])
    result = {}
    if not isinstance(teams_data, list):
        return {}

    for item in teams_data:
        if not isinstance(item, dict):
            continue
        team_abbr = normalize_team_abbr(item.get("displayName") or item.get("name") or "")
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
            detail_desc = details.get("type") or details.get("detail") or inj.get("type") or inj.get("shortComment") or ""
            status = inj.get("status") or "Injured"
            headshot = athlete.get("headshot", {}).get("href", "") if isinstance(athlete.get("headshot"), dict) else (athlete.get("headshot") or "")

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


@app.get("/api/scoreboard-espn")
async def get_scoreboard_espn(date: str | None = None):
    params = f"?dates={date.replace('-', '')}" if date else ""
    url = f"{ESPN_BASE}/scoreboard{params}"
    cache_key = f"espn:scoreboard:{date or 'today'}"
    data = await fetch_with_cache(cache_key, url, CACHE_TTL["espn"])
    if not isinstance(data, dict):
        return []
    return data.get("events", []) if isinstance(data.get("events"), list) else []


# Предматчевый аналитический центр
@app.get("/api/pregame/{game_id}")
async def pregame(
    game_id: str,
    date: str | None = None,
    away: str | None = None,
    home: str | None = None,
):
    current_season = current_season_id()

    rail_task = fetch_with_cache(f"rightrail:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/right-rail", CACHE_TTL["rightrail"])
    landing_task = fetch_with_cache(f"landing:{game_id}", f"{NHL_BASE}/gamecenter/{game_id}/landing", CACHE_TTL["score"])
    standings_task = fetch_with_cache("standings", f"{NHL_BASE}/standings/now", CACHE_TTL["standings"])
    injuries_task = fetch_espn_injuries()
    summary_task = fetch_with_cache(
        f"team-summary:{current_season}",
        f"{NHL_STATS_BASE}/team/summary?isAggregate=false&isGame=false&cayenneExp=gameTypeId=2%20and%20seasonId={current_season}",
        CACHE_TTL["standings"]
    )

    rail_data, landing_data, standings_data, injuries_data, summary_data = await asyncio.gather(
        rail_task,
        landing_task,
        standings_task,
        injuries_task,
        summary_task,
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
        make_comp("powerPlayPctg", "Большинство (%PP)", away_spec.get("pp") or away_st.get("powerPlayPctg"), home_spec.get("pp") or home_st.get("powerPlayPctg"), True),
        make_comp("penaltyKillPctg", "Меньшинство (%PK)", away_spec.get("pk") or away_st.get("penaltyKillPctg"), home_spec.get("pk") or home_st.get("penaltyKillPctg"), True),
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


# Telegram Webhook
@app.post("/webhook")
async def telegram_webhook(update: dict):
    # === Обработка новых постов из Telegram-канала ===
    channel_post = update.get("channel_post")
    if channel_post:
        chat = channel_post.get("chat", {})
        channel_username = chat.get("username", "")
        message_id = channel_post.get("message_id")
        
        # Получаем текст (для обычных постов) или подпись к фото (caption)
        raw_text = channel_post.get("text") or channel_post.get("caption") or ""
        
        # Первая строчка поста — заголовок, остальное — описание
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        title = lines[0] if lines else "Новость канала"
        short_desc = lines[1] if len(lines) > 1 else (raw_text[:140] + "..." if len(raw_text) > 140 else raw_text)

        # Ссылка на пост в Telegram
        if channel_username:
            post_link = f"https://t.me/{channel_username}/{message_id}"
        else:
            # Для закрытых каналов
            clean_id = str(chat.get("id", "")).replace("-100", "")
            post_link = f"https://t.me/c/{clean_id}/{message_id}"

        # Проверяем наличие фото (берём в наилучшем разрешении)
        photo_id = ""
        photos = channel_post.get("photo", [])
        if isinstance(photos, list) and photos:
            photo_id = photos[-1].get("file_id", "")

        # Форматируем дату (МСК)
        post_ts = channel_post.get("date", time.time())
        date_str = time.strftime("%d.%m в %H:%M", time.localtime(post_ts + 3 * 3600))

        news_item = {
            "id": message_id,
            "title": title,
            "desc": short_desc,
            "link": post_link,
            "photo_id": photo_id,
            "date": date_str,
            "timestamp": post_ts
        }

        # Добавляем в начало списка и сохраняем
        global _news_store
        _news_store = [n for n in _news_store if n.get("id") != message_id]
        _news_store.insert(0, news_item)
        _news_store = _news_store[:30]
        save_news_to_disk(_news_store)
        return {"ok": True}

    # === Обработка личных команд боту (/start и др.) ===
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text in ("/start", "/matches", "/standings", "/leaders", "/goalies", "/players", "/transactions"):
        keyboard = {
            "inline_keyboard": [
                [{"text": "🏒 ОТКРЫТЬ NHL", "web_app": {"url": WEBAPP_URL}}],
                [
                    {"text": "📅 Матчи", "web_app": {"url": f"{WEBAPP_URL}?section=matches"}},
                    {"text": "📊 Таблица", "web_app": {"url": f"{WEBAPP_URL}?section=standings"}},
                ],
                [
                    {"text": "🏆 Лидеры", "web_app": {"url": f"{WEBAPP_URL}?section=leaders"}},
                    {"text": "🔄 Трансферы", "web_app": {"url": f"{WEBAPP_URL}?section=transactions"}},
                ],
            ],
        }

        async with httpx.AsyncClient(timeout=12) as client:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "🏒 NHL LIVE\n\n"
                        "Всё главное по NHL — в одном месте.\n\n"
                        "📅 Матчи, результаты и обзоры\n"
                        "📊 Турнирная таблица\n"
                        "🏆 Лидеры сезона\n"
                        "🔄 Трансферы и травмы лиги\n\n"
                        "Открой приложение и смотри NHL прямо в Telegram."
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
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    if STATIC_INDEX.is_file():
        return FileResponse(str(STATIC_INDEX), media_type="text/html")
    if ROOT_INDEX.is_file():
        return FileResponse(str(ROOT_INDEX), media_type="text/html")
    return {"detail": "index.html not found"}
