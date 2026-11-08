# -*- coding: utf-8 -*-
"""Бэктест модели CatBoost на реальных матчах из истории игрока.

Для каждого завершённого матча собираем предматчевые признаки обеих команд
(статы игроков только из матчей, сыгранных РАНЬШЕ этого), считаем вероятность
победы faction1 и сверяем с фактическим победителем и с winProbability FACEIT.

Запуск:  C:\\ProgramData\\anaconda3\\python.exe src/backtest_history.py [число_матчей]
"""

import datetime as dt
import json
import os
import statistics
import sys
import time

import numpy as np
import pandas as pd
import requests
from catboost import CatBoostClassifier

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}
API = 'https://www.faceit.com/api'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, 'data', 'backtest_cache')
ME = '-J0ker'
MODEL_MAPS = ['de_anubis', 'de_dust2', 'de_inferno', 'de_mirage', 'de_nuke', 'de_vertigo']

FEATURE_COLS = [
    'team_1_avg_elo', 'team_2_avg_elo', 'elo_diff',
    'team_1_elo_std', 'team_2_elo_std', 'elo_std_diff',
    'team_1_avg_kd', 'team_2_avg_kd', 'kd_diff',
    'team_1_avg_adr', 'team_2_avg_adr', 'adr_diff',
    'team_1_hs_rate', 'team_2_hs_rate', 'hs_diff',
    'team_1_map_winrate', 'team_2_map_winrate', 'map_winrate_diff',
    'team_1_streak', 'team_2_streak', 'streak_diff',
    'team_1_avg_matches', 'team_2_avg_matches',
    'map_name_de_anubis', 'map_name_de_dust2', 'map_name_de_inferno',
    'map_name_de_mirage', 'map_name_de_nuke', 'map_name_de_vertigo',
]

os.makedirs(CACHE_DIR, exist_ok=True)


def get(url, tries=6):
    for attempt in range(tries):
        try:
            time.sleep(0.3)
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                time.sleep(min(16, 1.5 * (2 ** attempt)))
                continue
            return None
        except requests.RequestException:
            time.sleep(min(16, 1.5 * (2 ** attempt)))
    return None


def cached(name, fetch):
    path = os.path.join(CACHE_DIR, name + '.json')
    if os.path.exists(path):
        if time.time() - os.path.getmtime(path) < 7 * 86400:
            with open(path, encoding='utf-8') as fh:
                return json.load(fh)
    data = fetch()
    if data is not None:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)
    return data


def player_history(pid):
    return cached('hist_' + pid, lambda: get(
        f'{API}/stats/v1/stats/time/users/{pid}/games/cs2?size=100&page=0') or [])


def player_lifetime(pid):
    return cached('life_' + pid, lambda: get(
        f'{API}/stats/v1/stats/users/{pid}/games/cs2') or {})


def match_payload(mid):
    data = cached('match_' + mid, lambda: (get(f'{API}/match/v2/match/{mid}') or {}).get('payload'))
    return data


def num(x, default=None):
    try:
        v = float(x)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


def to_ms(value, fallback=None):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
                       .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        except ValueError:
            pass
    return fallback


def smooth_wr(w, l):
    if not w and not l:
        return None
    return (w + 2.5) / (w + l + 5) * 100.0


def pre_match_stats(pid, before_ts):
    """Предматчевые признаки игрока: только матчи с date < before_ts."""
    hist = [m for m in player_history(pid) or [] if m.get('date') and m['date'] < before_ts]
    hist.sort(key=lambda m: m['date'], reverse=True)
    if not hist:
        return None

    def mean(key, window, fallback):
        vals = [num(m.get(key)) for m in hist[:window]]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else fallback

    recent = hist[:20]
    wins = sum(1 for m in recent if (num(m.get('elo_delta')) or 0) > 0)
    losses = sum(1 for m in recent if (num(m.get('elo_delta')) or 0) < 0)
    rolling_wr = smooth_wr(wins, losses)

    streak = 0
    for m in hist:
        d = num(m.get('elo_delta'))
        if d is None or d == 0:
            break
        sign = 1 if d > 0 else -1
        if streak == 0:
            streak = sign
        elif (streak > 0) == (sign > 0):
            streak += sign
        else:
            break

    lt = player_lifetime(pid).get('lifetime') or {}
    total = num(lt.get('m1'))
    newer = sum(1 for m in player_history(pid) or [] if m.get('date') and m['date'] >= before_ts)
    matches_at_time = max(total - newer, len(hist)) if total is not None else len(hist)

    return {
        'kd': mean('c2', 10, 1.0),
        'adr': mean('c10', 10, 77.0),
        'hs': mean('c4', 10, 42.0),
        'wr': rolling_wr if rolling_wr is not None else 48.0,
        'streak': streak,
        'matches': matches_at_time,
        'hist': hist,
    }


