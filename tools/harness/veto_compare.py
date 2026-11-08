# -*- coding: utf-8 -*-
"""Сравнивает рекомендации вето-таблицы при пороге выборки >=3 и >=20 игр.

Логика повторяет renderVeto из chrome_extension/content.js: агрегат по карте
(победа = elo_delta > 0), сглаженный винрейт (w+2.5)/(n+5), Δ в п.п.,
pick = лучший по Δ, баны = худшие ceil((N-1)/2) из годных строк.

    python tools/harness/veto_compare.py                 # 6 последних матчей -J0ker
    python tools/harness/veto_compare.py 1-8f1bbaca-...  # конкретные комнаты
"""
import json
import math
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROOMS = os.path.join(HERE, 'rooms')
FIXTURES = os.path.join(HERE, 'fixtures')
EXPLAIN_CACHE = os.path.join(ROOT, 'data', 'explain_cache')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
ME_ID = '299bcdfd-ed9f-42f6-91ea-5ff75e442d85'
SIZE = int(os.environ.get('FAI_SIZE', '50'))
HISTS = os.path.join(HERE, 'hists-%d' % SIZE)
MAP_LABELS = ['de_ancient', 'de_anubis', 'de_cache', 'de_dust2', 'de_inferno',
              'de_mirage', 'de_nuke', 'de_overpass', 'de_train', 'de_vertigo']


