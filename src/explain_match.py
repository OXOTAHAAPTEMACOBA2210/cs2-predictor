# -*- coding: utf-8 -*-
"""Воспроизводит вердикт расширения для конкретной комнаты.

Тянет те же данные и строит те же признаки, что chrome_extension/content.js,
прогоняет их через model.json (тот же код дерева, что в браузере) и печатает
вклад каждой группы признаков, отключая его по одному.

    python src/explain_match.py 1-8f1bbaca-662f-4cbd-bdce-b744a5c36cff [-J0ker]
"""
import json
import math
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, 'data', 'explain_cache')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
MAPS = ['de_dust2', 'de_mirage', 'de_nuke', 'de_anubis', 'de_vertigo', 'de_inferno', 'de_ancient']


def api(path):
    req = urllib.request.Request('https://www.faceit.com/api' + path,
                                 headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            code = getattr(exc, 'code', None)
            if code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2.5 * (attempt + 1))
                continue
            raise
    return None


def calc_streak(s0):
    if not isinstance(s0, list) or not s0:
        return 0
    last = str(s0[-1])
    n = 0
    for v in reversed(s0):
        if str(v) == last:
            n += 1
        else:
            break
    return n if last == '1' else -n


def history(pid):
    raw = api('/stats/v1/stats/time/users/%s/games/cs2?size=50&page=0' % pid) or []
    out = []
    for m in raw if isinstance(raw, list) else []:
        out.append({'map': m.get('i1') or '', 'd': float(m.get('elo_delta') or 0),
                    'adr': float(m.get('c10') or 0)})
    return out


def map_agg(hist):
    out = {}
    for m in hist:
        if not m['map'].startswith('de_'):
            continue
        r = out.setdefault(m['map'], {'w': 0, 'l': 0})
        if m['d'] > 0:
            r['w'] += 1
        elif m['d'] < 0:
            r['l'] += 1
    return out


def player(pid, nick, elo):
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    path = os.path.join(CACHE_DIR, pid + '.json')
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 6 * 3600:
        p = json.load(open(path, encoding='utf-8'))
        p['nick'] = nick
        p['elo'] = float(elo or 0) or None
        return p

    p = {'id': pid, 'nick': nick, 'elo': float(elo or 0) or None,
         'kd': None, 'adr': None, 'hs': None, 'wr': None, 'matches': None, 'streak': 0}
    s = api('/stats/v1/stats/users/%s/games/cs2' % pid) or {}
    lt = s.get('lifetime') or {}
    if lt.get('k5'):
        p['kd'] = float(lt['k5'])
        p['adr'] = float(lt['k17']) if lt.get('k17') else None
        p['hs'] = float(lt['k8']) if lt.get('k8') else None
        p['wr'] = float(lt['k6']) if lt.get('k6') else None
        p['matches'] = int(lt['m1']) if lt.get('m1') else None
        p['streak'] = calc_streak(lt.get('s0'))
    time.sleep(0.3)
    p['mapAgg'] = map_agg(history(p['id']))
    time.sleep(0.3)
    json.dump(p, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return p


def agg(lst, key, fallback):
    vals = [(fallback if p[key] is None else p[key]) for p in lst] or [fallback]
    return sum(vals) / len(vals)


def team_elo_std(lst):
    vals = [(1000.0 if p['elo'] is None else p['elo']) for p in lst]
    if len(vals) < 2:
        return 80.0
    avg = sum(vals) / len(vals)
    return math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))


def team_map_wr(lst, game_map):
    w = l = 0
    for p in lst:
        r = (p.get('mapAgg') or {}).get(game_map)
        if not r:
            continue
        w += r['w']
        l += r['l']
    if not w and not l:
        return None
    return (w + 2.5) / (w + l + 5) * 100.0, (w, l)


def team_stats(lst, game_map):
    wr_raw = team_map_wr(lst, game_map)
    wr = wr_raw if isinstance(wr_raw, tuple) else (wr_raw, (0, 0))
    return {
        'elo': agg(lst, 'elo', 1000), 'kd': agg(lst, 'kd', 1.0), 'adr': agg(lst, 'adr', 77),
        'hs': agg(lst, 'hs', 42), 'wr': agg(lst, 'wr', 48), 'eloStd': team_elo_std(lst),
        'matches': agg(lst, 'matches', 750), 'streak': agg(lst, 'streak', 0),
        'mapWr': wr_raw[0] if isinstance(wr_raw, tuple) else None, 'mapGames': wr[1],
    }