def player_map_wr(stats, map_name):
    w = l = 0
    for m in stats['hist']:
        if m.get('i1') != map_name:
            continue
        d = num(m.get('elo_delta'))
        if d is None or d == 0:
            continue
        if d > 0:
            w += 1
        else:
            l += 1
    return w, l


def team_features(players, map_name):
    known = [p for p in players if p['stats']]
    elos = [p['elo'] for p in known]
    if not elos:
        return None
    w = l = 0
    for p in known:
        pw, pl = player_map_wr(p['stats'], map_name)
        w += pw
        l += pl
    map_wr = smooth_wr(w, l)
    if map_wr is None:
        map_wr = sum(p['stats']['wr'] for p in known) / len(known)
    return {
        'elo': sum(elos) / len(elos),
        'elo_std': statistics.pstdev(elos) if len(elos) > 1 else 80.0,
        'kd': sum(p['stats']['kd'] for p in known) / len(known),
        'adr': sum(p['stats']['adr'] for p in known) / len(known),
        'hs': sum(p['stats']['hs'] for p in known) / len(known),
        'wr': sum(p['stats']['wr'] for p in known) / len(known),
        'streak': sum(p['stats']['streak'] for p in known) / len(known),
        'matches': sum(p['stats']['matches'] for p in known) / len(known),
        'map_wr': map_wr,
        'map_games': w + l,
        'known': len(known),
    }


def build_row(t1, t2, map_name):
    row = {c: 0.0 for c in FEATURE_COLS}
    row['team_1_avg_elo'], row['team_2_avg_elo'] = t1['elo'], t2['elo']
    row['elo_diff'] = t1['elo'] - t2['elo']
    row['team_1_elo_std'], row['team_2_elo_std'] = t1['elo_std'], t2['elo_std']
    row['elo_std_diff'] = t1['elo_std'] - t2['elo_std']
    row['team_1_avg_kd'], row['team_2_avg_kd'] = t1['kd'], t2['kd']
    row['kd_diff'] = t1['kd'] - t2['kd']
    row['team_1_avg_adr'], row['team_2_avg_adr'] = t1['adr'], t2['adr']
    row['adr_diff'] = t1['adr'] - t2['adr']
    row['team_1_hs_rate'], row['team_2_hs_rate'] = t1['hs'], t2['hs']
    row['hs_diff'] = t1['hs'] - t2['hs']
    row['team_1_map_winrate'], row['team_2_map_winrate'] = t1['map_wr'], t2['map_wr']
    row['map_winrate_diff'] = t1['map_wr'] - t2['map_wr']
    row['team_1_streak'], row['team_2_streak'] = t1['streak'], t2['streak']
    row['streak_diff'] = t1['streak'] - t2['streak']
    row['team_1_avg_matches'], row['team_2_avg_matches'] = t1['matches'], t2['matches']
    dummy = 'map_name_' + map_name
    if dummy in row:
        row[dummy] = 1.0
    return row


def my_history(limit):
    hist = get(f'{API}/stats/v1/stats/time/users/{PID}/games/cs2?size=100&page=0') or []
    done = [m for m in hist if num(m.get('elo_delta')) is not None]
    return done[:limit]


