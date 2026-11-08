// Faceit CS2 Predictor — панель с прогнозом CatBoost, статами игроков и вето-помощником
(() => {
  'use strict';
  if (window.__faiScoutLoaded) return;
  window.__faiScoutLoaded = true;

  const ME = '-J0ker';
  const API = 'https://www.faceit.com/api';
  const CACHE_TTL = 6 * 3600 * 1000;
  const MAPS = ['de_anubis', 'de_dust2', 'de_inferno', 'de_mirage', 'de_nuke', 'de_vertigo'];
  const STD_MAPS = ['de_ancient', 'de_anubis', 'de_cache', 'de_dust2', 'de_inferno',
    'de_mirage', 'de_nuke', 'de_overpass', 'de_train', 'de_vertigo'];
  const LEVEL_ELO = [300, 625, 825, 975, 1125, 1275, 1440, 1640, 1875, 2100];
  const MIN_MAP_GAMES = 20;
  const PLAY_P = 0.55;
  const WEAK_P = 0.46;

  let hud = null;
  let currentId = null;
  let model = null;
  let featureOrder = null;
  let runSeq = 0;
  let lastState = null;

  const histMemo = new Map();

  function mapLabel(m) {
    const s = String(m || '').replace(/^de_/, '');
    return s ? s[0].toUpperCase() + s.slice(1) : '—';
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  // Кэш общий для всех окон: sessionStorage живёт на вкладку, и два окна одной
  // комнаты считали по разным снимкам статов.
  const memCache = new Map();

  const cache = {
    loaded: false,
    async load() {
      if (this.loaded) return;
      this.loaded = true;
      try {
        const all = await chrome.storage.local.get(null);
        const drop = [];
        for (const key of Object.keys(all)) {
          if (!key.startsWith('fai_')) continue;
          const item = all[key];
          if (!item || !item.t || Date.now() - item.t > CACHE_TTL) drop.push(key);
          else memCache.set(key, item);
        }
        if (drop.length) await chrome.storage.local.remove(drop);
      } catch (e) {}
      try {
        Object.keys(sessionStorage).filter((k) => k.startsWith('fai_')).forEach((k) => sessionStorage.removeItem(k));
      } catch (e) {}
    },
    get(key) {
      const item = memCache.get(key);
      if (!item || Date.now() - item.t > CACHE_TTL) return null;
      return item.d;
    },
    set(key, data) {
      const item = { t: Date.now(), d: data };
      memCache.set(key, item);
      try { chrome.storage.local.set({ [key]: item }); } catch (e) {}
    },
    clearFailed() {
      const drop = [...memCache.keys()]
        .filter((k) => k.startsWith('fai_p_'))
        .filter((k) => {
          const v = memCache.get(k);
          return !v || !v.d || v.d.unknown;
        });
      drop.forEach((k) => memCache.delete(k));
      if (drop.length) { try { chrome.storage.local.remove(drop); } catch (e) {} }
    },
  };

  function matchIdFromUrl() {
    const m = location.pathname.match(/\/room\/(\d-[0-9a-zA-Z-]+)/);
    return m ? m[1] : null;
  }

  async function api(path, tries = 5) {
    let last;
    for (let i = 0; i < tries; i++) {
      try {
        const r = await fetch(API + path, {
          headers: { Accept: 'application/json' },
          credentials: 'include',
        });
        if (r.ok) return r.json();
        last = new Error('HTTP ' + r.status);
        if (r.status !== 403 && r.status !== 429 && r.status < 500) throw last;
      } catch (e) {
        last = e;
      }
      await sleep([800, 1600, 3200, 5000, 8000][i] || 8000);
    }
    throw last || new Error('request failed');
  }

  function calcStreak(s0) {
    if (!Array.isArray(s0) || !s0.length) return 0;
    const last = String(s0[s0.length - 1]);
    let n = 0;
    for (let i = s0.length - 1; i >= 0; i--) {
      if (String(s0[i]) === last) n++;
      else break;
    }
    return last === '1' ? n : -n;
  }

  async function getHistory(id) {
    const key = 'fai_h_' + id;
    const cached = cache.get(key);
    if (cached) return cached;
    if (histMemo.has(id)) return histMemo.get(id);

    const task = (async () => {
      const raw = await api(`/stats/v1/stats/time/users/${id}/games/cs2?size=50&page=0`, 3);
      const arr = (Array.isArray(raw) ? raw : []).map((m) => ({
        id: m.matchId,
        elo: Number(m.elo) || 0,
        d: Number(m.elo_delta) || 0,
        map: m.i1 || '',
        adr: Number(m.c10) || 0,
      }));
      if (arr.length) cache.set(key, arr);
      return arr;
    })();
    histMemo.set(id, task);
    try { return await task; } finally { histMemo.delete(id); }
  }

  function mapAgg(hist) {
    const out = {};
    for (const m of hist) {
      if (!m.map || !m.map.startsWith('de_')) continue;
      const r = out[m.map] || (out[m.map] = {
        w: 0, l: 0, adrSum: 0, adrN: 0,
      });
      if (m.d > 0) r.w++;
      else if (m.d < 0) r.l++;
      if (m.adr) { r.adrSum += m.adr; r.adrN++; }
    }
    return out;
  }

  function teamMapAgg(list) {
    const out = {};
    for (const p of list) {
      const agg = p.mapAgg || {};
      for (const [map, r] of Object.entries(agg)) {
        const t = out[map] || (out[map] = {
          w: 0, l: 0, adrSum: 0, adrN: 0,
        });
        t.w += r.w;
        t.l += r.l;
        t.adrSum += r.adrSum;
        t.adrN += r.adrN;
      }
    }
    return out;
  }

  async function resolveElo(p, out, getHist) {
    const hist = await getHist();

    if (hist.length) {
      const known = hist.find((m) => Number(m.elo) > 0);
      if (known) {
        out.elo = Number(known.elo);
        out.eloSrc = 'history';
        return;
      }

      let sum = 0;
      let n = 0;
      for (const m of hist.slice(0, 3)) {
        try {
          const d = await api(`/match/v2/match/${m.id}`);
          const teams = (d.payload && d.payload.teams) || {};
          const rosters = [
            ...((teams.faction1 && teams.faction1.roster) || []),
            ...((teams.faction2 && teams.faction2.roster) || []),
          ];
          for (const r of rosters) {
            if (r.id === p.id) continue;
            const e = Number(r.elo);
            if (e > 0) { sum += e; n += 1; }
          }
        } catch (e) {}
        await sleep(250);
      }
      if (n >= 5) {
        out.elo = Math.round(sum / n);
        out.eloSrc = 'lobby';
        return;
      }
    }

    if (out.level >= 1 && out.level <= 10) {
      out.elo = LEVEL_ELO[out.level - 1];
      out.eloSrc = 'level';
      return;
    }

    out.elo = 1000;
    out.eloSrc = 'default';
  }

  async function playerInfo(p) {
    const key = 'fai_p_' + p.id;
    const cached = cache.get(key);
    if (cached) {
      const fresh = { ...cached, id: p.id, nickname: p.nickname, party: p.partyId };
      if (p.elo != null && Number(p.elo) > 0) {
        fresh.elo = Number(p.elo);
        fresh.eloSrc = 'roster';
        fresh.eloEstimated = false;
      }
      if (p.gameSkillLevel) fresh.level = p.gameSkillLevel;
      return fresh;
    }

    const out = {
      id: p.id,
      nickname: p.nickname,
      party: p.partyId,
      elo: p.elo != null ? Number(p.elo) : null,
      level: p.gameSkillLevel || null,
      kd: null, adr: null, hs: null, wr: null, matches: null, streak: 0,
    };

    let hist = null;
    let histFailed = false;
    const getHist = async () => {
      if (hist !== null) return hist;
      try {
        hist = await getHistory(p.id);
      } catch (e) {
        hist = [];
        histFailed = true;
      }
      return hist;
    };

    // профиль нужен только если в лобби нет ELO (калибровка)
    if (out.elo == null) {
      try {
        const u = await api(`/users/v1/users/${p.id}`);
        const cs2 = (u.payload && u.payload.games && u.payload.games.cs2) || {};
        if (cs2.faceit_elo) out.elo = Number(cs2.faceit_elo);
        if (cs2.skill_level) out.level = cs2.skill_level;
      } catch (e) {}
      await sleep(150);
    }

    try {
      const s = await api(`/stats/v1/stats/users/${p.id}/games/cs2`);
      const lt = s.lifetime || {};
      if (lt.updated_at) out.updatedAt = Number(lt.updated_at);
      if (lt.k5) {
        out.kd = parseFloat(lt.k5);
        out.adr = lt.k17 ? parseFloat(lt.k17) : null;
        out.hs = lt.k8 ? parseFloat(lt.k8) : null;
        out.wr = lt.k6 ? parseFloat(lt.k6) : null;
        out.matches = lt.m1 ? parseInt(lt.m1, 10) : null;
        out.streak = calcStreak(lt.s0);
      }
    } catch (e) {}

    if (!out.elo) await resolveElo(p, out, getHist);

    if (out.kd == null) {
      const h = await getHist();
      if (!h.length && !histFailed) out.newPlayer = true;
    }

    if (out.updatedAt && Date.now() - out.updatedAt > 30 * 86400000) {
      out.staleDays = Math.floor((Date.now() - out.updatedAt) / 86400000);
    }

    out.eloEstimated = !!(out.eloSrc && out.eloSrc !== 'history');
    out.unknown = out.kd == null;
    if (!out.unknown) cache.set(key, out);
    return out;
  }

  function agg(list, key, fallback) {
    if (!list.length) return fallback;
    const vals = list.map((p) => (p[key] == null ? fallback : p[key]));
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }

  function teamEloStd(list) {
    const vals = list.map((p) => (p.elo == null ? 1000 : p.elo));
    if (vals.length < 2) return 80;
    const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
    return Math.sqrt(vals.reduce((s, v) => s + (v - avg) ** 2, 0) / vals.length);
  }

  function teamMapGames(list, map) {
    let n = 0;
    for (const p of list) {
      const r = p.mapAgg && p.mapAgg[map];
      if (!r) continue;
      n += r.w + r.l;
    }
    return n;
  }

  function teamMapWr(list, map) {
    let w = 0;
    let l = 0;
    for (const p of list) {
      const r = p.mapAgg && p.mapAgg[map];
      if (!r) continue;
      w += r.w;
      l += r.l;
    }
    if (!w && !l) return null;
    return ((w + 2.5) / (w + l + 5)) * 100;
  }

  function teamStats(list, map) {
    return {
      elo: agg(list, 'elo', 1000),
      kd: agg(list, 'kd', 1.0),
      adr: agg(list, 'adr', 77),
      hs: agg(list, 'hs', 42),
      wr: agg(list, 'wr', 48),
      eloStd: teamEloStd(list),
      matches: agg(list, 'matches', 750),
      streak: agg(list, 'streak', 0),
      mapWr: teamMapWr(list, map),
    };
  }

  function buildFeatures(mine, enemy, map) {
    const f = { map_name_de_anubis: 0, map_name_de_dust2: 0, map_name_de_inferno: 0,
      map_name_de_mirage: 0, map_name_de_nuke: 0, map_name_de_vertigo: 0 };
    const mWr = mine.mapWr != null ? mine.mapWr : mine.wr;
    const eWr = enemy.mapWr != null ? enemy.mapWr : enemy.wr;
    f.team_1_avg_elo = mine.elo;
    f.team_2_avg_elo = enemy.elo;
    f.elo_diff = mine.elo - enemy.elo;
    f.team_1_elo_std = mine.eloStd;
    f.team_2_elo_std = enemy.eloStd;
    f.elo_std_diff = mine.eloStd - enemy.eloStd;
    f.team_1_avg_kd = mine.kd;
    f.team_2_avg_kd = enemy.kd;
    f.kd_diff = mine.kd - enemy.kd;
    f.team_1_avg_adr = mine.adr;
    f.team_2_avg_adr = enemy.adr;
    f.adr_diff = mine.adr - enemy.adr;
    f.team_1_hs_rate = mine.hs;
    f.team_2_hs_rate = enemy.hs;
    f.hs_diff = mine.hs - enemy.hs;
    f.team_1_map_winrate = mWr;
    f.team_2_map_winrate = eWr;
    f.map_winrate_diff = mWr - eWr;
    f.team_1_streak = mine.streak;
    f.team_2_streak = enemy.streak;
    f.streak_diff = mine.streak - enemy.streak;
    f.team_1_avg_matches = mine.matches;
    f.team_2_avg_matches = enemy.matches;
    if (MAPS.includes(map)) f['map_name_' + map] = 1;
    return f;
  }

  async function loadModel() {
    if (model) return model;
    const r = await fetch(chrome.runtime.getURL('model.json'));
    model = await r.json();
    featureOrder = model.features_info.float_features
      .slice()
      .sort((a, b) => a.feature_index - b.feature_index)
      .map((f) => f.feature_id);
    return model;
  }

  function predict(features) {
    const x = featureOrder.map((name) => features[name] || 0);
    const scale = model.scale_and_bias[0];
    const bias = model.scale_and_bias[1][0];
    let sum = 0;
    for (const tree of model.oblivious_trees) {
      let idx = 0;
      const splits = tree.splits;
      for (let i = 0; i < splits.length; i++) {
        if (x[splits[i].float_feature_index] > splits[i].border) idx |= 1 << i;
      }
      sum += tree.leaf_values[idx];
    }
    return 1 / (1 + Math.exp(-(sum * scale + bias)));
  }

  function flags(p) {
    const out = [];
    if (p.kd != null && p.wr != null && p.matches != null) {
      if (p.matches < 80 && p.kd >= 1.35 && p.wr >= 60) out.push(['смурф', 'smurf']);
      else if (p.matches < 150 && p.kd >= 1.45) out.push(['смурф?', 'smurf']);
      else if (p.matches < 50 && p.kd >= 1.25) out.push(['смурф?', 'smurf']);
    }
    if (p.streak <= -4) out.push(['руинер', 'ruin']);
    else if (p.streak === -3 && p.kd != null && p.kd < 0.85) out.push(['тильт', 'ruin']);
    else if (p.kd != null && p.kd < 0.7 && p.matches > 80) out.push(['руинер', 'ruin']);
    return out;
  }

  function makeHud() {
    if (hud && document.body.contains(hud)) return hud;
    hud = document.createElement('div');
    hud.id = 'fai-hud';
    hud.innerHTML = `
      <div class="fai-head">
        <span class="fai-logo">FACEIT CS2 PREDICTOR</span>
        <span class="fai-tools">
          <button class="fai-btn fai-refresh" title="Обновить">⟳</button>
          <button class="fai-btn fai-min" title="Свернуть">–</button>
          <button class="fai-btn fai-close" title="Закрыть">✕</button>
        </span>
      </div>
      <div class="fai-body"><div class="fai-loading">Загружаю лобби…</div></div>`;
    document.body.appendChild(hud);
    hud.querySelector('.fai-close').addEventListener('click', () => { hud.remove(); hud = null; });
    hud.querySelector('.fai-min').addEventListener('click', () => hud.classList.toggle('fai-collapsed'));
    hud.querySelector('.fai-refresh').addEventListener('click', () => { cache.clearFailed(); run(true); });
    return hud;
  }

  function setBody(html) {
    const node = makeHud().querySelector('.fai-body');
    node.innerHTML = html;
  }

  function setProgress(done, total, label = 'Загружаю статы') {
    const node = hud && hud.querySelector('.fai-progress');
    if (node) node.textContent = `${label} ${done}/${total}…`;
  }

  function rowHtml(p, isMe) {
    const tags = (p.eloEstimated ? '<span class="fai-tag calib">калибровка</span>' : '')
      + (p.newPlayer ? '<span class="fai-tag new" title="Нет ни одного матча на FACEIT">новичок</span>' : '')
      + (p.staleDays ? `<span class="fai-tag stale" title="Последний матч ${p.staleDays} дн. назад">после перерыва</span>` : '')
      + flags(p).map(([t, c]) => `<span class="fai-tag ${c}">${t}</span>`).join('');
    const streakCls = p.streak > 0 ? 'fai-g' : p.streak < 0 ? 'fai-r' : '';
    return `<tr class="${isMe ? 'fai-me' : ''}${p.unknown ? ' fai-na' : ''}">
      <td class="fai-nick" title="${esc(p.nickname)}">${esc(p.nickname)}${tags}</td>
      <td>${p.elo == null ? '—' : (p.eloEstimated ? '≈' : '') + Math.round(p.elo)}</td>
      <td>${p.kd == null ? '—' : p.kd.toFixed(2)}</td>
      <td>${p.adr == null ? '—' : p.adr.toFixed(1)}</td>
      <td>${p.hs == null ? '—' : Math.round(p.hs) + '%'}</td>
      <td>${p.matches == null ? '—' : p.matches}</td>
      <td class="${streakCls}">${p.streak > 0 ? '+' + p.streak : p.streak}</td>
    </tr>`;
  }

  function teamBlock(title, list, stats, accent, unknownCount) {
    const note = unknownCount ? ` <span class="fai-tag smurf">нет стат: ${unknownCount}</span>` : '';
    return `<div class="fai-team ${accent}">
      <div class="fai-team-head">
        <span>${esc(title)}${note}</span>
        <span class="fai-avg">${Math.round(stats.elo)} ELO · KD ${stats.kd.toFixed(2)} · ADR ${stats.adr.toFixed(1)}</span>
      </div>
      <table class="fai-table">
        <thead><tr><th>Игрок</th><th>ELO</th><th>K/D</th><th>ADR</th><th>HS</th><th>Игр</th><th>Стрик</th></tr></thead>
        <tbody>${list.map((p) => rowHtml(p, p.nickname === ME)).join('')}</tbody>
      </table>
    </div>`;
  }

  function summaryPlayerLine(p) {
    const elo = p.elo == null ? '—' : (p.eloEstimated ? '≈' : '') + Math.round(p.elo);
    const tags = [
      p.eloEstimated ? 'калибровка' : '',
      p.newPlayer ? 'новичок' : '',
      p.staleDays ? `после перерыва ${p.staleDays}д` : '',
      p.unknown && !p.newPlayer ? 'нет стат' : '',
      ...flags(p).map(([t]) => t),
    ].filter(Boolean);
    return [
      p.nickname.padEnd(16),
      String(elo).padStart(5),
      (p.kd == null ? '—' : p.kd.toFixed(2)).padStart(5),
      (p.adr == null ? '—' : p.adr.toFixed(1)).padStart(5),
      (p.hs == null ? '—' : Math.round(p.hs) + '%').padStart(4),
      String(p.matches == null ? '—' : p.matches).padStart(5),
      (p.streak > 0 ? '+' + p.streak : String(p.streak)).padStart(5),
    ].join(' ') + (tags.length ? '  ' + tags.join(', ') : '');
  }

  function summaryTeam(title, stats, list) {
    return [
      `${title} · ${Math.round(stats.elo)} ELO · KD ${stats.kd.toFixed(2)} · ADR ${stats.adr.toFixed(1)}`,
      ['Игрок'.padEnd(16), 'ELO'.padStart(5), 'K/D'.padStart(5), 'ADR'.padStart(5),
        'HS'.padStart(4), 'Игр'.padStart(5), 'Стрик'.padStart(5)].join(' '),
      ...list.map(summaryPlayerLine),
    ];
  }

  function summaryVeto(veto) {
    if (!veto) return ['', 'ВЕТО · ещё считается…'];
    const { rows, bans, pick, backup, t1, t2 } = veto;
    const lines = ['', 'ВЕТО · последние 50 матчей'];
    lines.push(`Баним: ${bans.map((r) => mapLabel(r.map)).join(' · ') || '—'}`);
    lines.push(`Играть: ${pick ? mapLabel(pick.map) : '—'}${backup && !bans.includes(backup)
      ? ` (запасная: ${mapLabel(backup.map)})` : ''}`);
    lines.push(['Карта'.padEnd(10), t1.padStart(10), t2.padStart(10), 'Δ'.padStart(7), 'ADR'.padStart(9)].join(' '));
    for (const r of rows) {
      const wrM = r.wrM == null ? '—' : `${Math.round(r.wrM)}% (${r.dM})`;
      const wrE = r.wrE == null ? '—' : `${Math.round(r.wrE)}% (${r.dE})`;
      const diff = r.diff == null ? '—' : `${r.diff > 0 ? '+' : ''}${r.diff.toFixed(1)}`;
      const adr = r.adrM == null && r.adrE == null
        ? '—'
        : `${r.adrM == null ? '—' : Math.round(r.adrM)}/${r.adrE == null ? '—' : Math.round(r.adrE)}`;
      lines.push([
        mapLabel(r.map).padEnd(10),
        wrM.padStart(10),
        wrE.padStart(10),
        diff.padStart(7),
        adr.padStart(9),
      ].join(' ') + (r.ok ? '' : '  мало'));
    }
    return lines;
  }

  function buildSummary() {
    if (!lastState) return '';
    const {
      map, mapPicked, prob, label, myTeamName, enemyTeamName,
      mine, enemy, myStats, enemyStats, inLobby, veto, partial, mapThin,
      gamesMine, gamesEnemy,
    } = lastState;
    const dElo = Math.round(myStats.elo - enemyStats.elo);
    const when = new Date().toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
    const mapNote = mapPicked ? '' : ' (не выбрана — прогноз условный)';
    const tail = [
      partial ? 'пробелы в статах — цифра ориентировочная' : '',
      mapThin ? `мало игр на карте: мы ${gamesMine}, они ${gamesEnemy} из ${MIN_MAP_GAMES} — винрейт карты не считался` : '',
    ].filter(Boolean).join(' · ');
    const lines = [
      `FACEIT CS2 PREDICTOR · ${when}`,
      `Карта: ${mapLabel(map)}${mapNote} · шанс победы ${myTeamName}: ${partial ? '≈ ' : ''}${(prob * 100).toFixed(1)}% (${label}) · ΔELO ${dElo > 0 ? '+' : ''}${dElo}${tail ? '\n⚠ ' + tail : ''}`,
      '',
      ...summaryTeam(`${inLobby ? 'ТВОЯ КОМАНДА' : 'КОМАНДА 1'} · ${myTeamName}`, myStats, mine),
      '',
      ...summaryTeam(`${inLobby ? 'ПРОТИВНИК' : 'КОМАНДА 2'} · ${enemyTeamName}`, enemyStats, enemy),
      ...summaryVeto(veto),
      '',
      'Faceit CS2 Predictor · CatBoost',
    ];
    return '```\n' + lines.join('\n') + '\n```';
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {}
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e) { return false; }
  }

  function render(map, mine, enemy, myStats, enemyStats, prob, inLobby, myTeamName, enemyTeamName, mapPicked, opts) {
    const o = opts || {};
    const pct = (prob * 100).toFixed(1);
    // Пороги переставлены по бэктесту на 38 реальных матчах (08.11): полоса
    // >=0.55 выигрывалась в 67%, а «додж» при любом пороге оказывался хуже
    // монетки (46-50% поражений), поэтому нижней рекомендации больше нет.
    const cls = prob >= PLAY_P ? 'play' : prob >= WEAK_P ? 'neutral' : 'weak';
    const label = prob >= PLAY_P ? 'ИГРАТЬ' : prob >= WEAK_P ? 'НЕЙТРАЛЬНО' : 'БЕЗ СИГНАЛА';
    const mapCap = map.replace('de_', '').replace(/^./, (c) => c.toUpperCase());
    const mapWarn = MAPS.includes(map) || map === 'de_ancient'
      ? '' : ' <span class="fai-tag smurf">нет в обучении</span>';
    const hint = inLobby ? '' : '<div class="fai-warn">Тебя нет в этом лобби — показана команда 1</div>';

    const estimated = [...mine, ...enemy].filter((p) => p.eloEstimated).length;
    const estNote = estimated
      ? `<div class="fai-warn">≈ — оценка ELO у ${estimated} игрок(а) на калибровке (по их последним матчам)</div>`
      : '';
    const unknownMine = mine.filter((p) => p.unknown && !p.newPlayer).length;
    const unknownEnemy = enemy.filter((p) => p.unknown && !p.newPlayer).length;
    const unknownTotal = unknownMine + unknownEnemy;
    const warn = unknownTotal
      ? `<div class="fai-warn">Не загрузились статы: ${unknownTotal}. Прогноз по неполным данным.
           <button class="fai-retry">Повторить</button></div>`
      : '';
    const histFailed = [...mine, ...enemy].filter((p) => p.mapAgg == null).length;
    const partial = histFailed > 0;
    const partialNote = partial
      ? `<div class="fai-warn">История не догрузилась у ${histFailed} игрок(а) — винрейт по картам неполный,
           цифра ниже ориентировочная. <button class="fai-retry">Повторить</button></div>`
      : '';
    const thinNote = o.mapThin
      ? `<div class="fai-warn">Мало игр на ${mapCap}: мы ${o.gamesMine}, они ${o.gamesEnemy} из ${MIN_MAP_GAMES}.
           Винрейт карты в расчёт не брался, взят общий.</div>`
      : '';
    const weakNote = prob < WEAK_P
      ? `<div class="fai-warn">Модель даёт меньше 50%, но по бэктесту на реальных матчах комнаты из этой
           полосы заканчивались победой примерно в половине случаев — это не повод уклоняться от матча.
           Рекомендацию «додж» панель больше не выдаёт: на реальных матчах этот сигнал не подтвердился.</div>`
      : '';

    lastState = {
      map, mapPicked, prob, label, myTeamName, enemyTeamName,
      mine, enemy, myStats, enemyStats, inLobby, veto: null,
      partial: histFailed, mapThin: !!o.mapThin,
      gamesMine: o.gamesMine, gamesEnemy: o.gamesEnemy,
    };

    setBody(`
      ${hint}
      ${estNote}
      ${warn}
      ${partialNote}
      ${thinNote}
      ${weakNote}
      <div class="fai-verdict ${cls}${partial ? ' fai-partial' : ''}">
        <div class="fai-prob">${partial ? '≈ ' : ''}${pct}%</div>
        <div class="fai-label">${label}</div>
      </div>
      <div class="fai-of">шанс победы · <b>${esc(myTeamName)}</b></div>
      <div class="fai-meta">
        <span>${esc(mapCap)}${mapWarn}</span>
        <span class="fai-delta">ΔELO ${Math.round(myStats.elo - enemyStats.elo) > 0 ? '+' : ''}${Math.round(myStats.elo - enemyStats.elo)}</span>
      </div>
      <div class="fai-actions"><button class="fai-copy" title="Вердикт, статы 10 игроков и вето-план в буфер обмена">Скопировать сводку</button></div>
      ${teamBlock(inLobby ? 'Твоя команда' : 'Команда 1', mine, myStats, 'fai-mine', unknownMine)}
      ${teamBlock(inLobby ? 'Противник' : 'Команда 2', enemy, enemyStats, 'fai-enemy', unknownEnemy)}
      <div id="fai-veto"></div>
      <div class="fai-foot">CatBoost · ${model.oblivious_trees.length} деревьев · прогноз для твоей команды</div>
    `);

    hud && hud.querySelectorAll('.fai-retry').forEach((retry) => {
      retry.addEventListener('click', () => { cache.clearFailed(); run(true); });
    });

    const copyBtn = hud && hud.querySelector('.fai-copy');
    if (copyBtn) copyBtn.addEventListener('click', async () => {
      const ok = await copyText(buildSummary());
      copyBtn.classList.toggle('ok', ok);
      copyBtn.textContent = ok ? 'Скопировано ✓' : 'Не удалось скопировать';
      setTimeout(() => {
        if (!copyBtn.isConnected) return;
        copyBtn.classList.remove('ok');
        copyBtn.textContent = 'Скопировать сводку';
      }, 1800);
    });
  }

  function renderVeto(wrap, mine, enemy, pool, inLobby) {
    const a = teamMapAgg(mine);
    const b = teamMapAgg(enemy);
    const seen = [...new Set([...Object.keys(a), ...Object.keys(b)])];
    let maps = (pool || []).filter((m) => m && m.startsWith('de_'));
    if (maps.length < 3) {
      for (const m of seen) if (!maps.includes(m)) maps.push(m);
      if (!maps.length) maps = STD_MAPS.slice();
    }

    const rows = maps.map((map) => {
      const x = a[map] || null;
      const y = b[map] || null;
      const dM = x ? x.w + x.l : 0;
      const dE = y ? y.w + y.l : 0;
      const adjM = dM ? (x.w + 2.5) / (dM + 5) : null;
      const adjE = dE ? (y.w + 2.5) / (dE + 5) : null;
      return {
        map,
        dM,
        dE,
        wrM: dM ? (x.w / dM) * 100 : null,
        wrE: dE ? (y.w / dE) * 100 : null,
        diff: adjM != null && adjE != null ? (adjM - adjE) * 100 : null,
        adrM: x && x.adrN ? x.adrSum / x.adrN : null,
        adrE: y && y.adrN ? y.adrSum / y.adrN : null,
        ok: dM >= MIN_MAP_GAMES && dE >= MIN_MAP_GAMES,
      };
    });

    const rated = rows.filter((r) => r.ok).sort((p, q) => p.diff - q.diff);
    const pick = rated.length ? rated[rated.length - 1] : null;
    const backup = rated.length > 1 ? rated[rated.length - 2] : null;
    const maxBans = Math.max(0, Math.ceil((maps.length - 1) / 2));
    const bans = rated.slice(0, Math.max(0, Math.min(maxBans, rated.length - 1)));
    const ordered = rated.concat(rows.filter((r) => !r.ok));
    const t1 = inLobby ? 'Мы' : 'К1';
    const t2 = inLobby ? 'Они' : 'К2';

    const rec = !pick
      ? '<div class="fai-veto-rec fai-low">Мало матчей по обеим командам — рекомендация появится позже</div>'
      : `<div class="fai-veto-rec">
          <div class="fai-ban-line">${inLobby ? 'Баним' : 'Баны К1'}:
            ${bans.map((r) => `<b>${esc(mapLabel(r.map))}</b>`).join(' · ') || '—'}</div>
          <div class="fai-pick-line">${inLobby ? 'Наша карта' : 'Лучшая у К1'}:
            <b>${esc(mapLabel(pick.map))}</b>${backup && !bans.includes(backup)
              ? ` · запасная: <b>${esc(mapLabel(backup.map))}</b>` : ''}</div>
        </div>`;

    const cellWr = (v, n) => (v == null ? '—' : `${Math.round(v)}% <span class="fai-games">(${n})</span>`);
    const cellAdr = (m, e) => {
      if (m == null && e == null) return '—';
      return `${m == null ? '—' : Math.round(m)} / ${e == null ? '—' : Math.round(e)}`;
    };

    const body = ordered.map((r) => {
      const cls = [r === pick ? 'fai-pick-row' : '', bans.includes(r) ? 'fai-ban-row' : '', r.ok ? '' : 'fai-low']
        .filter(Boolean).join(' ');
      const dcls = r.diff == null ? '' : r.diff >= 5 ? 'fai-g' : r.diff <= -5 ? 'fai-r' : '';
      const diff = r.diff == null ? '—' : `${r.diff > 0 ? '+' : ''}${r.diff.toFixed(1)}`;
      return `<tr class="${cls}">
        <td class="fai-map">${esc(mapLabel(r.map))}${r.ok ? '' : '<span class="fai-tag low">мало</span>'}</td>
        <td>${cellWr(r.wrM, r.dM)}</td>
        <td>${cellWr(r.wrE, r.dE)}</td>
        <td class="${dcls}">${diff}</td>
        <td>${cellAdr(r.adrM, r.adrE)}</td>
      </tr>`;
    }).join('');

    if (lastState) lastState.veto = { rows: ordered, bans, pick, backup, t1, t2 };

    wrap.innerHTML = `
      <div class="fai-veto-head">
        <span>ВЕТО · КАРТЫ</span>
        <span class="fai-avg">последние 50 матчей</span>
      </div>
      ${rec}
      <table class="fai-table fai-veto-table">
        <thead><tr><th>Карта</th><th>${t1}</th><th>${t2}</th><th>Δ</th><th>ADR</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
      <div class="fai-veto-note">WR фактический · Δ — по сглаженному WR (п.п.) · ADR ${t1} / ${t2}</div>`;
  }

  async function loadMaps(token, infos) {
    for (let i = 0; i < infos.length; i++) {
      if (token !== runSeq || !hud) return false;
      const p = infos[i];
      if (p.mapAgg == null) {
        if (p.newPlayer) {
          p.mapAgg = {};
        } else {
          try {
            p.mapAgg = mapAgg(await getHistory(p.id));
          } catch (e) {
            p.mapAgg = null;
          }
        }
      }
      if (token !== runSeq || !hud) return false;
      setProgress(i + 1, infos.length, 'Считаю карты');
      await sleep(320);
    }
    return true;
  }

  function showVeto(mine, enemy, pool, inLobby) {
    const wrap = hud && hud.querySelector('#fai-veto');
    if (!wrap) return;
    renderVeto(wrap, mine, enemy, pool, inLobby);
  }

  async function run() {
    const id = matchIdFromUrl();
    if (!id) return;
    runSeq++;
    const token = runSeq;
    currentId = id;
    if (hud) { hud.remove(); hud = null; }
    setBody('<div class="fai-loading"><div class="fai-progress">Загружаю лобби…</div></div>');

    try {
      const data = await api(`/match/v2/match/${id}`);
      const payload = data.payload || {};
      const factions = payload.teams || {};
      const roster1 = (factions.faction1 && factions.faction1.roster) || [];
      const roster2 = (factions.faction2 && factions.faction2.roster) || [];

      if (roster1.length < 5 || roster2.length < 5) {
        setBody('<div class="fai-warn">Ждём подключения всех 10 игроков…<br><button class="fai-retry">Проверить снова</button></div>');
        const b = hud && hud.querySelector('.fai-retry');
        if (b) b.addEventListener('click', () => run(true));
        return;
      }

      const pick = (payload.voting && payload.voting.map && payload.voting.map.pick) || [];
      const map = pick[0] || (payload.maps && payload.maps[0] && payload.maps[0].class_name) || 'de_mirage';
      const ents = (payload.voting && payload.voting.map && payload.voting.map.entities) || [];
      const mapPool = ents
        .map((e) => e && (e.class_name || e.game_map_id))
        .filter((m) => m && m.startsWith('de_'));

      await cache.load();
      await loadModel();

      const all = [
        ...roster1.map((p) => ({ p, team: 1 })),
        ...roster2.map((p) => ({ p, team: 2 })),
      ];
      const infos = [];
      for (const item of all) {
        const info = await playerInfo(item.p);
        infos.push({ ...info, team: item.team });
        setProgress(infos.length, all.length);
        await sleep(300);
      }

      setBody('<div class="fai-loading"><div class="fai-progress">Считаю карты 0/10…</div></div>');
      const mapsReady = await loadMaps(token, infos);
      if (!mapsReady) return;

      const mineAll = infos.filter((p) => p.team === 1);
      const enemyAll = infos.filter((p) => p.team === 2);
      const inLobby = infos.some((p) => p.nickname === ME);
      const name1 = (factions.faction1 && factions.faction1.name) || 'Команда 1';
      const name2 = (factions.faction2 && factions.faction2.name) || 'Команда 2';
      let mine = mineAll;
      let enemy = enemyAll;
      let myTeamName = name1;
      let enemyTeamName = name2;
      if (inLobby && !mineAll.some((p) => p.nickname === ME)) {
        mine = enemyAll;
        enemy = mineAll;
        myTeamName = name2;
        enemyTeamName = name1;
      }

      const myStats = teamStats(mine, map);
      const enemyStats = teamStats(enemy, map);
      const gamesMine = teamMapGames(mine, map);
      const gamesEnemy = teamMapGames(enemy, map);
      const mapThin = gamesMine < MIN_MAP_GAMES || gamesEnemy < MIN_MAP_GAMES;
      if (mapThin) { myStats.mapWr = null; enemyStats.mapWr = null; }
      const prob = predict(buildFeatures(myStats, enemyStats, map));
      render(map, mine, enemy, myStats, enemyStats, prob, inLobby, myTeamName, enemyTeamName, !!pick[0],
        { mapThin, gamesMine, gamesEnemy });
      showVeto(mine, enemy, mapPool, inLobby);
    } catch (e) {
      setBody(`<div class="fai-warn">Ошибка: ${esc(e.message)}<br><button class="fai-retry">Повторить</button></div>`);
      const b = hud && hud.querySelector('.fai-retry');
      if (b) b.addEventListener('click', () => { cache.clearFailed(); run(true); });
    }
  }

  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname === lastPath) return;
    lastPath = location.pathname;
    const id = matchIdFromUrl();
    if (id) run();
    else if (hud) { hud.remove(); hud = null; }
  }, 1000);

  if (chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
      if (msg && msg.type === 'fai-ping') {
        sendResponse({ ok: true, matchId: matchIdFromUrl(), hasHud: !!(hud && document.body.contains(hud)) });
      }
    });
  }

  const initialId = matchIdFromUrl();
  if (initialId) {
    console.log('[Faceit CS2 Predictor] внедрён, комната:', initialId);
    run();
  } else {
    console.log('[Faceit CS2 Predictor] внедрён, ждём комнату матча');
  }
})();