PAIRS = {
    'ELO': ('elo_diff', 'team_1_avg_elo', 'team_2_avg_elo'),
    'разброс ELO': ('elo_std_diff', 'team_1_elo_std', 'team_2_elo_std'),
    'K/D': ('kd_diff', 'team_1_avg_kd', 'team_2_avg_kd'),
    'ADR': ('adr_diff', 'team_1_avg_adr', 'team_2_avg_adr'),
    'HS %': ('hs_diff', 'team_1_hs_rate', 'team_2_hs_rate'),
    'винрейт на карте': ('map_winrate_diff', 'team_1_map_winrate', 'team_2_map_winrate'),
    'стрик': ('streak_diff', 'team_1_streak', 'team_2_streak'),
    'опыт (матчей)': (None, 'team_1_avg_matches', 'team_2_avg_matches'),
}


def build_features(mine, enemy, game_map):
    f = {'map_name_' + m: 0 for m in ['de_anubis', 'de_dust2', 'de_inferno',
                                      'de_mirage', 'de_nuke', 'de_vertigo']}
    m_wr = mine['mapWr'] if mine['mapWr'] is not None else mine['wr']
    e_wr = enemy['mapWr'] if enemy['mapWr'] is not None else enemy['wr']
    f.update({
        'team_1_avg_elo': mine['elo'], 'team_2_avg_elo': enemy['elo'],
        'elo_diff': mine['elo'] - enemy['elo'],
        'team_1_elo_std': mine['eloStd'], 'team_2_elo_std': enemy['eloStd'],
        'elo_std_diff': mine['eloStd'] - enemy['eloStd'],
        'team_1_avg_kd': mine['kd'], 'team_2_avg_kd': enemy['kd'],
        'kd_diff': mine['kd'] - enemy['kd'],
        'team_1_avg_adr': mine['adr'], 'team_2_avg_adr': enemy['adr'],
        'adr_diff': mine['adr'] - enemy['adr'],
        'team_1_hs_rate': mine['hs'], 'team_2_hs_rate': enemy['hs'],
        'hs_diff': mine['hs'] - enemy['hs'],
        'team_1_map_winrate': m_wr, 'team_2_map_winrate': e_wr,
        'map_winrate_diff': m_wr - e_wr,
        'team_1_streak': mine['streak'], 'team_2_streak': enemy['streak'],
        'streak_diff': mine['streak'] - enemy['streak'],
        'team_1_avg_matches': mine['matches'], 'team_2_avg_matches': enemy['matches'],
    })
    if game_map in MAPS:
        f['map_name_' + game_map] = 1
    return f


class JsModel(object):
    """Тот же обливный лес, что считает content.js."""

    def __init__(self, path):
        m = json.load(open(path, encoding='utf-8'))
        self.order = [f['feature_id'] for f in
                      sorted(m['features_info']['float_features'],
                             key=lambda x: x['feature_index'])]
        self.raw = m['oblivious_trees']
        self.scale = m['scale_and_bias'][0]
        self.bias = m['scale_and_bias'][1][0]

    def prob(self, feats):
        x = [float(feats.get(n) or 0) for n in self.order]
        total = 0.0
        for tree in self.raw:
            idx = 0
            for i, sp in enumerate(tree['splits']):
                if x[sp['float_feature_index']] > sp['border']:
                    idx |= 1 << i
            total += tree['leaf_values'][idx]
        return 1.0 / (1.0 + math.exp(-(total * self.scale + self.bias)))