PID = os.environ.get('FACEIT_PLAYER_ID', '299bcdfd-ed9f-42f6-91ea-5ff75e442d85')


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    model = CatBoostClassifier()
    model.load_model(os.path.join(ROOT, 'models', 'catboost_faceit.cbm'))

    hist = my_history(limit)
    rows = []
    for entry in hist:
        mid = entry.get('matchId')
        payload = match_payload(mid)
        if not payload or payload.get('status') != 'FINISHED':
            continue
        teams = payload.get('teams') or {}
        pick = ((payload.get('voting') or {}).get('map') or {}).get('pick') or []
        map_name = pick[0] if pick else ((payload.get('maps') or [{}])[0].get('class_name'))
        if not map_name:
            continue
        started = to_ms(payload.get('startedAt'), entry.get('date'))
        factions = {}
        ok = True
        for key in ('faction1', 'faction2'):
            roster = (teams.get(key) or {}).get('roster') or []
            players = []
            for pl in roster:
                stats = pre_match_stats(pl['id'], started)
                elo = num(pl.get('elo'))
                if elo is None:
                    ok = False
                players.append({'elo': elo if elo is not None else 1000.0, 'stats': stats})
            tf = team_features(players, map_name)
            if not tf or tf['known'] < 5:
                ok = False
            factions[key] = tf
        if not ok:
            continue

        res = payload.get('results')
        winner = None
        score = {}
        if isinstance(res, list) and res:
            winner = res[0].get('winner')
            score = {k: v.get('score') for k, v in (res[0].get('factions') or {}).items()}
        row = build_row(factions['faction1'], factions['faction2'], map_name)
        prob1 = float(model.predict_proba(pd.DataFrame([row]))[0, 1])

        me_faction = None
        for key in ('faction1', 'faction2'):
            if any(p.get('nickname') == ME for p in (teams.get(key) or {}).get('roster') or []):
                me_faction = key
        faceit_p1 = ((teams.get('faction1') or {}).get('stats') or {}).get('winProbability')

        p_me = prob1 if me_faction == 'faction1' else 1 - prob1
        won = (winner == me_faction) if winner and me_faction else None
        rows.append({
            'match_id': mid,
            'map': map_name,
            'p1': round(prob1 * 100, 1),
            'p_me': round(p_me * 100, 1),
            'won_me': won,
            'me_faction': me_faction,
            'winner': winner,
            'score': f"{score.get('faction1', '?')}:{score.get('faction2', '?')}",
            'hit': None if won is None else (p_me >= 0.5) == won,
            'model_favored_me': p_me >= 0.5,
            'faceit_p1': round(faceit_p1 * 100, 1) if isinstance(faceit_p1, (int, float)) else None,
            'map_games_t1': factions['faction1']['map_games'],
            'map_games_t2': factions['faction2']['map_games'],
        })
        print(f"{mid[:18]} {map_name:<12} P(f1)={prob1*100:5.1f}%  P(me)={p_me*100:5.1f}%  "
              f"faceit={faceit_p1 if isinstance(faceit_p1,(int,float)) else '-'}  score={score.get('faction1','?')}:{score.get('faction2','?')}  winner={winner}")
        time.sleep(0.25)

    out = os.path.join(ROOT, 'data', 'backtest_result.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    hits = [r for r in rows if r['hit'] is not None]
    if hits:
        n = len(hits)
        acc = sum(1 for r in hits if r['hit']) / n
        probs = np.array([r['p_me'] / 100 for r in hits])
        outcome = np.array([1.0 if r['won_me'] else 0.0 for r in hits])
        brier = float(np.mean((probs - outcome) ** 2))
        print(f'\nМатчей в выборке: {n}')
        print(f'Модель угадала победителя: {sum(1 for r in hits if r["hit"])} из {n} = {acc*100:.1f}%')
        print(f'Brier score (0.25 = монетка, меньше — лучше): {brier:.4f}')
        print(f'Средняя P(me): {probs.mean()*100:.1f}%  |  реальных побед: {outcome.mean()*100:.1f}%')
        buckets = [(50, 60), (60, 70), (70, 101)]
        for lo, hi in buckets:
            sel = [r for r in hits if lo <= r['p_me'] < hi]
            if sel:
                wr = sum(1 for r in sel if r['won_me']) / len(sel) * 100
                print(f'  P(me) в [{lo}, {hi}): {len(sel)} матч(ов), победили в {wr:.0f}%')
    print('Результат:', out)


if __name__ == '__main__':
    main()
