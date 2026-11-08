# -*- coding: utf-8 -*-
"""
Генератор репрезентативного набора данных матчей платформы FACEIT (CS2 / CS:GO)
Создает 15 000 соревновательных матчей с реалистичными характеристиками:
- ELO игроков и разница рейтингов
- K/D, ADR, процент хедшотов
- Винрейт команд на конкретных картах активного пула
- Винстрики и дисперсия мастерства внутри команд
"""

import numpy as np
import pandas as pd
import os

np.random.seed(42)

def generate_faceit_dataset(n_matches=15000):
    maps = ['de_mirage', 'de_inferno', 'de_nuke', 'de_dust2', 'de_anubis', 'de_ancient', 'de_vertigo']
    map_probabilities = [0.32, 0.20, 0.14, 0.12, 0.10, 0.07, 0.05]
    
    selected_maps = np.random.choice(maps, size=n_matches, p=map_probabilities)
    
    # Базовый ELO для матча (от 800 до 3100, пик в районе 1700 - 6-8 уровни FACEIT)
    base_match_elo = np.random.normal(loc=1750, scale=420, size=n_matches)
    base_match_elo = np.clip(base_match_elo, 750, 3400)
    
    # Разница ELO между командами (в матчмейкинге FACEIT команды обычно сбалансированы +-150 ELO)
    elo_delta = np.random.normal(loc=0, scale=110, size=n_matches)
    elo_delta = np.clip(elo_delta, -350, 350)
    
    team_1_elo = np.round(base_match_elo + elo_delta / 2).astype(int)
    team_2_elo = np.round(base_match_elo - elo_delta / 2).astype(int)
    elo_diff = team_1_elo - team_2_elo
    
    # Дисперсия скилла внутри команд (стандартное отклонение ELO 5 игроков)
    # Низкая std = 5 игроков одного уровня; высокая std = смурф + слабые тиммейты
    team_1_elo_std = np.round(np.random.gamma(shape=4.0, scale=22.0, size=n_matches) + 30, 1)
    team_2_elo_std = np.round(np.random.gamma(shape=4.0, scale=22.0, size=n_matches) + 30, 1)
    std_diff = team_1_elo_std - team_2_elo_std
    
    # Средний K/D команд (около 1.05 с дисперсией)
    # Коррелирует с ELO
    t1_kd_base = 0.92 + (team_1_elo / 3000) * 0.25 + np.random.normal(0, 0.08, n_matches)
    t2_kd_base = 0.92 + (team_2_elo / 3000) * 0.25 + np.random.normal(0, 0.08, n_matches)
    team_1_avg_kd = np.round(np.clip(t1_kd_base, 0.70, 1.65), 2)
    team_2_avg_kd = np.round(np.clip(t2_kd_base, 0.70, 1.65), 2)
    kd_diff = np.round(team_1_avg_kd - team_2_avg_kd, 2)
    
    # Средний урон за раунд (ADR - Average Damage per Round, обычно от 60 до 95)
    t1_adr = 55 + team_1_avg_kd * 22 + np.random.normal(0, 3.5, n_matches)
    t2_adr = 55 + team_2_avg_kd * 22 + np.random.normal(0, 3.5, n_matches)
    team_1_avg_adr = np.round(np.clip(t1_adr, 58.0, 105.0), 1)
    team_2_avg_adr = np.round(np.clip(t2_adr, 58.0, 105.0), 1)
    adr_diff = np.round(team_1_avg_adr - team_2_avg_adr, 1)
    
    # Процент попаданий в голову (% Headshots)
    t1_hs = 42.0 + (team_1_elo / 3000) * 12 + np.random.normal(0, 4.0, n_matches)
    t2_hs = 42.0 + (team_2_elo / 3000) * 12 + np.random.normal(0, 4.0, n_matches)
    team_1_hs_rate = np.round(np.clip(t1_hs, 30.0, 68.0), 1)
    team_2_hs_rate = np.round(np.clip(t2_hs, 30.0, 68.0), 1)
    hs_diff = np.round(team_1_hs_rate - team_2_hs_rate, 1)
    
    # Винрейт на выбранной карте (в процентах, от 30% до 75%)
    t1_map_wr = np.random.normal(loc=52.0, scale=9.0, size=n_matches)
    t2_map_wr = np.random.normal(loc=51.0, scale=9.0, size=n_matches)
    team_1_map_winrate = np.round(np.clip(t1_map_wr, 25.0, 80.0), 1)
    team_2_map_winrate = np.round(np.clip(t2_map_wr, 25.0, 80.0), 1)
    map_winrate_diff = np.round(team_1_map_winrate - team_2_map_winrate, 1)
    
    # Текущая серия побед / поражений (Streak: от -5 до +6)
    team_1_streak = np.random.choice(range(-4, 6), size=n_matches, p=[0.05, 0.10, 0.20, 0.30, 0.18, 0.10, 0.05, 0.01, 0.008, 0.002])
    team_2_streak = np.random.choice(range(-4, 6), size=n_matches, p=[0.05, 0.10, 0.20, 0.30, 0.18, 0.10, 0.05, 0.01, 0.008, 0.002])
    streak_diff = team_1_streak - team_2_streak
    
    # Средний наигранный опыт игроков (кол-во матчей на FACEIT, от 100 до 3500)
    team_1_avg_matches = np.round(np.random.exponential(scale=650, size=n_matches) + 120).astype(int)
    team_2_avg_matches = np.round(np.random.exponential(scale=650, size=n_matches) + 120).astype(int)
    
    # Логистическая функция расчета истинной вероятности победы Team 1
    # С учетом стохастичности киберспорта (пистолетки, клатчи, овертаймы)
    logit = (
        0.0048 * elo_diff +
        2.10 * kd_diff +
        0.045 * adr_diff +
        0.038 * map_winrate_diff +
        0.075 * streak_diff +
        0.012 * hs_diff -
        0.0025 * std_diff +
        np.random.normal(0, 0.52, size=n_matches)
    )
    
    prob_team_1_win = 1.0 / (1.0 + np.exp(-logit))
    team_1_win = (np.random.rand(n_matches) < prob_team_1_win).astype(int)
    
    df = pd.DataFrame({
        'match_id': [f"match_{i+1:06d}" for i in range(n_matches)],
        'map_name': selected_maps,
        'team_1_avg_elo': team_1_elo,
        'team_2_avg_elo': team_2_elo,
        'elo_diff': elo_diff,
        'team_1_elo_std': team_1_elo_std,
        'team_2_elo_std': team_2_elo_std,
        'elo_std_diff': std_diff,
        'team_1_avg_kd': team_1_avg_kd,
        'team_2_avg_kd': team_2_avg_kd,
        'kd_diff': kd_diff,
        'team_1_avg_adr': team_1_avg_adr,
        'team_2_avg_adr': team_2_avg_adr,
        'adr_diff': adr_diff,
        'team_1_hs_rate': team_1_hs_rate,
        'team_2_hs_rate': team_2_hs_rate,
        'hs_diff': hs_diff,
        'team_1_map_winrate': team_1_map_winrate,
        'team_2_map_winrate': team_2_map_winrate,
        'map_winrate_diff': map_winrate_diff,
        'team_1_streak': team_1_streak,
        'team_2_streak': team_2_streak,
        'streak_diff': streak_diff,
        'team_1_avg_matches': team_1_avg_matches,
        'team_2_avg_matches': team_2_avg_matches,
        'team_1_win': team_1_win
    })
    
    return df

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "faceit_matches.csv")
    
    print(f"Генерация 15 000 соревновательных матчей FACEIT...")
    df = generate_faceit_dataset(15000)
    df.to_csv(out_file, index=False)
    print(f"Успешно сохранено: {out_file}")
    print(f"Размер датасета: {df.shape}")
    print(f"Баланс классов:\n{df['team_1_win'].value_counts(normalize=True)}")
