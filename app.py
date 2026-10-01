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

# Render запускает приложение из корня репозитория. В текущей структуре
# index.html лежит рядом с app.py, поэтому корневой URL / должен отдавать
# именно этот файл. При этом оставляем поддержку старой структуры static/.
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
