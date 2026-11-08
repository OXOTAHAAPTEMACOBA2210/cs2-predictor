// CS2 Pro Predictor (HLTV) — фаза 2: статистика вето и винрейтов + прогноз
// модели на реальных матчах HLTV (28 415 матчей, 2023-05..2026-11) и live-
// пересчёт вероятности по ходу серии. Запросов к HLTV не делает: модель и
// снимок рейтингов лежат в пакете расширения.
(() => {
  if (window.__hltvProLoaded) return;
  window.__hltvProLoaded = true;

  const MIN_GAMES = 5;    // меньше — не сравниваем
  const THIN_GAMES = 10;  // меньше — предупреждаем о тонкой выборке
  const NOISE_PP = 8;     // разрыв меньше — шум
  const THIN_RATING = 20; // меньше матчей в рейтинге — прогноз шаткий
  const EDGE_P = 0.55;    // перевес, с которого называем фаворита
  const CLEAR_P = 0.65;   // явный фаворит
  const DAY_MS = 86400000;
  const MAP_CODES = {
    ancient: 'de_ancient', dust2: 'de_dust2', dust64: 'de_dust2', inferno: 'de_inferno',
    mirage: 'de_mirage', nuke: 'de_nuke', anubis: 'de_anubis', cache: 'de_cache',
    overpass: 'de_overpass', train: 'de_train', vertigo: 'de_vertigo',
  };

  const txt = (n) => (n && n.textContent ? n.textContent.trim() : '');
  const pctVal = (s) => {
    const m = /(\d+(?:[.,]\d+)?)\s*%/.exec(s || '');
    return m ? parseFloat(m[1].replace(',', '.')) : null;
  };
  const intVal = (s) => {
    const m = /(\d+)/.exec(s || '');
    return m ? parseInt(m[1], 10) : null;
  };
  const mapKey = (name) => MAP_CODES[String(name || '').toLowerCase().replace(/[^a-z0-9]/g, '')] || null;
  const mapLabel = (k) => (k || '').replace(/^de_/, '').replace(/^\w/, (c) => c.toUpperCase());
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function extractTeams(doc) {
    const head = doc.querySelector('.map-stats-infobox-header');
    if (head) {
      const a = head.querySelector('.team:not(.team2)');
      const b = head.querySelector('.team.team2, .team2');
      const n1 = txt(a && a.querySelector('.team-name')) || txt(a);
      const n2 = txt(b && b.querySelector('.team-name')) || txt(b);
      if (n1 && n2) return { t1: n1, t2: n2 };
    }
    // На BO1-страницах инфобокса нет, берём команды из шапки матча, а не со
    // всей страницы — там 70+ ссылок на команды соседних матчей.
    const inBox = (scope) => {
      const names = [];
      for (const a of [...scope.querySelectorAll('a[href^="/team/"]')]) {
        const n = (a.textContent || '').trim().replace(/\s+/g, ' ');
        if (n && !names.includes(n)) names.push(n);
        if (names.length === 2) break;
      }
      return names;
    };
    const box = doc.querySelector('.teamsBox');
    let names = box ? inBox(box) : [];
    if (names.length < 2) names = inBox(doc);
    if (names.length === 2) return { t1: names[0], t2: names[1] };
    const title = /(.+?)\s+vs\.?\s+(.+?)(?:\s+at\s|$)/.exec(doc.title || '');
    if (title) return { t1: title[1].trim(), t2: title[2].trim() };
    return null;
  }

  // Реальное вето: "1. Butterfly removes Nuke" / "7. Inferno was left over".
  // Симуляция HLTV та же по форме, но в настоящем времени и с процентом на
  // конце: "1. Underworld removes Nuke 70%" / "7. Ancient is left over 47%".
  function parseVetoLine(line) {
    let m = /^(?:\d+\.\s*)?(.+?)\s+(removed|removes|banned|bans|picked|picks|chosen)\s+(.+?)\s*(?:\d+\s*%)?\.?$/i.exec(line);
    if (m) {
      return { team: m[1].trim(), act: /ban|remov/i.test(m[2]) ? 'ban' : 'pick',
               mapName: m[3].trim() };
    }
    m = /^(?:\d+\.\s*)?(.+?)\s+(?:was|is|will be)\s+left\s+over\s*(?:\d+\s*%)?\.?$/i.exec(line);
    if (m) return { team: null, act: 'leftover', mapName: m[1].trim() };
    return null;
  }

  // Настоящее вето живёт в .veto-box, но симуляция HLTV сидит в блоке с теми же
  // классами (.veto-box.simulated-veto): без фильтра несыгранное вето
  // читается как сыгранное.
  function extractVeto(doc) {
    const host = doc.querySelector('.veto-box:not(.simulated-veto)');
    if (!host) return [];
    const steps = [];
    for (const node of [...host.querySelectorAll('.padding div')]) {
      const s = parseVetoLine(txt(node));
      if (s) {
        s.map = mapKey(s.mapName);
        steps.push(s);
      }
    }
    return steps;
  }

  // Формат: "Best of 3 (Online)" лежит в подписи блока вето; если его там нет,
  // берём первый "Best of N" из текста страницы.
  function extractFormat(doc) {
    const host = doc.querySelector('.veto-box:not(.simulated-veto)');
    const texts = [host && host.innerText, doc.body && doc.body.innerText].filter(Boolean);
    for (const text of texts) {
      const m = /Best of (\d)/i.exec(text);
      if (m) return parseInt(m[1], 10);
    }
    return null;
  }

  // Окно статистики, по которой HLTV считает винрейты, зашито в href ссылок
  // инфобокса: startDate=2026-08-05&endDate=2026-11-05
  function extractWindow(doc) {
    const a = doc.querySelector('.map-stats-infobox-winpercentage a');
    const href = a ? a.getAttribute('href') || '' : '';
    const s = /[?&]startDate=(\d{4})-(\d{2})-(\d{2})/.exec(href);
    const e = /[?&]endDate=(\d{4})-(\d{2})-(\d{2})/.exec(href);
    return s && e ? `${s[3]}.${s[2]} — ${e[3]}.${e[2]}` : null;
  }

  function extractMapStats(doc) {
    const cell = (el) => {
      if (!el) return null;
      const playedText = txt(el.querySelector('.map-stats-infobox-maps-played'));
      return {
        wr: pctVal(txt(el.querySelector('.map-stats-infobox-winpercentage'))),
        games: intVal(playedText),
        isMapCount: /map/i.test(playedText),
        mark: el.querySelector('.map-stats-infobox-pick') ? 'pick'
          : el.querySelector('.map-stats-infobox-ban') ? 'ban' : null,
        adv: !!el.querySelector('.map-stats-infobox-winpercentage.advantage'),
      };
    };
    // В DOM висят три секции инфобокса (Win/Pick/Ban): в винрейтах HLTV пишет
    // «N maps», в пик/бан-статистике — «N possibilities».
    return [...doc.querySelectorAll('.map-stats-infobox-maps')].map((box) => {
      const code = box.getAttribute('data-mapname') || '';
      const name = txt(box.querySelector('.mapname')) || code;
      const key = mapKey(code) || mapKey(name);
      const t1 = box.querySelector('.map-stats-infobox-stats:not(.team2)');
      const t2 = box.querySelector('.map-stats-infobox-stats.team2');
      return {
        map: key, mapName: mapLabel(key) || name,
        t1: cell(t1), t2: cell(t2),
        notPicked: /not-picked/.test(box.className),
      };
    }).filter((r) => r.mapName
      && ((r.t1 && r.t1.isMapCount) || (r.t2 && r.t2.isMapCount) || !r.t1 && !r.t2));
  }

  // Симуляция вето HLTV: вкладки Likeliest / 2nd / 3rd — берём первую.
  function extractSimulated(doc) {
    const alt = doc.querySelector('.simulated-veto-alt--0') || doc.querySelector('.simulated-veto-alt');
    if (!alt) return null;
    const steps = [...alt.querySelectorAll('.simulated-veto-step')].map((n) => {
      const chanceEl = n.querySelector('.simulated-veto-step-chance');
      // textContent шага склеивает название карты и процент («Dust2» + «49%» =
      // «Dust249%»), поэтому процент берём из отдельного span, а текст — без него.
      const raw = [...n.childNodes].filter((c) => c !== chanceEl)
        .map((c) => c.textContent).join('').replace(/\s+/g, ' ').trim();
      const s = parseVetoLine(raw);
      if (!s) return null;
      s.chance = intVal(txt(chanceEl));
      s.map = mapKey(s.mapName);
      return s;
    }).filter(Boolean);
    if (!steps.length) return null;
    return {
      steps,
      line: txt(alt.querySelector('.simulated-veto-maps-line')).replace(/\s+/g, ' '),
      maps: steps.filter((s) => s.act !== 'ban').map((s) => s.mapName),
    };
  }

  // Время старта зашито в data-unix (мс) у блоков .timeAndEvent/.countdown;
  // во время матча .countdown получает класс countdown-live и текст «LIVE».
  function extractStart(doc) {
    const el = doc.querySelector('.timeAndEvent .time[data-unix]')
      || doc.querySelector('.countdown[data-unix]');
    const v = el ? parseInt(el.getAttribute('data-unix'), 10) : NaN;
    return v > 0 ? v : null;
  }

  // Карты серии: сыгранные — с числовым счётом, текущая/будущие — с прочерком.
  // Текущий счёт берётся из скорботады, где порядок сторон CT/T меняется после
  // смены сторон, поэтому команду на CT определяем по классу thead.
  function extractSeries(doc) {
    const maps = [];
    for (const mh of doc.querySelectorAll('.mapholder:not(.simulated-map)')) {
      if (!mh.querySelector('.results')) continue;
      const side = (sel) => {
        const e = mh.querySelector(sel);
        if (!e) return null;
        return {
          name: txt(e.querySelector('.results-teamname')),
          score: intVal(txt(e.querySelector('.results-team-score'))),
          pick: /\bpick\b/.test(e.className),
        };
      };
      const left = side('.results-left');
      const right = side('.results-right');
      if (left && right && left.name) maps.push({ name: txt(mh.querySelector('.mapname')), left, right });
    }
    let cur = null;
    const bar = doc.querySelector('.scorebot .score.scoreText');
    if (bar) {
      const ct = intVal(txt(bar.querySelector('.ctScore')));
      const t = intVal(txt(bar.querySelector('.tScore')));
      const ctName = txt(doc.querySelector('.scorebot table.team thead.ctTeamHeaderBg .teamName'))
        .replace(/\s+/g, ' ');
      if (ct != null && t != null) cur = { ct, t, ctName };
    }
    const rm = /^(\d+)\s*-\s*(.+)$/.exec(txt(doc.querySelector('.scorebot .currentRoundText')));
    return {
      live: !!doc.querySelector('.countdown-live'),
      maps,
      cur,
      round: rm ? parseInt(rm[1], 10) : null,
      roundMap: rm ? rm[2].trim() : null,
    };
  }

  function extractProMatch(doc) {
    const veto = extractVeto(doc);
    let bo = extractFormat(doc);
    if (!bo) {
      // Если подписи «Best of N» на странице нет, формат выводим из протокола
      // вето: сколько карт осталось после банов (BO1 = 1, BO3 = 3, BO5 = 5).
      const left = veto.filter((s) => s.act !== 'ban').length;
      if (veto.length >= 3 && left >= 1 && left <= 5) bo = left;
    }
    const series = extractSeries(doc);
    if (!bo && series.maps.length >= 1 && series.maps.length <= 5) bo = series.maps.length;
    return {
      teams: extractTeams(doc),
      veto,
      maps: extractMapStats(doc),
      sim: extractSimulated(doc),
      bo,
      win: extractWindow(doc),
      start: extractStart(doc),
      series,
      noVeto: !!doc.querySelector('.map-stats-infobox-right.no-veto'),
    };
  }

  window.__hltvExtractProMatch = extractProMatch;

  // ---------- модель на реальных матчах HLTV ----------
  // Обучена на 28 415 сыгранных матчах из архива /results (2023-05..2026-11),
  // признаки считаются хронологически и повторяются здесь офлайн: снимок
  // рейтингов команд лежит в пакете расширения, запросов к HLTV нет.

  const FEATURES = ['elo_diff', 'form5_diff', 'form10_diff', 'rest_diff',
    'n30_diff', 'log_n_diff', 'is_bo1', 'is_bo5'];

  let bundle = null;
  let bundleDone = false;

  function loadBundle() {
    if (bundleDone) return Promise.resolve(bundle);
    bundleDone = true;
    // Стенды для headless-прогона не имеют chrome.runtime и подкладывают бандл сами.
    if (window.__hltvProBundle) {
      bundle = window.__hltvProBundle;
      return Promise.resolve(bundle);
    }
    if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.getURL) {
      return Promise.resolve(null);
    }
    return Promise.all([
      fetch(chrome.runtime.getURL('model_hltv.json')).then((r) => r.json()),
      fetch(chrome.runtime.getURL('team_ratings.json')).then((r) => r.json()),
    ]).then(([model, ratings]) => {
      bundle = { model, asOf: ratings.as_of, teams: ratings.teams, meta: ratings.meta || null };
      return bundle;
    }).catch(() => { bundle = null; return null; });
  }

  function modelProb(x) {
    const m = bundle.model;
    const scale = m.scale_and_bias[0];
    const bias = m.scale_and_bias[1][0];
    let sum = 0;
    for (const tree of m.oblivious_trees) {
      let idx = 0;
      const s = tree.splits;
      for (let i = 0; i < s.length; i++) {
        if (x[s[i].float_feature_index] > s[i].border) idx |= 1 << i;
      }
      sum += tree.leaf_values[idx];
    }
    return 1 / (1 + Math.exp(-(sum * scale + bias)));
  }

  const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

  // HLTV пишет название команды то с тегом, то без («ex-ENCE», «9INE»), поэтому
  // кроме точного ключа пробуем сравнение без не-буквенно-цифровых символов.
  function findTeam(name) {
    const teams = bundle.teams;
    if (teams[name]) return { name, r: teams[name] };
    const key = norm(name);
    if (!key) return null;
    for (const k of Object.keys(teams)) {
      if (norm(k) === key) return { name: k, r: teams[k] };
    }
    return null;
  }

  function restDays(last, when) {
    if (!last) return 30;
    const t = Date.parse(`${last}T12:00:00Z`);
    if (!t) return 30;
    return Math.min(Math.max(Math.round((when - t) / DAY_MS), 0), 90);
  }

  function predictSeries(t1, t2, bo, when) {
    if (!bundle) return null;
    const a = findTeam(t1);
    const b = findTeam(t2);
    if (!a || !b) return { missing: [a ? null : t1, b ? null : t2].filter(Boolean) };
    const rest1 = restDays(a.r.last, when);
    const rest2 = restDays(b.r.last, when);
    const f5 = (r) => (r.f5 == null ? 0.5 : r.f5);
    const f10 = (r) => (r.f10 == null ? 0.5 : r.f10);
    const raw = {
      elo_diff: a.r.elo - b.r.elo,
      form5_diff: f5(a.r) - f5(b.r),
      form10_diff: f10(a.r) - f10(b.r),
      rest_diff: Math.log1p(rest1) - Math.log1p(rest2),
      n30_diff: (a.r.n30 || 0) - (b.r.n30 || 0),
      log_n_diff: Math.log1p(a.r.n || 0) - Math.log1p(b.r.n || 0),
      is_bo1: bo === 1 ? 1 : 0,
      is_bo5: bo === 5 ? 1 : 0,
    };
    return {
      prob: modelProb(FEATURES.map((k) => raw[k])),
      raw, a, b, rest1, rest2, bo: bo || 3,
      thin: Math.min(a.r.n || 0, b.r.n || 0) < THIN_RATING,
    };
  }

  // ---------- live-пересчёт ----------
  // Предматчевая вероятность серии разворачивается в вероятность одной карты,
  // дальше карта считается динамикой MR12 (до 13, при 12:12 — овертайм-блоки
  // по 6 раундов с победой на 4), а серия — деревом до ceil(bo/2) карт.

  function binom(n, k) {
    let r = 1;
    for (let i = 0; i < k; i++) r = (r * (n - i)) / (i + 1);
    return r;
  }

  function seriesFromMap(p, bo) {
    if (bo <= 1) return p;
    const need = Math.ceil(bo / 2);
    let s = 0;
    for (let k = need; k <= bo; k++) s += binom(bo, k) * Math.pow(p, k) * Math.pow(1 - p, bo - k);
    return s;
  }

  function invertSeries(P, bo) {
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 60; i++) {
      const mid = (lo + hi) / 2;
      if (seriesFromMap(mid, bo) < P) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }

  function mapWinProb(a, b, p) {
    const q = Math.min(Math.max(p, 1e-3), 1 - 1e-3);
    const block = (u, v, V, memo) => {
      if (u >= 4) return 1;
      if (v >= 4) return 0;
      if (u === 3 && v === 3) return V;
      const k = u * 8 + v;
      if (memo.has(k)) return memo.get(k);
      const r = q * block(u + 1, v, V, memo) + (1 - q) * block(u, v + 1, V, memo);
      memo.set(k, r);
      return r;
    };
    // ценность ничейного овертайм-блока входит в саму себя — ищем неподвижную точку
    let V = 0.5;
    for (let i = 0; i < 40; i++) V = block(0, 0, V, new Map());
    const ot = new Map();
    const reg = new Map();
    const walk = (i, j) => {
      if (i >= 13 && i - j >= 2) return 1;
      if (j >= 13 && j - i >= 2) return 0;
      if (i > 12 || j > 12) {
        let u = i - 12;
        let v = j - 12;
        while (u >= 3 && v >= 3) { u -= 3; v -= 3; }
        return block(u, v, V, ot);
      }
      if (i === 12 && j === 12) return V;
      const k = i * 32 + j;
      if (reg.has(k)) return reg.get(k);
      const r = q * walk(i + 1, j) + (1 - q) * walk(i, j + 1);
      reg.set(k, r);
      return r;
    };
    return walk(Math.max(a || 0, 0), Math.max(b || 0, 0));
  }

  function seriesWinProb(m1, m2, need, cur, p) {
    const memo = new Map();
    const walk = (i, j) => {
      if (i >= need) return 1;
      if (j >= need) return 0;
      const k = i * 8 + j;
      if (memo.has(k)) return memo.get(k);
      // карта, которая идёт прямо сейчас, считается по её счёту, остальные — по p
      const w = i + j === m1 + m2 ? cur : p;
      const r = w * walk(i + 1, j) + (1 - w) * walk(i, j + 1);
      memo.set(k, r);
      return r;
    };
    return walk(m1, m2);
  }

  // Наружу — для офлайн-стенда с проверками динамики (tools/harness).
  window.__hltvProDP = { seriesFromMap, invertSeries, mapWinProb, seriesWinProb };

  // Состояние серии со страницы: сколько карт взяли, какая идёт, счёт на ней.
  function liveState(m, t1, t2) {
    const s = m.series;
    if (!s || !s.maps.length) return null;
    const won1 = s.maps.filter((x) => x.left.score != null && x.right.score != null
      && x.left.score > x.right.score).length;
    const won2 = s.maps.filter((x) => x.left.score != null && x.right.score != null
      && x.right.score > x.left.score).length;
    const byName = (n) => s.maps.findIndex((x) => norm(x.name) === norm(n));
    let idx = s.roundMap ? byName(s.roundMap) : -1;
    if (idx < 0) idx = s.maps.findIndex((x) => x.left.score == null);
    const current = idx >= 0 ? s.maps[idx] : null;
    let c1 = null;
    let c2 = null;
    if (s.cur && current) {
      // ctScore/tScore — это стороны, а не команды: сопоставляем по имени
      const ctIsLeft = norm(s.cur.ctName) === norm(current.left.name)
        || norm(s.cur.ctName) === norm(t1);
      const ctIsRight = norm(s.cur.ctName) === norm(current.right.name)
        || norm(s.cur.ctName) === norm(t2);
      if (ctIsLeft && !ctIsRight) { c1 = s.cur.ct; c2 = s.cur.t; } else if (ctIsRight && !ctIsLeft) { c1 = s.cur.t; c2 = s.cur.ct; }
    }
    return {
      live: s.live, won1, won2, current, c1, c2,
      played: s.maps.some((x) => x.left.score != null),
      round: s.round, roundMap: s.roundMap,
    };
  }

  // ---------- вывод ----------

  function analyse(m) {
    const vetoRole = {};
    for (const s of (m.veto || [])) {
      const k = s.map || s.mapName;
      if (k) vetoRole[k] = { act: s.act, team: s.team };
    }
    const rows = (m.maps || []).map((r) => {
      const g1 = r.t1 && r.t1.games != null ? r.t1.games : 0;
      const g2 = r.t2 && r.t2.games != null ? r.t2.games : 0;
      const ok = !!(r.t1 && r.t2) && r.t1.wr != null && r.t2.wr != null
        && g1 >= MIN_GAMES && g2 >= MIN_GAMES;
      const v = vetoRole[r.map] || vetoRole[r.mapName];
      const inSeries = v ? v.act === 'pick' || v.act === 'leftover'
        : !r.notPicked && !!(r.t1 && r.t1.mark === 'pick' || r.t2 && r.t2.mark === 'pick');
      return {
        map: r.map, mapName: r.mapName, t1: r.t1, t2: r.t2, ok, inSeries,
        role: v ? (v.act === 'leftover' ? 'осталась'
          : `${v.act === 'ban' ? 'бан' : 'пик'} ${v.team || ''}`.trim())
          : r.notPicked ? 'вне серии' : '',
        games: Math.min(g1, g2),
        diff: ok ? r.t1.wr - r.t2.wr : null,
      };
    });
    const sum = (side) => rows.reduce((s, r) => s + (r[side] && r[side].games || 0), 0);
    const rated = rows.filter((r) => r.ok);
    const byAbs = (a, b) => Math.abs(a.diff) - Math.abs(b.diff);

    // О чём говорит вердикт: сначала реальное вето, затем симуляция HLTV,
    // затем весь пул.
    const series = rated.filter((r) => r.inSeries);
    const simNames = (m.sim && m.sim.maps) || [];
    const likely = simNames.length
      ? rated.filter((r) => simNames.some((n) => (mapKey(n) || n) === (r.map || r.mapName)))
      : [];
    const set = series.length ? series : (likely.length ? likely : rated);
    const seriesAll = rows.filter((r) => r.inSeries).length;
    const label = series.length ? 'картам серии'
      : likely.length ? 'вероятным картам из симуляции HLTV' : 'всему пулу';
    const sorted = set.slice().sort(byAbs);
    return {
      rows, rated, set, label, decided: series.length > 0, seriesAll,
      lead: sorted.length ? sorted[sorted.length - 1] : null,
      ahead1: set.filter((r) => r.diff > 0).length,
      ahead2: set.filter((r) => r.diff < 0).length,
      poolGames: { t1: sum('t1'), t2: sum('t2') },
    };
  }

  function cellWr(c) {
    if (!c) return '<span class="hp-dim">—</span>';
    if (c.wr == null) {
      return c.games === 0 ? '<span class="hp-dim">нет игр</span>'
        : `<span class="hp-dim">—${c.games ? ` (${c.games})` : ''}</span>`;
    }
    const g = c.games == null ? '' : ` <span class="hp-games">(${c.games})</span>`;
    return `${Math.round(c.wr)}%${g}${c.mark ? ` <span class="hp-mark hp-${c.mark}">${c.mark === 'pick' ? 'Пик' : 'Бан'}</span>` : ''}`;
  }

  const fmtDate = (s) => {
    const d = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
    return d ? `${d[3]}.${d[2]}.${d[1]}` : (s || '');
  };
  const pct = (v) => `${(v * 100).toFixed(1)}%`;
  const signed = (v, d) => `${v > 0 ? '+' : ''}${v.toFixed(d)}`;

  function renderPrediction(m, t1, t2) {
    if (!m.teams || !bundleDone) return '';
    const mm = bundle && bundle.meta;
    const head1 = `CatBoost · ${(mm && mm.matches) || '28 415'} реальных матчей HLTV`
      + (bundle ? ` · снимок рейтингов ${fmtDate(bundle.asOf)}` : '');
    const head = (inner, low) => `<div class="hp-pred${low ? ' hp-low' : ''}">`
      + `<div class="hp-pred-head"><span>ПРОГНОЗ МОДЕЛИ</span><span class="hp-bo">${esc(head1)}</span></div>`
      + inner + `</div>`;
    if (!bundle) {
      return typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.getURL
        ? head('Файлы модели не удалось прочитать из пакета расширения — ниже только статистика HLTV.', true)
        : '';
    }
    const st = liveState(m, t1, t2);
    const bo = m.bo || 3;
    const p = predictSeries(t1, t2, bo, m.start || Date.now());
    if (!p) return '';
    if (p.missing) {
      return head(`Прогноза нет: <b>${esc(p.missing.join(' и '))}</b> не нашлось в снимке рейтингов `
        + `от ${fmtDate(bundle.asOf)} — это новый или переименованный состав. `
        + `Ниже остаётся разбор статистики HLTV.`, true);
    }
    // Снимок рейтингов собран по архиву результатов до asOf: всё, что сыграно
    // раньше, уже внутри, и «прогноз» на такой матч был бы подгонкой.
    const isLive = !!(st && st.live);
    const asOfMs = Date.parse(`${bundle.asOf}T00:00:00Z`);
    const before = !!(m.start && asOfMs && m.start < asOfMs);
    const played = !!(st && st.played) || before;
    if (played && !isLive) {
      return head(`Матч сыгран${before ? ` (дата раньше снимка рейтингов от ${fmtDate(bundle.asOf)})` : ''}, `
        + `поэтому прогноз не показываю: снимок уже включает этот результат, `
        + `и число было бы подгонкой задним числом.`, true);
    }

    const P = p.prob;
    const need = Math.ceil(bo / 2);
    let live = null;
    if (isLive) {
      const pMap = invertSeries(P, bo);
      const haveScore = st.c1 != null && st.c2 != null;
      const curP = haveScore ? mapWinProb(st.c1, st.c2, pMap) : pMap;
      live = { p: seriesWinProb(st.won1, st.won2, need, curP, pMap), pMap, curP, haveScore, need };
    }

    const lead = P >= 0.5 ? t1 : t2;
    const top = Math.max(P, 1 - P);
    const tier = top >= CLEAR_P ? `явный фаворит — <b>${esc(lead)}</b>`
      : top >= EDGE_P ? `умеренный перевес у <b>${esc(lead)}</b>`
        : `составы равны, перевес <b>${esc(lead)}</b> в пределах шума`;
    const num = (v, d) => (v == null ? 0.5 : v).toFixed(d);
    const f = (label, val) => `<span class="hp-f"><i>${label}</i>${val}</span>`;
    const feats = `<div class="hp-feats">`
      + f('ΔElo', signed(p.raw.elo_diff, 0))
      + f('форма 5', `${num(p.a.r.f5, 2)} / ${num(p.b.r.f5, 2)}`)
      + f('форма 10', `${num(p.a.r.f10, 2)} / ${num(p.b.r.f10, 2)}`)
      + f('за 30 дней', `${p.a.r.n30 || 0} / ${p.b.r.n30 || 0}`)
      + f('отдых', `${p.rest1} / ${p.rest2} дн.`)
      + f('всего матчей', `${p.a.r.n || 0} / ${p.b.r.n || 0}`)
      + `<span class="hp-f hp-dim"><i>порядок</i>${esc(t1)} / ${esc(t2)}</span></div>`;
    const acc = mm && mm.test_n
      ? `Проверка на ${mm.test_n} матчах последних трёх месяцев, которых модель не видела: `
        + `точных исходов ${(mm.test_acc * 100).toFixed(1)}%, AUC ${mm.test_auc.toFixed(2)}. `
        + `Простая ставка «всегда первая команда» на тех же матчах — ${(mm.first_team_acc * 100).toFixed(1)}%. `
      : '';

    let out = `<div class="hp-pred"><div class="hp-pred-head">`
      + `<span>ПРОГНОЗ МОДЕЛИ · BO${bo}</span><span class="hp-bo">${esc(head1)}</span></div>`
      + `<div class="hp-pred-main"><div class="hp-pred-num">${pct(P)}</div>`
      + `<div class="hp-pred-txt">Вероятность победы <b>${esc(t1)}</b> во всей серии. `
      + `<b>${esc(t2)}</b> — ${pct(1 - P)}. По модели ${tier}.</div></div>`
      + feats
      + (p.thin ? `<div class="hp-warn">У одной из команд меньше ${THIN_RATING} матчей в рейтинге — `
          + `такой прогноз заметно менее надёжен.</div>` : '')
      + `<div class="hp-note">${acc}Это оценка вероятности, а не гарантия и не совет ставить.</div></div>`;

    if (live && st) {
      const mapName = st.roundMap || (st.current && st.current.name) || 'текущая карта';
      const score = live.haveScore ? `${st.c1}:${st.c2}` : 'счёт карты ещё не читается';
      out += `<div class="hp-pred hp-live"><div class="hp-pred-head">`
        + `<span>LIVE · ${esc(mapName)} ${esc(score)}${st.round ? `, раунд ${st.round}` : ''}</span>`
        + `<span class="hp-bo">карты ${st.won1}:${st.won2}, серия до ${live.need}</span></div>`
        + `<div class="hp-pred-main"><div class="hp-pred-num">${pct(live.p)}</div>`
        + `<div class="hp-pred-txt">Шанс <b>${esc(t1)}</b> забрать серию прямо сейчас; `
        + `<b>${esc(t2)}</b> — ${pct(1 - live.p)}. На текущей карте <b>${esc(t1)}</b> — ${pct(live.curP)}. `
        + `До матча модель давала <b>${esc(t1)}</b> ${pct(P)}.</div></div>`
        + `<div class="hp-note">Пересчёт наш, а не HLTV: вероятность карты выведена из предматчевого прогноза, `
        + `дальше динамика MR12 (до 13 раундов, при 12:12 — овертаймы) и дерево серии.`
        + (live.haveScore ? '' : ' Счёт карты не определился, считаю её с 0:0.')
        + ` Поправки на сторону CT/T нет, поэтому точность на уровне карты, а не отдельного раунда.</div></div>`;
    }
    return out;
  }

  function render(m, host) {
    const a = analyse(m);
    const t1 = m.teams ? m.teams.t1 : 'К1';
    const t2 = m.teams ? m.teams.t2 : 'К2';

    const head = `<div class="hp-head"><span>PRO · ВЕТО И КАРТЫ</span>`
      + `<span class="hp-bo">${m.bo ? `BO${m.bo}` : 'BO?'} · винрейты HLTV${m.win ? `, окно ${m.win}` : ''}</span></div>`;

    const vetoLine = (m.veto && m.veto.length)
      ? `<div class="hp-veto">${m.veto.map((s) => (s.act === 'leftover'
          ? `<b>${esc(mapLabel(s.map) || s.mapName)}</b> — осталась`
          : `${s.act === 'ban' ? 'бан' : 'пик'}: <b>${esc(mapLabel(s.map) || s.mapName)}</b> (${esc(s.team)})`
        )).join(' · ')}</div>`
      : (m.sim
          ? `<div class="hp-veto hp-dim">Вето ещё не сыграно. Симуляция HLTV: `
            + m.sim.steps.map((s) => `${s.act === 'ban' ? 'бан' : s.act === 'leftover' ? 'остаток' : 'пик'} `
              + `<b>${esc(s.mapName)}</b> ${s.chance == null ? '' : s.chance + '%'}`).join(', ')
            + (m.sim.line ? `. ${esc(m.sim.line)}` : '') + `</div>`
          : '');

    const pp = (d) => `${Math.abs(d).toFixed(0)} п.п.`;
    const ofWho = (d) => (d > 0 ? t1 : t2);
    const against = (d) => (d > 0 ? t2 : t1);
    const gapOf = (r) => `${Math.round(r.diff > 0 ? r.t1.wr : r.t2.wr)}% против `
      + `${Math.round(r.diff > 0 ? r.t2.wr : r.t1.wr)}%`;

    const pred = renderPrediction(m, t1, t2);

    if (!m.maps.length) {
      host.innerHTML = head + vetoLine + pred
        + `<div class="hp-rec hp-low">HLTV не выложил статистику карт для этого матча `
        + `(так бывает в BO1) — сравнивать винрейты ни по чем, выше только вето и прогноз модели.</div>`
        + `<div class="hp-note">Не связано с HLTV.</div>`;
      return;
    }

    let verdict;
    if (!a.lead) {
      const weak = a.poolGames.t1 <= a.poolGames.t2 ? [t1, a.poolGames.t1] : [t2, a.poolGames.t2];
      verdict = `<div class="hp-rec hp-low">Сравнивать нечего: у <b>${esc(weak[0])}</b> `
        + `${weak[1]} сыгранных карт на всём пуле${m.win ? ` в окне HLTV ${m.win}` : ''}. `
        + `HLTV считает винрейты только по составу, отыгравшему вместе минимум 3 матча, `
        + `поэтому чисел для сравнения нет.`
        + (m.sim ? ' Выше — симуляция вето, сейчас это единственный ориентир.' : '') + `</div>`;
    } else {
      const b = a.lead;
      const n = a.set.length;
      const draw = a.ahead1 === a.ahead2;
      const leader = a.ahead1 > a.ahead2 ? t1 : t2;
      const noise = Math.abs(b.diff) < NOISE_PP;
      const thin = b.games < THIN_GAMES;
      verdict = `<div class="hp-rec${noise || thin ? ' hp-low' : ''}">`
        + (draw
          ? `По ${a.label} равновесие (${a.ahead1}:${a.ahead2}).`
          : `По ${a.label} перевес у <b>${esc(leader)}</b> — сильнее на ${Math.max(a.ahead1, a.ahead2)} из ${n} карт.`)
        + ` Крупнейший разрыв — <b>${esc(b.mapName)}</b>: у <b>${esc(ofWho(b.diff))}</b> ${pp(b.diff)} (${gapOf(b)}),`
        + ` у <b>${esc(against(b.diff))}</b> — наоборот.`
        + (noise ? ` Разрыв меньше ${NOISE_PP} п.п. — это шум, а не сигнал.` : '')
        + (thin && !noise ? ` Выборка тонкая: ${b.games} сыгранных карт у слабой стороны.` : '')
        + (a.seriesAll > a.set.length
            ? ' Часть карт серии в вердикт не вошла: у HLTV нет по ним сопоставимой выборки.'
            : '')
        + (a.decided ? '' : ' Карты серии ещё не утверждены — после вето картина изменится.')
        + `</div>`;
    }

    const body = a.rows.map((r) => {
      const cls = [r.ok ? '' : 'hp-dim', r === a.lead ? 'hp-good' : ''].filter(Boolean).join(' ');
      const d = r.diff == null ? '—' : `${r.diff > 0 ? '+' : ''}${r.diff.toFixed(0)}`;
      const dcls = r.diff == null ? 'hp-dim' : r.diff > 0 ? 'hp-g' : r.diff < 0 ? 'hp-r' : '';
      return `<tr class="${cls}"><td class="hp-map">${esc(r.mapName)}`
        + `<span class="hp-role">${esc(r.role)}</span></td>`
        + `<td>${cellWr(r.t1)}</td><td>${cellWr(r.t2)}</td>`
        + `<td class="${dcls}">${d}</td></tr>`;
    }).join('');

    host.innerHTML = head + vetoLine + pred + verdict
      + `<table class="hp-table"><thead><tr><th>Карта</th><th>${esc(t1)}</th><th>${esc(t2)}</th><th>Δ п.п.</th></tr></thead>`
      + `<tbody>${body}</tbody></table>`
      + `<div class="hp-note">Δ = разница винрейтов (${esc(t1)} минус ${esc(t2)}); в скобках — число карт в выборке. `
      + `«Вне серии» — карты, не вошедшие в BO. Таблица и вето — статистика HLTV, `
      + `блок выше — прогноз нашей модели. Не связано с HLTV.</div>`;
  }

  let lastMatch = null;

  function mount() {
    const onMatch = /^\/matches\/\d+/.test(location.pathname) || window.__hltvForceMount;
    if (!onMatch) return;
    const m = extractProMatch(document);
    lastMatch = m;
    // Панель нужна и без статистики HLTV: прогноз модели и live-счёт важнее винрейтов.
    if (!m.teams) return;

    let host = document.getElementById('hltv-pro-panel');
    if (!host) {
      host = document.createElement('div');
      host.id = 'hltv-pro-panel';
      host.className = 'hltv-pro';
      const anchor = document.querySelector('.map-stats-infobox')
        || document.querySelector('.veto-box:not(.simulated-veto)')
        || document.querySelector('#main') || document.body;
      if (anchor === document.body) anchor.appendChild(host);
      else anchor.parentNode.insertBefore(host, anchor);
    }
    render(m, host);
  }

  const onMatchPage = /^\/matches\/\d+/.test(location.pathname) || window.__hltvForceMount;
  if (onMatchPage) {
    mount();
    loadBundle().then(() => mount());
    // инфоблок и симуляция вето домонтируются после загрузки страницы
    let tries = 0;
    const timer = setInterval(() => {
      mount();
      if (++tries > 12) clearInterval(timer);
    }, 1000);
    // на живом матче счёт и вероятность обновляем постоянно
    setInterval(() => {
      if (lastMatch && lastMatch.series && lastMatch.series.live) mount();
    }, 5000);
  }
})();
