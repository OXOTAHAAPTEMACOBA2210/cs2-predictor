# -*- coding: utf-8 -*-
"""
Парсер матчей FACEIT по ссылке или ID комнаты
Включает:
1. Разрешение калибровки (последний известный ELO)
2. Детектор СМУРФОВ (Smurf Detector)
3. Детектор РУИНЕРОВ / ТИЛЬТЕРОВ / ЛИВЕРОВ (Ruiner & Leaver Detector)
"""

import re
import time
import statistics
import requests
import concurrent.futures

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

def extract_match_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    m = re.search(r"room/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    m = re.search(r"([0-9]-[a-fA-F0-9-]+)", url_or_id)
    if m:
        return m.group(1)
    return url_or_id

def analyze_player_behavior(matches, kd, winrate, recent_streak):
    """
    Анализ поведения: выявление смурфов, бустеров, тильтеров и потенциальных руинеров
    """
    smurf_score = 0
    smurf_reasons = []
    
    # 1. Алгоритм детекции смурфов
    if matches < 80 and kd >= 1.35 and winrate >= 60:
        smurf_score = 90
        smurf_reasons.append(f"Новый акк ({matches} матчей), K/D {kd:.2f}, винрейт {winrate:.0f}%")
    elif matches < 150 and kd >= 1.45:
        smurf_score = 80
        smurf_reasons.append(f"Аномально высокий K/D ({kd:.2f}) для {matches} матчей")
    elif matches < 50 and kd >= 1.25:
        smurf_score = 70
        smurf_reasons.append(f"Свежий аккаунт ({matches} игр) с высоким K/D {kd:.2f}")
    elif matches < 35:
        smurf_score = 60
        smurf_reasons.append(f"Слишком мало матчей ({matches}) для точной оценки")

    # 2. Алгоритм детекции руинеров / тильтеров / ливеров
    ruin_score = 0
    ruin_reasons = []
    
    if recent_streak <= -4:
        ruin_score = 85
        ruin_reasons.append(f"Жесткий тильт-лузстрик: {abs(recent_streak)} поражений подряд!")
    elif recent_streak <= -3 and (kd < 0.85 or winrate < 46):
        ruin_score = 75
        ruin_reasons.append(f"Лузстрик 3+ матча и низкий K/D ({kd:.2f})")
    elif kd < 0.70 and matches > 80:
        ruin_score = 80
        ruin_reasons.append(f"Критически низкий K/D ({kd:.2f}) — балласт для команды")
    elif winrate < 38 and matches > 50:
        ruin_score = 75
        ruin_reasons.append(f"Катастрофический винрейт ({winrate:.0f}%) — высокий риск руина")

    # Итоговый бейдж
    if smurf_score >= 70:
        tag = f"👶 Смурф ({smurf_score}%)"
        category = "SMURF"
    elif ruin_score >= 70:
        tag = f"💣 Тильт/Руин ({ruin_score}%)"
        category = "RUINER"
    elif recent_streak >= 3:
        tag = f"🔥 На волне (+{recent_streak})"
        category = "HOT"
    else:
        tag = "🛡️ Обычный"
        category = "NORMAL"

    return {
        'tag': tag,
        'category': category,
        'smurf_score': smurf_score,
        'smurf_reasons': smurf_reasons,
        'ruin_score': ruin_score,
        'ruin_reasons': ruin_reasons
    }

def fetch_player_stats(player):
    pid = player.get('id')
    raw_elo = player.get('elo')
    nickname = player.get('nickname', 'Unknown')
    
    stats = {
        'id': pid,
        'nickname': nickname,
        'elo': int(raw_elo) if raw_elo is not None else None,
        'is_calibrating': False,
        'kd': 1.0,
        'adr': 75.0,
        'hs': 40.0,
        'matches': 500,
        'winrate': 50.0,
        'recent_streak': 0,
        'tag': '🛡️ Обычный',
        'category': 'NORMAL',
        'behavior_details': ''
    }
    
    if not pid:
        if stats['elo'] is None:
            stats['elo'] = 1000
        return stats
        
    # 1. Если игрок на калибровке ("Нет ранга"), вытаскиваем его скрытый / последний известный ELO
    try:
        user_url = f"https://www.faceit.com/api/users/v1/users/{pid}"
        ur = requests.get(user_url, headers=HEADERS, timeout=3.5)
        if ur.status_code == 200:
            u_data = ur.json().get('payload', {})
            cs2_info = u_data.get('games', {}).get('cs2', {})
            if not cs2_info:
                cs2_info = u_data.get('games', {}).get('csgo', {})
                
            stats['is_calibrating'] = cs2_info.get('is_calibrating', False)
            last_known_elo = cs2_info.get('faceit_elo')
            if last_known_elo is not None and (stats['elo'] is None or stats['is_calibrating']):
                stats['elo'] = int(last_known_elo)
    except Exception:
        pass
        
    if stats['elo'] is None:
        stats['elo'] = 1000
        
    # 2. Подтягиваем статистику матчей, K/D, ADR, Winrate
    try:
        url = f"https://www.faceit.com/api/stats/v1/stats/users/{pid}/games/cs2"
        r = requests.get(url, headers=HEADERS, timeout=3.5)
        if r.status_code == 200:
            data = r.json()
            lt = data.get('lifetime', {})
            
            kd_val = lt.get('k5') or lt.get('k1')
            if kd_val: stats['kd'] = float(kd_val)
                
            adr_val = lt.get('k17')
            if adr_val:
                stats['adr'] = float(adr_val)
            else:
                stats['adr'] = round(stats['kd'] * 76.5, 1)
                
            hs_val = lt.get('k8') or lt.get('k4')
            if hs_val: stats['hs'] = float(hs_val)
                
            m_val = lt.get('m1')
            if m_val:
                try: stats['matches'] = int(m_val)
                except Exception: pass
                    
            wr_val = lt.get('k6')
            if wr_val: stats['winrate'] = float(wr_val)

            # Вычисление винстрика / лузстрика из s0
            s0 = lt.get('s0', [])
            if s0 and isinstance(s0, list):
                # Последние матчи идут от старых к новым или наоборот
                streak = 0
                first_val = int(s0[-1]) if s0[-1] in ['0', '1', 0, 1] else 0
                for item in reversed(s0):
                    val = int(item) if item in ['0', '1', 0, 1] else 0
                    if val == first_val:
                        streak += 1
                    else:
                        break
                stats['recent_streak'] = streak if first_val == 1 else -streak
    except Exception:
        pass

    # 3. Анализ смурфа / руинера
    beh = analyze_player_behavior(stats['matches'], stats['kd'], stats['winrate'], stats['recent_streak'])
    stats['tag'] = beh['tag']
    stats['category'] = beh['category']
    stats['smurf_score'] = beh['smurf_score']
    stats['ruin_score'] = beh['ruin_score']
    reasons = beh['smurf_reasons'] + beh['ruin_reasons']
    stats['behavior_details'] = '; '.join(reasons) if reasons else 'Стабильный профиль'

    return stats

def fetch_player_map_winrate(player_id, map_name, size=50):
    """WR игрока на конкретной карте по последним матчам (знак elo_delta)."""
    if not player_id or not map_name:
        return None
    url = (f"https://www.faceit.com/api/stats/v1/stats/time/users/{player_id}"
           f"/games/cs2?size={size}&page=0")
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code != 200:
            return None
        arr = r.json()
        if not isinstance(arr, list):
            return None
        wins = losses = 0
        for m in arr:
            if m.get('i1') != map_name:
                continue
            delta = float(m.get('elo_delta') or 0)
            if delta > 0:
                wins += 1
            elif delta < 0:
                losses += 1
        if wins + losses == 0:
            return None
        return round((wins / (wins + losses)) * 100, 1)
    except Exception:
        return None

def fetch_match_details(url_or_id: str):
    match_id = extract_match_id(url_or_id)
    url = f"https://www.faceit.com/api/match/v2/match/{match_id}"
    
    r = requests.get(url, headers=HEADERS, timeout=6)
    if r.status_code != 200:
        raise ValueError(f"Не удалось найти матч на FACEIT по ID: {match_id} (Код: {r.status_code})")
        
    payload = r.json().get('payload', {})
    teams = payload.get('teams', {})
    
    t1_data = teams.get('faction1', {})
    t2_data = teams.get('faction2', {})
    
    t1_roster = t1_data.get('roster', [])
    t2_roster = t2_data.get('roster', [])
    
    if not t1_roster or not t2_roster:
        raise ValueError("Лобби матча еще не заполнено игроками или матч отменен.")
        
    # Параллельная выгрузка статистики 10 игроков с детекцией смурфов и руинеров
    all_players = t1_roster + t2_roster
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        all_stats = list(executor.map(fetch_player_stats, all_players))
        
    t1_stats = all_stats[:len(t1_roster)]
    t2_stats = all_stats[len(t1_roster):]
    
    # Карта матча
    picked_map = "de_mirage"
    voting = payload.get('voting', {})
    map_picks = voting.get('map', {}).get('pick', [])
    if map_picks:
        picked_map = map_picks[0]
    elif payload.get('maps'):
        picked_map = payload.get('maps')[0].get('class_name', 'de_mirage')

    # WR на конкретной карте по последним 50 матчам каждого игрока
    for p in all_stats:
        p['map_wr'] = fetch_player_map_winrate(p.get('id'), picked_map) or p['winrate']
        time.sleep(0.25)
        
    # Агрегация характеристик команд
    t1_avg_elo = sum(p['elo'] for p in t1_stats) / len(t1_stats)
    t2_avg_elo = sum(p['elo'] for p in t2_stats) / len(t2_stats)
    
    t1_avg_kd = sum(p['kd'] for p in t1_stats) / len(t1_stats)
    t2_avg_kd = sum(p['kd'] for p in t2_stats) / len(t2_stats)
    
    t1_avg_adr = sum(p['adr'] for p in t1_stats) / len(t1_stats)
    t2_avg_adr = sum(p['adr'] for p in t2_stats) / len(t2_stats)
    
    t1_hs = sum(p['hs'] for p in t1_stats) / len(t1_stats)
    t2_hs = sum(p['hs'] for p in t2_stats) / len(t2_stats)
    
    t1_mwr = sum(p['map_wr'] for p in t1_stats) / len(t1_stats)
    t2_mwr = sum(p['map_wr'] for p in t2_stats) / len(t2_stats)

    t1_elo_std = statistics.pstdev([p['elo'] for p in t1_stats]) if len(t1_stats) > 1 else 80.0
    t2_elo_std = statistics.pstdev([p['elo'] for p in t2_stats]) if len(t2_stats) > 1 else 80.0
    t1_avg_matches = sum(p['matches'] for p in t1_stats) / len(t1_stats)
    t2_avg_matches = sum(p['matches'] for p in t2_stats) / len(t2_stats)
    t1_streak = sum(p['recent_streak'] for p in t1_stats) / len(t1_stats)
    t2_streak = sum(p['recent_streak'] for p in t2_stats) / len(t2_stats)

    # Выявление угроз для доджа (Threats)
    alerts = []
    
    # Смурфы во вражеской команде
    for p in t2_stats:
        if p['category'] == 'SMURF':
            alerts.append({
                'type': 'DANGER',
                'title': f"🚨 СМУРФ В КОМАНДЕ ВРАГА: {p['nickname']}",
                'desc': f"Игрок с вероятностью {p['smurf_score']}% является смурфом ({p['matches']} матчей, K/D {p['kd']:.2f}, винрейт {p['winrate']:.0f}%). Резко снижает шансы на победу!"
            })
            
    # Руинеры в твоей команде
    for p in t1_stats:
        if p['category'] == 'RUINER':
            alerts.append({
                'type': 'WARNING',
                'title': f"💣 РУИНЕР / ТИЛЬТ В ТВОЕЙ КОМАНДЕ: {p['nickname']}",
                'desc': f"Игрок в зоне риска ({p['behavior_details']}). Высокая вероятность слива или лива!"
            })

    # Смурф в твоей команде
    for p in t1_stats:
        if p['category'] == 'SMURF':
            alerts.append({
                'type': 'GOOD',
                'title': f"👶 СМУРФ В ТВОЕЙ КОМАНДЕ: {p['nickname']}",
                'desc': f"Сильный керри-игрок ({p['matches']} матчей, K/D {p['kd']:.2f}). Отличный шанс на легкую победу!"
            })
    
    return {
        'match_id': match_id,
        'status': payload.get('status', 'ONGOING'),
        'map': picked_map,
        'alerts': alerts,
        'team_1': {
            'name': t1_data.get('name', 'Team 1'),
            'avg_elo': round(t1_avg_elo),
            'elo_std': round(t1_elo_std, 1),
            'avg_kd': round(t1_avg_kd, 2),
            'avg_adr': round(t1_avg_adr, 1),
            'hs': round(t1_hs, 1),
            'map_wr': round(t1_mwr, 1),
            'avg_matches': round(t1_avg_matches),
            'streak': round(t1_streak, 1),
            'players': t1_stats
        },
        'team_2': {
            'name': t2_data.get('name', 'Team 2'),
            'avg_elo': round(t2_avg_elo),
            'elo_std': round(t2_elo_std, 1),
            'avg_kd': round(t2_avg_kd, 2),
            'avg_adr': round(t2_avg_adr, 1),
            'hs': round(t2_hs, 1),
            'map_wr': round(t2_mwr, 1),
            'avg_matches': round(t2_avg_matches),
            'streak': round(t2_streak, 1),
            'players': t2_stats
        }
    }