def main():
    match = (sys.argv[1] if len(sys.argv) > 1 else '').split('/')[-1]
    me_nick = sys.argv[2] if len(sys.argv) > 2 else '-J0ker'
    payload = api('/match/v2/match/%s' % match)
    m = payload.get('payload') or payload
    game_map = ((m.get('voting') or {}).get('map') or {}).get('pick') or ''
    if isinstance(game_map, list):
        game_map = game_map[0]
    print('комната %s  статус %s  карта %s' % (match, m.get('status'), game_map))

    teams = {}
    for f in ('faction1', 'faction2'):
        t = m['teams'][f]
        rows = []
        for r in t.get('roster') or []:
            rows.append(player(r.get('playerId') or r.get('id') or r.get('guid'),
                               r.get('nickname'), r.get('elo')))
        teams[f] = {'name': t.get('name'), 'rows': rows}

    mine_key, enemy_key = ('faction1', 'faction2')
    for f in teams:
        if any((r['nick'] or '').lower() == me_nick.lower() for r in teams[f]['rows']):
            mine_key = f
            enemy_key = 'faction2' if f == 'faction1' else 'faction1'
            break

    mine = team_stats(teams[mine_key]['rows'], game_map)
    enemy = team_stats(teams[enemy_key]['rows'], game_map)
    feats = build_features(mine, enemy, game_map)
    model = JsModel(os.path.join(ROOT, 'chrome_extension', 'model.json'))
    base = model.prob(feats)

    def row(label, t):
        games = t['mapGames']
        print('%-12s ELO %6.1f (std %4.1f)  KD %.2f  ADR %5.1f  HS %.0f%%  WR %5.1f%%  '
              'стрик %+d  матчей %.0f  %s WR %s (%d игр)'
              % (label, t['elo'], t['eloStd'], t['kd'], t['adr'], t['hs'], t['wr'],
                 t['streak'], t['matches'], game_map,
                 '--' if t['mapWr'] is None else '%.1f%%' % t['mapWr'], games[0] + games[1]))

    print()
    row('МОЯ ' + str(teams[mine_key]['name']), mine)
    row('ВРАГ ' + str(teams[enemy_key]['name']), enemy)
    print()
    print('%-18s %8s %8s %9s' % ('признак', 'моя', 'враг', 'дельта'))
    for name, a, b in [('elo', 'elo', 'elo'), ('kd', 'kd', 'kd'), ('adr', 'adr', 'adr'),
                       ('hs', 'hs', 'hs'), ('winrate карты', 'mapWr', 'mapWr'),
                       ('стрик', 'streak', 'streak'), ('elo_std', 'eloStd', 'eloStd'),
                       ('матчи', 'matches', 'matches')]:
        va, vb = mine[a], enemy[b]
        if va is None or vb is None:
            continue
        print('%-18s %8.2f %8.2f %9.2f' % (name, va, vb, va - vb))

    print('\n>>> ШАНС ПОБЕДЫ МОЕЙ (%s): %.1f%%  (%.4f)' % (teams[mine_key]['name'], base * 100, base))
    print('    FACEIT winProbability: %s / %s' % (
        (teams[mine_key]['rows'] and (m['teams'][mine_key].get('stats') or {}).get('winProbability')),
        (m['teams'][enemy_key].get('stats') or {}).get('winProbability')))

    print('\nразбор: что ноль, если сравнять команды по этому признаку')
    print('%-22s %8s %8s %9s' % ('признак', 'P сейчас', 'P без него', 'вклад, п.п.'))
    for label, (diff, a, b) in PAIRS.items():
        f2 = dict(feats)
        mid = (f2[a] + f2[b]) / 2.0
        if diff is not None and diff in f2:
            f2[diff] = 0.0
        f2[a] = f2[b] = mid
        p2 = model.prob(f2)
        print('%-22s %7.1f%% %7.1f%% %+9.1f' % (label, base * 100, p2 * 100, (p2 - base) * 100))

    f3 = dict(feats)
    f3['team_1_map_winrate'] = mine['wr']
    f3['team_2_map_winrate'] = enemy['wr']
    f3['map_winrate_diff'] = mine['wr'] - enemy['wr']
    print('\nесли вместо %s (моя команда: %d игр) взять общий винрейт: P = %.1f%% (%+.1f п.п.)'
          % (game_map, mine['mapGames'][0] + mine['mapGames'][1], model.prob(f3) * 100,
             (model.prob(f3) - base) * 100))

    neutral = dict(feats)
    for diff, a, b in PAIRS.values():
        mid = (neutral[a] + neutral[b]) / 2.0
        if diff is not None and diff in neutral:
            neutral[diff] = 0.0
        neutral[a] = neutral[b] = mid
    print('идеально равные команды по всем признакам: P = %.1f%%' % (model.prob(neutral) * 100))

    pool = sorted(set(MAPS + ['de_ancient', 'de_cache']))
    print('\nта же комната на другой карте (состав не меняем):')
    for cand in pool:
        mm = team_stats(teams[mine_key]['rows'], cand)
        ee = team_stats(teams[enemy_key]['rows'], cand)
        p = model.prob(build_features(mm, ee, cand))
        print('  %-12s моя %5.1f%% (%d игр)  враг %5.1f%% (%d игр)  ->  P = %5.1f%%'
              % (cand,
                 mm['mapWr'] if mm['mapWr'] is not None else mm['wr'],
                 mm['mapGames'][0] + mm['mapGames'][1],
                 ee['mapWr'] if ee['mapWr'] is not None else ee['wr'],
                 ee['mapGames'][0] + ee['mapGames'][1], p * 100))
    json.dump({'match': match, 'map': game_map, 'features': feats, 'p_me': base},
              open(os.path.join(ROOT, 'data', 'explain_%s.json' % match), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
