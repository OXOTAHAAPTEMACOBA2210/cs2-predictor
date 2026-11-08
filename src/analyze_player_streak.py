# -*- coding: utf-8 -*-
import requests
import json
import datetime
import pandas as pd

pid = '299bcdfd-ed9f-42f6-91ea-5ff75e442d85'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': f'https://www.faceit.com/ru/players/{pid}',
    'Accept': 'application/json'
}

url = f'https://www.faceit.com/api/stats/v1/stats/time/users/{pid}/games/cs2?size=100'
r = requests.get(url, headers=headers)
matches = r.json()

records = []
for m in matches:
    dt = datetime.datetime.fromtimestamp(m.get('date', 0) / 1000.0) if m.get('date') else None
    elo_val = int(m['elo']) if 'elo' in m and m['elo'] is not None else None
    delta = int(m['elo_delta']) if 'elo_delta' in m and m['elo_delta'] is not None else 0
    # i10: win (1) or loss (0)
    win = int(m.get('i10', 0))
    kills = int(m.get('i6', 0))
    deaths = int(m.get('i8', 0))
    kd = float(m.get('c2', 0)) if m.get('c2') else (kills/deaths if deaths>0 else kills)
    adr = float(m.get('c10', 0)) if m.get('c10') else 0.0
    hs = float(m.get('c4', 0)) if m.get('c4') else 0.0
    map_name = m.get('i1', 'unknown')
    premade = m.get('premade', False)
    score = m.get('i18', '')
    records.append({
        'dt': dt, 'elo': elo_val, 'delta': delta, 'win': win,
        'kills': kills, 'deaths': deaths, 'kd': kd, 'adr': adr, 'hs': hs,
        'map': map_name, 'premade': premade, 'score': score
    })

# Chronological order (oldest to newest)
records.reverse()

df = pd.DataFrame(records)
print(f"Total matches analyzed: {len(df)}")
if 'elo' in df and df['elo'].notnull().any():
    print(f"Min ELO: {df['elo'].min()} | Max ELO: {df['elo'].max()} | Current ELO: {df['elo'].iloc[-1]}")

peak_idx = df['elo'].idxmax()
print(f"\n--- Peak Performance around Match {peak_idx} ---")
peak_row = df.iloc[peak_idx]
print(f"Peak Date: {peak_row['dt']} | Peak ELO: {peak_row['elo']} | Map: {peak_row['map']} | KD: {peak_row['kd']} | ADR: {peak_row['adr']}")

# Analyze phase 1: The climb / peak
climb_df = df.iloc[max(0, peak_idx-25):peak_idx+1]
# Analyze phase 2: The slump / derank
slump_df = df.iloc[peak_idx+1:]

print("\n=== CLIMB / PEAK PHASE (25 matches before and at peak) ===")
print(f"Winrate: {climb_df['win'].mean()*100:.1f}% ({climb_df['win'].sum()}W - {len(climb_df)-climb_df['win'].sum()}L)")
print(f"Avg KD: {climb_df['kd'].mean():.2f}")
print(f"Avg ADR: {climb_df['adr'].mean():.1f}")
print(f"Premade ratio (party games): {climb_df['premade'].mean()*100:.1f}%")
print("Maps during climb:\n", climb_df['map'].value_counts())

print(f"\n=== SLUMP / DERANK PHASE ({len(slump_df)} matches after peak) ===")
if len(slump_df) > 0:
    print(f"Winrate: {slump_df['win'].mean()*100:.1f}% ({slump_df['win'].sum()}W - {len(slump_df)-slump_df['win'].sum()}L)")
    print(f"Avg KD: {slump_df['kd'].mean():.2f}")
    print(f"Avg ADR: {slump_df['adr'].mean():.1f}")
    print(f"Premade ratio (party games): {slump_df['premade'].mean()*100:.1f}%")
    print("Maps during slump:\n", slump_df['map'].value_counts())

print("\n--- Recent 15 matches breakdown ---")
for i, r in df.tail(15).iterrows():
    w_str = "WIN " if r['win'] == 1 else "LOSS"
    p_str = "Party" if r['premade'] else "Solo "
    print(f"{r['dt'].strftime('%d.%m %H:%M') if r['dt'] else ''} | {w_str} | ELO: {r['elo']:4d} ({r['delta']:+3d}) | KD: {r['kd']:4.2f} | ADR: {r['adr']:5.1f} | {r['map']:10s} | {p_str} | {r['score']}")