def api(path):
    req = urllib.request.Request('https://www.faceit.com/api' + path,
                                 headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            code = getattr(exc, 'code', None)
            if code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(8 * (attempt + 1))
                continue
            raise


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def room_payload(match_id):
    fx = os.path.join(FIXTURES, 'match-%s.json' % match_id)
    if os.path.exists(fx):
        return load_json(fx)['/match/v2/match/%s' % match_id]
    path = os.path.join(ROOMS, '%s.json' % match_id)
    if os.path.exists(path):
        return load_json(path)
    time.sleep(1.2)
    data = api('/match/v2/match/%s' % match_id)
    save_json(path, data)
    return data


def history(pid):
    """Список [{'map','d','adr'}] из последних 50 матчей, с локальным кэшем."""
    if pid in _HIST_MEMO:
        return _HIST_MEMO[pid]
    res = _history(pid)
    _HIST_MEMO[pid] = res
    return res


_HIST_MEMO = {}
_FX_BLOB = None


def fixtures_blob():
    global _FX_BLOB
    if _FX_BLOB is None:
        _FX_BLOB = {}
        if os.path.isdir(FIXTURES):
            for name in os.listdir(FIXTURES):
                if name.startswith('match-'):
                    _FX_BLOB.update(load_json(os.path.join(FIXTURES, name)))
    return _FX_BLOB


def _history(pid):
    key = '/stats/v1/stats/time/users/%s/games/cs2?size=%d&page=0' % (pid, SIZE)
    blob = fixtures_blob() if SIZE == 50 else {}
    if key in blob:
        return parse_hist(blob[key])
    path = os.path.join(HISTS, '%s.json' % pid)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 6 * 3600:
        return load_json(path)
    time.sleep(1.2)
    raw = api(key)
    arr = parse_hist(raw)
    save_json(path, arr)
    return arr


def parse_hist(raw):
    return [{'id': m.get('matchId') or '', 'map': m.get('i1') or '',
             'd': int(m.get('elo_delta') or 0), 'adr': float(m.get('c10') or 0)}
            for m in (raw or [])]


def map_agg(hist):
    out = {}
    for m in hist:
        if not m['map'].startswith('de_'):
            continue
        r = out.setdefault(m['map'], {'w': 0, 'l': 0, 'adrSum': 0.0, 'adrN': 0})
        if m['d'] > 0:
            r['w'] += 1
        elif m['d'] < 0:
            r['l'] += 1
        if m['adr']:
            r['adrSum'] += m['adr']
            r['adrN'] += 1
    return out


def team_agg(hists):
    out = {}
    for agg in hists:
        for mp, r in agg.items():
            t = out.setdefault(mp, {'w': 0, 'l': 0, 'adrSum': 0.0, 'adrN': 0})
            t['w'] += r['w']
            t['l'] += r['l']
            t['adrSum'] += r['adrSum']
            t['adrN'] += r['adrN']
    return out


def smooth(r):
    n = r['w'] + r['l']
    return None if not n else (r['w'] + 2.5) / (n + 5) * 100


def veto(a, b, pool, min_games, gate=None):
    """Возвращает (строки, баны, pick, запасная) при заданном пороге выборки.

    gate — минимальный |Δ| в п.п.: банится только то, что хуже на gate и больше,
    играется — только то, что лучше. Без gates бан добирается картами с Δ ≈ 0.
    """
    seen = set(a) | set(b)
    maps = [m for m in (pool or []) if m and m.startswith('de_')]
    if len(maps) < 3:
        for m in sorted(seen):
            if m not in maps:
                maps.append(m)
        if not maps:
            maps = list(MAP_LABELS)
    rows = []
    for mp in maps:
        x, y = a.get(mp), b.get(mp)
        nx = (x['w'] + x['l']) if x else 0
        ny = (y['w'] + y['l']) if y else 0
        sx, sy = smooth(x) if x else None, smooth(y) if y else None
        rows.append({
            'map': mp, 'n1': nx, 'n2': ny,
            'wr1': (x['w'] / nx * 100) if nx else None,
            'wr2': (y['w'] / ny * 100) if ny else None,
            'diff': (sx - sy) if sx is not None and sy is not None else None,
            'adr1': (x['adrSum'] / x['adrN']) if x and x['adrN'] else None,
            'adr2': (y['adrSum'] / y['adrN']) if y and y['adrN'] else None,
            'ok': nx >= min_games and ny >= min_games,
        })
    rated = sorted([r for r in rows if r['ok']], key=lambda r: r['diff'])
    if not rated:
        return rows, [], None, None
    if gate is None:
        pick = rated[-1]
        backup = rated[-2] if len(rated) > 1 else None
        max_bans = max(0, math.ceil((len(maps) - 1) / 2))
        bans = rated[:max(0, min(max_bans, len(rated) - 1))]
    else:
        good = [r for r in rated if r['diff'] > gate]
        bad = [r for r in rated if r['diff'] < -gate]
        max_bans = max(0, math.ceil((len(maps) - 1) / 2))
        pick = good[-1] if good else None
        backup = good[-2] if len(good) > 1 else None
        bans = bad[:max_bans]
    return rows, bans, pick, backup


def label(m):
    return m.replace('de_', '').capitalize() if m else '—'


def rec_text(bans, pick, backup):
    if not pick:
        return 'нет рекомендации (мало матчей)'
    b = ' · '.join(label(r['map']) for r in bans) or '—'
    extra = label(backup['map']) if backup and backup not in bans else None
    return 'Баним: %s | Наша: %s%s' % (
        b, label(pick['map']), (' (запасная: %s)' % extra) if extra else '')


def main():
    ids = sys.argv[1:]
    if not ids:
        ids = [m['id'] for m in history(ME_ID)[-6:]][::-1]
    for match_id in ids:
        data = room_payload(match_id)
        payload = data.get('payload') or {}
        teams = payload.get('teams') or {}
        f1, f2 = teams.get('faction1') or {}, teams.get('faction2') or {}
        pick = ((payload.get('voting') or {}).get('map') or {}).get('pick') or []
        ents = ((payload.get('voting') or {}).get('map') or {}).get('entities') or []
        pool = [e.get('class_name') or e.get('game_map_id') for e in ents]
        pool = [m for m in pool if m]
        r1 = [p['id'] for p in f1.get('roster') or []]
        r2 = [p['id'] for p in f2.get('roster') or []]
        mine = [map_agg(history(p)) for p in r1]
        enemy = [map_agg(history(p)) for p in r2]
        my_name, en_name = f1.get('name'), f2.get('name')
        if ME_ID in r2:
            mine, enemy = enemy, mine
            my_name, en_name = en_name, my_name
        a, b = team_agg(mine), team_agg(enemy)

        print('\n=== %s · %s vs %s · карта %s · статус %s · окно %d матчей' % (
            match_id, my_name, en_name, label(pick[0]) if pick else '?',
            payload.get('status'), SIZE))
        rows3, bans3, pick3, back3 = veto(a, b, pool, 3)
        rows20, bans20, pick20, back20 = veto(a, b, pool, 20)
        _, bansG, pickG, backG = veto(a, b, pool, 20, gate=10.0)
        _, bansD, pickD, backD = veto(a, b, pool, 20, gate=0.0)
        print('%-9s %14s %14s %8s %7s %7s' % (
            'карта', 'мы', 'они', 'Δ п.п.', '>=3', '>=20'))
        by20 = {r['map']: r for r in rows20}
        for r in rows3:
            o = by20[r['map']]
            print('%-9s %7s (%3d) %7s (%3d) %8s %7s %7s' % (
                label(r['map']),
                '%.0f%%' % r['wr1'] if r['wr1'] is not None else '—', r['n1'],
                '%.0f%%' % r['wr2'] if r['wr2'] is not None else '—', r['n2'],
                '%+.1f' % r['diff'] if r['diff'] is not None else '—',
                'да' if r['ok'] else 'нет', 'да' if o['ok'] else 'нет'))
        print('  A сейчас (>=3):      ' + rec_text(bans3, pick3, back3))
        print('  B только >=20:       ' + rec_text(bans20, pick20, back20))
        print('  D >=20 и Δ<0:        ' + rec_text(bansD, pickD, backD))
        print('  C >=20 и |Δ|>10:     ' + rec_text(bansG, pickG, backG))
        same = len({r['map'] for r in bans3} & {r['map'] for r in bans20})
        decided = [r for r in rows3 if r['n1'] >= 20 and r['n2'] >= 20]
        print('  совпало банов A/B: %d из %d; pick %s; годных карт под >=20: %d из %d' % (
            same, len(bans3),
            'та же' if pick3 and pick20 and pick3['map'] == pick20['map'] else 'ДРУГАЯ',
            len(decided), len(rows3)))


if __name__ == '__main__':
    main()
