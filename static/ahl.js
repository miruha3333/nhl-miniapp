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

  let ahlBoxData = null;
  let ahlBoxSortKey = {};
  let ahlBoxSortAsc = {};

  function ahlStr(v, fb = "—") {
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
    const s = String(pos || "").trim().toUpperCase();
    if (!s) return "";
    const map = {
      // Стандартная 5-значная сетка
      "1": "D", "2": "C", "3": "LW", "4": "RW", "5": "G",
      // Расширенная 8-значная сетка лиги
      "6": "LW", "7": "C", "8": "RW", "9": "F", "10": "D",
      // Буквенные обозначения
      "D": "D", "C": "C", "LW": "LW", "RW": "RW", "G": "G",
      "F": "F", "W": "W", "L": "LW", "R": "RW",
      "LD": "D", "RD": "D",
      "DEFENCE": "D", "DEFENSE": "D", "DEFENCEMAN": "D", "DEFENSEMAN": "D",
      "CENTER": "C", "CENTRE": "C",
      "LEFT WING": "LW", "RIGHT WING": "RW", "WINGER": "W", "FORWARD": "F",
      "GOALIE": "G", "GOALTENDER": "G"
    };
    if (map[s]) return map[s];
    // Если всё ещё осталась цифра — заменяем по смыслу на F
    if (/^\d+$/.test(s)) return "F";
    return s.length <= 3 ? s : "";
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

    // Официальные ID регулярных чемпионатов AHL из базы LeagueStat
    const officialAhlSeasons = [
      { id: "86", name: "2024-25 Регулярный сезон" },
      { id: "83", name: "2023-24 Регулярный сезон" },
      { id: "79", name: "2022-23 Регулярный сезон" },
      { id: "73", name: "2021-22 Регулярный сезон" },
      { id: "69", name: "2020-21 Регулярный сезон (COVID)" },
      { id: "65", name: "2019-20 Регулярный сезон (COVID)" },
      { id: "61", name: "2018-19 Регулярный сезон" },
      { id: "57", name: "2017-18 Регулярный сезон" },
      { id: "54", name: "2016-17 Регулярный сезон" },
      { id: "51", name: "2015-16 Регулярный сезон" },
      { id: "48", name: "2014-15 Регулярный сезон" },
      { id: "43", name: "2013-14 Регулярный сезон" },
      { id: "40", name: "2012-13 Регулярный сезон" },
      { id: "37", name: "2011-12 Регулярный сезон" },
      { id: "34", name: "2010-11 Регулярный сезон" },
    ];

    if (!ahlSelectedSeasonId) {
      ahlSelectedSeasonId = "86";
    }

    select.innerHTML = officialAhlSeasons.map(s => {
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

    ["tab-draft", "tab-transactions", "tab-news"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAhl ? "none" : "";
    });

    ["std-mode-wc", "std-mode-adv"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAhl ? "none" : "";
    });
    const bracket = document.getElementById("bracket-container");
    if (bracket && isAhl) bracket.innerHTML = "";

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
      if (!["all", "conf", "div"].includes(ahlStandingsMode)) {
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

          const boxAttrs = g.started
            ? `data-ahl-game-id="${escapeHtml(g.id)}"`
            : `data-ahl-preview-id="${escapeHtml(g.id)}" data-ahl-season="${escapeHtml(g.seasonId || "")}" data-ahl-away-id="${escapeHtml(away.id)}" data-ahl-home-id="${escapeHtml(home.id)}"`;

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

                <div class="score-box game-center clickable" ${boxAttrs} data-ahl-away="${escapeHtml(away.abbrev)}" data-ahl-home="${escapeHtml(home.abbrev)}" data-ahl-away-logo="${escapeHtml(away.logo)}" data-ahl-home-logo="${escapeHtml(home.logo)}">
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

  // 2. ТАБЛИЦА AHL + СЕТКА ПЛЕЙ-ОФФ
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

  async function loadPlayoffBracket(seasonId) {
    const container = document.getElementById("bracket-container");
    if (!container) return;
    container.innerHTML = `<div class="bracket-wrap"><div class="loading">Загрузка плей-офф Кубка Колдера...</div></div>`;

    try {
      const qs = seasonId ? `?season=${encodeURIComponent(seasonId)}` : "";
      const res = await fetch(`${API_BASE}/api/ahl/brackets${qs}`);
      const data = await res.json();
      const rounds = Array.isArray(data?.rounds) ? data.rounds : [];

      if (!rounds.length) {
        container.innerHTML = `
          <div class="bracket-wrap">
            <div class="section-title">Плей-офф Кубка Колдера</div>
            <div class="empty">Сетка плей-офф за выбранный сезон ещё не сформирована</div>
          </div>
        `;
        return;
      }

      let html = `<div class="bracket-wrap"><div class="section-title">Плей-офф (${escapeHtml(data.seasonName || "Кубок Колдера")})</div>`;
      rounds.forEach(rd => {
        html += `<div class="bracket-round-title">${escapeHtml(rd.roundName || "Раунд")}</div>`;
        (rd.series || []).forEach(ser => {
          const t1 = ser.team1 || {};
          const t2 = ser.team2 || {};
          const w1 = Number(t1.wins || 0);
          const w2 = Number(t2.wins || 0);
          const t1Win = (ser.winnerId && ser.winnerId === t1.id) || (w1 > w2 && w1 >= 2 && w2 < w1);
          const t2Win = (ser.winnerId && ser.winnerId === t2.id) || (w2 > w1 && w2 >= 2 && w1 < w2);

          html += `
            <div class="bracket-series">
              <div class="bracket-team-row ${t1Win ? "winner" : ""}" data-ahl-team-id="${escapeHtml(t1.id || "")}" data-ahl-team-name="${escapeHtml(t1.name || "")}" data-ahl-team-abbr="${escapeHtml(t1.abbrev || "")}" data-ahl-season-id="${escapeHtml(data.playoffSeasonId || "")}" style="cursor:pointer;">
                <div class="bt-name">
                  <img src="${escapeHtml(t1.logo || "")}" alt="" onerror="this.style.display='none'">
                  <span>${escapeHtml(t1.abbrev || t1.name || "TBD")}</span>
                </div>
                <div class="bt-wins">${w1}</div>
              </div>
              <div class="bracket-team-row ${t2Win ? "winner" : ""}" data-ahl-team-id="${escapeHtml(t2.id || "")}" data-ahl-team-name="${escapeHtml(t2.name || "")}" data-ahl-team-abbr="${escapeHtml(t2.abbrev || "")}" data-ahl-season-id="${escapeHtml(data.playoffSeasonId || "")}" style="cursor:pointer;">
                <div class="bt-name">
                  <img src="${escapeHtml(t2.logo || "")}" alt="" onerror="this.style.display='none'">
                  <span>${escapeHtml(t2.abbrev || t2.name || "TBD")}</span>
                </div>
                <div class="bt-wins">${w2}</div>
              </div>
            </div>
          `;
        });
      });
      html += "</div>";
      container.innerHTML = html;
    } catch (_) {
      container.innerHTML = `<div class="bracket-wrap"><div class="empty">Не удалось загрузить сетку плей-офф</div></div>`;
    }
  }

  async function loadStandings() {
    const body = document.getElementById("standings-body");
    if (body) body.innerHTML = '<div class="loading">Загрузка таблицы AHL...</div>';
    await populateSeasonSelect();

    const targetSeason = ahlSelectedSeasonId || (document.getElementById("season-select")?.value || "");

    try {
      const qs = targetSeason ? `?season=${encodeURIComponent(targetSeason)}` : "";
      const res = await fetch(`${API_BASE}/api/ahl/standings${qs}`);
      const data = await res.json();
      ahlStandingsData = Array.isArray(data?.standings) ? data.standings : [];
      setStandingsMode(ahlStandingsMode);
      loadPlayoffBracket(targetSeason);
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

  // 4. ПРЕВЬЮ НЕНАЧАВШЕГОСЯ МАТЧА AHL
  async function openFutureGamePreview(gameId, awayFallback = {}, homeFallback = {}, seasonId = "") {
    openDetail({ type: "ahl-preview", fn: () => openFutureGamePreview(gameId, awayFallback, homeFallback, seasonId) });
    const body = document.getElementById("detail-body");

    try {
      const qs = new URLSearchParams();
      if (seasonId) qs.set("season", seasonId);
      if (awayFallback.id) qs.set("awayId", awayFallback.id);
      if (homeFallback.id) qs.set("homeId", homeFallback.id);

      const [res, voteRes] = await Promise.all([
        fetch(`${API_BASE}/api/ahl/preview/${encodeURIComponent(gameId)}?${qs}`),
        fetch(`${API_BASE}/api/vote/ahl_${encodeURIComponent(gameId)}`).catch(() => null),
      ]);
      const data = await res.json();
      const voteData = voteRes && voteRes.ok ? await voteRes.json() : { total: 0, awayPct: 0, tiePct: 0, homePct: 0 };

      const away = data.awayTeam || awayFallback || {};
      const home = data.homeTeam || homeFallback || {};
      const awayCode = away.abbrev || awayFallback.abbrev || "AWAY";
      const homeCode = home.abbrev || homeFallback.abbrev || "HOME";
      const startTime = data.startTimeUTC
        ? new Date(data.startTimeUTC).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" }) + " (МСК)"
        : "Время уточняется";

      const renderPickem = (v) => {
        const picked = localStorage.getItem(`nhl_pick_ahl_${gameId}`) || "";
        const tot = v?.total || 0;
        const aP = v?.awayPct ?? 0;
        const tP = v?.tiePct ?? 0;
        const hP = v?.homePct ?? 0;
        return `
          <div class="card">
            <div class="pregame-pickem-grid">
              <button class="pickem-btn ${picked === "away" ? "selected" : ""}" data-ahl-vote="away" type="button">
                <span>${escapeHtml(awayCode)}</span>
                <span style="font-family:'Roboto Mono',monospace;font-size:13px;color:#fff;">${aP}%</span>
              </button>
              <button class="pickem-btn ${picked === "tie" ? "selected" : ""}" data-ahl-vote="tie" type="button">
                <span>Ничья (ОТ/Б)</span>
                <span style="font-family:'Roboto Mono',monospace;font-size:13px;color:#fff;">${tP}%</span>
              </button>
              <button class="pickem-btn ${picked === "home" ? "selected" : ""}" data-ahl-vote="home" type="button">
                <span>${escapeHtml(homeCode)}</span>
                <span style="font-family:'Roboto Mono',monospace;font-size:13px;color:#fff;">${hP}%</span>
              </button>
            </div>
            ${tot > 0 ? `
              <div class="pickem-bar">
                <div style="width:${aP}%;background:#3a86ff;"></div>
                <div style="width:${tP}%;background:#f39c12;"></div>
                <div style="width:${hP}%;background:#2ecc71;"></div>
              </div>
              <div style="font-size:10px;color:var(--silver-dim);text-align:center;margin-top:6px;">Всего голосов: ${tot}</div>
            ` : '<div style="font-size:10px;color:var(--silver-dim);text-align:center;margin-top:8px;">Сделайте свой прогноз на матч</div>'}
          </div>
        `;
      };

      let html = `
        <div class="detail-head-game">
          <img class="team-logo" src="${escapeHtml(away.logo || awayFallback.logo || "")}" alt="" data-ahl-team-id="${escapeHtml(away.id || "")}" data-ahl-team-name="${escapeHtml(away.name || awayCode)}" style="cursor:pointer;" onerror="this.style.visibility='hidden'">
          <div>
            <div class="title">${escapeHtml(awayCode)} — ${escapeHtml(homeCode)}</div>
            <div class="subtitle" style="color:#2ecc71;font-weight:700;">НАЧАЛО (AHL): ${escapeHtml(startTime)}</div>
          </div>
          <img class="team-logo" src="${escapeHtml(home.logo || homeFallback.logo || "")}" alt="" data-ahl-team-id="${escapeHtml(home.id || "")}" data-ahl-team-name="${escapeHtml(home.name || homeCode)}" style="cursor:pointer;" onerror="this.style.visibility='hidden'">
        </div>

        <div class="section-title">Прогноз болельщиков (Pick'em)</div>
        <div id="ahl-pickem-slot">${renderPickem(voteData)}</div>

        <div class="section-title">Сравнение показателей команд</div>
        <div class="card" style="padding:10px 14px;">
      `;

      (data.preGameStats || []).forEach(st => {
        const aNum = parseFloat(String(st.awayValue).replace("%", ""));
        const hNum = parseFloat(String(st.homeValue).replace("%", ""));
        let aCol = "#ffffff", hCol = "#ffffff";
        if (!Number.isNaN(aNum) && !Number.isNaN(hNum) && aNum !== hNum) {
          const awayBest = st.higherIsBetter === false ? (aNum < hNum) : (aNum > hNum);
          aCol = awayBest ? "#2ecc71" : "#ff4d4d";
          hCol = awayBest ? "#ff4d4d" : "#2ecc71";
        }
        html += `
          <div class="comp-row">
            <div class="val away" style="color:${aCol} !important;font-weight:700;">${escapeHtml(ahlStr(st.awayValue))}</div>
            <div class="metric">${escapeHtml(st.label)}</div>
            <div class="val home" style="color:${hCol} !important;font-weight:700;">${escapeHtml(ahlStr(st.homeValue))}</div>
          </div>
        `;
      });
      html += `</div>`;

      const topScorers = data.topScorers || { away: [], home: [] };
      if ((topScorers.away?.length || 0) > 0 || (topScorers.home?.length || 0) > 0) {
        const renderScCol = (list, label) => `
          <div class="injury-team-col">
            <h4>${escapeHtml(label)}</h4>
            ${(list || []).map(p => `
              <div class="injury-item" data-ahl-player-id="${escapeHtml(p.id)}" style="cursor:pointer;display:flex;align-items:center;gap:8px;">
                <img src="${escapeHtml(p.headshot)}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;background:var(--surface-2);flex-shrink:0;" onerror="this.src='https://assets.nhle.com/mugs/nhl/default-player.png'">
                <div style="min-width:0;flex:1;">
                  <div class="injury-name" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(p.name)}</div>
                  <div style="font-family:'Roboto Mono',monospace;font-size:11px;font-weight:700;"><span style="color:#3a86ff;">${p.gamesPlayed}</span> <span style="color:#2ecc71;">${p.goals}+${p.assists}=${p.points}</span></div>
                </div>
              </div>
            `).join("") || '<div class="empty">Нет данных</div>'}
          </div>
        `;
        html += `
          <div class="section-title">Топ-3 бомбардира команд</div>
          <div class="pregame-injuries-grid">
            ${renderScCol(topScorers.away, awayCode)}
            ${renderScCol(topScorers.home, homeCode)}
          </div>
        `;
      }

      const clubGoalies = data.clubGoalies || { away: [], home: [] };
      if ((clubGoalies.away?.length || 0) > 0 || (clubGoalies.home?.length || 0) > 0) {
        const renderGlCol = (list, label) => `
          <div class="injury-team-col">
            <h4>${escapeHtml(label)}</h4>
            ${(list || []).map(g => `
              <div class="injury-item" data-ahl-player-id="${escapeHtml(g.id)}" style="cursor:pointer;">
                <div class="injury-item-top">
                  <div class="injury-name">${escapeHtml(g.name)}</div>
                  <span style="font-family:'Roboto Mono',monospace;font-size:10px;color:#2ecc71;font-weight:700;">${Number(g.savePctg || 0).toFixed(3)}</span>
                </div>
                <div class="injury-desc">И: ${g.gamesPlayed} · ${g.wins}-${g.losses}-${g.otLosses} · ГКИ ${Number(g.gaa || 0).toFixed(2)}${g.shutouts ? ` · ${g.shutouts} сух.` : ""}</div>
              </div>
            `).join("") || '<div class="empty">Нет данных</div>'}
          </div>
        `;
        html += `
          <div class="section-title">Вратари команд в сезоне</div>
          <div class="pregame-injuries-grid">
            ${renderGlCol(clubGoalies.away, awayCode)}
            ${renderGlCol(clubGoalies.home, homeCode)}
          </div>
        `;
      }

      html += `
        <div class="section-title">Форма и рекорды команд</div>
        <div class="card" style="padding:10px 14px;">
          <div class="comp-row"><div class="val away">${escapeHtml(ahlStr(away.record))}</div><div class="metric">Рекорд (В-П-ОТ)</div><div class="val home">${escapeHtml(ahlStr(home.record))}</div></div>
          ${away.streak || home.streak ? `<div class="comp-row"><div class="val away">${escapeHtml(ahlStr(away.streak))}</div><div class="metric">Серия</div><div class="val home">${escapeHtml(ahlStr(home.streak))}</div></div>` : ""}
          ${away.past10 || home.past10 ? `<div class="comp-row"><div class="val away">${escapeHtml(ahlStr(away.past10))}</div><div class="metric">Посл. 10</div><div class="val home">${escapeHtml(ahlStr(home.past10))}</div></div>` : ""}
          ${away.roadRecord || home.homeRecord ? `<div class="comp-row"><div class="val away">${escapeHtml(ahlStr(away.roadRecord))} (Г)</div><div class="metric">В гостях / Дома</div><div class="val home">${escapeHtml(ahlStr(home.homeRecord))} (Д)</div></div>` : ""}
        </div>
      `;

      const series = Array.isArray(data.seasonSeries) ? data.seasonSeries : [];
      if (series.length) {
        html += `<div class="section-title">Очные встречи в сезоне (${series.length})</div><div class="card" style="padding:0;">`;
        series.forEach(sg => {
          const dStr = sg.date ? new Date(sg.date).toLocaleDateString("ru-RU") : "";
          const as = sg.awayScore;
          const hs = sg.homeScore;
          let aCol = "inherit", hCol = "inherit";

          if (sg.isFinal && as != null && hs != null && as !== hs) {
            aCol = as > hs ? "#2ecc71" : "#ff4d4d";
            hCol = hs > as ? "#2ecc71" : "#ff4d4d";
          }

          html += `
            <div class="h2h-game-row ${sg.isFinal ? "clickable-row" : ""}" ${sg.isFinal ? `data-ahl-game-id="${escapeHtml(sg.id)}" data-ahl-away="${escapeHtml(sg.awayAbbrev)}" data-ahl-home="${escapeHtml(sg.homeAbbrev)}" style="cursor:pointer;"` : ""}>
              <div class="h2h-team-cell left" style="color:${aCol};font-weight:${aCol !== "inherit" ? "700" : "normal"};">${escapeHtml(sg.awayAbbrev)}</div>
              <div class="h2h-center-cell">
                <div class="h2h-score-val">${sg.isFinal && as != null && hs != null ? `${as} : ${hs}` : "Предстоит"}</div>
                ${dStr ? `<div class="h2h-date-sub">${escapeHtml(dStr)}</div>` : ""}
              </div>
              <div class="h2h-team-cell right" style="color:${hCol};font-weight:${hCol !== "inherit" ? "700" : "normal"};">${escapeHtml(sg.homeAbbrev)}</div>
            </div>
          `;
        });
        html += `</div>`;
      }

      if (body) body.innerHTML = html;

      const pickemSlot = document.getElementById("ahl-pickem-slot");
      if (pickemSlot) {
        pickemSlot.addEventListener("click", async (e) => {
          const btn = e.target.closest("[data-ahl-vote]");
          if (!btn) return;
          const pick = btn.dataset.ahlVote;
          const key = `nhl_pick_ahl_${gameId}`;
          if (localStorage.getItem(key)) return;
          localStorage.setItem(key, pick);
          try {
            const vRes = await fetch(`${API_BASE}/api/vote/ahl_${encodeURIComponent(gameId)}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ pick }),
            });
            pickemSlot.innerHTML = renderPickem(await vRes.json());
          } catch (_) {}
        });
      }
    } catch (_) {
      if (body) body.innerHTML = '<div class="empty">Не удалось загрузить превью матча AHL</div>';
    }
  }

  // 5. КАРТА БРОСКОВ И ПРОТОКОЛ СЫГРАННОГО / LIVE МАТЧА AHL
  function renderAhlShotMap(pxp, homeId, awayId, homeAbbr, awayAbbr) {
    if (!Array.isArray(pxp) || !pxp.length) return "";
    const shots = pxp.filter(ev => {
      const k = String(ev.event || ev.type || "").toLowerCase();
      return (k === "shot" || k === "goal" || k === "missed_shot") &&
        ev.x_location != null && ev.y_location != null &&
        (Number(ev.x_location) !== 0 || Number(ev.y_location) !== 0);
    });
    if (!shots.length) return "";

    let maxX = 0, maxY = 0;
    shots.forEach(s => {
      maxX = Math.max(maxX, Math.abs(Number(s.x_location)));
      maxY = Math.max(maxY, Math.abs(Number(s.y_location)));
    });
    const isPixel600 = maxX > 110;
    const isPixel200 = !isPixel600 && shots.every(s => Number(s.x_location) >= 0 && Number(s.y_location) >= 0);

    let perFilter = "all";
    let typeFilter = "sog";

    const buildSvg = () => {
      const filtered = shots.filter(ev => {
        const k = String(ev.event || ev.type || "").toLowerCase();
        if (typeFilter === "sog" && k === "missed_shot") return false;
        const per = String(ev.period_id || ev.period || "");
        if (perFilter !== "all" && per !== perFilter) return false;
        return true;
      });

      let awaySog = 0, homeSog = 0, awayG = 0, homeG = 0;
      const dots = filtered.map(ev => {
        const rx = Number(ev.x_location);
        const ry = Number(ev.y_location);
        let svgX = 200, svgY = 85;
        if (isPixel600) {
          svgX = Math.max(12, Math.min(388, (rx / 600) * 400));
          svgY = Math.max(10, Math.min(160, (ry / 300) * 170));
        } else if (isPixel200) {
          svgX = Math.max(12, Math.min(388, (rx / Math.max(200, maxX)) * 400));
          svgY = Math.max(10, Math.min(160, (ry / Math.max(85, maxY)) * 170));
        } else {
          svgX = Math.max(12, Math.min(388, (rx + 100) * 2));
          svgY = Math.max(10, Math.min(160, (42.5 - ry) * 2));
        }

        const k = String(ev.event || ev.type || "").toLowerCase();
        const isGoal = k === "goal";
        const isMiss = k === "missed_shot";
        const evTeamId = String(ev.team_id || ev.home_or_visitor || "");
        const isHome = evTeamId === homeId || evTeamId === "home";

        if (!isMiss) {
          if (isHome) homeSog++;
          else awaySog++;
        }
        if (isGoal) {
          if (isHome) homeG++;
          else awayG++;
        }

        const col = isHome ? "#ff595e" : "#3a86ff";
        const r = isGoal ? 6 : (isMiss ? 3 : 4);
        const op = isMiss ? 0.45 : (isGoal ? 1 : 0.85);
        const stroke = isGoal ? "#f1c40f" : "#ffffff";
        const pName = hlPersonName(ev.player) || ev.player_name || "Игрок";
        const tCode = isHome ? homeAbbr : awayAbbr;
        const tip = `${tCode} · ${pName} — ${isGoal ? "ГОЛ" : (isMiss ? "Мимо" : "В створ")}, ${ev.period_id || ev.period || 1}П ${ev.time || ""}`;

        return `<circle cx="${svgX.toFixed(1)}" cy="${svgY.toFixed(1)}" r="${r}" fill="${col}" fill-opacity="${op}" stroke="${stroke}" stroke-width="${isGoal ? 2 : 0.7}" class="shot-pt" data-shot-info="${escapeHtml(tip)}" style="cursor:pointer;" />`;
      }).join("");

      return {
        svg: `
          <svg class="shot-map-svg" viewBox="0 0 400 170" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="2" width="396" height="166" rx="34" ry="34" fill="#101a26" stroke="#3b4a5e" stroke-width="2"/>
            <line x1="22" y1="6" x2="22" y2="164" stroke="#c8102e" stroke-width="1.2" opacity="0.65"/>
            <line x1="378" y1="6" x2="378" y2="164" stroke="#c8102e" stroke-width="1.2" opacity="0.65"/>
            <line x1="150" y1="2" x2="150" y2="168" stroke="#1f5fce" stroke-width="2" opacity="0.7"/>
            <line x1="250" y1="2" x2="250" y2="168" stroke="#1f5fce" stroke-width="2" opacity="0.7"/>
            <line x1="200" y1="2" x2="200" y2="168" stroke="#c8102e" stroke-width="1.8" stroke-dasharray="4 3" opacity="0.75"/>
            <circle cx="200" cy="85" r="24" fill="none" stroke="#1f5fce" stroke-width="1.2" opacity="0.6"/>
            <circle cx="62" cy="41" r="22" fill="none" stroke="#c8102e" stroke-width="1" opacity="0.45"/>
            <circle cx="62" cy="129" r="22" fill="none" stroke="#c8102e" stroke-width="1" opacity="0.45"/>
            <circle cx="338" cy="41" r="22" fill="none" stroke="#c8102e" stroke-width="1" opacity="0.45"/>
            <circle cx="338" cy="129" r="22" fill="none" stroke="#c8102e" stroke-width="1" opacity="0.45"/>
            ${dots}
          </svg>
        `,
        awaySog, homeSog, awayG, homeG
      };
    };

    const initial = buildSvg();
    const wrapId = `ahl-shotmap-${Date.now()}`;
    setTimeout(() => {
      const wrap = document.getElementById(wrapId);
      if (!wrap) return;
      const svgSlot = wrap.querySelector(".shotmap-svg-slot");
      const cntSlot = wrap.querySelector(".shotmap-counts");
      const tipSlot = wrap.querySelector(".shotmap-tip");
      const refresh = () => {
        const r = buildSvg();
        if (svgSlot) svgSlot.innerHTML = r.svg;
        if (cntSlot) {
          cntSlot.innerHTML = `
            <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#3a86ff;"></span>${escapeHtml(awayAbbr)}: ${r.awaySog} б/с (${r.awayG} г)</span>
            <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#ff595e;"></span>${escapeHtml(homeAbbr)}: ${r.homeSog} б/с (${r.homeG} г)</span>
            <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#f1c40f;"></span>Гол</span>
          `;
        }
      };
      wrap.addEventListener("click", (e) => {
        const pt = e.target.closest(".shot-pt");
        if (pt && tipSlot) { tipSlot.textContent = pt.dataset.shotInfo || ""; return; }
        const tb = e.target.closest("[data-shot-type]");
        if (tb) {
          typeFilter = tb.dataset.shotType;
          wrap.querySelectorAll("[data-shot-type]").forEach(b => b.classList.toggle("active", b === tb));
          refresh();
          return;
        }
        const pb = e.target.closest("[data-shot-period]");
        if (pb) {
          perFilter = pb.dataset.shotPeriod;
          wrap.querySelectorAll("[data-shot-period]").forEach(b => b.classList.toggle("active", b === pb));
          refresh();
        }
      });
    }, 0);

    return `
      <div class="section-title">Карта бросков (Play-by-Play)</div>
      <div class="shot-map-wrap" id="${wrapId}">
        <div class="filter-chips-row" style="margin-bottom:8px;">
          <button class="filter-chip active" data-shot-type="sog" type="button">В створ + Голы</button>
          <button class="filter-chip" data-shot-type="all" type="button">Все (с мимо)</button>
          <button class="filter-chip active" data-shot-period="all" type="button">Весь матч</button>
          <button class="filter-chip" data-shot-period="1" type="button">1П</button>
          <button class="filter-chip" data-shot-period="2" type="button">2П</button>
          <button class="filter-chip" data-shot-period="3" type="button">3П</button>
          <button class="filter-chip" data-shot-period="4" type="button">ОТ</button>
        </div>
        <div class="shotmap-svg-slot">${initial.svg}</div>
        <div class="shot-legend shotmap-counts">
          <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#3a86ff;"></span>${escapeHtml(awayAbbr)}: ${initial.awaySog} б/с (${initial.awayG} г)</span>
          <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#ff595e;"></span>${escapeHtml(homeAbbr)}: ${initial.homeSog} б/с (${initial.homeG} г)</span>
          <span class="shot-legend-item"><span class="shot-dot-swatch" style="background:#f1c40f;"></span>Гол</span>
        </div>
        <div class="shotmap-tip" style="margin-top:6px;font-size:11px;color:var(--silver);min-height:14px;">Нажмите на точку на площадке, чтобы увидеть детали броска</div>
      </div>
    `;
  }

  function renderAhlBoxTables(awayAbbr, homeAbbr) {
    const container = document.getElementById("ahl-boxscore-container");
    if (!container || !ahlBoxData) return;

    const arrow = (sec, col) => ahlBoxSortKey[sec] === col ? `<span class="sort-arrow">${ahlBoxSortAsc[sec] ? "▲" : "▼"}</span>` : "";

    const sortRows = (list, sec, defCol) => {
      const k = ahlBoxSortKey[sec] || defCol;
      const asc = !!ahlBoxSortAsc[sec];
      return [...list].sort((a, b) => (asc ? (Number(a[k] ?? 0) - Number(b[k] ?? 0)) : (Number(b[k] ?? 0) - Number(a[k] ?? 0))));
    };

    const renderSide = (lineup, abbr, pfx) => {
      const players = Array.isArray(lineup?.players) ? lineup.players : [];
      const goalies = Array.isArray(lineup?.goalies) ? lineup.goalies : [];
      let out = "";
      if (players.length) {
        const sorted = sortRows(players, `${pfx}_sk`, "points");
        out += `
          <div class="section-title">Полевые игроки — ${escapeHtml(abbr)}</div>
          <div class="table-scroll"><table class="stat-table">
            <thead><tr>
              <th>Игрок</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="goals">Г${arrow(`${pfx}_sk`, "goals")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="assists">П${arrow(`${pfx}_sk`, "assists")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="points">О${arrow(`${pfx}_sk`, "points")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="plus_minus">+/-${arrow(`${pfx}_sk`, "plus_minus")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="shots">Б${arrow(`${pfx}_sk`, "shots")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_sk" data-ahl-bcol="pim">Штр${arrow(`${pfx}_sk`, "pim")}</th>
            </tr></thead>
            <tbody>
              ${sorted.map(pl => {
                const pid = hlPersonId(pl);
                const pos = formatAhlPos(pl.position);
                const num = pl.jersey_number != null ? `<span style="color:var(--silver-dim);font-family:'Roboto Mono',monospace;font-size:10px;display:inline-block;min-width:22px;">#${escapeHtml(pl.jersey_number)}</span>` : "";
                const posHtml = pos ? ` <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">${escapeHtml(pos)}</span>` : "";
                return `
                  <tr class="clickable-row" data-ahl-player-id="${escapeHtml(pid)}">
                    <td>${num}${escapeHtml(hlPersonName(pl))}${posHtml}</td>
                    <td class="num">${ahlStr(pl.goals, 0)}</td>
                    <td class="num">${ahlStr(pl.assists, 0)}</td>
                    <td class="num" style="color:#fff;font-weight:700;">${ahlStr(pl.points, 0)}</td>
                    <td class="num">${ahlStr(pl.plus_minus, 0)}</td>
                    <td class="num">${ahlStr(pl.shots, 0)}</td>
                    <td class="num">${ahlStr(pl.pim, 0)}</td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table></div>
        `;
      }
      if (goalies.length) {
        const sortedG = sortRows(goalies, `${pfx}_gk`, "saves");
        out += `
          <div class="section-title" style="margin-top:12px;">Вратари — ${escapeHtml(abbr)}</div>
          <div class="table-scroll"><table class="stat-table">
            <thead><tr>
              <th>Вратарь</th>
              <th class="sortable" data-ahl-bsec="${pfx}_gk" data-ahl-bcol="shots_against">Бр${arrow(`${pfx}_gk`, "shots_against")}</th>
              <th class="sortable" data-ahl-bsec="${pfx}_gk" data-ahl-bcol="saves">ОБ${arrow(`${pfx}_gk`, "saves")}</th>
              <th>%ОБ</th>
              <th class="sortable" data-ahl-bsec="${pfx}_gk" data-ahl-bcol="goals_against">ПШ${arrow(`${pfx}_gk`, "goals_against")}</th>
              <th>ВП</th>
            </tr></thead>
            <tbody>
              ${sortedG.map(gl => {
                const sa = Number(gl.shots_against || 0);
                const sv = Number(gl.saves || 0);
                const pct = sa > 0 ? (sv / sa).toFixed(3) : "—";
                return `
                  <tr class="clickable-row" data-ahl-player-id="${escapeHtml(hlPersonId(gl))}">
                    <td>${escapeHtml(hlPersonName(gl))} <span style="color:var(--silver-dim);font-size:10px;font-weight:400;">G</span></td>
                    <td class="num">${sa}</td>
                    <td class="num">${sv}</td>
                    <td class="num" style="color:#fff;font-weight:700;">${pct}</td>
                    <td class="num">${ahlStr(gl.goals_against, 0)}</td>
                    <td class="num" style="color:var(--silver-dim);">${escapeHtml(ahlStr(gl.toi))}</td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table></div>
        `;
      }
      return out;
    };

    container.innerHTML = renderSide(ahlBoxData.visitor_team_lineup, awayAbbr, "away") + renderSide(ahlBoxData.home_team_lineup, homeAbbr, "home");
    container.querySelectorAll("th[data-ahl-bsec]").forEach(th => {
      th.onclick = () => {
        const sec = th.dataset.ahlBsec;
        const col = th.dataset.ahlBcol;
        ahlBoxSortAsc[sec] = ahlBoxSortKey[sec] === col ? !ahlBoxSortAsc[sec] : false;
        ahlBoxSortKey[sec] = col;
        renderAhlBoxTables(awayAbbr, homeAbbr);
      };
    });
  }

  async function openGameDetail(gameId, awayFallback = {}, homeFallback = {}, silent = false) {
    if (!silent) {
      openDetail({ type: "ahl-game", fn: () => openGameDetail(gameId, awayFallback, homeFallback) });
    }
    const body = document.getElementById("detail-body");

    try {
      const res = await fetch(`${API_BASE}/api/ahl/game/${encodeURIComponent(gameId)}`);
      const g = await res.json();
      ahlBoxData = g;

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
        <div id="ahl-video-recap-slot"></div>
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

      html += renderAhlShotMap(g.pxp, homeId, awayId, homeAbbr, awayAbbr);

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
            const rawNum = idx === 0 ? gl.assist1_num : gl.assist2_num;
            const fbNum = idx === 0 ? gl.assist1_season_num : gl.assist2_season_num;
            const anum = (rawNum !== undefined && rawNum !== null && rawNum !== "" && Number(rawNum) > 0) ? rawNum : fbNum;
            const numHtml = anum ? ` <span style="color:#3a86ff;font-family:'Roboto Mono',monospace;font-weight:700;">(${escapeHtml(anum)})</span>` : "";
            return `<span class="player-link-inline" data-ahl-player-id="${escapeHtml(aid)}">${escapeHtml(aname)}</span>${numHtml}`;
          }).join(", ");

          const tags = [gl.power_play === "1" ? "PP" : "", gl.short_handed === "1" ? "SH" : "", gl.empty_net === "1" ? "EN" : ""].filter(Boolean).join(",");

          html += `
            <div class="goal-row">
              <div class="time">${escapeHtml(ahlStr(gl.time))}</div>
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
          const rawOffender = p.resolved_offender || p.player_penalized_info || p.player_penalized || p.taken_by || p.takenBy || p.player || p.offender || null;
          const rawServed = p.resolved_served || p.player_served_info || p.player_served || p.served_by || p.servedBy || null;
          const pid = hlPersonId(rawOffender) || hlPersonId(rawServed);
          const offenderName = hlPersonName(rawOffender);
          const servedName = hlPersonName(rawServed);
          const pName = offenderName || (servedName ? `Командный штраф (отб. ${servedName})` : "Командный штраф");
          const teamCode = String(p.team_id || "") === homeId ? homeAbbr : awayAbbr;
          const desc = typeof formatPenaltyName === "function" ? formatPenaltyName(p.description || p.lang_penalty_description) : (p.description || "Штраф");
          html += `
            <div class="goal-row">
              <div class="time">${escapeHtml(ahlStr(p.time))}</div>
              <div class="desc">
                <div class="scorer"><span class="${pid ? "player-link-inline" : ""}" data-ahl-player-id="${escapeHtml(pid)}">${escapeHtml(pName)}</span> (${escapeHtml(teamCode)})</div>
                <div class="assists">${escapeHtml(desc)}</div>
              </div>
              <div class="scoreline" style="color:#ff4d4d !important;">${escapeHtml(ahlStr(p.minutes, 2))} мин</div>
            </div>
          `;
        });
      }

      // Расширенная статистика команд
      const sumShots = (lineup) => (Array.isArray(lineup?.players) ? lineup.players : []).reduce((s, p) => s + (Number(p.shots) || 0), 0);
      const awaySog = meta.visiting_shots ?? meta.visitor_shots ?? away.shots ?? sumShots(g.visitor_team_lineup);
      const homeSog = meta.home_shots ?? home.shots ?? sumShots(g.home_team_lineup);

      /// Броски по периодам: проверяем все структуры периодов
      const pArr = Array.isArray(g.periods) ? g.periods : [];
      const getPShots = (idx, isHome) => {
        const per = pArr[idx];
        if (!per) return null;
        if (isHome) {
          return per.home_shots ?? per.homeShots ?? per.shots?.home ?? per.shots?.home_shots ?? null;
        }
        return per.visiting_shots ?? per.visitor_shots ?? per.visitorShots ?? per.shots?.visitor ?? per.shots?.visiting_shots ?? null;
      };

      let s1A = getPShots(0, false), s1H = getPShots(0, true);
      let s2A = getPShots(1, false), s2H = getPShots(1, true);
      let s3A = getPShots(2, false), s3H = getPShots(2, true);

      // Если в периодах было пусто — считаем точно по событиям из PXP
      if ((s1A == null || s1H == null) && Array.isArray(g.pxp)) {
        const pxpShots = g.pxp.filter(ev => {
          const k = String(ev?.event || ev?.type || "").toLowerCase();
          return k === "shot" || k === "goal";
        });
        const countPxp = (pNum, isH) => pxpShots.filter(ev => {
          const p = Number(ev.period_id || ev.period || 0);
          if (p !== pNum) return false;
          const tId = String(ev.team_id || ev.home_or_visitor || "");
          return isH ? (tId === homeId || tId === "home") : (tId === awayId || tId === "visitor");
        }).length;

        if (pxpShots.length) {
          s1A = countPxp(1, false); s1H = countPxp(1, true);
          s2A = countPxp(2, false); s2H = countPxp(2, true);
          s3A = countPxp(3, false); s3H = countPxp(3, true);
        }
      }

      const fmtS = (v) => (v != null && v !== "" ? v : "0");

      // Большинство и штраф
      const awayPim = penalties.filter(p => String(p.team_id || "") !== homeId).reduce((s, p) => s + (Number(p.minutes) || 0), 0);
      const homePim = penalties.filter(p => String(p.team_id || "") === homeId).reduce((s, p) => s + (Number(p.minutes) || 0), 0);
      const awayPpg = goals.filter(gl => String(gl.team_id || "") !== homeId && gl.power_play === "1").length;
      const homePpg = goals.filter(gl => String(gl.team_id || "") === homeId && gl.power_play === "1").length;
      const awayPpOpp = penalties.filter(p => String(p.team_id || "") === homeId && Number(p.minutes || 0) <= 4).length;
      const homePpOpp = penalties.filter(p => String(p.team_id || "") !== homeId && Number(p.minutes || 0) <= 4).length;
      const awayPpStr = meta.visiting_power_play || `${awayPpg} / ${Math.max(awayPpg, awayPpOpp)}`;
      const homePpStr = meta.home_power_play || `${homePpg} / ${Math.max(homePpg, homePpOpp)}`;
      const awayPpPct = Math.max(awayPpg, awayPpOpp) > 0 ? `${((awayPpg / Math.max(awayPpg, awayPpOpp)) * 100).toFixed(1)}%` : "0.0%";
      const homePpPct = Math.max(homePpg, homePpOpp) > 0 ? `${((homePpg / Math.max(homePpg, homePpOpp)) * 100).toFixed(1)}%` : "0.0%";

      html += `
        <div class="section-title">Статистика команд</div>
        <div class="card" style="padding:0;">
          <div class="teamstat-header-flex">
            <div class="teamstat-side-flex"><img class="team-logo" src="${escapeHtml(awayLogo)}" onerror="this.style.display='none'"> <span>${escapeHtml(awayAbbr)}</span></div>
            <div class="teamstat-side-flex right"><span>${escapeHtml(homeAbbr)}</span> <img class="team-logo" src="${escapeHtml(homeLogo)}" onerror="this.style.display='none'"></div>
          </div>
          <div class="teamstat-row-flex"><div class="teamstat-val-flex left" style="font-weight:800;">${escapeHtml(awaySog)}</div><div class="teamstat-label-flex">Броски всего</div><div class="teamstat-val-flex right" style="font-weight:800;">${escapeHtml(homeSog)}</div></div>
          <div class="teamstat-row-flex"><div class="teamstat-val-flex left">${escapeHtml(fmtS(s1A))} | ${escapeHtml(fmtS(s2A))} | ${escapeHtml(fmtS(s3A))}</div><div class="teamstat-label-flex">Броски по периодам (1|2|3)</div><div class="teamstat-val-flex right">${escapeHtml(fmtS(s1H))} | ${escapeHtml(fmtS(s2H))} | ${escapeHtml(fmtS(s3H))}</div></div>
          <div class="teamstat-row-flex"><div class="teamstat-val-flex left">${escapeHtml(awayPpStr)} (${awayPpPct})</div><div class="teamstat-label-flex">Большинство (%PP)</div><div class="teamstat-val-flex right">${escapeHtml(homePpStr)} (${homePpPct})</div></div>
          <div class="teamstat-row-flex"><div class="teamstat-val-flex left">${escapeHtml(awayPim)} (${penalties.filter(p => String(p.team_id || "") !== homeId).length} уд.)</div><div class="teamstat-label-flex">Штраф (мин)</div><div class="teamstat-val-flex right">${escapeHtml(homePim)} (${penalties.filter(p => String(p.team_id || "") === homeId).length} уд.)</div></div>
        </div>
      `;

      // Судьи и тренеры
      const refs = Array.isArray(g.referees) ? g.referees.map(r => hlPersonName(r)).filter(Boolean) : [];
      const lines = Array.isArray(g.linesmen) ? g.linesmen.map(r => hlPersonName(r)).filter(Boolean) : [];
      const awayCoach = Array.isArray(away.coaches) ? away.coaches.map(c => hlPersonName(c)).filter(Boolean).join(", ") : "";
      const homeCoach = Array.isArray(home.coaches) ? home.coaches.map(c => hlPersonName(c)).filter(Boolean).join(", ") : "";
      if (refs.length || lines.length || awayCoach || homeCoach) {
        html += `<div class="section-title">Официальные лица</div><div class="card">`;
        if (awayCoach || homeCoach) html += `<div style="font-size:12px;margin-bottom:6px;"><strong style="color:var(--silver-dim);">Тренеры:</strong> ${escapeHtml(awayAbbr)} — ${escapeHtml(awayCoach || "—")} · ${escapeHtml(homeAbbr)} — ${escapeHtml(homeCoach || "—")}</div>`;
        if (refs.length) html += `<div style="font-size:12px;margin-bottom:4px;"><strong style="color:var(--silver-dim);">Главные арбитры:</strong> ${escapeHtml(refs.join(", "))}</div>`;
        if (lines.length) html += `<div style="font-size:12px;"><strong style="color:var(--silver-dim);">Линейные судьи:</strong> ${escapeHtml(lines.join(", "))}</div>`;
        html += `</div>`;
      }

      html += '<div id="ahl-boxscore-container"></div>';

      if (body) body.innerHTML = html;
      renderAhlBoxTables(awayAbbr, homeAbbr);

      if (isFinal) {
        const vSlot = document.getElementById("ahl-video-recap-slot");
        if (vSlot && !vSlot.innerHTML.trim()) {
          const cleanTeam = (nm, ab) => {
            const s = String(nm || ab || "").trim();
            return s.replace(/\s*hockey\s*club/i, "");
          };
          const awayQ = cleanTeam(away.name, awayAbbr);
          const homeQ = cleanTeam(home.name, homeAbbr);
          const gDate = (meta.date_played || "").slice(0, 10);

          fetch(`${API_BASE}/api/game-youtube-recap?away=${encodeURIComponent(awayQ)}&home=${encodeURIComponent(homeQ)}&date=${encodeURIComponent(gDate)}&league=AHL`)
            .then(r => r.json())
            .then(v => {
              if (!vSlot) return;
              if (v && v.videoId) {
                vSlot.innerHTML = `
                  <div class="section-title">Видеообзор матча (YouTube)</div>
                  <div class="video-container">
                    <iframe src="https://www.youtube.com/embed/${escapeHtml(v.videoId)}?playsinline=1&rel=0" allowfullscreen></iframe>
                  </div>
                `;
              }
            }).catch(() => {});
        }
      }

      if (isLive) {
        startLivePolling(() => openGameDetail(gameId, awayFallback, homeFallback, true), 20000);
      } else {
        stopLivePolling();
      }
    } catch (_) {
      if (!silent && body) body.innerHTML = '<div class="empty">Не удалось загрузить протокол матча AHL</div>';
    }
  }

  // 6. КАРТОЧКА КЛУБА AHL
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
        const dStr = g.date ? new Date(g.date).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
        const fin = g.isFinal || (g.awayScore != null && g.homeScore != null);
        const attr = fin
          ? `data-ahl-game-id="${escapeHtml(g.id)}"`
          : `data-ahl-preview-id="${escapeHtml(g.id)}" data-ahl-away-id="${escapeHtml(g.awayId)}" data-ahl-home-id="${escapeHtml(g.homeId)}"`;

        let resBadge = "—";
        if (fin) {
          const isWin = (g.awayAbbrev === abbr && g.awayScore > g.homeScore) || (g.homeAbbrev === abbr && g.homeScore > g.awayScore);
          if (isWin) {
            if (g.isSo) resBadge = '<span style="color:#2ecc71;font-weight:700;" title="Победа по буллитам">ВБ</span>';
            else if (g.isOt) resBadge = '<span style="color:#2ecc71;font-weight:700;" title="Победа в овертайме">ВО</span>';
            else resBadge = '<span style="color:#2ecc71;font-weight:700;" title="Победа в основное время">В</span>';
          } else {
            if (g.isSo) resBadge = '<span style="color:#e67e22;font-weight:700;" title="Поражение по буллитам">ПБ</span>';
            else if (g.isOt) resBadge = '<span style="color:#f39c12;font-weight:700;" title="Поражение в овертайме">ПО</span>';
            else resBadge = '<span style="color:#e74c3c;font-weight:700;" title="Поражение в основное время">П</span>';
          }
        }

        return `
          <div class="h2h-game-row clickable-row" style="cursor:pointer;" ${attr} data-ahl-away="${escapeHtml(g.awayAbbrev)}" data-ahl-home="${escapeHtml(g.homeAbbrev)}">
            <div style="font-family:'Roboto Mono',monospace;font-size:10px;color:var(--silver-dim);width:66px;flex-shrink:0;">${escapeHtml(dStr)}</div>
            <div class="h2h-team-cell left" style="${g.awayAbbrev === abbr ? "color:#fff;font-weight:700;" : ""}">${escapeHtml(g.awayAbbrev)}</div>
            <div class="h2h-center-cell"><span class="h2h-score-val">${fin ? `${g.awayScore} : ${g.homeScore}` : "vs"}</span></div>
            <div class="h2h-team-cell right" style="${g.homeAbbrev === abbr ? "color:#fff;font-weight:700;" : ""}">${escapeHtml(g.homeAbbrev)}</div>
            <div style="width:28px;text-align:right;font-family:'Oswald',sans-serif;flex-shrink:0;">${resBadge}</div>
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

  // 7. КАРТОЧКА ИГРОКА AHL
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
          <div><div class="label">Дата рождения</div><div class="value">${escapeHtml(ahlStr(info.birthdate || info.birth_date))}</div></div>
          <div><div class="label">Место рождения</div><div class="value">${escapeHtml(ahlStr(info.birthplace || info.hometown))}</div></div>
          <div><div class="label">Рост / Вес</div><div class="value">${escapeHtml(ahlStr(info.height))} / ${escapeHtml(ahlStr(info.weight))}</div></div>
          <div><div class="label">Хват</div><div class="value">${escapeHtml(ahlStr(info.shoots || info.catches))}</div></div>
        </div>
      `;

      if (gbg.length) {
        const last10 = gbg.slice(0, 10);
        let sG = 0, sA = 0, sP = 0, sPm = 0, sB = 0, sSa = 0, sSv = 0, sGa = 0;
        html += `<div class="section-title">Последние матчи AHL</div><div class="table-scroll"><table class="stat-table"><thead><tr><th>Дата</th><th>Матч</th>${isGoalie ? "<th>Бр</th><th>ОБ</th><th>ПШ</th>" : "<th>Г</th><th>П</th><th>О</th><th>+/-</th><th>Б</th>"}</tr></thead><tbody>`;
        last10.forEach(m => {
          const dStr = m.date_played ? new Date(m.date_played).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
          if (isGoalie) {
            sSa += Number(m.shots_against || 0);
            sSv += Number(m.saves || 0);
            sGa += Number(m.goals_against || 0);
          } else {
            sG += Number(m.goals || 0);
            sA += Number(m.assists || 0);
            sP += Number(m.points || 0);
            sPm += Number(m.plus_minus || 0);
            sB += Number(m.shots || 0);
          }
          html += `<tr class="clickable-row" data-ahl-game-id="${escapeHtml(m.game_id || "")}">
            <td class="num">${escapeHtml(dStr)}</td>
            <td>${escapeHtml(m.opponent_team_code || m.opponent || "—")}</td>
            ${isGoalie
              ? `<td class="num">${ahlStr(m.shots_against, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlStr(m.saves, 0)}</td><td class="num">${ahlStr(m.goals_against, 0)}</td>`
              : `<td class="num">${ahlStr(m.goals, 0)}</td><td class="num">${ahlStr(m.assists, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlStr(m.points, 0)}</td><td class="num">${ahlStr(m.plus_minus, 0)}</td><td class="num">${ahlStr(m.shots, 0)}</td>`}
          </tr>`;
        });
        html += isGoalie
          ? `<tr style="background:var(--surface-2);font-weight:700;"><td colspan="2" style="color:#fff;">Итого (${last10.length} и)</td><td class="num" style="color:#fff;">${sSa}</td><td class="num" style="color:#2ecc71;">${sSv}</td><td class="num" style="color:#fff;">${sGa}</td></tr>`
          : `<tr style="background:var(--surface-2);font-weight:700;"><td colspan="2" style="color:#fff;">Итого (${last10.length} и)</td><td class="num" style="color:#2ecc71;">${sG}</td><td class="num" style="color:#3a86ff;">${sA}</td><td class="num" style="color:#fff;">${sP}</td><td class="num" style="color:${sPm >= 0 ? "#2ecc71" : "#ff4d4d"};">${sPm > 0 ? `+${sPm}` : sPm}</td><td class="num" style="color:#fff;">${sB}</td></tr>`;
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
                <td class="num">${ahlStr(s.games_played, 0)}</td>
                ${isGoalie
                  ? `<td class="num">${ahlStr(s.wins, 0)}</td><td class="num">${ahlStr(s.losses, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlStr(s.save_percentage)}</td><td class="num">${ahlStr(s.goals_against_average)}</td>`
                  : `<td class="num">${ahlStr(s.goals, 0)}</td><td class="num">${ahlStr(s.assists, 0)}</td><td class="num" style="color:#fff;font-weight:700;">${ahlStr(s.points, 0)}</td><td class="num">${ahlStr(s.plus_minus, 0)}</td><td class="num">${ahlStr(s.penalty_minutes, 0)}</td>`}
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

    const ahlPrev = e.target.closest("[data-ahl-preview-id]");
    if (ahlPrev && ahlPrev.dataset.ahlPreviewId) {
      openFutureGamePreview(
        ahlPrev.dataset.ahlPreviewId,
        { id: ahlPrev.dataset.ahlAwayId || "", abbrev: ahlPrev.dataset.ahlAway || "", logo: ahlPrev.dataset.ahlAwayLogo || "" },
        { id: ahlPrev.dataset.ahlHomeId || "", abbrev: ahlPrev.dataset.ahlHome || "", logo: ahlPrev.dataset.ahlHomeLogo || "" },
        ahlPrev.dataset.ahlSeason || ""
      );
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
    openFutureGamePreview,
    openGameDetail,
    openTeamDetail,
    openPlayerDetail,
  };
})();
