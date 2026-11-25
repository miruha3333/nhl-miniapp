(function () {
  let ahlSeasons = [];
  let ahlSelectedSeasonId = "";
  let ahlStandingsData = [];
  let ahlStandingsMode = "all";
  let ahlStandingsSortKey = "points";
  let ahlStandingsSortAsc = false;

  let ahlLeadersType = "skaters";
  let ahlSkaterCat = "points";
  let ahlGoalieCat = "wins";
  let ahlGoalieSortAsc = false;
  let ahlLeadersLimit = 25;
  let ahlCachedSkaters = [];
  let ahlCachedGoalies = [];
  let ahlSearchFilter = "";

  let ahlTeamData = null;
  let ahlTeamSortKey = "points";
  let ahlTeamSortAsc = false;

  function ahlGoalStr(v, fb = "—") {
    return typeof val === "function" ? val(v, fb) : (v === undefined || v === null || v === "" ? fb : v);
  }

  function formatAhlTime(game) {
    if (game?.startTimeUTC) {
      try {
        return new Date(game.startTimeUTC).toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Europe/Moscow",
        });
      } catch (_) {}
    }
    return game?.scheduleTime || "vs";
  }

  function formatAhlPos(pos) {
    const up = String(pos || "").toUpperCase().trim();
    if (up === "L") return "LW";
    if (up === "R") return "RW";
    return up;
  }

  function hlPersonName(obj) {
    if (!obj) return "";
    if (typeof obj === "string") return obj.trim();
    const full = `${obj.first_name || obj.firstName || ""} ${obj.last_name || obj.lastName || ""}`.trim();
    return full || obj.name || obj.full_name || "";
  }

  function hlPersonId(obj) {
    if (!obj || typeof obj !== "object") return "";
    return String(obj.player_id || obj.id || "");
  }

  async function ensureSeasonsLoaded() {
    if (ahlSeasons.length) return ahlSeasons;
    try {
      const res = await fetch(`${API_BASE}/api/ahl/seasons`);
      const data = await res.json();
      ahlSeasons = Array.isArray(data?.seasons) ? data.seasons : [];
      if (!ahlSelectedSeasonId && data?.currentSeasonId) {
        ahlSelectedSeasonId = String(data.currentSeasonId);
      }
    } catch (_) {
      ahlSeasons = [];
    }
    return ahlSeasons;
  }

  async function populateSeasonSelect() {
    const select = document.getElementById("season-select");
    if (!select) return;
    const list = await ensureSeasonsLoaded();
    if (!list.length) {
      select.innerHTML = "<option value=''>Текущий сезон AHL</option>";
      return;
    }
    select.innerHTML = list
      .filter(s => !s.isPlayoff)
      .slice(0, 20)
      .map(s => {
        const sel = String(s.id) === String(ahlSelectedSeasonId) ? "selected" : "";
        return `<option value="${escapeHtml(s.id)}" ${sel}>${escapeHtml(s.name)}</option>`;
      }).join("");
  }

  function setSeason(seasonId) {
    ahlSelectedSeasonId = String(seasonId || "");
    ahlStandingsData = [];
    ahlCachedSkaters = [];
    ahlCachedGoalies = [];
  }

  function updateUiForLeague(league) {
    const isAhl = league === "AHL";
    document.querySelectorAll("#league-switch .league-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.league === league);
    });

    // Скрываем вкладки, которых нет в AHL (Драфт, Трансферы, Новости)
    ["tab-draft", "tab-transactions", "tab-news"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAhl ? "none" : "";
    });

    // В таблице скрываем NHL-only кнопки (Wild Card и Продвинутая)
    ["std-mode-wc", "std-mode-adv"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAhl ? "none" : "";
    });
    const bracket = document.getElementById("bracket-container");
    if (bracket && isAhl) bracket.innerHTML = "";

    // В лидерах скрываем NHL-only фильтры (Защитники, Новички, Избранные) и недоступные в AHL метрики
    ["leaders-def-btn", "leaders-rookies-btn", "leaders-favs-btn"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAhl ? "none" : "";
    });
    ["hits", "blockedShots", "toiPerGame"].forEach(cat => {
      const btn = document.querySelector(`#skater-categories button[data-cat="${cat}"]`);
      if (btn) btn.style.display = isAhl ? "none" : "";
    });
    const gsBtn = document.querySelector('#goalie-categories button[data-goalie-sort="gamesStarted"]');
    if (gsBtn) gsBtn.style.display = isAhl ? "none" : "";

    const searchInput = document.getElementById("player-search-input");
    if (searchInput) {
      searchInput.placeholder = isAhl
        ? "🔍 Фильтр игроков AHL по имени или клубу..."
        : "🔍 Поиск любого игрока NHL (например: Ovechkin, McDavid)...";
      searchInput.value = "";
      ahlSearchFilter = "";
      const sr = document.getElementById("player-search-results");
      if (sr) sr.style.display = "none";
    }

    if (isAhl) {
      if (["draft", "transactions", "news"].includes(lastMainTab)) {
        lastMainTab = "schedule";
      }
      if (ahlStandingsMode !== "all" && ahlStandingsMode !== "conf" && ahlStandingsMode !== "div") {
        ahlStandingsMode = "all";
      }
    }
  }

  // 1. МАТЧИ AHL
  async function loadSchedule(silent = false) {
    const gamesBox = document.getElementById("games");
    const dateInput = document.getElementById("date-picker");
    const liveBanner = document.getElementById("live-status-banner");
    const date = fmtDate(currentDate);

    if (!silent && gamesBox) gamesBox.innerHTML = '<div class="loading">Загрузка матчей AHL...</div>';
    if (dateInput) dateInput.value = date;

    try {
      const res = await fetch(`${API_BASE}/api/ahl/schedule?date=${encodeURIComponent(date)}`);
      const data = await res.json();
      const list = Array.isArray(data?.games) ? data.games : [];

      if (!list.length) {
        if (liveBanner) liveBanner.style.display = "none";
        stopLivePolling();
        if (gamesBox) gamesBox.innerHTML = '<div class="empty">В этот день матчей AHL нет</div>';
        return;
      }

      if (gamesBox) {
        gamesBox.innerHTML = list.map(g => {
          const away = g.awayTeam || {};
          const home = g.homeTeam || {};
          const status = g.started
            ? (g.isLive ? `● ${g.statusText || "LIVE"}` : "Финал")
            : formatAhlTime(g);

          return `
            <div class="card">
              <div class="game-row">
                <div class="team ahl-team-btn" data-ahl-team-id="${escapeHtml(away.id)}" data-ahl-team-name="${escapeHtml(away.name)}" data-ahl-team-abbr="${escapeHtml(away.abbrev)}" data-ahl-team-logo="${escapeHtml(away.logo)}">
                  <img class="team-logo" src="${escapeHtml(away.logo)}" alt="" onerror="this.style.visibility='hidden'">
                  <div>
                    <div class="abbr">${escapeHtml(away.abbrev || away.name)}</div>
                    ${away.record ? `<div class="team-record"><strong>${escapeHtml(away.record)}</strong></div>` : ""}
                  </div>
                </div>

                <div class="score-box game-center ${g.started ? "clickable" : ""}" data-ahl-game-id="${escapeHtml(g.id)}" data-ahl-away="${escapeHtml(away.abbrev)}" data-ahl-home="${escapeHtml(home.abbrev)}" data-ahl-away-logo="${escapeHtml(away.logo)}" data-ahl-home-logo="${escapeHtml(home.logo)}">
                  <div class="score" style="color:#ffffff;">${g.started ? `${away.score ?? 0} : ${home.score ?? 0}` : "vs"}</div>
                  <div class="status ${g.isLive ? "live-pulse" : ""}">${escapeHtml(status)}</div>
                </div>

                <div class="team right ahl-team-btn" data-ahl-team-id="${escapeHtml(home.id)}" data-ahl-team-name="${escapeHtml(home.name)}" data-ahl-team-abbr="${escapeHtml(home.abbrev)}" data-ahl-team-logo="${escapeHtml(home.logo)}">
                  <div>
                    <div class="abbr">${escapeHtml(home.abbrev || home.name)}</div>
                    ${home.record ? `<div class="team-record"><strong>${escapeHtml(home.record)}</strong></div>` : ""}
                  </div>
                  <img class="team-logo" src="${escapeHtml(home.logo)}" alt="" onerror="this.style.visibility='hidden'">
                </div>
              </div>
            </div>
          `;
        }).join("");
      }

      const hasLive = list.some(g => g.isLive);
      if (liveBanner) liveBanner.style.display = hasLive ? "flex" : "none";
      if (hasLive && lastMainTab === "schedule" && document.getElementById("view-detail")?.style.display === "none") {
        startLivePolling(() => loadSchedule(true), 20000);
      } else if (!hasLive) {
        stopLivePolling();
      }
    } catch (_) {
      if (!silent && gamesBox) gamesBox.innerHTML = '<div class="empty">Не удалось загрузить матчи AHL</div>';
    }
  }

  // 2. ТАБЛИЦА AHL
  function setStandingsMode(mode) {
    ahlStandingsMode = ["all", "conf", "div"].includes(mode) ? mode : "all";
    document.getElementById("std-mode-all")?.classList.toggle("active", ahlStandingsMode === "all");
    document.getElementById("std-mode-conf")?.classList.toggle("active", ahlStandingsMode === "conf");
    document.getElementById("std-mode-div")?.classList.toggle("active", ahlStandingsMode === "div");
    document.getElementById("std-mode-wc")?.classList.remove("active");
    document.getElementById("std-mode-adv")?.classList.remove("active");

    const regTable = document.getElementById("standings-table-regular");
    const advTable = document.getElementById("standings-table-advanced");
    if (advTable) advTable.style.display = "none";
    if (regTable) regTable.style.display = "block";

    renderStandings();
  }

  function sortStandingsBy(key) {
    ahlStandingsSortAsc = ahlStandingsSortKey === key ? !ahlStandingsSortAsc : false;
    ahlStandingsSortKey = key;
    renderStandings();
  }

  function renderAhlTeamRow(t, rank) {
    const diff = Number(t.goalDifferential ?? (t.goalFor - t.goalAgainst));
    let clinchHtml = "";
    if (t.clinch) {
      const c = String(t.clinch).replace(/[^a-zA-Z]/g, "").toUpperCase();
      if (c) clinchHtml = `<span class="clinch-badge clinch-x">${escapeHtml(c)}</span>`;
    }
    return `
      <div class="standings-row" data-ahl-team-id="${escapeHtml(t.teamId)}" data-ahl-team-name="${escapeHtml(t.teamName)}" data-ahl-team-abbr="${escapeHtml(t.teamAbbrev)}" data-ahl-team-logo="${escapeHtml(t.logo)}">
        <div class="num sticky-col sticky-col-1">${rank}</div>
        <div class="sticky-col sticky-col-2">
          <img class="team-logo" src="${escapeHtml(t.logo)}" alt="" onerror="this.style.visibility='hidden'">
        </div>
        <div class="name sticky-col sticky-col-3">${escapeHtml(t.teamAbbrev || t.teamName)} ${clinchHtml}</div>
        <div class="num" style="color:#ffffff;">${t.gamesPlayed ?? 0}</div>
        <div class="num" style="color:#ffffff;">${t.wins ?? 0}</div>
        <div class="num" style="color:#ffffff;">${t.otLosses ?? 0}</div>
        <div class="num" style="color:#ffffff;">${t.losses ?? 0}</div>
        <div class="num" style="color:#ffffff;">${t.goalFor ?? 0}</div>
        <div class="num" style="color:#ffffff;">${t.goalAgainst ?? 0}</div>
        <div class="diff" style="color:${diff >= 0 ? "#2ecc71" : "#e74c3c"}">${diff > 0 ? "+" : ""}${diff}</div>
        <div class="pts" style="color:#ffffff !important;font-weight:700;">${t.points ?? 0}</div>
      </div>
    `;
  }

  function renderStandings() {
    const body = document.getElementById("standings-body");
    if (!body) return;
    if (!ahlStandingsData.length) {
      body.innerHTML = '<div class="empty">Нет данных таблицы AHL</div>';
      return;
    }

    const sortList = (arr) => [...arr].sort((a, b) => {
      const va = Number(a[ahlStandingsSortKey] ?? 0);
      const vb = Number(b[ahlStandingsSortKey] ?? 0);
      return ahlStandingsSortAsc ? va - vb : vb - va;
    });

    let html = "";
    if (ahlStandingsMode === "all") {
      html = sortList(ahlStandingsData).map((t, i) => renderAhlTeamRow(t, i + 1)).join("");
    } else {
      const field = ahlStandingsMode === "conf" ? "conferenceName" : "divisionName";
      const groups = {};
      ahlStandingsData.forEach(t => {
        const g = t[field] || "AHL";
        if (!groups[g]) groups[g] = [];
        groups[g].push(t);
      });
      Object.keys(groups).sort().forEach(g => {
        html += `<div class="group-header-row">${escapeHtml(g)}</div>`;
        html += sortList(groups[g]).map((t, i) => renderAhlTeamRow(t, i + 1)).join("");
      });
    }
    body.innerHTML = html;
  }

  async function loadStandings() {
    const body = document.getElementById("standings-body");
    if (body) body.innerHTML = '<div class="loading">Загрузка таблицы AHL...</div>';
    await populateSeasonSelect();

    try {
      const qs = ahlSelectedSeasonId ? `?season=${encodeURIComponent(ahlSelectedSeasonId)}` : "";
      const res = await fetch(`${API_BASE}/api/ahl/standings${qs}`);
      const data = await res.json();
      ahlStandingsData = Array.isArray(data?.standings) ? data.standings : [];
      setStandingsMode(ahlStandingsMode);
    } catch (_) {
      if (body) body.innerHTML = '<div class="empty">Не удалось загрузить таблицу AHL</div>';
    }
  }

  // 3. ЛИДЕРЫ AHL
  function renderLeadersList() {
    const body = document.getElementById("players-body");
    if (!body) return;

    const isGoalies = ahlLeadersType === "goalies";
    const source = isGoalies ? ahlCachedGoalies : ahlCachedSkaters;
    if (!source.length) {
      body.innerHTML = '<div class="empty">Нет данных лидеров AHL</div>';
      return;
    }

    let list = [...source];
    if (ahlSearchFilter) {
      const q = ahlSearchFilter.toLowerCase();
      list = list.filter(p =>
        String(p.name || "").toLowerCase().includes(q) ||
        String(p.teamAbbrev || "").toLowerCase().includes(q)
      );
    }

    if (isGoalies) {
      const maxGp = Math.max(...list.map(g => g.gamesPlayed || 0), 5);
      const minGp = Math.max(1, Math.floor(maxGp * 0.25));
      if (ahlGoalieCat === "savePctg" || ahlGoalieCat === "gaa") {
        const qual = list.filter(g => (g.gamesPlayed || 0) >= minGp);
        if (qual.length >= 5) list = qual;
      }
      list.sort((a, b) => {
        const va = Number(a[ahlGoalieCat] ?? 0);
        const vb = Number(b[ahlGoalieCat] ?? 0);
        return ahlGoalieSortAsc ? va - vb : vb - va;
      });
    } else {
      list.sort((a, b) => Number(b[ahlSkaterCat] ?? 0) - Number(a[ahlSkaterCat] ?? 0));
    }

    const visible = list.slice(0, ahlLeadersLimit);
    if (!visible.length) {
      body.innerHTML = '<div class="empty">Ничего не найдено</div>';
      return;
    }

    let html = visible.map((p, idx) => {
      let valStr = isGoalies ? (p[ahlGoalieCat] ?? "—") : (p[ahlSkaterCat] ?? "—");
      if (isGoalies && ahlGoalieCat === "savePctg") valStr = Number(valStr).toFixed(3);
      else if (isGoalies && ahlGoalieCat === "gaa") valStr = Number(valStr).toFixed(2);
      else if (!isGoalies && ahlSkaterCat === "plusMinus" && Number(valStr) > 0) valStr = `+${valStr}`;
      const posStr = p.position ? ` · ${formatAhlPos(p.position)}` : "";

      return `
        <div class="player-row" data-ahl-player-id="${escapeHtml(p.id)}">
          <div class="rank">${idx + 1}</div>
          <img class="headshot" src="${escapeHtml(p.headshot)}" alt="" onerror="this.src='https://assets.nhle.com/mugs/nhl/default-player.png'">
          <div class="info">
            <div class="pname">${escapeHtml(p.name)}</div>
            <div class="pteam">
              ${p.teamId ? `<img class="team-logo" src="https://assets.leaguestat.com/ahl/logos/${escapeHtml(p.teamId)}.png" alt="" onerror="this.style.display='none'">` : ""}
              <span>${escapeHtml(p.teamAbbrev || "")}${escapeHtml(posStr)}</span>
            </div>
          </div>
          <div class="pgames">${p.gamesPlayed ?? 0}</div>
          <div class="pvalue">${escapeHtml(String(valStr))}</div>
        </div>
      `;
    }).join("");

    if (list.length > ahlLeadersLimit) {
      html += `<button class="show-more" id="ahl-leaders-more">Показать ещё (+25)</button>`;
    }

    body.innerHTML = html;
    const moreBtn = document.getElementById("ahl-leaders-more");
    if (moreBtn) {
      moreBtn.onclick = () => {
        ahlLeadersLimit += 25;
        renderLeadersList();
      };
    }
  }

  async function loadPlayers() {
    const body = document.getElementById("players-body");
    if (body) body.innerHTML = '<div class="loading">Загрузка лидеров AHL...</div>';

    const isGoalies = ahlLeadersType === "goalies";
    document.getElementById("leaders-all-btn")?.classList.toggle("active", !isGoalies);
    document.getElementById("leaders-goalies-btn")?.classList.toggle("active", isGoalies);
    const sCat = document.getElementById("skater-categories");
    if (sCat) sCat.style.display = isGoalies ? "none" : "grid";
    const gCat = document.getElementById("goalie-categories");
    if (gCat) gCat.style.display = isGoalies ? "grid" : "none";

    if (isGoalies && ahlCachedGoalies.length) {
      renderLeadersList();
      return;
    }
    if (!isGoalies && ahlCachedSkaters.length) {
      renderLeadersList();
      return;
    }

    try {
      const qs = new URLSearchParams({ type: ahlLeadersType });
      if (ahlSelectedSeasonId) qs.set("season", ahlSelectedSeasonId);
      const res = await fetch(`${API_BASE}/api/ahl/leaders?${qs}`);
      const data = await res.json();
      const players = Array.isArray(data?.players) ? data.players : [];
      if (isGoalies) ahlCachedGoalies = players;
      else ahlCachedSkaters = players;
      renderLeadersList();
    } catch (_) {
      if (body) body.innerHTML = '<div class="empty">Не удалось загрузить лидеров AHL</div>';
    }
  }

  function setLeadersMode(mode, cat = "") {
    ahlLeadersLimit = 25;
    if (mode === "goalies") {
      ahlLeadersType = "goalies";
      if (cat) {
        ahlGoalieSortAsc = ahlGoalieCat === cat ? !ahlGoalieSortAsc : (cat === "gaa" || cat === "losses");
        ahlGoalieCat = cat;
      }
    } else {
      ahlLeadersType = "skaters";
      if (cat) ahlSkaterCat = cat;
    }
    loadPlayers();
  }

  function setSearchFilter(q) {
    ahlSearchFilter = String(q || "").trim();
    ahlLeadersLimit = 25;
    const clearBtn = document.getElementById("player-search-clear");
    if (clearBtn) clearBtn.style.display = ahlSearchFilter ? "flex" : "none";
    renderLeadersList();
  }

  // 4. ПРОТОКОЛ МАТЧА AHL
  async function openGameDetail(gameId, awayFallback = {}, homeFallback = {}, silent = false) {
    if (!silent) {
      openDetail({ type: "ahl-game", fn: () => openGameDetail(gameId, awayFallback, homeFallback) });
    }
    const body = document.getElementById("detail-body");

    try {
      const res = await fetch(`${API_BASE}/api/ahl/game/${encodeURIComponent(gameId)}`);
      const g = await res.json();
      const meta = g.meta || {};
      const away = g.visitor || awayFallback || {};
      const home = g.home || homeFallback || {};

      const awayId = String(away.id || awayFallback.id || "");
      const homeId = String(home.id || homeFallback.id || "");
      const awayAbbr = away.code || awayFallback.abbrev || away.name || "AWAY";
      const homeAbbr = home.code || homeFallback.abbrev || home.name || "HOME";
      const awayLogo = away.logo || awayFallback.logo || (awayId ? `https://assets.leaguestat.com/ahl/logos/${awayId}.png` : "");
      const homeLogo = home.logo || homeFallback.logo || (homeId ? `https://assets.leaguestat.com/ahl/logos/${homeId}.png` : "");

      const awayScore = meta.visiting_goal_count ?? meta.visitor_score ?? away.goals ?? 0;
      const homeScore = meta.home_goal_count ?? meta.home_score ?? home.goals ?? 0;
      const isFinal = meta.final === "1" || meta.status === "4" || /final/i.test(meta.game_status || "");
      const isLive = !isFinal && (meta.started === "1" || meta.status === "2" || meta.status === "3");

      const statusText = isFinal
        ? "ФИНАЛ (AHL)"
        : (isLive ? `● LIVE ${meta.period ? `${meta.period}П` : ""} ${meta.game_clock || ""}`.trim() : "МАТЧ AHL");

      let html = `
        <div class="detail-head-game">
          <img class="team-logo" src="${escapeHtml(awayLogo)}" alt="" data-ahl-team-id="${escapeHtml(awayId)}" data-ahl-team-name="${escapeHtml(away.name || awayAbbr)}" data-ahl-team-abbr="${escapeHtml(awayAbbr)}" data-ahl-team-logo="${escapeHtml(awayLogo)}" style="cursor:pointer;" onerror="this.style.visibility='hidden'">
          <div>
            <div class="title">${escapeHtml(awayAbbr)} ${awayScore} : ${homeScore} ${escapeHtml(homeAbbr)}</div>
            <div class="subtitle" style="color:#2ecc71;font-weight:700;">${escapeHtml(statusText)}</div>
          </div>
          <img class="team-logo" src="${escapeHtml(homeLogo)}" alt="" data-ahl-team-id="${escapeHtml(homeId)}" data-ahl-team-name="${escapeHtml(home.name || homeAbbr)}" data-ahl-team-abbr="${escapeHtml(homeAbbr)}" data-ahl-team-logo="${escapeHtml(homeLogo)}" style="cursor:pointer;" onerror="this.style.visibility='hidden'">
        </div>
      `;

      const stars = Array.isArray(g.mvp) ? g.mvp : (Array.isArray(g.three_stars) ? g.three_stars : []);
      if (stars.length) {
        const titles = ["1-я звезда", "2-я звезда", "3-я звезда"];
        const badges = ["🥇", "🥈", "🥉"];
        html += `
          <div class="section-title">Три звезды матча</div>
          <div style="display:grid;grid-template-columns:repeat(${Math.min(3, stars.length)}, 1fr);gap:8px;margin-bottom:14px;">
            ${stars.slice(0, 3).map((s, idx) => {
              const pid = hlPersonId(s);
              const name = hlPersonName(s) || "Игрок";
              return `
                <div class="card" style="padding:10px 4px;text-align:center;display:flex;flex-direction:column;align-items:center;cursor:pointer;" data-ahl-player-id="${escapeHtml(pid)}">
                  <div style="font-size:11px;font-family:'Oswald',sans-serif;color:var(--silver-dim);margin-bottom:6px;text-transform:uppercase;">${badges[idx]} ${titles[idx]}</div>
                  <img src="https://assets.leaguestat.com/ahl/240x240/${escapeHtml(pid)}.jpg" style="width:46px;height:46px;border-radius:50%;object-fit:cover;background:var(--surface-2);border:1px solid var(--border);" onerror="this.src='https://assets.nhle.com/mugs/nhl/default-player.png'">
                  <div style="font-family:'Oswald',sans-serif;font-weight:700;font-size:12px;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;">${escapeHtml(name)}</div>
                </div>
              `;
            }).join("")}
          </div>
        `;
      }

      // Голы
      html += '<div class="section-title">Голы</div>';
      const goals = Array.isArray(g.goals) ? g.goals : [];
      if (!goals.length) {
        html += '<div class="empty">Голов в матче не было</div>';
      } else {
        let curPer = "";
        goals.forEach(gl => {
          const perLabel = typeof gl.period === "object" ? (gl.period.long_name || gl.period.short_name || "") : `${gl.period}-й период`;
          if (perLabel && perLabel !== curPer) {
            curPer = perLabel;
            html += `<div class="period-label">${escapeHtml(perLabel)}</div>`;
          }
          const scorerName = hlPersonName(gl.goal_scorer) || "Игрок";
          const scorerId = hlPersonId(gl.goal_scorer);
          const teamCode = String(gl.team_id || "") === homeId ? homeAbbr : awayAbbr;
          const gNum = gl.scorer_goal_num ? ` <span style="color:#2ecc71;font-family:'Roboto Mono',monospace;font-weight:700;">(${escapeHtml(gl.scorer_goal_num)})</span>` : "";

          const assists = [gl.assist1_player, gl.assist2_player].filter(a => a && hlPersonName(a));
          const assistsHtml = assists.map((a, idx) => {
            const aid = hlPersonId(a);
            const aname = hlPersonName(a);
            const anum = idx === 0 ? gl.assist1_num : gl.assist2_num;
            const numHtml = anum ? ` <span style="color:#3a86ff;font-family:'Roboto Mono',monospace;font-weight:700;">(${escapeHtml(anum)})</span>` : "";
            return `<span class="player-link-inline" data-ahl-player-id="${escapeHtml(aid)}">${escapeHtml(aname)}</span>${numHtml}`;
          }).join(", ");

          const tags = [gl.power_play === "1" ? "PP" : "", gl.short_handed === "1" ? "SH" : "", gl.empty_net === "1" ? "EN" : ""].filter(Boolean).join(",");

          html += `
            <div class="goal-row">
              <div class="time">${escapeHtml(ahlGoalStr(gl.time))}</div>
              <div class="desc">
                <div class="scorer">
                  <span class="${scorerId ? "player-link-inline" : ""}" data-ahl-player-id="${escapeHtml(scorerId)}">${escapeHtml(scorerName)}</span>${gNum}
                  (${escapeHtml(teamCode)})
                  ${tags ? `<span style="font-size:10px;color:#f39c12;">[${escapeHtml(tags)}]</span>` : ""}
                </div>
                ${assistsHtml ? `<div class="assists">Передачи: ${assistsHtml}</div>` : ""}
              </div>
              <div class="scoreline">${gl.visitor_score != null && gl.home_score != null ? `${gl.visitor_score} : ${gl.home_score}` : ""}</div>
            </div>
          `;
        });
      }

      // Удаления
      html += '<div class="section-title">Удаления (Penalties)</div>';
      const penalties = Array.isArray(g.penalties) ? g.penalties : [];
      if (!penalties.length) {
        html += '<div class="empty">Удалений в матче не зафиксировано</div>';
      } else {
        let curPer = "";
        penalties.forEach(p => {
          const perLabel = typeof p.period === "object" ? (p.period.long_name || p.period.short_name || "") : `${p.period}-й период`;
          if (perLabel && perLabel !== curPer) {
            curPer = perLabel;
            html += `<div class="period-label">${escapeHtml(perLabel)}</div>`;
          }
          const pid = hlPersonId(p.player_penalized) || hlPersonId(p.player_served);
          const pName = hlPersonName(p.player_penalized) || (hlPersonName(p.player_served) ? `Командный штраф (отб. ${hlPersonName(p.player_served)})` : "Командный штраф");
          const teamCode = String(p.team_id || "") === homeId ? homeAbbr : awayAbbr;
          const desc = typeof formatPenaltyName === "function" ? formatPenaltyName(p.description || p.lang_penalty_description) : (p.description || "Штраф");
          html += `
            <div class="goal-row">
              <div class="time">${escapeHtml(ahlGoalStr(p.time))}</div>
              <div class="desc">
                <div class="scorer"><span class="${pid ? "player-link-inline" : ""}" data-ahl-player-id="${escapeHtml(pid)}">${escapeHtml(pName)}</span> (${escapeHtml(teamCode)})</div>
                <div class="assists">${escapeHtml(desc)}</div>
              </div>
              <div class="scoreline" style="color:#ff4d4d !important;">${escapeHtml(ahlGoalStr(p.minutes, 2))} мин</div>
            </div>
          `;
        });
      }

      // Составы и статистика игроков
      const renderSideBox = (lineup, abbr) => {
        const players = Array.isArray(lineup?.players) ? lineup.players : [];
        const goalies = Array.isArray(lineup?.goalies) ? lineup.goalies : [];
        let out = "";
        if (players.length) {
          const sorted = [...players].sort((a, b) => (Number(b.points) || 0) - (Number(a.points) || 0) || (Number(b.goals) || 0) - (Number(a.goals) || 0));
          out += `
            <div class="section-title">Полевые игроки — ${escapeHtml(abbr)}</div>
            <div class="table-scroll"><table class="stat-table">
              <thead><tr><th>Игрок</th><th>Г</th><th>П</th><th>О</th><th>+/-</th><th>Б</th><th>Штр</th></tr></thead>
              <tbody>
                ${sorted.map(pl => {
                  const pid = hlPersonId(pl);
                  const pos = formatAhlPos(pl.position);
                  const num = pl.jersey_number != null ? `<span style="color:var(--silver-dim);font-family:'Roboto Mono',monospace;font-size:10px;display:inline-block;min-width:22px;">#${escapeHtml(pl.jersey_number)}</span>` : "";
                  const posHtml = pos ? ` <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">${escapeHtml(pos)}</span>` : "";
                  return `
                    <tr class="clickable-row" data-ahl-player-id="${escapeHtml(pid)}">
                      <td>${num}${escapeHtml(hlPersonName(pl))}${posHtml}</td>
                      <td class="num">${ahlGoalStr(pl.goals, 0)}</td>
                      <td class="num">${ahlGoalStr(pl.assists, 0)}</td>
                      <td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(pl.points, 0)}</td>
                      <td class="num">${ahlGoalStr(pl.plus_minus, 0)}</td>
                      <td class="num">${ahlGoalStr(pl.shots, 0)}</td>
                      <td class="num">${ahlGoalStr(pl.pim, 0)}</td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table></div>
          `;
        }
        if (goalies.length) {
          out += `
            <div class="section-title" style="margin-top:12px;">Вратари — ${escapeHtml(abbr)}</div>
            <div class="table-scroll"><table class="stat-table">
              <thead><tr><th>Вратарь</th><th>Бр</th><th>ОБ</th><th>ПШ</th><th>ВП</th></tr></thead>
              <tbody>
                ${goalies.map(gl => `
                  <tr class="clickable-row" data-ahl-player-id="${escapeHtml(hlPersonId(gl))}">
                    <td>${escapeHtml(hlPersonName(gl))} <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">G</span></td>
                    <td class="num">${ahlGoalStr(gl.shots_against, 0)}</td>
                    <td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(gl.saves, 0)}</td>
                    <td class="num">${ahlGoalStr(gl.goals_against, 0)}</td>
                    <td class="num" style="color:var(--silver-dim);">${escapeHtml(ahlGoalStr(gl.toi))}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table></div>
          `;
        }
        return out;
      };

      html += renderSideBox(g.visitor_team_lineup, awayAbbr);
      html += renderSideBox(g.home_team_lineup, homeAbbr);

      if (body) body.innerHTML = html;

      if (isLive) {
        startLivePolling(() => openGameDetail(gameId, awayFallback, homeFallback, true), 20000);
      } else {
        stopLivePolling();
      }
    } catch (_) {
      if (!silent && body) body.innerHTML = '<div class="empty">Не удалось загрузить протокол матча AHL</div>';
    }
  }

  // 5. КАРТОЧКА КЛУБА AHL
  function renderTeamRoster() {
    const container = document.getElementById("ahl-team-container");
    if (!container || !ahlTeamData) return;

    const skaters = [...(ahlTeamData.skaters || [])].sort((a, b) => {
      const va = Number(a[ahlTeamSortKey] ?? 0);
      const vb = Number(b[ahlTeamSortKey] ?? 0);
      return ahlTeamSortAsc ? va - vb : vb - va;
    });
    const goalies = [...(ahlTeamData.goalies || [])].sort((a, b) => (b.gamesPlayed || 0) - (a.gamesPlayed || 0));

    if (!skaters.length && !goalies.length) {
      container.innerHTML = '<div class="empty">Нет данных состава за этот сезон</div>';
      return;
    }

    const arrow = (col) => ahlTeamSortKey === col ? `<span class="sort-arrow">${ahlTeamSortAsc ? "▲" : "▼"}</span>` : "";

    let html = `
      <div class="section-title">Полевые игроки</div>
      <div class="table-scroll"><table class="stat-table">
        <thead>
          <tr>
            <th>Игрок</th>
            <th class="sortable" data-ahl-tsort="gamesPlayed">И${arrow("gamesPlayed")}</th>
            <th class="sortable" data-ahl-tsort="goals">Г${arrow("goals")}</th>
            <th class="sortable" data-ahl-tsort="assists">П${arrow("assists")}</th>
            <th class="sortable" data-ahl-tsort="points">О${arrow("points")}</th>
            <th class="sortable" data-ahl-tsort="plusMinus">+/-${arrow("plusMinus")}</th>
            <th class="sortable" data-ahl-tsort="penaltyMinutes">Штр${arrow("penaltyMinutes")}</th>
          </tr>
        </thead>
        <tbody>
          ${skaters.map(p => {
            const numHtml = p.sweaterNumber != null ? `<span style="color:var(--silver-dim);font-family:'Roboto Mono',monospace;font-size:10px;display:inline-block;min-width:24px;">#${escapeHtml(p.sweaterNumber)}</span>` : "";
            const pos = formatAhlPos(p.position);
            const posHtml = pos ? ` <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">${escapeHtml(pos)}</span>` : "";
            return `
              <tr class="clickable-row" data-ahl-player-id="${escapeHtml(p.id)}">
                <td>${numHtml}${escapeHtml(p.name)}${posHtml}</td>
                <td class="num">${p.gamesPlayed}</td>
                <td class="num">${p.goals}</td>
                <td class="num">${p.assists}</td>
                <td class="num" style="color:#fff;font-weight:700;">${p.points}</td>
                <td class="num">${p.plusMinus}</td>
                <td class="num">${p.penaltyMinutes}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table></div>
    `;

    if (goalies.length) {
      html += `
        <div class="section-title" style="margin-top:16px;">Вратари</div>
        <div class="table-scroll"><table class="stat-table">
          <thead><tr><th>Вратарь</th><th>И</th><th>В</th><th>П</th><th>%ОБ</th><th>ГКИ</th></tr></thead>
          <tbody>
            ${goalies.map(g => {
              const numHtml = g.sweaterNumber != null ? `<span style="color:var(--silver-dim);font-family:'Roboto Mono',monospace;font-size:10px;display:inline-block;min-width:24px;">#${escapeHtml(g.sweaterNumber)}</span>` : "";
              return `
                <tr class="clickable-row" data-ahl-player-id="${escapeHtml(g.id)}">
                  <td>${numHtml}${escapeHtml(g.name)} <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">G</span></td>
                  <td class="num">${g.gamesPlayed}</td>
                  <td class="num">${g.wins}</td>
                  <td class="num">${g.losses}</td>
                  <td class="num" style="color:#fff;font-weight:700;">${Number(g.savePctg || 0).toFixed(3)}</td>
                  <td class="num">${Number(g.gaa || 0).toFixed(2)}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table></div>
      `;
    }

    container.innerHTML = html;
    container.querySelectorAll("th[data-ahl-tsort]").forEach(th => {
      th.onclick = () => {
        const col = th.dataset.ahlTsort;
        ahlTeamSortAsc = ahlTeamSortKey === col ? !ahlTeamSortAsc : false;
        ahlTeamSortKey = col;
        renderTeamRoster();
      };
    });
  }

  function renderTeamSchedule() {
    const container = document.getElementById("ahl-team-container");
    if (!container || !ahlTeamData) return;
    const games = Array.isArray(ahlTeamData.schedule) ? ahlTeamData.schedule : [];
    if (!games.length) {
      container.innerHTML = '<div class="empty">Расписание не найдено</div>';
      return;
    }

    const abbr = ahlTeamData.team?.abbrev || "";
    container.innerHTML = `<div class="section-title">Матчи сезона</div><div class="card" style="padding:0;">` +
      games.map(g => {
        const dStr = g.date ? new Date(g.date).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) : "";
        const fin = g.isFinal || (g.awayScore != null && g.homeScore != null);
        return `
          <div class="h2h-game-row clickable-row" style="cursor:pointer;" data-ahl-game-id="${escapeHtml(g.id)}" data-ahl-away="${escapeHtml(g.awayAbbrev)}" data-ahl-home="${escapeHtml(g.homeAbbrev)}">
            <div style="font-family:'Roboto Mono',monospace;font-size:11px;color:var(--silver-dim);width:45px;">${escapeHtml(dStr)}</div>
            <div class="h2h-team-cell left" style="${g.awayAbbrev === abbr ? "color:#fff;font-weight:700;" : ""}">${escapeHtml(g.awayAbbrev)}</div>
            <div class="h2h-center-cell"><span class="h2h-score-val">${fin ? `${g.awayScore} : ${g.homeScore}` : "vs"}</span></div>
            <div class="h2h-team-cell right" style="${g.homeAbbrev === abbr ? "color:#fff;font-weight:700;" : ""}">${escapeHtml(g.homeAbbrev)}</div>
          </div>
        `;
      }).join("") + `</div>`;
  }

  async function openTeamDetail(teamIdOrName, teamName = "", teamAbbrev = "", teamLogo = "", seasonId = "", seasonLabel = "") {
    openDetail({ type: "ahl-team", fn: () => openTeamDetail(teamIdOrName, teamName, teamAbbrev, teamLogo, seasonId, seasonLabel) });
    const body = document.getElementById("detail-body");

    try {
      const qs = new URLSearchParams();
      if (seasonId) qs.set("season", seasonId);
      else if (ahlSelectedSeasonId && !seasonLabel) qs.set("season", ahlSelectedSeasonId);
      if (seasonLabel) qs.set("seasonLabel", seasonLabel);

      const res = await fetch(`${API_BASE}/api/ahl/team/${encodeURIComponent(teamIdOrName)}?${qs}`);
      const data = await res.json();
      if (data?.error) {
        if (body) body.innerHTML = `<div class="empty">${escapeHtml(data.error)}</div>`;
        return;
      }

      ahlTeamData = data;
      ahlTeamSortKey = "points";
      ahlTeamSortAsc = false;
      const t = data.team || {};
      const seasonStr = /^\d{8}$/.test(seasonLabel) ? `Сезон ${seasonLabel.slice(0, 4)}-${seasonLabel.slice(6, 8)}` : "";
      const sub = [t.abbrev || teamAbbrev, t.division, seasonStr].filter(Boolean).join(" · ");

      if (body) {
        body.innerHTML = `
          <div class="detail-head">
            <img class="team-logo" src="${escapeHtml(t.logo || teamLogo)}" alt="" onerror="this.style.visibility='hidden'">
            <div>
              <div class="title">${escapeHtml(t.name || teamName || teamIdOrName)}</div>
              ${sub ? `<div class="subtitle">${escapeHtml(sub)}</div>` : ""}
            </div>
          </div>
          <div class="cat-row" style="margin-top:12px;">
            <button id="ahl-btn-roster" class="active">Состав</button>
            <button id="ahl-btn-sched">Расписание</button>
          </div>
          <div id="ahl-team-container"></div>
        `;
      }

      safeOn("ahl-btn-roster", "click", () => {
        document.getElementById("ahl-btn-roster")?.classList.add("active");
        document.getElementById("ahl-btn-sched")?.classList.remove("active");
        renderTeamRoster();
      });
      safeOn("ahl-btn-sched", "click", () => {
        document.getElementById("ahl-btn-sched")?.classList.add("active");
        document.getElementById("ahl-btn-roster")?.classList.remove("active");
        renderTeamSchedule();
      });

      renderTeamRoster();
    } catch (_) {
      if (body) body.innerHTML = '<div class="empty">Не удалось загрузить данные клуба AHL</div>';
    }
  }

  // 6. КАРТОЧКА ИГРОКА AHL
  async function openPlayerDetail(playerId) {
    openDetail({ type: "ahl-player", fn: () => openPlayerDetail(playerId) });
    const body = document.getElementById("detail-body");

    try {
      const res = await fetch(`${API_BASE}/api/ahl/player/${encodeURIComponent(playerId)}`);
      const data = await res.json();
      const prof = data?.profile || {};
      const info = prof.info || prof || {};
      const fullName = `${info.firstName || info.first_name || ""} ${info.lastName || info.last_name || ""}`.trim() || info.name || "Игрок AHL";
      const pos = formatAhlPos(info.position || "");
      const isGoalie = pos === "G";

      const statsRoot = data?.seasonStats || {};
      const regSeasons = Array.isArray(statsRoot.regular) ? statsRoot.regular : (Array.isArray(statsRoot.career) ? statsRoot.career : []);
      const poSeasons = Array.isArray(statsRoot.playoff) ? statsRoot.playoff : [];
      const gbg = Array.isArray(data?.gameByGame?.games) ? data.gameByGame.games : (Array.isArray(data?.gameByGame) ? data.gameByGame : []);

      let html = `
        <div class="detail-head">
          <img class="headshot" src="https://assets.leaguestat.com/ahl/240x240/${escapeHtml(playerId)}.jpg" alt="" onerror="this.src='https://assets.nhle.com/mugs/nhl/default-player.png'">
          <div>
            <div class="title" style="text-align:left;">${escapeHtml(fullName)}</div>
            <div class="subtitle" style="text-align:left;">${escapeHtml(info.team_name || info.current_team || "AHL")}${info.jerseyNumber ? ` · №${escapeHtml(info.jerseyNumber)}` : ""}${pos ? ` · ${escapeHtml(pos)}` : ""}</div>
          </div>
        </div>

        <div class="section-title">Личные данные</div>
        <div class="bio-grid">
          <div><div class="label">Дата рождения</div><div class="value">${escapeHtml(ahlGoalStr(info.birthdate || info.birth_date))}</div></div>
          <div><div class="label">Место рождения</div><div class="value">${escapeHtml(ahlGoalStr(info.birthplace || info.hometown))}</div></div>
          <div><div class="label">Рост / Вес</div><div class="value">${escapeHtml(ahlGoalStr(info.height))} / ${escapeHtml(ahlGoalStr(info.weight))}</div></div>
          <div><div class="label">Хват</div><div class="value">${escapeHtml(ahlGoalStr(info.shoots || info.catches))}</div></div>
        </div>
      `;

      if (gbg.length) {
        const last10 = gbg.slice(0, 10);
        html += `<div class="section-title">Последние матчи AHL</div><div class="table-scroll"><table class="stat-table"><thead><tr><th>Дата</th><th>Матч</th>${isGoalie ? "<th>Бр</th><th>ОБ</th><th>ПШ</th>" : "<th>Г</th><th>П</th><th>О</th><th>+/-</th><th>Б</th>"}</tr></thead><tbody>`;
        last10.forEach(m => {
          const dStr = m.date_played ? new Date(m.date_played).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
          html += `<tr class="clickable-row" data-ahl-game-id="${escapeHtml(m.game_id || "")}">
            <td class="num">${escapeHtml(dStr)}</td>
            <td>${escapeHtml(m.opponent_team_code || m.opponent || "—")}</td>
            ${isGoalie
              ? `<td class="num">${ahlGoalStr(m.shots_against, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(m.saves, 0)}</td><td class="num">${ahlGoalStr(m.goals_against, 0)}</td>`
              : `<td class="num">${ahlGoalStr(m.goals, 0)}</td><td class="num">${ahlGoalStr(m.assists, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(m.points, 0)}</td><td class="num">${ahlGoalStr(m.plus_minus, 0)}</td><td class="num">${ahlGoalStr(m.shots, 0)}</td>`}
          </tr>`;
        });
        html += `</tbody></table></div>`;
      }

      if (regSeasons.length || poSeasons.length) {
        const renderAhlSeasonRows = (rows, label) => {
          if (!rows.length) return "";
          return `<tr class="playoff-header-row"><td colspan="${isGoalie ? 7 : 8}">${label}</td></tr>` +
            rows.map(s => `
              <tr>
                <td>${escapeHtml(s.season_name || s.season || "—")}</td>
                <td style="text-align:left;">
                  ${s.team_id
                    ? `<span class="tx-player-link" data-ahl-team-id="${escapeHtml(s.team_id)}" data-ahl-team-name="${escapeHtml(s.team_name || "")}" data-ahl-season-id="${escapeHtml(s.season_id || "")}">${escapeHtml(s.team_name || s.shortname || "—")}</span>`
                    : escapeHtml(s.team_name || s.shortname || "—")}
                </td>
                <td class="num">${ahlGoalStr(s.games_played, 0)}</td>
                ${isGoalie
                  ? `<td class="num">${ahlGoalStr(s.wins, 0)}</td><td class="num">${ahlGoalStr(s.losses, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(s.save_percentage)}</td><td class="num">${ahlGoalStr(s.goals_against_average)}</td>`
                  : `<td class="num">${ahlGoalStr(s.goals, 0)}</td><td class="num">${ahlGoalStr(s.assists, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlGoalStr(s.points, 0)}</td><td class="num">${ahlGoalStr(s.plus_minus, 0)}</td><td class="num">${ahlGoalStr(s.penalty_minutes, 0)}</td>`}
              </tr>
            `).join("");
        };

        html += `
          <div class="section-title">Статистика карьеры в AHL</div>
          <div class="table-scroll"><table class="stat-table">
            <thead><tr><th>Сезон</th><th>Клуб</th><th>И</th>${isGoalie ? "<th>В</th><th>П</th><th>%ОБ</th><th>ГКИ</th>" : "<th>Г</th><th>П</th><th>О</th><th>+/-</th><th>Штр</th>"}</tr></thead>
            <tbody>
              ${renderAhlSeasonRows(regSeasons, "Регулярный сезон")}
              ${renderAhlSeasonRows(poSeasons, "Плей-офф")}
            </tbody>
          </table></div>
        `;
      }

      if (body) body.innerHTML = html;
    } catch (_) {
      if (body) body.innerHTML = '<div class="empty">Не удалось загрузить профиль игрока AHL</div>';
    }
  }

  // Делегирование кликов для элементов AHL
  document.addEventListener("click", (e) => {
    const ahlPlayer = e.target.closest("[data-ahl-player-id]");
    if (ahlPlayer && ahlPlayer.dataset.ahlPlayerId) {
      openPlayerDetail(ahlPlayer.dataset.ahlPlayerId);
      return;
    }

    const ahlGame = e.target.closest("[data-ahl-game-id]");
    if (ahlGame && ahlGame.dataset.ahlGameId) {
      openGameDetail(
        ahlGame.dataset.ahlGameId,
        { abbrev: ahlGame.dataset.ahlAway || "", logo: ahlGame.dataset.ahlAwayLogo || "" },
        { abbrev: ahlGame.dataset.ahlHome || "", logo: ahlGame.dataset.ahlHomeLogo || "" }
      );
      return;
    }

    const ahlTeam = e.target.closest("[data-ahl-team-id], [data-ahl-team-name]");
    if (ahlTeam) {
      openTeamDetail(
        ahlTeam.dataset.ahlTeamId || ahlTeam.dataset.ahlTeamName,
        ahlTeam.dataset.ahlTeamName || "",
        ahlTeam.dataset.ahlTeamAbbr || "",
        ahlTeam.dataset.ahlTeamLogo || "",
        ahlTeam.dataset.ahlSeasonId || "",
        ahlTeam.dataset.ahlSeasonLabel || ""
      );
    }
  });

  window.AHL = {
    updateUiForLeague,
    loadSchedule,
    loadStandings,
    setStandingsMode,
    sortStandingsBy,
    setSeason,
    loadPlayers,
    setLeadersMode,
    setSearchFilter,
    openGameDetail,
    openTeamDetail,
    openPlayerDetail,
  };
})();
