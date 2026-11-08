// Заглушки для офлайн-стенда: chrome.storage, FACEIT API, буфер обмена.
//
// Cases (?case=):
//   clean   — обычные ответы, прогон дважды подряд
//   seeded  — в chrome.storage.local заранее лежит устаревший кэш с чужим ELO
//   broken  — у первых N игроков (/break=2) история матчей отвечает 400
(() => {
  'use strict';

  const params = new URLSearchParams(location.search);
  const CASE = params.get('case') || 'clean';
  let breakLeft = parseInt(params.get('break') || '0', 10);
  if (CASE !== 'broken') breakLeft = 0;

  window.__faiStorage = window.__faiStorage || {};
  window.__case = CASE;

  chrome.runtime = { getURL: (p) => '../../../chrome_extension/' + p };
  chrome.storage = {
    local: {
      async get(keys) {
        if (keys === null || keys === undefined) return { ...window.__faiStorage };
        if (typeof keys === 'string') return { [keys]: window.__faiStorage[keys] };
        const out = {};
        for (const k of keys) if (k in window.__faiStorage) out[k] = window.__faiStorage[k];
        return out;
      },
      async set(obj) { Object.assign(window.__faiStorage, JSON.parse(JSON.stringify(obj))); },
      async remove(keys) {
        for (const k of (Array.isArray(keys) ? keys : [keys])) delete window.__faiStorage[k];
      },
    },
  };

  const nativeFetch = window.fetch.bind(window);

  window.bootHarness = async function bootHarness(fixtures, matchId) {
    window.__fixtures = fixtures;
    window.__net = [];
    window.__missing = [];

    if (CASE === 'seeded') {
      const room = fixtures['/match/v2/match/' + matchId];
      const teams = room.payload.teams || {};
      for (const t of Object.values(teams)) {
        for (const p of t.roster || []) {
          window.__faiStorage['fai_p_' + p.id] = {
            t: Date.now(),
            d: {
              id: p.id, nickname: p.nickname, party: p.partyId,
              elo: 1000, eloSrc: 'history', eloEstimated: true, level: 4,
              kd: 1.0, adr: 70, hs: 40, wr: 50, matches: 500, streak: 0,
            },
          };
        }
      }
    }

    window.fetch = async (url, opts) => {
      const u = String(url);
      const at = u.indexOf('/api/');
      if (at < 0) return nativeFetch(u, opts);
      const path = u.slice(at + 4);
      window.__net.push(path);
      if (path.includes('/stats/time/') && breakLeft > 0) {
        breakLeft--;
        return { ok: false, status: 400, json: async () => ({}) };
      }
      if (!(path in fixtures)) {
        window.__missing.push(path);
        return { ok: false, status: 404, json: async () => ({}) };
      }
      const body = fixtures[path];
      return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) };
    };

    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { async writeText(t) { window.__copied = t; return true; } },
    });
  };
})();
